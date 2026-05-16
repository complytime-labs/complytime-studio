# ADK A2A Streaming

**Status:** Resolved
**Date:** 2026-04-21

## Context

The BYO assistant agent built with Google ADK (`google-adk` 1.31.0, `a2a-sdk` 0.3.26) stopped returning streamed responses. The workbench sends `message/stream` A2A requests, but the agent returned:

```json
{"error":{"code":-32603,"message":"Streaming is not supported by the agent"}}
```

## Root Cause

Two missing configuration items in `agents/assistant/main.py`:

1. **Agent card capabilities** — `AgentCardBuilder` defaults to `AgentCapabilities()` (empty). The A2A SDK server checks `capabilities.streaming` before routing `message/stream` and rejects if absent.

2. **Queue manager** — `DefaultRequestHandler` requires an `InMemoryQueueManager` to dispatch SSE events during streaming. Without it, the handler has no event dispatch mechanism even if capabilities are declared.

## Fix

```python
from a2a.server.events import InMemoryQueueManager
from a2a.types import AgentCapabilities

# 1. Declare streaming in agent card
card_builder = AgentCardBuilder(
    agent=root_agent,
    rpc_url=rpc_url,
    capabilities=AgentCapabilities(streaming=True),
)

# 2. Provide queue manager for event dispatch
queue_manager = InMemoryQueueManager()
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    push_config_store=push_config_store,
    queue_manager=queue_manager,
)
```

## Notes

- The upstream `to_a2a()` convenience function also defaults to `AgentCapabilities()` — this is a known gap tracked in [google/adk-python#4240](https://github.com/google/adk-python/issues/4240).
- Since we use a manual setup (not `to_a2a()`), both items must be configured explicitly.
