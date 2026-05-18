# SPDX-License-Identifier: Apache-2.0

"""Tests for nodes.py — extract_draft_node."""

from langchain_core.messages import AIMessage

from nodes import extract_draft_node


class TestExtractDraftNode:
    def test_extracts_yaml_from_fenced_block(self):
        content = (
            "Here is the draft:\n\n"
            "```yaml\n"
            "metadata:\n"
            "  type: AuditLog\n"
            "  policy-id: stig-v1\n"
            "evidence:\n"
            "  - reference-id: ev-001\n"
            "  - reference-id: ev-002\n"
            "```\n"
        )
        state = {"messages": [AIMessage(content=content)]}
        result = extract_draft_node(state)

        assert "draft_yaml" in result
        assert "policy-id: stig-v1" in result["draft_yaml"]
        assert result["evidence_refs"] == ["ev-001", "ev-002"]

    def test_extracts_bare_yaml(self):
        content = "metadata:\n  type: AuditLog\n  policy-id: abc"
        state = {"messages": [AIMessage(content=content)]}
        result = extract_draft_node(state)

        assert "draft_yaml" in result
        assert "metadata:" in result["draft_yaml"]

    def test_returns_empty_when_no_yaml(self):
        state = {"messages": [AIMessage(content="The audit looks good overall.")]}
        result = extract_draft_node(state)

        assert result == {}

    def test_returns_empty_for_no_messages(self):
        assert extract_draft_node({"messages": []}) == {}

    def test_deduplicates_evidence_refs(self):
        content = (
            "```yml\n"
            "evidence:\n"
            "  - reference-id: ev-001\n"
            "  - reference-id: ev-001\n"
            "  - reference-id: ev-002\n"
            "```\n"
        )
        state = {"messages": [AIMessage(content=content)]}
        result = extract_draft_node(state)

        assert result["evidence_refs"] == ["ev-001", "ev-002"]
