# SPDX-License-Identifier: Apache-2.0

"""Tests for tools.py — SQL guard."""

import pytest

from tools import sql_guard_filter, validate_sql_query


class TestValidateSqlQuery:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM policies",
            "select count(*) from evidence where policy_id = 'abc'",
            "SELECT p.name, e.status FROM policies p JOIN evidence e ON p.id = e.policy_id",
            "WITH cte AS (SELECT 1) SELECT * FROM cte",
        ],
    )
    def test_allows_select_queries(self, sql):
        assert validate_sql_query(sql) is None

    @pytest.mark.parametrize(
        "keyword",
        [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "CREATE", "TRUNCATE", "GRANT", "REVOKE", "EXEC",
        ],
    )
    def test_blocks_write_keywords(self, keyword):
        sql = f"{keyword} INTO policies VALUES ('x')"
        result = validate_sql_query(sql)
        assert result is not None
        assert "Only SELECT" in result

    def test_case_insensitive(self):
        assert validate_sql_query("insert into foo values (1)") is not None
        assert validate_sql_query("Drop Table policies") is not None

    def test_keyword_in_string_literal_still_blocks(self):
        assert validate_sql_query("SELECT 'DELETE' FROM foo") is not None

    def test_empty_query_allowed(self):
        assert validate_sql_query("") is None


class TestSqlGuardFilter:
    def test_blocks_query_database_with_write(self):
        result = sql_guard_filter("query_database", {"query": "DELETE FROM policies"})
        assert result is not None
        assert "error" in result

    def test_blocks_query_evidence_with_write(self):
        result = sql_guard_filter("query_evidence", {"query": "DROP TABLE evidence"})
        assert result is not None
        assert "error" in result

    def test_allows_query_database_with_select(self):
        result = sql_guard_filter("query_database", {"query": "SELECT 1"})
        assert result is None

    def test_allows_query_evidence_with_select(self):
        result = sql_guard_filter("query_evidence", {"query": "SELECT * FROM evidence"})
        assert result is None

    def test_blocks_unknown_tool_with_write_in_args(self):
        """Defense-in-depth: catches write SQL in any string arg."""
        result = sql_guard_filter("some_new_tool", {"payload": "DELETE FROM evidence"})
        assert result is not None
        assert "error" in result

    def test_allows_non_guarded_tool_without_sql(self):
        result = sql_guard_filter("validate_gemara_artifact", {"yaml": "metadata: {}"})
        assert result is None

    def test_checks_sql_arg_key(self):
        result = sql_guard_filter("query_database", {"sql": "INSERT INTO foo VALUES (1)"})
        assert result is not None

    def test_empty_args(self):
        result = sql_guard_filter("query_database", {})
        assert result is None
