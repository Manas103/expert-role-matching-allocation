import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


@pytest_asyncio.fixture
async def pg_pool():
    try:
        pool = await db.make_pg_pool(min_size=1, max_size=5)
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def redis_client():
    client = db.make_redis_client()
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis unreachable: {exc}")
    yield client
    await client.aclose()
