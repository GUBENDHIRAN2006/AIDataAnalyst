"""Tests for the Groq-backed analysis agent."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import agent
from config import Settings
from agent import (
    TOOL_REGISTRY,
    _call_groq_rest,
    _execute_tool,
    _validate_tool_arguments,
    run_agent,
)
from analysis_tools import ToolError
from data_loader import DatasetInfo


@pytest.fixture
def dataset_info(simple_df):
    return DatasetInfo(
        df=simple_df,
        filename="test.csv",
        file_format="CSV",
        row_count=len(simple_df),
        column_count=len(simple_df.columns),
        column_names=list(simple_df.columns),
        dtypes={column: str(simple_df[column].dtype) for column in simple_df.columns},
        missing_counts={column: int(simple_df[column].isna().sum()) for column in simple_df.columns},
        duplicate_row_count=int(simple_df.duplicated().sum()),
        file_size_bytes=1024,
        encoding_detected="utf-8",
    )


def _settings(**overrides):
    values = {
        "groq_api_key": "test-groq-key",
        "has_groq_key": True,
        "groq_model": "openai/gpt-oss-120b",
        "groq_max_tokens": 1024,
        "api_timeout_seconds": 60,
        "max_tool_calls": 10,
        "max_result_rows": 1000,
        "max_chart_categories": 50,
        "validate_ai_configuration": lambda: None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _api_response(payload, status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload
    return response


def _assistant_response(content=None, tool_calls=None):
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls or [],
            }
        }]
    }


def _tool_call(name, arguments, call_id="call-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class TestToolValidation:
    def test_expected_tools_are_registered(self):
        expected = {
            "get_dataset_profile",
            "get_missing_values",
            "get_summary_statistics",
            "aggregate_data",
            "filter_data",
            "top_n_analysis",
            "make_chart_data",
            "detect_outliers",
            "get_correlation",
            "generate_data_quality_report",
        }
        assert expected.issubset(TOOL_REGISTRY)
        assert all("exec" not in name.lower() for name in TOOL_REGISTRY)

    def test_unknown_tool_is_rejected(self, dataset_info):
        with pytest.raises(ToolError, match="Unknown tool"):
            _validate_tool_arguments("run_shell_command", {}, dataset_info)

    def test_invalid_column_is_rejected(self, dataset_info):
        with pytest.raises(ToolError, match="not found"):
            _validate_tool_arguments(
                "get_summary_statistics",
                {"column": "NotAColumn"},
                dataset_info,
            )

    def test_validated_tool_executes(self, simple_df):
        result, error = _execute_tool("get_missing_values", {}, simple_df)
        assert error is None
        assert "total_missing" in result


class TestGroqConfiguration:
    def test_groq_key_is_read_and_model_defaults_to_supported_model(self):
        settings = Settings(_env_file=None, groq_api_key="test-groq-key")
        assert settings.has_groq_key
        assert settings.groq_model == "openai/gpt-oss-120b"
        assert settings.groq_max_tokens == 1024
        assert settings.safe_summary()["api_key_configured"]

    def test_missing_groq_key_is_reported(self):
        settings = Settings(_env_file=None)
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            settings.validate_ai_configuration()


class TestGroqRequest:
    def test_request_uses_bearer_auth_and_openai_tool_schema(self):
        mock_settings = _settings()
        response = _api_response(_assistant_response(content="Hello"))

        with patch.object(agent, "settings", mock_settings), \
             patch("agent.requests.post", return_value=response) as post:
            result = _call_groq_rest(
                "test-groq-key",
                "openai/gpt-oss-120b",
                "system prompt",
                [{"role": "user", "content": "hello"}],
            )

        assert result["choices"][0]["message"]["content"] == "Hello"
        args, kwargs = post.call_args
        assert args[0] == agent.GROQ_CHAT_COMPLETIONS_URL
        assert kwargs["headers"]["Authorization"] == f"Bearer {'test' + '-groq-key'}"
        assert kwargs["json"]["model"] == "openai/gpt-oss-120b"
        assert kwargs["json"]["messages"][0] == {
            "role": "system",
            "content": "system prompt",
        }
        assert kwargs["json"]["max_tokens"] == mock_settings.groq_max_tokens
        assert kwargs["json"]["tools"][0]["type"] == "function"

    def test_api_error_is_reported_without_suppressing_it(self):
        mock_settings = _settings()
        response = _api_response({"error": {"message": "invalid key"}}, 401)

        with patch.object(agent, "settings", mock_settings), \
             patch("agent.requests.post", return_value=response):
            with pytest.raises(RuntimeError, match="HTTP 401: invalid key"):
                _call_groq_rest("test-groq-key", "openai/gpt-oss-120b", "system", [])


class TestRunAgent:
    def test_empty_question_returns_error(self, dataset_info):
        with patch.object(agent, "settings", _settings()):
            result = run_agent("", dataset_info)
        assert result.error == "Please enter a question."

    def test_explicit_chart_request_is_generated_without_groq(self, dataset_info):
        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post") as post:
            result = run_agent("Create a bar chart of Revenue by Product.", dataset_info)

        post.assert_not_called()
        assert result.error is None
        assert result.charts[0]["chart_type"] == "bar"
        assert result.charts[0]["x_column"] == "Product"
        assert result.charts[0]["y_column"] == "Revenue"
        assert result.charts[0]["title"] == "Sum of Revenue by Product"

    def test_histogram_request_uses_the_requested_numeric_column(self, dataset_info):
        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post") as post:
            result = run_agent("Show a histogram of Revenue.", dataset_info)

        post.assert_not_called()
        assert result.error is None
        assert result.charts[0]["chart_type"] == "histogram"
        assert result.charts[0]["x_column"] == "Revenue"

    def test_without_key_uses_demo_mode(self, dataset_info):
        mock_settings = _settings(groq_api_key="", has_groq_key=False)
        with patch.object(agent, "settings", mock_settings), \
             patch("agent.requests.post") as post:
            result = run_agent("show the dataset profile", dataset_info)
        post.assert_not_called()
        assert result.error is None
        assert any("GROQ_API_KEY" in warning for warning in result.warnings)

    def test_tool_call_then_final_answer(self, dataset_info):
        first = _api_response(_assistant_response(
            tool_calls=[_tool_call("get_missing_values", {})]
        ))
        second = _api_response(_assistant_response(content="There are no missing values."))
        mock_settings = _settings()

        with patch.object(agent, "settings", mock_settings), \
             patch("agent.requests.post", side_effect=[first, second]) as post:
            result = run_agent("Are there missing values?", dataset_info)

        assert result.error is None
        assert result.answer == "There are no missing values."
        assert result.total_tool_calls == 1
        assert result.tool_calls_made[0]["name"] == "get_missing_values"
        sent_messages = post.call_args_list[1].kwargs["json"]["messages"]
        assert sent_messages[-1]["role"] == "tool"
        assert sent_messages[-1]["tool_call_id"] == "call-1"

    def test_tool_call_history_is_used_for_follow_up(self, dataset_info):
        response = _api_response(_assistant_response(content="The answer is 12."))

        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post", return_value=response) as post:
            result = run_agent(
                "What about Finland?",
                dataset_info,
                conversation_history=[
                    {"role": "user", "content": "Show total sales."},
                    {"role": "assistant", "content": "Total sales are 100."},
                ],
            )

        assert result.answer == "The answer is 12."
        sent_messages = post.call_args.kwargs["json"]["messages"]
        assert sent_messages[1:3] == [
            {"role": "user", "content": "Show total sales."},
            {"role": "assistant", "content": "Total sales are 100."},
        ]
        assert sent_messages[-1] == {
            "role": "user",
            "content": "What about Finland?",
        }

    def test_empty_final_response_is_not_reported_as_success(self, dataset_info):
        response = _api_response(_assistant_response(content=""))

        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post", return_value=response):
            result = run_agent("Summarize the dataset.", dataset_info)

        assert result.answer == ""
        assert result.error is not None
        assert "no text answer" in result.error.lower()

    def test_tool_calls_never_exceed_configured_limit(self, dataset_info):
        response = _api_response(_assistant_response(
            tool_calls=[
                _tool_call("get_missing_values", {}, "call-1"),
                _tool_call("get_missing_values", {}, "call-2"),
                _tool_call("get_missing_values", {}, "call-3"),
            ]
        ))
        mock_settings = _settings(max_tool_calls=2)

        with patch.object(agent, "settings", mock_settings), \
             patch("agent.requests.post", return_value=response) as post:
            result = run_agent("Check missing values", dataset_info)

        assert result.total_tool_calls == 2
        assert len(result.tool_calls_made) == 2
        assert any("limit" in warning.lower() for warning in result.warnings)
        post.assert_called_once()

    def test_unknown_tool_is_not_executed(self, dataset_info):
        first = _api_response(_assistant_response(
            tool_calls=[_tool_call("run_shell_command", {"cmd": "whoami"})]
        ))
        second = _api_response(_assistant_response(content="I cannot run commands."))

        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post", side_effect=[first, second]):
            result = run_agent("Run a command", dataset_info)

        assert result.answer == "I cannot run commands."
        assert any("Unknown tool" in warning for warning in result.warnings)
        assert not result.tool_calls_made

    def test_api_key_is_not_in_response_on_auth_failure(self, dataset_info):
        secret = "secret-groq-key"
        response = _api_response(
            {"error": {"message": f"unauthenticated: {secret}"}},
            401,
        )

        with patch.object(agent, "settings", _settings(groq_api_key=secret)), \
             patch("agent.requests.post", return_value=response):
            result = run_agent("How many rows?", dataset_info)

        assert result.error is not None
        assert secret not in result.error

    def test_tpm_rate_limit_has_actionable_message(self, dataset_info):
        response = _api_response(
            {"error": {"message": "Rate limit reached for tokens per minute"}},
            429,
        )

        with patch.object(agent, "settings", _settings()), \
             patch("agent.requests.post", return_value=response):
            result = run_agent("How many rows?", dataset_info)

        assert result.error is not None
        assert "rate limit reached" in result.error.lower()
        assert "shared by all apps" in result.error.lower()
        assert "quota window to reset" in result.error.lower()
        assert "does not increase" in result.error.lower()
