# 0030 — Recommendation Engine Deferred to Workbench

**Status:** Deferred
**Date:** 2026-05-14

## Context

The UI's program detail view calls `/api/programs/{id}/recommendations` endpoints (list, attach, dismiss). These endpoints were never implemented in the gateway. The UI degrades silently -- the recommendation section shows empty.

Recommendations are a derived intelligence layer: "given your posture, policies, and evidence gaps, here's what you should do next." This is fundamentally different from the gateway's role of storing and certifying facts.

## Decision

Defer the recommendation engine. When implemented, it belongs in the **Studio Workbench** (complytime-studio), not the data platform.

## Rationale

- Recommendations require inference over evidence, posture, control mappings, and threat/risk catalogs. The workbench already has agent infrastructure and MCP access to all of these via `complytime://` resources.
- A recommendation agent reading `complytime://posture` + `complytime://policies` + `complytime://risks` and producing actionable suggestions fits the existing agent pattern.
- The gateway should not contain recommendation logic -- it would couple policy interpretation to the data layer.

## When to Revisit

- When program management moves beyond CRUD (active monitoring, automated remediation)
- When users request "what should I do next?" workflows
- When the workbench agent framework is stable enough to support always-on background agents

## Consequences

- UI recommendation components remain inert. No 500 errors -- the fetch calls fail silently.
- No gateway endpoints to implement or maintain.
- Future implementation path: workbench agent + new `/workbench/recommendations` API, UI rewired to that endpoint.
