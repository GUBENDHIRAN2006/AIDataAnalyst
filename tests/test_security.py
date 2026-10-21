"""
tests/test_security.py - Security-Focused Tests
================================================
Tests that no dangerous code paths exist in the application.
"""

import pytest
from analysis_tools import filter_data, ToolError
import pandas as pd


class TestNoArbitraryExecution:
    """Ensure no code path evaluates or executes untrusted strings."""

    def test_filter_does_not_eval_value(self):
        """
        filter_data must never pass the value argument to eval() or exec().
        A value like '__import__("os").system("whoami")' must be treated as
        a literal string, not executed.
        """
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [90, 80]})
        # This should either raise ToolError or return empty results — never execute
        try:
            result = filter_data(df, "Name", "eq", "__import__('os').system('whoami')")
            assert result["total_matching_rows"] == 0  # No match expected
        except ToolError:
            pass  # Also acceptable

    def test_filter_does_not_exec_python(self):
        """Test that Python code in filter values is not executed."""
        df = pd.DataFrame({"Code": ["exec('print(1)')", "normal"]})
        result = filter_data(df, "Code", "contains", "exec")
        # Should return the row containing "exec" as a string, not execute it
        assert result["total_matching_rows"] == 1

    def test_no_shell_command_tool(self):
        """Verify there is no shell execution tool in the registry."""
        from agent import TOOL_REGISTRY
        for name in TOOL_REGISTRY:
            assert "shell" not in name.lower()
            assert "system" not in name.lower()
            assert "subprocess" not in name.lower()
            assert "os" not in name.lower()

    def test_filter_operator_allowlist(self):
        """Only operators in the allowlist should be accepted."""
        df = pd.DataFrame({"A": [1, 2, 3]})
        dangerous_operators = [
            "exec", "eval", "__import__", "lambda",
            "and", "or", "not", "in", "is",
        ]
        for op in dangerous_operators:
            with pytest.raises(ToolError):
                filter_data(df, "A", op, 1)

    def test_aggregate_operation_allowlist(self):
        """Only whitelisted aggregation operations should be accepted."""
        from analysis_tools import aggregate_data
        df = pd.DataFrame({"Cat": ["A"], "Val": [1]})
        dangerous_ops = ["exec", "eval", "apply", "map", "__builtins__"]
        for op in dangerous_ops:
            with pytest.raises(ToolError):
                aggregate_data(df, "Cat", "Val", op)
