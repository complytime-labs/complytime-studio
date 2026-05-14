---
name: studio-audit
description: Audit methodology, classification criteria, coverage mapping, and studio-mcp resource reference
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

## MCP — Gemara tools

**validate_gemara_artifact**: `artifact_content` (YAML string), `definition` (e.g. `#AuditLog`), `version` (optional)

**migrate_gemara_artifact**: `artifact_content` (YAML string), `artifact_type` (optional), `gemara_version` (optional)

## MCP — studio-mcp (data)

Read JSON via **`studio://`** resources (see agent prompt). Do **not** execute SQL.

**ingest_evidence**: Insert evidence rows when the user explicitly needs new rows loaded; each row needs `policy_id`, `target_id`, `control_id`, `collected_at`, and other fields expected by the platform store.

**save_draft_audit_log**: After validation, persist draft YAML — `policy_id`, `yaml`, optional `agent_reasoning` (JSON string), optional `model` / `prompt_version`.

## Workbench posture vs. studio resources

The workbench calls `GET /api/posture` with optional `start` and `end` to bound evidence by `collected_at`. **`studio://posture`** returns aggregates from the store; when you need parity with a user-selected window, filter evidence rows client-side using the same date range (presets: 7d, 30d, 90d, or all-time).

## Platform entities (JSON shape)

Underlying storage is PostgreSQL; **`studio://`** resources expose the same entities as JSON. Use resource payloads instead of ad-hoc SQL.

| Entity | Typical fields | Resource hints |
|:--|:--|:--|
| Policies | policy_id, title, content (YAML), oci_reference | `studio://policies`, `studio://policies/{id}` |
| Evidence | evidence_id, target_id, policy_id, control_id, requirement_id, eval_result, compliance_status, collected_at, engine_name | `studio://evidence?policy_id=` |
| Mappings | mapping_id, policy_id, framework, content | `studio://mappings` |
| Catalogs | catalog_id, catalog_type, title, policy_id | `studio://catalogs` |
| Threats / Risks | catalog_id, ids, titles, severity | `studio://threats`, `studio://risks` |
| Audit logs | audit metadata + content | `studio://audit-logs?policy_id=` (policy_id required) |

## Example resource reads

- Policy body: `studio://policies/ampel-branch-protection`
- Evidence page: `studio://evidence?policy_id=ampel-branch-protection&limit=100&offset=0`
- Mapping list: `studio://mappings`
- Risks for catalog: `studio://risks?catalog_id=<catalog_id>`
