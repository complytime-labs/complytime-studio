# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the validation gate."""

from validation import MAX_VALIDATION_ATTEMPTS, route_after_validation


class TestRouteAfterValidation:
    def test_valid_routes_to_publish(self):
        state = {
            "validation_result": {"valid": True, "errors": []},
            "validation_attempts": 1,
        }
        assert route_after_validation(state) == "publish"

    def test_invalid_with_retries_routes_to_fix(self):
        state = {
            "validation_result": {"valid": False, "errors": ["schema error"]},
            "validation_attempts": 1,
        }
        assert route_after_validation(state) == "fix"

    def test_invalid_at_max_routes_to_halt(self):
        state = {
            "validation_result": {"valid": False, "errors": ["schema error"]},
            "validation_attempts": MAX_VALIDATION_ATTEMPTS,
        }
        assert route_after_validation(state) == "halt"

    def test_invalid_exceeds_max_routes_to_halt(self):
        state = {
            "validation_result": {"valid": False, "errors": ["err"]},
            "validation_attempts": MAX_VALIDATION_ATTEMPTS + 1,
        }
        assert route_after_validation(state) == "halt"

    def test_valid_on_third_attempt_routes_to_publish(self):
        state = {
            "validation_result": {"valid": True, "errors": []},
            "validation_attempts": MAX_VALIDATION_ATTEMPTS,
        }
        assert route_after_validation(state) == "publish"

    def test_empty_state_routes_to_fix(self):
        state = {}
        assert route_after_validation(state) == "fix"
