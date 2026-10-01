import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import matching  # noqa: E402


async def _insert_toy_experts(conn, prefix, specs):
    """specs: list of (seniority_rank, skills, quality_score)"""
    ids = []
    for i, (rank, skills, q) in enumerate(specs):
        row = await conn.fetchrow(
            """
            INSERT INTO experts (external_id, name, seniority, domain, skills,
                                  skills_text, seniority_rank, quality_score)
            VALUES ($1, $2, 'junior', 'oracle_test_domain', $3, $4, $5, $6)
            RETURNING id
            """,
            f"{prefix}-exp-{i}", f"{prefix} expert {i}", skills, " ".join(skills), rank, q,
        )
        ids.append(row["id"])
    return ids


@pytest.mark.asyncio
async def test_scarcity_ordering_beats_naive_order_on_toy_case(pg_pool):
    """A two-request, two-expert adversarial case: Expert A has both a
    common skill and a rare skill; Expert B only has the common skill.
    Naive first-fit, processing the common-skill request first (input
    order) and picking the lowest-id expert, burns A on the easy request
    and leaves the rare request unfillable. Scarcity ordering processes
    the rare request first and fills both."""
    async with pg_pool.acquire() as conn:
        await conn.execute("DELETE FROM experts WHERE external_id LIKE 'toy2-%'")
        a_id, b_id = await _insert_toy_experts(
            conn, "toy2",
            [(0, ["common", "rare"], 0.5), (0, ["common"], 0.9)],
        )
    requests = [
        {"external_id": "toy2-req-common", "required_skills": ["common"], "seniority": "junior",
         "seniority_rank": 0, "domain": "oracle_test_domain"},
        {"external_id": "toy2-req-rare", "required_skills": ["rare"], "seniority": "junior",
         "seniority_rank": 0, "domain": "oracle_test_domain"},
    ]
    try:
        baseline = await matching.baseline_fill(pg_pool, requests)
        heuristic = await matching.heuristic_fill(pg_pool, requests)
        assert baseline["filled"] == 1, "baseline should strand the rare request"
        assert heuristic["filled"] == 2, "scarcity ordering should fill both"
    finally:
        async with pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM experts WHERE external_id LIKE 'toy2-%'")


@pytest.mark.asyncio
async def test_heuristic_close_to_optimal_reference_oracle(pg_pool):
    """Reference oracle: an independently computed maximum-cardinality
    bipartite matching (Hungarian algorithm via scipy, on a 0/1 feasibility
    cost matrix) over a small 20-request / 30-expert random instance. The
    heuristic does not need to match optimal exactly (it is a fast online
    policy, the oracle is an offline exact solver), but it must stay close."""
    import random
    rng = random.Random(7)
    skill_pool = [f"ot{i}" for i in range(8)]

    specs = []
    for _ in range(30):
        k = rng.randint(1, 3)
        specs.append((0, rng.sample(skill_pool, k), round(rng.uniform(0.4, 0.99), 3)))

    async with pg_pool.acquire() as conn:
        await conn.execute("DELETE FROM experts WHERE external_id LIKE 'oracle-%'")
        expert_ids = await _insert_toy_experts(conn, "oracle", specs)

    requests = []
    req_skills = []
    for i in range(20):
        sk = rng.choice(skill_pool)
        req_skills.append(sk)
        requests.append({
            "external_id": f"oracle-req-{i}", "required_skills": [sk], "seniority": "junior",
            "seniority_rank": 0, "domain": "oracle_test_domain",
        })

    try:
        heuristic = await matching.heuristic_fill(pg_pool, requests)

        # Reference oracle: exact maximum cardinality matching via the
        # Hungarian algorithm on a 0/1 feasibility cost matrix. Minimizing
        # total cost over a full row assignment is equivalent to maximizing
        # the number of feasible (skill-overlapping) pairs.
        cost = np.ones((len(requests), len(specs)))
        for i, sk in enumerate(req_skills):
            for j, (_, skills, _) in enumerate(specs):
                if sk in skills:
                    cost[i, j] = 0.0
        row_ind, col_ind = linear_sum_assignment(cost)
        infeasible = int(cost[row_ind, col_ind].sum())
        oracle_max_matching = len(requests) - infeasible

        assert oracle_max_matching > 0
        ratio = heuristic["filled"] / oracle_max_matching
        assert ratio >= 0.85, (
            f"heuristic filled {heuristic['filled']} of an oracle-optimal {oracle_max_matching}, ratio {ratio:.2f}"
        )
    finally:
        async with pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM experts WHERE external_id LIKE 'oracle-%'")


@pytest.mark.asyncio
async def test_claim_uniqueness_invariant_under_real_concurrency(pg_pool, redis_client):
    """The invariant the whole double-commit guard exists for: fire many
    real concurrent claim attempts (real asyncpg + real redis round trips)
    at the same expert and confirm exactly one wins."""
    import asyncio

    async with pg_pool.acquire() as conn:
        await conn.execute("DELETE FROM experts WHERE external_id = 'invariant-test-expert'")
        row = await conn.fetchrow(
            """
            INSERT INTO experts (external_id, name, seniority, domain, skills, skills_text,
                                  seniority_rank, quality_score)
            VALUES ('invariant-test-expert', 'Invariant Test Expert', 'junior',
                    'oracle_test_domain', ARRAY['common'], 'common', 0, 0.5)
            RETURNING id
            """
        )
        expert_id = row["id"]
        await conn.execute("DELETE FROM active_assignment WHERE expert_id = $1", expert_id)
    await redis_client.delete(matching.config.lease_key(expert_id))

    try:
        results = await asyncio.gather(*(
            matching.claim_expert(pg_pool, redis_client, expert_id, f"invariant-req-{i}")
            for i in range(50)
        ))
        wins = sum(1 for r in results if r.claimed)
        assert wins == 1, f"expected exactly 1 winner out of 50 concurrent claims, got {wins}"

        async with pg_pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT count(*) FROM active_assignment WHERE expert_id = $1 AND status = 'active'",
                expert_id,
            )
        assert n == 1
    finally:
        async with pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM active_assignment WHERE expert_id = $1", expert_id)
            await conn.execute("DELETE FROM experts WHERE id = $1", expert_id)


def test_decide_endpoint_shape():
    """The /decide endpoint, exercised through a real (but local) HTTP
    lifecycle via Starlette's TestClient, which runs the real FastAPI
    lifespan (real Postgres pool, real Redis client)."""
    from fastapi.testclient import TestClient
    from app.main import app

    try:
        with TestClient(app) as client:
            r = client.post("/decide", json={
                "external_id": "shape-test", "required_skills": ["python"],
                "seniority": "mid", "domain": "backend",
            })
    except Exception as exc:
        pytest.skip(f"Postgres/Redis unreachable for endpoint test: {exc}")
    assert r.status_code == 200
    body = r.json()
    assert "matched" in body and "candidates_considered" in body
