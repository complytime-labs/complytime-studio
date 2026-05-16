-- SPDX-License-Identifier: Apache-2.0
-- Migration 003: Recommendation dismissals (moved from complytime-core migration 007).

CREATE TABLE IF NOT EXISTS workbench.recommendation_dismissals (
    program_id   UUID NOT NULL REFERENCES workbench.programs(id),
    policy_id    TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id, policy_id)
);
