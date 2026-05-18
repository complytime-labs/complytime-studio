# Agent Artifact Delivery to Workbench Editor

Status: **accepted** (client-side extraction); **deferred** (server-side A2A artifacts)

## Problem

Agents produce Gemara YAML (ThreatCatalog, ControlCatalog, Policy, etc.) as their primary output. That YAML must reach the workbench editor so users can review, edit, and validate it. Previously, streamed agent output was never scanned for artifacts on finalization, so YAML embedded in chat messages did not appear in the editor.

## Decision

### Phase 1 (implemented)

Client-side extraction in the workbench frontend:

1. **Streaming finalization** -- `finalizeStreamedContent()` runs `extractArtifacts` on the accumulated streaming buffer at every boundary: status `ready`, pre-tool-call flush, non-partial message close, and `onDone`.
2. **Broader fence detection** -- `extractArtifacts` now matches ` ```yaml `, ` ```yml `, and bare ` ``` ` fenced blocks.
3. **Raw YAML fallback** -- When no fenced blocks are found, `extractArtifacts` scans for inline Gemara YAML starting at a recognized top-level key (`metadata:`, `threats:`, etc.) with at least 3 lines.
4. **A2A artifact events** -- The `onArtifact` callback already calls `proposeArtifact`, so any `TaskArtifactUpdateEvent` from kagent also routes to the editor. Added handling for singular `result.artifact` (SSE streaming event shape).

5. **Platform prompt directive** -- `agents/platform.md` now instructs agents to wrap each artifact in a ` ```yaml ` fenced code block, ensuring reliable client-side detection.
6. **YAML gate** -- `proposeArtifact` rejects content that doesn't pass `isGemaraArtifact()` (must contain recognized top-level keys like `threats:`, `controls:`, `policy:`, etc.). Prevents non-YAML agent output from reaching the editor.
7. **Preview before apply** -- The proposal banner includes a Preview toggle that expands a scrollable pane showing the full YAML content. Users can inspect the artifact before choosing Apply or Dismiss.

### Phase 2 (deferred)

Server-side artifact emission via A2A protocol:

| Capability | Current State | Gap |
|---|---|---|
| `TaskArtifactUpdateEvent` on completion | kagent emits one on success, parts = last status message parts | Duplicates text; no MIME typing |
| Streaming artifact chunks (`append`) | A2A spec supports it | kagent/ADK streams text as `TaskStatusUpdateEvent`, not artifact chunks |
| ADK `save_artifact` | Available (`InMemoryArtifactService`) | Not wired to A2A `TaskArtifactUpdateEvent` output |
| MIME-typed YAML parts | A2A supports `FileWithBytes` | Agent would need `inline_data` with `application/yaml` MIME; requires executor/tool changes |

**When to revisit:**
- kagent adds explicit artifact emission distinct from status messages
- ADK wires `save_artifact` to A2A artifact events ([adk-python#660](https://github.com/google/adk-python/issues/660), [adk-python#4148](https://github.com/google/adk-python/issues/4148))
- We need agents to produce multiple distinct artifacts per run (current text extraction handles single-artifact responses well)

## Tracking

| Item | Link |
|---|---|
| kagent A2A library swap | [kagent#1336](https://github.com/kagent-dev/kagent/issues/1336) |
| ADK artifact APIs | [adk-python#660](https://github.com/google/adk-python/issues/660) |
| ADK artifact UI | [adk-python#4148](https://github.com/google/adk-python/issues/4148) |
