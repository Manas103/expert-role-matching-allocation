"""Connection settings, all overridable by environment variable so the same
code runs against a developer's own Postgres/Redis instance. Defaults point
at this project's own local database and its own Redis key prefix, chosen
so this service does not collide with sibling projects that share the same
WSL2 Postgres and Redis instances (see README "Why this exists")."""

import os

PG_HOST = os.environ.get("ERM_PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("ERM_PG_PORT", "5432"))
PG_USER = os.environ.get("ERM_PG_USER", "erm_app")
PG_PASSWORD = os.environ.get("ERM_PG_PASSWORD", "erm_app_pw_local_dev")
PG_DATABASE = os.environ.get("ERM_PG_DATABASE", "expert_matching")

REDIS_HOST = os.environ.get("ERM_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("ERM_REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("ERM_REDIS_DB", "0"))
REDIS_KEY_PREFIX = os.environ.get("ERM_REDIS_PREFIX", "erm:")

LEASE_TTL_MS = int(os.environ.get("ERM_LEASE_TTL_MS", "5000"))

SENIORITY_LEVELS = ["junior", "mid", "senior", "staff"]
SENIORITY_RANK = {level: i for i, level in enumerate(SENIORITY_LEVELS)}


def pg_dsn() -> str:
    return f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"


def redis_url() -> str:
    return f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


def lease_key(expert_id: int) -> str:
    return f"{REDIS_KEY_PREFIX}lease:{expert_id}"
