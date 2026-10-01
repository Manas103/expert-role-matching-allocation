"""Measures claim 1 and claim 2: heuristic fill rate vs naive greedy
first-fit baseline, on the identical 2,000 synthetic role requests against
the identical 50,000 synthetic expert pool (run scripts/generate_data.py
first). Run with: python scripts/run_fill_rate_benchmark.py"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, matching  # noqa: E402


async def main():
    pool = await db.make_pg_pool(min_size=4, max_size=10)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT external_id, required_skills, seniority, seniority_rank, domain FROM role_requests ORDER BY id"
        )
    requests = [dict(r) for r in rows]
    assert len(requests) == 2000, f"expected 2000 role_requests, found {len(requests)}, run generate_data.py"

    t0 = time.perf_counter()
    heuristic = await matching.heuristic_fill(pool, requests)
    t1 = time.perf_counter()
    baseline = await matching.baseline_fill(pool, requests)
    t2 = time.perf_counter()
    await pool.close()

    lines = [
        f"total requests: {len(requests)}",
        f"heuristic (scarcity-ordered): filled={heuristic['filled']} fill_rate={heuristic['fill_rate']*100:.2f}% elapsed={t1-t0:.2f}s",
        f"baseline (greedy first-fit, input order): filled={baseline['filled']} fill_rate={baseline['fill_rate']*100:.2f}% elapsed={t2-t1:.2f}s",
    ]
    out = "\n".join(lines)
    print(out)
    Path(__file__).resolve().parent.parent.joinpath("docs").mkdir(exist_ok=True)
    Path(__file__).resolve().parent.parent.joinpath("docs/benchmark_fill_rate.txt").write_text(out + "\n")


if __name__ == "__main__":
    asyncio.run(main())
