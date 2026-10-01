"""Measures claim 6: 0 double-commitments across 20,000 concurrent claims,
via the real Redis-lease-plus-Postgres-unique-constraint protocol
(app.matching.claim_expert), run in-process (no HTTP layer, so the test
runs quickly) against the real shared WSL2 Postgres and Redis. Deliberately
contends 20,000 claim attempts over a small pool of 100 experts so the
guard is actually exercised under real contention, not applied to disjoint
work that could never race. Run with: python scripts/run_concurrency_test.py"""

import asyncio
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, matching  # noqa: E402

N_CLAIMS = 20_000
N_CONTENDED_EXPERTS = 100
MAX_IN_FLIGHT = 200


async def main():
    pg_pool = await db.make_pg_pool(min_size=10, max_size=20)
    redis_client = db.make_redis_client()

    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM experts ORDER BY id LIMIT $1", N_CONTENDED_EXPERTS)
        expert_ids = [r["id"] for r in rows]
        await conn.execute(
            "DELETE FROM active_assignment WHERE expert_id = ANY($1::int[])", expert_ids
        )
    for eid in expert_ids:
        await redis_client.delete(matching.config.lease_key(eid))

    rng = random.Random(99)
    attempts = [
        (rng.choice(expert_ids), f"conc-req-{i:06d}")
        for i in range(N_CLAIMS)
    ]

    sem = asyncio.Semaphore(MAX_IN_FLIGHT)
    counts = {"claimed": 0, "not_claimed": 0}
    counts_lock = asyncio.Lock()

    async def do_claim(expert_id, req_id):
        async with sem:
            result = await matching.claim_expert(pg_pool, redis_client, expert_id, req_id)
        async with counts_lock:
            counts["claimed" if result.claimed else "not_claimed"] += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(do_claim(eid, rid) for eid, rid in attempts))
    elapsed = time.perf_counter() - t0

    async with pg_pool.acquire() as conn:
        dup_rows = await conn.fetch(
            """
            SELECT expert_id, count(*) AS n FROM active_assignment
            WHERE status = 'active' AND expert_id = ANY($1::int[])
            GROUP BY expert_id HAVING count(*) > 1
            """,
            expert_ids,
        )
        total_active = await conn.fetchval(
            "SELECT count(*) FROM active_assignment WHERE status='active' AND expert_id = ANY($1::int[])",
            expert_ids,
        )

    double_commitments = sum(r["n"] - 1 for r in dup_rows)

    lines = [
        f"total claim attempts: {N_CLAIMS}, contended experts: {N_CONTENDED_EXPERTS}, max in-flight: {MAX_IN_FLIGHT}",
        f"elapsed: {elapsed:.2f}s",
        f"claimed: {counts['claimed']}, rejected (lease contention or already assigned): {counts['not_claimed']}",
        f"active_assignment rows for contended experts after the run: {total_active} (expected <= {N_CONTENDED_EXPERTS})",
        f"double-commitments (experts with more than one active row): {double_commitments}",
    ]
    out = "\n".join(lines)
    print(out)
    (Path(__file__).resolve().parent.parent / "docs").mkdir(exist_ok=True)
    (Path(__file__).resolve().parent.parent / "docs/benchmark_concurrency.txt").write_text(out + "\n")

    await pg_pool.close()
    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
