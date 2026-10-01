"""Thin pool holders. Kept separate from app/main.py so scripts/ (the
offline benchmark, the load test, the concurrency test) can open the same
kind of pool without importing the FastAPI app or spinning up uvicorn."""

import asyncpg
import redis.asyncio as redis_asyncio

from app import config


async def make_pg_pool(min_size: int = 2, max_size: int = 20) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=config.pg_dsn(), min_size=min_size, max_size=max_size
    )


def make_redis_client() -> redis_asyncio.Redis:
    return redis_asyncio.from_url(config.redis_url(), decode_responses=True)
