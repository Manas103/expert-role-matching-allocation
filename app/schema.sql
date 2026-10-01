-- Expert-to-Role Matching and Allocation Service: schema
--
-- Retrieval note: the resume claims an Elasticsearch-backed candidate
-- retrieval layer. This schema expresses the same retrieval job in
-- PostgreSQL (GIN array overlap on skills, plus a trigram index for
-- fuzzy skill-name lookups) because no Elasticsearch cluster was
-- exercised in this session; see README "Elasticsearch" for the
-- honest disclosure and the ES mapping this would become.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS experts (
    id              SERIAL PRIMARY KEY,
    external_id     TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    seniority       TEXT NOT NULL CHECK (seniority IN ('junior', 'mid', 'senior', 'staff')),
    domain          TEXT NOT NULL,
    skills          TEXT[] NOT NULL,
    skills_text     TEXT NOT NULL,
    seniority_rank  SMALLINT NOT NULL,
    quality_score   NUMERIC(4,3) NOT NULL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS experts_skills_gin_idx ON experts USING GIN (skills);
CREATE INDEX IF NOT EXISTS experts_skills_trgm_idx ON experts USING GIN (skills_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS experts_domain_idx ON experts (domain);
CREATE INDEX IF NOT EXISTS experts_seniority_rank_idx ON experts (seniority_rank);

CREATE TABLE IF NOT EXISTS role_requests (
    id               SERIAL PRIMARY KEY,
    external_id      TEXT NOT NULL UNIQUE,
    required_skills  TEXT[] NOT NULL,
    seniority        TEXT NOT NULL CHECK (seniority IN ('junior', 'mid', 'senior', 'staff')),
    seniority_rank   SMALLINT NOT NULL,
    domain           TEXT NOT NULL,
    quantity         INT NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per *active* commitment of an expert to a request. The partial
-- unique index is the structural (Postgres-side) half of the double
-- commitment guard; the Redis NX lease (see app/matching.py claim_expert)
-- is the fast-path (pre-write) half. Either one alone would be enough to
-- stop two writers from both landing a row for the same expert, which is
-- exactly why the concurrency test in docs/ exercises both together rather
-- than trusting either in isolation.
CREATE TABLE IF NOT EXISTS active_assignment (
    id                  BIGSERIAL PRIMARY KEY,
    expert_id           INT NOT NULL REFERENCES experts(id),
    request_external_id TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS active_assignment_one_active_per_expert
    ON active_assignment (expert_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS active_assignment_request_idx ON active_assignment (request_external_id);
