# 0030 — Recommendation Engine Deferred to Workbench

**Status:** Deferred
**Date:** 2026-05-14

## Context

Programs track compliance against a framework (e.g., NIST 800-53). Policies contain controls and assessment requirements that map to framework requirements. Evidence collected against a policy's assessment requirements contributes coverage toward the program's requirements.

Users need guidance on which policies to attach to a program. The recommendation engine answers: "given your program's uncovered requirements, which available policies would improve your compliance posture, and by how much?"

This is a derived intelligence layer — fundamentally different from the gateway's role of storing and certifying facts.

## Decision

Defer the recommendation engine. When implemented, it belongs in the **Studio Workbench** (complytime-studio), not the data platform.

## Algorithm Design

### Inputs

| Source | Data | MCP Resource |
|:---|:---|:---|
| Program | Framework requirements, attached policy IDs | — |
| Policies | Catalog imports, mapping references, effective controls | `complytime://policies` |
| Posture | Pass/fail per assessment requirement per policy | `complytime://posture` |
| Catalogs | Control → assessment requirement hierarchy | `complytime://catalogs` |

### Scoring Steps

1. **Resolve program requirements.** Enumerate the framework requirements the program must satisfy.
2. **Identify coverage gaps.** For each attached policy, resolve effective controls (via `ResolveEffectiveControls`). Mark which program requirements are already covered by attached policies. The remainder are gaps.
3. **Score candidate policies.** For each unattached policy in the system:
   - Resolve its effective controls.
   - Count how many of the program's gap requirements the candidate's controls map to. This is `mapping_strength` — the fraction of gaps the candidate addresses.
   - Compute `score` as a weighted combination of `mapping_strength` and evidence quality (how many of the candidate's own assessment requirements already have passing evidence).
4. **Forecast posture delta.** For each candidate, project the new compliance posture if attached:
   - `predicted_score_pct` = (currently covered requirements + candidate's covered requirements) / total program requirements
   - `score_delta` = `predicted_score_pct` - current posture percentage
5. **Rank and return.** Sort candidates by `score` descending. Exclude dismissed candidates (per `recommendation_dismissals` table).

### Example: NIST 800-53 Program

A program targets NIST 800-53 Moderate. It has 325 applicable requirements. 180 are covered by attached policies with passing evidence (55% posture).

An unattached policy for **CIS Benchmark branch protection** maps to controls satisfying 12 uncovered requirements (CM-3, CM-5, SA-10, SI-7, etc.). The policy already has passing evidence from a Kyverno evaluation log.

The engine recommends the policy with:
- `mapping_strength`: 12 / 145 gaps = 8.3%
- `predicted_score_pct`: (180 + 12) / 325 = 59%
- `score_delta`: +4%
- `reason`: "Covers 12 uncovered requirements across CM, SA, and SI families with existing evidence."

### Attach and Dismiss

- **Attach:** Adds the policy to the program's `policy_ids`, recomputes posture. The recommendation disappears from future results.
- **Dismiss:** Records a row in `workbench.recommendation_dismissals` (program_id, policy_id, user_id). The engine excludes dismissed candidates. Dismissals are reversible.

## Rationale

- Recommendations require inference over evidence, posture, control mappings, and catalogs. The workbench already has agent infrastructure and MCP access to all of these via `complytime://` resources.
- A recommendation agent reading `complytime://posture` + `complytime://policies` + `complytime://catalogs` and producing ranked suggestions fits the existing agent pattern.
- The gateway should not contain recommendation logic — it would couple policy interpretation to the data layer.

## When to Revisit

- When program management moves beyond CRUD (active monitoring, automated remediation)
- When users request "what should I do next?" workflows
- When the workbench agent framework is stable enough to support always-on background agents

## Consequences

- UI recommendation components are hidden (tab removed from bar) but fully implemented — state, fetch, render, attach/dismiss handlers all intact.
- Workbench stubs return `[]` (200) for list and `501` for actions.
- DB schema exists: `workbench.recommendation_dismissals` table (owned by complytime-studio, migrated from core via migration 015).
- Future implementation path: workbench service reads MCP resources, computes scores per algorithm above, exposes via `/workbench/programs/{id}/recommendations`. UI tab re-enabled by adding `["recommendations", "Recommendations"]` back to the tab bar array.
