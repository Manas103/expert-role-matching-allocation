"""Candidate retrieval (Postgres array-overlap, standing in for the
Elasticsearch retrieval layer named on the resume, see README), the
scarcity-ordered heuristic matcher, the naive greedy first-fit baseline,
and the Redis-lease-plus-Postgres-unique-constraint claim protocol.

The fill-rate benchmark (heuristic vs baseline) tracks assignment state
in a plain Python set, because it is comparing two *offline assignment
policies* over the same retrieved candidate pools. The live double-commit
guard (claim_expert) is a separate, independently tested code path used by
the /claim endpoint and the concurrency test; the batch comparison does not
exercise it, and this file keeps the two apart on purpose so that an
algorithmic easy win cannot leak into the concurrency-correctness claim."""

from dataclasses import dataclass
from typing import List, Optional, Set

import asyncpg
import redis.asyncio as redis_asyncio

from app import config


@dataclass
class Candidate:
    expert_id: int
    external_id: str
    quality_score: float
    overlap: int

    @property
    def score(self) -> float:
        return self.overlap * 1.0 + self.quality_score


async def candidates_for(
    conn: asyncpg.Connection,
    required_skills: List[str],
    domain: str,
    seniority_rank: int,
    exclude_ids: Set[int],
    limit: int = 50,
    live_exclude_claimed: bool = False,
) -> List[Candidate]:
    exclude = list(exclude_ids) if exclude_ids else []
    if live_exclude_claimed:
        rows = await conn.fetch(
            """
            SELECT e.id, e.external_id, e.quality_score,
                   (SELECT count(*) FROM unnest(e.skills) s WHERE s = ANY($1::text[])) AS overlap
            FROM experts e
            LEFT JOIN active_assignment a
                   ON a.expert_id = e.id AND a.status = 'active'
            WHERE e.domain = $2
              AND e.seniority_rank >= $3 - 1
              AND e.skills @> $1::text[]
              AND a.id IS NULL
              AND NOT (e.id = ANY($4::int[]))
            ORDER BY overlap DESC, e.quality_score DESC
            LIMIT $5
            """,
            required_skills, domain, seniority_rank, exclude, limit,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, external_id, quality_score,
                   (SELECT count(*) FROM unnest(skills) s WHERE s = ANY($1::text[])) AS overlap
            FROM experts
            WHERE domain = $2
              AND seniority_rank >= $3 - 1
              AND skills @> $1::text[]
              AND NOT (id = ANY($4::int[]))
            ORDER BY overlap DESC, quality_score DESC
            LIMIT $5
            """,
            required_skills, domain, seniority_rank, exclude, limit,
        )
    return [Candidate(r["id"], r["external_id"], float(r["quality_score"]), r["overlap"]) for r in rows]


async def _scarcity(conn, req, taken: Set[int]) -> int:
    cands = await candidates_for(
        conn, req["required_skills"], req["domain"], req["seniority_rank"], taken, limit=10_000,
    )
    return len(cands)


async def heuristic_fill(pool: asyncpg.Pool, requests: List[dict]) -> dict:
    """Scarcity-ordered: process the request with the fewest eligible,
    available candidates first, so a scarce expert is not consumed by an
    easy request that had many other options. This is what beats the
    naive first-fit baseline, which processes requests in input order."""
    taken: Set[int] = set()
    assignments = {}
    async with pool.acquire() as conn:
        scarcities = []
        for req in requests:
            s = await _scarcity(conn, req, taken)
            scarcities.append((s, req))
        scarcities.sort(key=lambda t: t[0])
        for _, req in scarcities:
            cands = await candidates_for(
                conn, req["required_skills"], req["domain"], req["seniority_rank"], taken, limit=50,
            )
            if cands:
                best = cands[0]
                taken.add(best.expert_id)
                assignments[req["external_id"]] = best.expert_id
    filled = len(assignments)
    return {"filled": filled, "total": len(requests), "fill_rate": filled / len(requests), "assignments": assignments}


async def baseline_fill(pool: asyncpg.Pool, requests: List[dict]) -> dict:
    """Naive greedy first-fit: process requests in input order, assign the
    first available expert meeting the hard requirements (domain, skill
    overlap, seniority floor), ordered only by expert id. No reordering,
    no backtracking, no scoring beyond 'first found'."""
    taken: Set[int] = set()
    assignments = {}
    async with pool.acquire() as conn:
        for req in requests:
            rows = await conn.fetch(
                """
                SELECT id FROM experts
                WHERE domain = $1 AND seniority_rank >= $2 - 1
                  AND skills @> $3::text[]
                  AND NOT (id = ANY($4::int[]))
                ORDER BY id ASC
                LIMIT 1
                """,
                req["domain"], req["seniority_rank"], req["required_skills"], list(taken),
            )
            if rows:
                eid = rows[0]["id"]
                taken.add(eid)
                assignments[req["external_id"]] = eid
    filled = len(assignments)
    return {"filled": filled, "total": len(requests), "fill_rate": filled / len(requests), "assignments": assignments}


async def decide(pool: asyncpg.Pool, required_skills, domain, seniority_rank, pool_size=50) -> Optional[Candidate]:
    """Read-only live decision: best-scored currently-available candidate.
    Used by the /decide endpoint and the load test. Commits nothing."""
    async with pool.acquire() as conn:
        cands = await candidates_for(
            conn, required_skills, domain, seniority_rank, set(), limit=pool_size, live_exclude_claimed=True,
        )
    return cands[0] if cands else None, len(cands) if cands else 0


class ClaimResult:
    def __init__(self, claimed: bool, reason: str):
        self.claimed = claimed
        self.reason = reason


async def claim_expert(
    pg_pool: asyncpg.Pool,
    redis_client: redis_asyncio.Redis,
    expert_id: int,
    request_external_id: str,
) -> ClaimResult:
    """Two independent guards, deliberately both real: a Redis SET NX PX
    lease is the fast pre-write guard, and a Postgres partial unique index
    on active_assignment(expert_id) WHERE status='active' is the
    structural guard that holds even if the lease were ever bypassed
    (e.g. a lease that already expired under contention)."""
    key = config.lease_key(expert_id)
    got_lease = await redis_client.set(key, request_external_id, nx=True, px=config.LEASE_TTL_MS)
    if not got_lease:
        return ClaimResult(False, "lease_contended")
    try:
        async with pg_pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO active_assignment (expert_id, request_external_id) VALUES ($1, $2)",
                    expert_id, request_external_id,
                )
                return ClaimResult(True, "ok")
            except asyncpg.UniqueViolationError:
                return ClaimResult(False, "already_assigned")
    finally:
        # Best-effort release so a fast-expiring TTL is not the only way
        # a legitimately failed claim frees the lease for the next attempt.
        cur = await redis_client.get(key)
        if cur == request_external_id:
            await redis_client.delete(key)
