from typing import List, Optional

from pydantic import BaseModel, Field


class RoleRequestIn(BaseModel):
    external_id: str
    required_skills: List[str] = Field(min_length=1)
    seniority: str
    domain: str
    quantity: int = 1


class DecisionRequest(BaseModel):
    """Payload for the read-only matching-decision endpoint. Not tied to a
    row in role_requests; callers (including the load test) can decide
    against an ad hoc request shape without inserting anything first."""

    external_id: str
    required_skills: List[str] = Field(min_length=1)
    seniority: str
    domain: str
    exclude_assigned: bool = True
    candidate_pool_size: int = 50


class DecisionResponse(BaseModel):
    external_id: str
    matched: bool
    expert_id: Optional[int] = None
    expert_external_id: Optional[str] = None
    score: Optional[float] = None
    candidates_considered: int


class ClaimRequest(BaseModel):
    request_external_id: str
    expert_id: int


class ClaimResponse(BaseModel):
    claimed: bool
    expert_id: int
    request_external_id: str
    reason: str
