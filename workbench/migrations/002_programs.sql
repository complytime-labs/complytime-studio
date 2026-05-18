-- SPDX-License-Identifier: Apache-2.0
-- Migration 002: Programs and related tables
-- (moved from complytime-core migrations 005, 009, 010, 012).
--
-- All DDL uses IF NOT EXISTS so this is safe regardless of whether core
-- migration 015 has already moved tables from public to workbench.

CREATE TABLE IF NOT EXISTS workbench.programs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    guidance_catalog_id TEXT,
    framework           TEXT NOT NULL,
    applicability       TEXT[] NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'intake',
    health              TEXT,
    owner               TEXT,
    description         TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}',
    policy_ids          TEXT[] NOT NULL DEFAULT '{}',
    environments        TEXT[] NOT NULL DEFAULT '{}',
    version             INTEGER NOT NULL DEFAULT 1,
    green_pct           INT NOT NULL DEFAULT 90,
    red_pct             INT NOT NULL DEFAULT 50,
    score_pct           INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT programs_status_check CHECK (
        status IN ('intake', 'active', 'monitoring', 'renewal', 'closed')
    ),
    CONSTRAINT programs_threshold_check CHECK (red_pct < green_pct)
);
CREATE INDEX IF NOT EXISTS idx_wb_programs_status
    ON workbench.programs(status) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS workbench.jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id  UUID NOT NULL REFERENCES workbench.programs(id),
    agent       TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wb_jobs_program
    ON workbench.jobs(program_id, created_at DESC);

CREATE TABLE IF NOT EXISTS workbench.program_members (
    program_id  UUID NOT NULL REFERENCES workbench.programs(id),
    user_email  TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'contributor',
    owns        TEXT[] NOT NULL DEFAULT '{}',
    notes       TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id, user_email),
    CONSTRAINT program_members_role_check CHECK (
        role IN ('owner', 'manager', 'contributor', 'viewer')
    )
);
CREATE INDEX IF NOT EXISTS idx_wb_program_members_email
    ON workbench.program_members(user_email);

CREATE TABLE IF NOT EXISTS workbench.program_findings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id  UUID NOT NULL REFERENCES workbench.programs(id),
    policy_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_id   TEXT,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    owner       TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    severity    TEXT,
    target_date DATE,
    resolved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT program_findings_status_check CHECK (
        status IN ('open', 'in_progress', 'resolved', 'accepted', 'deferred')
    ),
    CONSTRAINT program_findings_type_check CHECK (
        type IN ('Finding', 'Gap', 'Observation', 'Risk')
    ),
    CONSTRAINT program_findings_source_check CHECK (
        source IN ('audit_log', 'posture_check', 'manual')
    )
);
CREATE INDEX IF NOT EXISTS idx_wb_program_findings_program
    ON workbench.program_findings(program_id, status);
CREATE INDEX IF NOT EXISTS idx_wb_program_findings_policy
    ON workbench.program_findings(policy_id);
CREATE INDEX IF NOT EXISTS idx_wb_program_findings_source
    ON workbench.program_findings(source_id) WHERE source_id IS NOT NULL;
