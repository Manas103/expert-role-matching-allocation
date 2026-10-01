"""Measures claims 3 and 4: /decide decision p95 latency and throughput,
against a real uvicorn server this script starts itself (holding its PID)
and stops itself at the end. Run with: python scripts/run_load_test.py"""

import asyncio
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = 8731
N_REQUESTS = 3000
CONCURRENCY = 48

DOMAINS_SKILLS = [
    ("backend", ["python", "postgres"]),
    ("frontend", ["react", "typescript"]),
    ("data", ["sql", "spark"]),
    ("ml", ["pytorch", "nlp"]),
    ("infra", ["kubernetes", "terraform"]),
]


async def one_request(client: httpx.AsyncClient, i: int):
    domain, skills = DOMAINS_SKILLS[i % len(DOMAINS_SKILLS)]
    payload = {
        "external_id": f"load-{i}",
        "required_skills": skills,
        "seniority": "mid",
        "domain": domain,
        "exclude_assigned": True,
        "candidate_pool_size": 50,
    }
    t0 = time.perf_counter()
    resp = await client.post(f"http://127.0.0.1:{PORT}/decide", json=payload, timeout=10.0)
    dt = time.perf_counter() - t0
    resp.raise_for_status()
    return dt


async def run_load():
    sem = asyncio.Semaphore(CONCURRENCY)
    latencies = []

    async with httpx.AsyncClient() as client:
        async def bounded(i):
            async with sem:
                return await one_request(client, i)

        t0 = time.perf_counter()
        results = await asyncio.gather(*(bounded(i) for i in range(N_REQUESTS)))
        elapsed = time.perf_counter() - t0
        latencies.extend(results)

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    throughput = N_REQUESTS / elapsed
    return p50, p95, p99, throughput, elapsed


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT),
         "--workers", "1"],
        cwd=str(ROOT),
    )
    pid = proc.pid
    try:
        for _ in range(60):
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=1.0)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("server did not become healthy")

        p50, p95, p99, throughput, elapsed = asyncio.run(run_load())
        lines = [
            f"machine: AMD Ryzen 7 7800X3D, 8 physical / 16 logical cores, WSL2 Ubuntu 22.04 (capped 12 logical cores)",
            f"requests: {N_REQUESTS}, concurrency: {CONCURRENCY}, elapsed: {elapsed:.2f}s",
            f"p50={p50*1000:.2f}ms p95={p95*1000:.2f}ms p99={p99*1000:.2f}ms",
            f"throughput={throughput:.1f} req/sec",
        ]
        out = "\n".join(lines)
        print(out)
        (ROOT / "docs").mkdir(exist_ok=True)
        (ROOT / "docs/benchmark_load_test.txt").write_text(out + "\n")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        print(f"stopped uvicorn pid {pid}")


if __name__ == "__main__":
    main()
