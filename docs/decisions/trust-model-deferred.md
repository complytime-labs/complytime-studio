# Agent Trust Model Deferred

**Status:** Rejected for v1
**Date:** 2026-04-29

## Decision

Studio will not implement a graduated agent trust model (trust levels, self-enforcement, auto-promotion/demotion). Agents operate at a single behavioral tier: human-in-the-loop confirmation for all actions.

## Context

As Studio adds more AI agents, the question arises whether agents should have graduated autonomy — supervised at first, then progressively autonomous as they demonstrate reliability.

A candidate design was evaluated: a 3-tier trust model where agents read their trust level from a `trust_state` PostgreSQL table and self-enforce graduated autonomy (L1: confirm everything, L2: exception-only review, L3: autonomous). Agents would promote themselves based on quality gate pass rates.

A STRIDE threat model was performed against this design.

## STRIDE Analysis

| Category | Threat | Trust Model Mitigates? | Rationale |
|:--|:--|:--|:--|
| Spoofing | Agent impersonates higher-trust agent | No | Trust is self-reported. No cryptographic binding between agent pod and trust_state row. |
| Tampering | Agent modifies own trust_state to escalate | No | Self-enforcement means the agent writes its own trust level. |
| Repudiation | Agent denies performing autonomous action | Partially | trust_state logs updated_at, but the agent controls the log. No independent witness. |
| Info Disclosure | N/A | N/A | Trust model does not address data leakage. |
| Denial of Service | N/A | N/A | Trust model does not address availability. |
| Elevation of Privilege | L1 agent acts as L3 (skips confirmation) | No | Enforcement is a prompt instruction. LLM can ignore it. Gateway does not enforce. |

**Compound risk:** Tampering + Elevation of Privilege. An agent that writes its own trust level and then acts on that level has no separation of duties. The "control" and the "controlled entity" are the same process.

## Existing Controls That Address the Same Threats

| Threat | Existing Control |
|:--|:--|
| Agent calls destructive MCP tool | MCP tool allowlists per agent (kagent CRD `tools` field) |
| Agent exfiltrates data via tool call | OBO scopes, tool allowlists, network policies |
| Agent executes DML on ClickHouse | `before_tool` SQL injection guard |
| Agent acts without user awareness | Audit logs, A2A response stream visible to user |

## Conditions for Revisiting

Revisit if:
1. Operational data from 3+ agents in production shows a concrete need for graduated autonomy.
2. An external trust authority (not the agent itself) can enforce trust decisions server-side.
3. A regulatory requirement mandates graduated agent controls with independent attestation.

## Rejected Approaches

| Approach | Why Not                                                                                                                                                   |
|:--|:----------------------------------------------------------------------------------------------------------------------------------------------------------|
| Self-enforced trust (prompt instruction) | Not a security boundary. LLM can ignore instructions.                                                                                                     |
| Self-promotion via pass rates | Agent can inflate metrics by running easy tasks. Goodhart's Law.                                                                                          |
| Gateway-enforced trust | Couples gateway to agent-internal decision logic. Adds latency and complexity without addressing the core problem (trust levels are still self-reported). |
