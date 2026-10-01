"""Populates experts (50,000 synthetic) and role_requests (2,000
synthetic) in Postgres. Idempotent: truncates both tables first so re-runs
are safe. Run with: python scripts/generate_data.py"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, generator  # noqa: E402

N_EXPERTS = 50_000
N_REQUESTS = 2_000


async def main():
    pool = await db.make_pg_pool(min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE active_assignment, role_requests, experts RESTART IDENTITY CASCADE")
        experts = generator.generate_experts(N_EXPERTS)
        await conn.copy_records_to_table(
            "experts",
            records=[
                (e["external_id"], e["name"], e["seniority"], e["domain"],
                 e["skills"], e["skills_text"], e["seniority_rank"], e["quality_score"])
                for e in experts
            ],
            columns=["external_id", "name", "seniority", "domain", "skills",
                     "skills_text", "seniority_rank", "quality_score"],
        )
        requests = generator.generate_requests(N_REQUESTS)
        await conn.copy_records_to_table(
            "role_requests",
            records=[
                (r["external_id"], r["required_skills"], r["seniority"],
                 r["seniority_rank"], r["domain"], r["quantity"])
                for r in requests
            ],
            columns=["external_id", "required_skills", "seniority",
                     "seniority_rank", "domain", "quantity"],
        )
        n_experts = await conn.fetchval("SELECT count(*) FROM experts")
        n_requests = await conn.fetchval("SELECT count(*) FROM role_requests")
    await pool.close()
    print(f"experts inserted: {n_experts}")
    print(f"role_requests inserted: {n_requests}")


if __name__ == "__main__":
    asyncio.run(main())
