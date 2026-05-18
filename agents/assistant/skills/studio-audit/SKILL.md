---
name: studio-audit
description: Audit methodology, classification criteria, coverage mapping, and gateway tool reference
---

# Studio Audit

## Classification

| Type | Condition |
|:--|:--|
| Strength | eval_result = Passed, compliance_status = Compliant |
| Finding | eval_result = Failed, or cadence gaps detected |
| Gap | No evidence rows in audit window |
| Observation | eval_result = Needs Review, or mixed results |

Use most recent evidence per control+requirement. Enforcement with `remediation_status = Success` can convert Finding -> Strength. Exception with `exception_active = true` converts Finding -> annotated Strength.

## Satisfaction

| Determination | Condition |
|:--|:--|
| Satisfied | Evidence complete, current, confidence Medium/High, no cadence gaps |
| Partially Satisfied | Incomplete evidence, missing cycles, Low confidence, mixed results |
| Not Satisfied | Failed eval_result, critical cadence gaps without remediation |
| Not Applicable | Control scoped out for this target |

Never mark Satisfied without evidence. Absence = Gap.

## Cadence

Map `Policy.adherence.assessment-plans[].frequency` to cycle length (daily=1d, weekly=7d, monthly=30d, quarterly=90d, annually=365d). Expected cycles = floor((end - start) / cycle_length). Missing cycles are Findings.

## Coverage Mapping

When `mapping_documents` exist for the policy, join AuditResults with mapping entries:

| AuditResult | Strength 8-10 | 5-7 | 1-4 |
|:--|:--|:--|:--|
| Strength | Covered | Partially Covered | Weakly Covered |
| Finding | Not Covered | Not Covered | Not Covered |
| Gap | Not Covered | Not Covered | Not Covered |
| Observation | Needs Review | Needs Review | Needs Review |

Multiple controls mapping to the same external entry: use strongest coverage. No mapping documents = skip cross-framework analysis.

## Gemara Tools (MCP)

**validate_gemara_artifact**: `artifact_content` (YAML string), `definition` (e.g. `#AuditLog`), `version` (optional)

**migrate_gemara_artifact**: `artifact_content` (YAML string), `artifact_type` (optional), `gemara_version` (optional)

## Gateway Tools (@tool functions)

Data access via LangChain `@tool`-decorated functions that call the gateway REST API directly (ADR 0041).

| Tool | Purpose |
|:--|:--|
| `query_evidence` | Query evidence rows filtered by `policy_id`, `target`, with `limit`. |
| `list_policies` | List all imported policies (metadata). |
| `get_certifications` | Get certification records filtered by `policy_id` or `evidence_id`. |
| `list_catalogs` | List catalogs, optionally filtered by `catalog_type`. |

Evidence is ingested via the REST API or async NATS pipeline, not by agents. Do not attempt to write evidence.

## Draft Publishing

After `validate_gemara_artifact` succeeds and the user approves, `publish_audit_log` persists the draft via the gateway REST API. The draft is attributed to the authenticated user, not the agent.

## Posture vs. Evidence Query

The workbench exposes `GET /workbench/posture` with optional `start` and `end` to bound evidence by `collected_at`. When you need parity with a user-selected audit window, filter evidence rows client-side using the same date range (presets: 7d, 30d, 90d, or all-time).
