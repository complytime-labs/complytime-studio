# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the A2A delegation node."""

import pytest

from delegate import delegate_node


class TestDelegateNode:
    @pytest.mark.asyncio
    async def test_no_target_returns_error(self):
        state = {"delegation_target": "", "messages": [], "worker_data": {}}
        result = await delegate_node(state)
        assert "error" in result["worker_data"]

    @pytest.mark.asyncio
    async def test_clears_needs_delegation_flag(self):
        state = {
            "delegation_target": "nonexistent-agent",
            "needs_delegation": True,
            "messages": [],
            "worker_data": {},
        }
        result = await delegate_node(state)
        assert result["needs_delegation"] is False

    @pytest.mark.asyncio
    async def test_agent_not_found_returns_keyed_error(self):
        state = {
            "delegation_target": "fake-agent",
            "needs_delegation": True,
            "messages": [],
            "worker_data": {},
        }
        result = await delegate_node(state)
        assert "fake-agent" in result["worker_data"]
        assert "error" in result["worker_data"]["fake-agent"]
        assert "not found" in result["worker_data"]["fake-agent"]["error"]
