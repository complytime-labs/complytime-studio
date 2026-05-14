# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from callbacks import after_agent, before_agent


class _Part:
    def __init__(self, text: str):
        self.text = text


class _UserContent:
    def __init__(self, text: str):
        self.parts = [_Part(text)]


class TestBeforeAgent:
    @pytest.mark.asyncio
    async def test_returns_none_for_normal_message(self):
        ctx = SimpleNamespace(user_content=_UserContent("audit policy ampel for Q1 2026"))
        assert await before_agent(ctx) is None

    @pytest.mark.asyncio
    async def test_empty_message_logs_and_returns_none(self):
        ctx = SimpleNamespace(user_content=_UserContent("   "))
        assert await before_agent(ctx) is None


class TestAfterAgent:
    @pytest.mark.asyncio
    async def test_returns_none(self):
        ctx = SimpleNamespace()
        result = await after_agent(ctx)
        assert result is None
