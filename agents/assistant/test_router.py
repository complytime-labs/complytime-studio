# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the intent router."""

from router import AUDIT_KEYWORDS, POSTURE_KEYWORDS, classify_intent, router_node


class TestClassifyIntent:
    def test_audit_keyword_exact(self):
        assert classify_intent("run an audit") == "audit_production"

    def test_audit_keyword_mixed_case(self):
        assert classify_intent("Run An Audit on my policy") == "audit_production"

    def test_audit_keyword_substring(self):
        assert (
            classify_intent("I want to generate audit results for ampel")
            == "audit_production"
        )

    def test_posture_keyword_exact(self):
        assert classify_intent("posture") == "posture_check"

    def test_posture_keyword_mixed_case(self):
        assert classify_intent("How Ready are we for the audit?") == "posture_check"

    def test_posture_keyword_substring(self):
        assert (
            classify_intent("Check the evidence quality for my policy")
            == "posture_check"
        )

    def test_ambiguous_no_match(self):
        assert classify_intent("hello there") == ""

    def test_ambiguous_empty(self):
        assert classify_intent("") == ""

    def test_audit_takes_priority_over_posture(self):
        assert classify_intent("run an audit to check posture") == "audit_production"

    def test_all_audit_keywords_match(self):
        for kw in AUDIT_KEYWORDS:
            assert classify_intent(f"please {kw} now") == "audit_production", (
                f"Failed for: {kw}"
            )

    def test_all_posture_keywords_match(self):
        for kw in POSTURE_KEYWORDS:
            assert classify_intent(f"tell me about {kw}") == "posture_check", (
                f"Failed for: {kw}"
            )


class TestRouterNode:
    def test_skips_if_intent_already_set(self):
        state = {"intent": "audit_production", "messages": []}
        result = router_node(state)
        assert result == {}

    def test_classifies_from_last_message(self):
        class FakeMsg:
            content = "run an audit on ampel"

        state = {"intent": "", "messages": [FakeMsg()]}
        result = router_node(state)
        assert result == {"intent": "audit_production"}

    def test_empty_messages_returns_empty(self):
        state = {"intent": "", "messages": []}
        result = router_node(state)
        assert result == {}
