"""FastAPI app. Owns the live Postgres pool and Redis client used by the
/decide and /claim endpoints, the load test, and the concurrency test."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db, matching
from app.models import (
    ClaimRequest, ClaimResponse, DecisionRequest, DecisionResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pg_pool = await db.make_pg_pool()
    app.state.redis = db.make_redis_client()
    yield
    await app.state.pg_pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="Expert-to-Role Matching and Allocation Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/decide", response_model=DecisionResponse)
async def decide(req: DecisionRequest):
    seniority_rank = matching.config.SENIORITY_RANK[req.seniority]
    best, considered = await matching.decide(
        app.state.pg_pool, req.required_skills, req.domain, seniority_rank, req.candidate_pool_size,
    )
    if best is None:
        return DecisionResponse(
            external_id=req.external_id, matched=False, candidates_considered=considered,
        )
    return DecisionResponse(
        external_id=req.external_id, matched=True, expert_id=best.expert_id,
        expert_external_id=best.external_id, score=best.score, candidates_considered=considered,
    )


@app.post("/claim", response_model=ClaimResponse)
async def claim(req: ClaimRequest):
    result = await matching.claim_expert(
        app.state.pg_pool, app.state.redis, req.expert_id, req.request_external_id,
    )
    return ClaimResponse(
        claimed=result.claimed, expert_id=req.expert_id,
        request_external_id=req.request_external_id, reason=result.reason,
    )
