"""Synthetic data generator. Deterministic under a fixed seed so the fill
rate benchmark is reproducible across runs. All data here is synthetic and
is labeled as such everywhere it is reported."""

import random
from typing import List, Dict

DOMAINS = [
    "backend", "frontend", "data", "ml", "infra", "mobile",
    "security", "sre", "qa", "platform",
]

def _domain_skills(prefix: str, n: int) -> List[str]:
    return [f"{prefix}-{i:02d}" for i in range(n)]


# 40 skills per domain, each expert holding only 4 of them, each request
# requiring a specific 3-skill subset. Expected experts per domain (5,000)
# containing a *fixed* 3-skill combination is 5000 * C(37,1)/C(40,4) =~ 2,
# which is genuine scarcity: most requests have only a handful of truly
# eligible experts, so which request "gets there first" actually matters.
# Two earlier attempts (18 skills/domain with ANY-overlap matching, then
# 18 skills/domain with full-containment matching) both filled 100% of
# requests under both policies, i.e. demand never actually contended for a
# resource; see README "Findings" for the measured numbers and why. This is
# the third and final attempt allowed by the measurement rule.
SKILLS_BY_DOMAIN: Dict[str, List[str]] = {
    "backend": _domain_skills("be", 40),
    "frontend": _domain_skills("fe", 40),
    "data": _domain_skills("da", 40),
    "ml": _domain_skills("ml", 40),
    "infra": _domain_skills("in", 40),
    "mobile": _domain_skills("mo", 40),
    "security": _domain_skills("se", 40),
    "sre": _domain_skills("sr", 40),
    "qa": _domain_skills("qa", 40),
    "platform": _domain_skills("pl", 40),
}

SENIORITY_LEVELS = ["junior", "mid", "senior", "staff"]
SENIORITY_RANK = {level: i for i, level in enumerate(SENIORITY_LEVELS)}

def generate_experts(n: int, seed: int = 1337) -> List[dict]:
    rng = random.Random(seed)
    experts = []
    for i in range(n):
        domain = rng.choice(DOMAINS)
        pool = SKILLS_BY_DOMAIN[domain]
        skills = rng.sample(pool, 4)
        seniority = rng.choices(SENIORITY_LEVELS, weights=[0.3, 0.35, 0.25, 0.10])[0]
        experts.append({
            "external_id": f"exp-{i:06d}",
            "name": f"Synthetic Expert {i:06d}",
            "seniority": seniority,
            "domain": domain,
            "skills": skills,
            "skills_text": " ".join(skills),
            "seniority_rank": SENIORITY_RANK[seniority],
            "quality_score": round(rng.uniform(0.40, 0.99), 3),
        })
    return experts


def generate_requests(n: int, seed: int = 4242) -> List[dict]:
    rng = random.Random(seed)
    requests = []
    for i in range(n):
        domain = rng.choice(DOMAINS)
        pool = SKILLS_BY_DOMAIN[domain]
        required = rng.sample(pool, 3)
        seniority = rng.choices(SENIORITY_LEVELS, weights=[0.15, 0.35, 0.35, 0.15])[0]
        requests.append({
            "external_id": f"req-{i:06d}",
            "required_skills": required,
            "seniority": seniority,
            "seniority_rank": SENIORITY_RANK[seniority],
            "domain": domain,
            "quantity": 1,
        })
    return requests
