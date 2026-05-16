# ADK Empty Messages Workaround

**Status:** Active workaround — remove when upstream fix lands
**Date:** 2026-04-19

## Problem

Google ADK (v1.25.0) drops `tool_result` blocks during session history replay for Anthropic models. On the second LLM call after tool use, the `messages` array sent to Anthropic is empty, causing:

```
Error code: 400 - messages: at least one message is required
```

Upstream issue: [google/adk-python#5074](https://github.com/google/adk-python/issues/5074)
Fix PR: [google/adk-python#5157](https://github.com/google/adk-python/pull/5157)

## Observed Behavior

1. Agent receives A2A request, first Claude call succeeds (200)
2. Claude responds with `tool_use`, agent executes MCP tools
3. Second Claude call fails (400) — ADK reconstructed empty messages
4. kagent's executor retries with a fresh session, subsequent calls succeed
5. Frontend showed "failed" from the first attempt and stopped updating

## Workaround

`chat-drawer.tsx` treats `"failed"` as terminal and stops polling immediately. Auto-retrying on failure causes an infinite loop because each `streamReply` re-triggers the ADK bug. The user sees the error and can start a new job. kagent may recover internally, but the frontend does not chase those retries.

## When to Remove

Monitor [adk-python#5157](https://github.com/google/adk-python/pull/5157). Once merged and included in a kagent release:

1. Verify the kagent image bundles the fixed ADK version
2. Test a multi-turn tool-use session without the 400 error
3. The poll-retry-on-failure logic can stay (defensive) or be simplified
