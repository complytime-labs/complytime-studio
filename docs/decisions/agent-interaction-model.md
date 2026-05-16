# Agent Interaction Model: HITL Chatbot

**Date**: 2026-04-22
**Status**: Accepted

## Decision

The Studio assistant is a human-in-the-loop (HITL) chatbot. It drafts artifacts for human review — it does not produce autonomous findings. The human reviews, edits, and explicitly saves every artifact.

## Context

During architectural review, the agent layer was evaluated against the standard of an autonomous compliance analysis engine — multi-model consensus, per-call telemetry, confidence scoring, server-side auto-persistence. This led to proposals that would significantly thicken the agent infrastructure without matching the actual use case.

The assistant replaces a manual workflow: a human querying a dashboard, reading evidence, cross-referencing controls, and writing up findings in a YAML file. The agent automates the drafting step. The human remains the decision-maker.

| Manual process | Agent equivalent |
|:---|:---|
| Query evidence in dashboard | `run_select_query` via clickhouse-mcp |
| Read control definitions | `gemara://schema/definitions` resource |
| Draft AuditLog YAML | LLM generates artifact |
| Review and fix errors | `validate_gemara_artifact` + retry loop |
| Save to audit history | User clicks "Save to Audit History" |

## What This Means

| Justified now | Not justified now |
|:---|:---|
| Single-model generation | Multi-model consensus / voting |
| Schema validation loop (3 attempts) | Per-call telemetry (token counts, raw responses) |
| Few-shot examples for classification accuracy | Confidence scores on findings |
| Provenance metadata (`model`, `prompt_version`) | Autonomous scheduled runs |
| Filtered MCP tool surfaces | Server-side auto-persistence without human approval |
| `before_tool` SQL deny-list | Statistical defensibility of individual classifications |

## Future: Autonomous Operation

The infrastructure supports a future upgrade to autonomous operation without a rewrite. When the use case justifies it (e.g. scheduled audits, event-triggered analysis):

- Add the artifact-persistence gateway interceptor (spec drafted in `openspec/changes/artifact-persistence/`)
- Add a scheduler or event trigger for agent invocation
- Add confidence thresholds to gate which artifacts auto-persist vs. require human review
- Add per-call reasoning capture for audit trail

The agent code, prompt structure, MCP tooling, and provenance pipeline remain unchanged. Autonomy is an upgrade, not a redesign.

## Consequences

- Contributors should not add multi-model consensus, confidence scoring, or autonomous persistence to the agent without revisiting this decision.
- The "Save to Audit History" button is the human approval step, not a UX gap.
- Agent reliability improvements (few-shot examples, prompt versioning, schema validation) are justified because they improve draft quality for the human reviewer.
- The artifact-persistence spec is a UX improvement (prevent data loss on tab close), not an architectural correction.
