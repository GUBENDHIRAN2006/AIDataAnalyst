"""
agent.py - AI Agent using Groq's OpenAI-compatible REST API
==========================================================

Security:
  - No arbitrary Python/shell execution — only whitelisted tools called.
  - Column names validated against the current dataset schema.
  - Tool-call count is bounded.
  - Raw data values never sent to LLM.
  - API keys never logged or returned to UI.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

import pandas as pd
import requests

from analysis_tools import (
    ToolError,
    aggregate_data,
    detect_outliers,
    filter_data,
    generate_data_quality_report,
    get_correlation,
    get_dataset_profile,
    get_missing_values,
    get_summary_statistics,
    make_chart_data,
    top_n_analysis,
)
from config import settings
from data_loader import DatasetInfo

logger = logging.getLogger(__name__)

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


# ---------------------------------------------------------------------------
# Demo / Keyword Agent — runs without any API key
# ---------------------------------------------------------------------------

def run_demo_agent(question: str, dataset_info: DatasetInfo) -> AgentResponse:
    """
    Keyword-based agent that runs real analysis tools without calling any LLM.
    Used for demonstration when no valid API key is available.
    """
    response = AgentResponse()
    q = question.lower()
    df = dataset_info.df
    cols = dataset_info.column_names
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    try:
        # --- Profile / overview ---
        if any(w in q for w in ["profile", "overview", "describe", "about", "summary", "what is"]):
            result = get_dataset_profile(df)
            _collect_tool_output("get_dataset_profile", result, response)
            response.answer = (
                f"📊 **Dataset Overview**\n\n"
                f"Your dataset **{dataset_info.filename}** has **{result['dimensions']['rows']:,} rows** "
                f"and **{result['dimensions']['columns']} columns**.\n\n"
                f"- Numeric columns: {', '.join(result['numeric_columns']) or 'None'}\n"
                f"- Categorical columns: {', '.join(result['categorical_columns']) or 'None'}\n"
                f"- Duplicate rows: {result['duplicate_rows']:,}\n"
                f"- Total missing values: {result['missing_value_stats']['total_missing']:,}"
            )
            response.total_tool_calls = 1
            return response

        # --- Missing values ---
        if any(w in q for w in ["missing", "null", "nan", "empty", "incomplete"]):
            result = get_missing_values(df)
            _collect_tool_output("get_missing_values", result, response)
            total = result["total_missing"]
            response.answer = (
                f"🔍 **Missing Values Analysis**\n\n"
                f"Found **{total:,} missing values** across "
                f"**{len(result['columns_with_missing'])} columns** "
                f"({result['total_missing_pct']}% of all cells).\n\n"
                + (
                    "Columns with missing data: " +
                    ", ".join(f"{c} ({result['per_column_count'][c]})" for c in result["columns_with_missing"])
                    if result["columns_with_missing"] else "✅ No missing values found!"
                )
            )
            response.total_tool_calls = 1
            return response

        # --- Outliers ---
        if any(w in q for w in ["outlier", "anomal", "extreme", "unusual"]):
            result = detect_outliers(df)
            _collect_tool_output("detect_outliers", result, response)
            total_outlier_rows = result["total_outlier_rows"]
            response.answer = (
                f"🎯 **Outlier Detection (IQR Method)**\n\n"
                f"Found **{total_outlier_rows:,} rows** with outliers across "
                f"{len(result['columns_analysed'])} numeric columns."
            )
            response.total_tool_calls = 1
            return response

        # --- Correlation ---
        if any(w in q for w in ["correlat", "relation", "heatmap"]):
            if len(numeric_cols) >= 2:
                result = get_correlation(df)
                _collect_tool_output("get_correlation", result, response)
                top = result["top_pairs"]
                if top:
                    top_pair = top[0]
                    response.answer = (
                        f"🔗 **Correlation Analysis (Pearson)**\n\n"
                        f"Strongest correlation: **{top_pair['col1']}** ↔ **{top_pair['col2']}** "
                        f"= {top_pair['correlation']:.3f}\n\n"
                        "See the heatmap below for the full correlation matrix."
                    )
                else:
                    response.answer = "No significant correlations found."
                response.total_tool_calls = 1
            else:
                response.answer = "Need at least 2 numeric columns for correlation analysis."
            return response

        # --- Data quality report ---
        if any(w in q for w in ["quality", "report", "health", "clean"]):
            result = generate_data_quality_report(df)
            response.answer = (
                f"📋 **Data Quality Report**\n\n"
                f"- Quality Score: **{result.get('quality_score', 'N/A')}**\n"
                f"- Rows: {result.get('dimensions', {}).get('rows', dataset_info.row_count):,}\n"
                f"- Missing: {result.get('missing_value_stats', {}).get('total_missing', dataset_info.total_missing):,}\n"
                f"- Duplicates: {result.get('duplicate_rows', dataset_info.duplicate_row_count):,}\n\n"
                + ("\n".join(f"⚠️ {w}" for w in result.get("warnings", [])) or "✅ No major quality issues.")
            )
            response.total_tool_calls = 1
            return response

        # --- Top N analysis ---
        if any(w in q for w in ["top", "best", "highest", "most", "largest", "bottom", "lowest", "worst"]):
            n = 5
            ascending = any(w in q for w in ["bottom", "lowest", "worst", "least", "smallest"])
            if cat_cols and numeric_cols:
                cat_col = cat_cols[0]
                # Try to match a specific column from question
                for c in cat_cols:
                    if c.lower() in q:
                        cat_col = c
                        break
                val_col = numeric_cols[0]
                for c in numeric_cols:
                    if c.lower() in q:
                        val_col = c
                        break
                result = top_n_analysis(df, cat_col, val_col, n=n, ascending=ascending)
                _collect_tool_output("top_n_analysis", result, response)
                label = "Bottom" if ascending else "Top"
                response.answer = (
                    f"{'📉' if ascending else '📈'} **{label} {n} {cat_col} by {result['operation']} of {val_col}**\n\n"
                    + "\n".join(
                        f"{i+1}. **{r[cat_col]}** — {list(r.values())[1]:,.2f}"
                        for i, r in enumerate(result["results"])
                    )
                )
                response.total_tool_calls = 1
                return response

        # --- Chart / plot / visualize ---
        if any(w in q for w in ["chart", "plot", "graph", "visualiz", "bar", "line", "scatter", "histogram"]):
            chart_type = "bar"
            if "line" in q:
                chart_type = "line"
            elif "scatter" in q:
                chart_type = "scatter"
            elif "histogram" in q or "distribut" in q:
                chart_type = "histogram"

            x_col = cat_cols[0] if cat_cols else (numeric_cols[0] if numeric_cols else None)
            y_col = numeric_cols[0] if numeric_cols else None

            # Try to match column names from question
            for c in cols:
                if c.lower() in q:
                    if df[c].dtype == object or df[c].nunique() < 30:
                        x_col = c
                    elif pd.api.types.is_numeric_dtype(df[c]):
                        y_col = c

            if x_col:
                if chart_type == "histogram":
                    result = make_chart_data(df, chart_type="histogram", x_column=x_col if numeric_cols else numeric_cols[0])
                else:
                    result = make_chart_data(df, chart_type=chart_type, x_column=x_col, y_column=y_col)
                _collect_tool_output("make_chart_data", result, response)
                response.answer = (
                    f"📊 Here's a **{chart_type} chart** of "
                    f"**{y_col or x_col}** {'by ' + x_col if y_col else ''}."
                )
                response.total_tool_calls = 1
                return response

        # --- Statistics for a column ---
        if any(w in q for w in ["average", "mean", "median", "std", "statistics", "stat", "min", "max", "total", "sum", "count"]):
            target_col = None
            for c in numeric_cols:
                if c.lower() in q:
                    target_col = c
                    break
            if not target_col and numeric_cols:
                target_col = numeric_cols[0]
            if target_col:
                result = get_summary_statistics(df, target_col)
                response.answer = (
                    f"📊 **Statistics for '{target_col}'**\n\n"
                    f"- Count: {result.get('count', 0):,}\n"
                    f"- Mean: {result.get('mean', 0):,.2f}\n"
                    f"- Median: {result.get('median', 0):,.2f}\n"
                    f"- Std Dev: {result.get('std', 0):,.2f}\n"
                    f"- Min: {result.get('min', 0):,.2f}\n"
                    f"- Max: {result.get('max', 0):,.2f}\n"
                    f"- Missing: {result.get('missing_count', 0):,} ({result.get('missing_pct', 0)}%)"
                )
                response.total_tool_calls = 1
                return response

        # --- Aggregate (total/sum by group) ---
        if any(w in q for w in ["by", "group", "per", "each", "breakdown", "revenue", "sales", "total"]):
            op = "sum"
            if "average" in q or "mean" in q:
                op = "mean"
            elif "count" in q:
                op = "count"
            elif "max" in q:
                op = "max"
            elif "min" in q:
                op = "min"

            if cat_cols and numeric_cols:
                grp_col = cat_cols[0]
                val_col = numeric_cols[0]
                for c in cat_cols:
                    if c.lower() in q:
                        grp_col = c
                        break
                for c in numeric_cols:
                    if c.lower() in q:
                        val_col = c
                        break
                result = aggregate_data(df, grp_col, val_col, op, limit=10)
                _collect_tool_output("aggregate_data", result, response)
                response.answer = (
                    f"📊 **{op.capitalize()} of {val_col} by {grp_col}**\n\n"
                    + "\n".join(
                        f"- {list(r.values())[0]}: **{list(r.values())[1]:,.2f}**"
                        for r in result["results"]
                    )
                )
                response.total_tool_calls = 1
                return response

        # --- Default: profile ---
        result = get_dataset_profile(df)
        _collect_tool_output("get_dataset_profile", result, response)
        response.answer = (
            f"📊 Here's a profile of your dataset **{dataset_info.filename}**:\n\n"
            f"- **{result['dimensions']['rows']:,} rows** × **{result['dimensions']['columns']} columns**\n"
            f"- Numeric columns ({len(result['numeric_columns'])}): {', '.join(result['numeric_columns'][:5])}\n"
            f"- Categorical columns ({len(result['categorical_columns'])}): {', '.join(result['categorical_columns'][:5])}\n"
            f"- Missing values: {result['missing_value_stats']['total_missing']:,}\n"
            f"- Duplicate rows: {result['duplicate_rows']:,}\n\n"
            f"*(Demo mode — configure GROQ_API_KEY for full conversational AI)*"
        )
        response.total_tool_calls = 1

    except Exception as exc:
        response.error = f"Demo analysis error: {exc}"

    return response

# ---------------------------------------------------------------------------
# Tool Registry — only these functions can be called by the LLM
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {
    "get_dataset_profile": get_dataset_profile,
    "get_missing_values": get_missing_values,
    "get_summary_statistics": get_summary_statistics,
    "aggregate_data": aggregate_data,
    "filter_data": filter_data,
    "top_n_analysis": top_n_analysis,
    "make_chart_data": make_chart_data,
    "detect_outliers": detect_outliers,
    "get_correlation": get_correlation,
    "generate_data_quality_report": generate_data_quality_report,
}

# ---------------------------------------------------------------------------
# Tool Definitions — JSON Schema format for OpenAI-compatible tool calling
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = {
    "function_declarations": [
        {
            "name": "get_dataset_profile",
            "description": "Get a comprehensive profile of the loaded dataset: dimensions, column names, data types, missing value stats, duplicate count, numeric and categorical summaries.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_missing_values",
            "description": "Return missing-value counts and percentages for every column.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_summary_statistics",
            "description": "Return descriptive statistics (count, mean, median, std, min, max, quartiles, skewness) for a single numeric column.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string", "description": "Name of the numeric column."}
                },
                "required": ["column"],
            },
        },
        {
            "name": "aggregate_data",
            "description": "Group by one column and aggregate a numeric column. Use for: 'total sales by region', 'average salary by department'. Operation: sum, mean, min, max, count, or median.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by_column": {"type": "string", "description": "Column to group by."},
                    "value_column": {"type": "string", "description": "Numeric column to aggregate."},
                    "operation": {"type": "string", "description": "One of: sum, mean, min, max, count, median."},
                    "limit": {"type": "integer", "description": "Max groups to return (default 20)."},
                },
                "required": ["group_by_column", "value_column", "operation"],
            },
        },
        {
            "name": "filter_data",
            "description": "Filter rows by column value. Operators: eq, ne, gt, lt, gte, lte, is_missing, is_not_missing, contains.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string", "description": "Column to filter on."},
                    "operator": {"type": "string", "description": "eq, ne, gt, lt, gte, lte, is_missing, is_not_missing, contains."},
                    "value": {"type": "string", "description": "Value to compare (omit for is_missing/is_not_missing)."},
                    "limit": {"type": "integer", "description": "Max rows to return (default 100)."},
                },
                "required": ["column", "operator"],
            },
        },
        {
            "name": "top_n_analysis",
            "description": "Return top or bottom N categories by aggregated metric. Use for: 'top 5 products by revenue', 'bottom 3 regions by sales'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_column": {"type": "string"},
                    "value_column": {"type": "string"},
                    "n": {"type": "integer", "description": "Number of results (default 10)."},
                    "ascending": {"type": "boolean", "description": "True for bottom-N, False for top-N."},
                    "operation": {"type": "string", "description": "sum, mean, min, max, count, or median."},
                },
                "required": ["category_column", "value_column"],
            },
        },
        {
            "name": "make_chart_data",
            "description": "Prepare chart data for visualization. Chart types: bar, line, scatter, histogram, heatmap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "description": "bar, line, scatter, histogram, or heatmap."},
                    "x_column": {"type": "string", "description": "Column for X axis."},
                    "y_column": {"type": "string", "description": "Column for Y axis (not needed for histogram)."},
                    "aggregate": {"type": "boolean", "description": "Aggregate y by x?"},
                    "agg_operation": {"type": "string", "description": "sum, mean, min, max, count, or median."},
                    "limit": {"type": "integer", "description": "Max categories to plot (default 50)."},
                },
                "required": ["chart_type", "x_column"],
            },
        },
        {
            "name": "detect_outliers",
            "description": "Detect outliers in numeric columns using the IQR method. Outliers are reported, never removed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preview_limit": {"type": "integer", "description": "Max outlier rows to return (default 20)."},
                },
            },
        },
        {
            "name": "get_correlation",
            "description": "Compute correlation matrix for numeric columns. Method: pearson, spearman, or kendall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "pearson, spearman, or kendall."},
                },
            },
        },
        {
            "name": "generate_data_quality_report",
            "description": "Generate a comprehensive data quality report: missing values, duplicates, outliers, warnings, and a quality score.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]
}


# ---------------------------------------------------------------------------
# Agent Response
# ---------------------------------------------------------------------------

class AgentResponse:
    """Structured response returned from the agent to the UI."""

    def __init__(self):
        self.answer: str = ""
        self.tool_calls_made: list[dict] = []
        self.tables: list[dict] = []
        self.charts: list[dict] = []
        self.warnings: list[str] = []
        self.error: Optional[str] = None
        self.total_tool_calls: int = 0
        self.latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "tool_calls_made": self.tool_calls_made,
            "tables": self.tables,
            "charts": self.charts,
            "warnings": self.warnings,
            "error": self.error,
            "total_tool_calls": self.total_tool_calls,
            "latency_ms": self.latency_ms,
        }


# ---------------------------------------------------------------------------
# Argument Validation
# ---------------------------------------------------------------------------

def _validate_tool_arguments(
    tool_name: str,
    arguments: dict,
    dataset_info: DatasetInfo,
) -> None:
    if tool_name not in TOOL_REGISTRY:
        raise ToolError(
            f"Unknown tool {tool_name!r}. "
            f"Available: {sorted(TOOL_REGISTRY.keys())}"
        )

    column_args = [
        "column", "group_by_column", "value_column",
        "category_column", "x_column", "y_column",
    ]
    available_columns = set(dataset_info.column_names)

    for arg_name in column_args:
        col_val = arguments.get(arg_name)
        if col_val and isinstance(col_val, str):
            if col_val not in available_columns:
                raise ToolError(
                    f"Column {col_val!r} not found. "
                    f"Available columns: {sorted(available_columns)}"
                )

    for int_arg in ("n", "limit", "preview_limit"):
        val = arguments.get(int_arg)
        if val is not None:
            try:
                if int(val) < 1:
                    raise ToolError(f"Argument {int_arg!r} must be >= 1.")
            except (TypeError, ValueError):
                raise ToolError(f"Argument {int_arg!r} must be an integer.")


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

def _execute_tool(tool_name: str, arguments: dict, df) -> tuple[Any, Optional[str]]:
    func = TOOL_REGISTRY[tool_name]
    try:
        result = func(df, **arguments)
        return result, None
    except ToolError as exc:
        return None, str(exc)
    except Exception as exc:
        logger.exception("Unexpected error in tool %r", tool_name)
        return None, f"Tool error: {exc}"


# ---------------------------------------------------------------------------
# Groq REST API helpers
# ---------------------------------------------------------------------------

def _call_groq_rest(
    api_key: str,
    model: str,
    system_instruction: str,
    messages: list[dict],
    with_tools: bool = True,
) -> dict:
    """Call the Groq Chat Completions API and return its parsed JSON response."""
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system_instruction}, *messages],
        "temperature": 0.1,
        "max_tokens": settings.groq_max_tokens,
    }

    if with_tools:
        body["tools"] = [
            {"type": "function", "function": definition}
            for definition in TOOL_DEFINITIONS["function_declarations"]
        ]

    response = requests.post(
        GROQ_CHAT_COMPLETIONS_URL,
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=settings.api_timeout_seconds,
    )

    if response.status_code != 200:
        try:
            error_data = response.json().get("error", {})
            error_msg = error_data.get("message", response.text)
        except (ValueError, AttributeError):
            error_msg = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {error_msg}")

    return response.json()


def _build_system_prompt(dataset_info: DatasetInfo) -> str:
    schema = dataset_info.schema_summary()
    return f"""You are a professional data analyst AI assistant powered by Groq.

Dataset schema (NEVER fabricate data — only use tool results):
- Filename: {schema['filename']} ({schema.get('file_format', 'CSV')})
- Rows: {schema['rows']:,}
- Columns: {schema['columns']}
- Column names: {schema['column_names']}
- Data types: {json.dumps(schema['dtypes'], indent=2)}
- Missing counts: {json.dumps(schema['missing_counts'])}
- Duplicate rows: {schema['duplicate_rows']}

Rules:
1. Always call a tool before answering quantitative questions.
2. Never fabricate numbers — base your answer ONLY on tool results.
3. If a column doesn't exist, say so and list available columns.
4. Format numbers with commas for readability (e.g., 1,234,567).
5. Be concise but informative in your final answer.
"""


def _is_chart_request(question: str) -> bool:
    return bool(
        re.search(
            r"\b(chart|plot|graph|visuali[sz](?:e|ation)|histogram|heatmap)\b",
            question,
            flags=re.IGNORECASE,
        )
    )


def _make_requested_chart(question: str, df: pd.DataFrame) -> dict:
    lowered_question = question.casefold()
    columns = [str(column) for column in df.columns]
    if re.search(r"\b(pie|donut|doughnut|area)\b", lowered_question):
        raise ToolError(
            "Supported charts are bar, line, scatter, histogram, and heatmap."
        )
    numeric_columns = [
        str(column)
        for column in df.select_dtypes(include="number").columns
    ]
    category_columns = [
        str(column)
        for column in df.select_dtypes(exclude="number").columns
    ]

    def mentioned(candidates: list[str]) -> str | None:
        for column in candidates:
            if re.search(
                rf"(?<!\w){re.escape(column.casefold())}(?!\w)",
                lowered_question,
            ):
                return column
        return None

    if any(term in lowered_question for term in ("heatmap", "correlation matrix", "correlation chart")):
        chart = make_chart_data(df, "heatmap", columns[0])
        chart["title"] = "Correlation heatmap"
        return chart

    mentioned_numeric = mentioned(numeric_columns)
    if "histogram" in lowered_question or "distribution" in lowered_question:
        if not numeric_columns:
            raise ToolError("A histogram needs at least one numeric column.")
        x_column = mentioned_numeric or numeric_columns[0]
        chart = make_chart_data(df, "histogram", x_column)
        chart["title"] = f"Distribution of {x_column}"
        return chart

    if "scatter" in lowered_question:
        x_column = mentioned_numeric
        y_candidates = [column for column in numeric_columns if column != x_column]
        y_column = mentioned(y_candidates) or (y_candidates[0] if y_candidates else None)
        if not x_column and numeric_columns:
            x_column = numeric_columns[0]
            y_candidates = [column for column in numeric_columns if column != x_column]
            y_column = mentioned(y_candidates) or (y_candidates[0] if y_candidates else None)
        if not x_column or not y_column:
            raise ToolError("A scatter chart needs two numeric columns.")
        chart = make_chart_data(
            df,
            "scatter",
            x_column,
            y_column,
            aggregate=False,
        )
        chart["title"] = f"{y_column} vs {x_column}"
        return chart

    requested_line = any(
        term in lowered_question
        for term in ("line chart", "line graph", "trend", "over time")
    )
    if not category_columns and len(numeric_columns) < 2:
        if not numeric_columns:
            raise ToolError("No numeric columns are available to chart.")
        x_column = numeric_columns[0]
        chart = make_chart_data(df, "histogram", x_column)
        chart["title"] = f"Distribution of {x_column}"
        return chart

    x_candidates = category_columns or numeric_columns
    x_column = mentioned(x_candidates) or x_candidates[0]
    y_candidates = [column for column in numeric_columns if column != x_column]
    y_column = mentioned(y_candidates) or (y_candidates[0] if y_candidates else None)
    if not y_column:
        y_column = x_column
        operation = "count"
    else:
        operation = "sum"
    chart_type = "line" if requested_line else "bar"
    chart = make_chart_data(
        df,
        chart_type,
        x_column,
        y_column,
        aggregate=True,
        agg_operation=operation,
    )
    chart["title"] = (
        f"{operation.capitalize()} of {y_column} by {x_column}"
        if operation != "count"
        else f"Row count by {x_column}"
    )
    return chart


# ---------------------------------------------------------------------------
# Main Agent Function
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    dataset_info: DatasetInfo,
    conversation_history: Optional[list[dict]] = None,
) -> AgentResponse:
    """
    Run the Groq AI agent on a natural-language question about the dataset.
    Falls back to keyword/demo mode if no valid API key is configured.
    """
    response = AgentResponse()
    start_time = time.time()

    question = question.strip()
    if not question:
        response.error = "Please enter a question."
        return response

    if _is_chart_request(question):
        try:
            chart = _make_requested_chart(question, dataset_info.df)
        except ToolError as exc:
            response.error = f"Could not create the requested chart: {exc}"
            return response
        response.charts.append(chart)
        response.answer = "Generated a chart directly from the loaded dataset."
        response.tool_calls_made.append({
            "name": "make_chart_data",
            "arguments": {"question": question},
            "success": True,
            "error": None,
        })
        response.total_tool_calls = 1
        response.latency_ms = round((time.time() - start_time) * 1000, 1)
        return response

    # No API key → use demo mode immediately
    if not settings.has_groq_key:
        demo_resp = run_demo_agent(question, dataset_info)
        demo_resp.latency_ms = round((time.time() - start_time) * 1000, 1)
        demo_resp.warnings.append(
            "Running in Demo Mode (no API key set). "
            "Add GROQ_API_KEY to .env for full AI chat."
        )
        return demo_resp

    try:
        settings.validate_ai_configuration()
    except RuntimeError as exc:
        response.error = str(exc)
        return response

    api_key = settings.groq_api_key
    system_prompt = _build_system_prompt(dataset_info)
    df = dataset_info.df

    messages: list[dict] = []

    # Add prior conversation history
    if conversation_history:
        for msg in conversation_history[-6:]:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user" and isinstance(content, str):
                messages.append({"role": "user", "content": content})
            elif role == "assistant" and isinstance(content, str):
                messages.append({"role": "assistant", "content": content})

    # Add current question
    messages.append({"role": "user", "content": question})

    tool_call_count = 0
    model = settings.groq_model

    try:
        while tool_call_count < settings.max_tool_calls:
            logger.info("Calling Groq REST (iteration %d, model=%s)", tool_call_count + 1, model)

            resp_json = _call_groq_rest(
                api_key=api_key,
                model=model,
                system_instruction=system_prompt,
                messages=messages,
            )

            choices = resp_json.get("choices", [])
            if not choices:
                response.error = "Groq returned no response. Please try again."
                break

            assistant_message = choices[0].get("message", {})
            tool_calls = assistant_message.get("tool_calls", [])
            messages.append(assistant_message)

            if not tool_calls:
                response.answer = assistant_message.get("content") or ""
                if not response.answer:
                    response.error = (
                        "The AI returned no text answer. Any calculated tables or "
                        "charts are shown below; please try rephrasing your question."
                    )
                break

            for tool_call in tool_calls:
                if tool_call_count >= settings.max_tool_calls:
                    break
                tool_call_count += 1
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError):
                    arguments = {}
                    error_msg = "Tool arguments were not valid JSON."
                    response.warnings.append(f"{tool_name}: {error_msg}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps({"error": error_msg}),
                    })
                    continue
                if not isinstance(arguments, dict):
                    arguments = {}
                    error_msg = "Tool arguments must be a JSON object."
                    response.warnings.append(f"{tool_name}: {error_msg}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps({"error": error_msg}),
                    })
                    continue

                logger.info("Tool call: %s(%s)", tool_name, list(arguments.keys()))

                # Validate
                try:
                    _validate_tool_arguments(tool_name, arguments, dataset_info)
                except ToolError as exc:
                    error_msg = str(exc)
                    response.warnings.append(f"Validation: {error_msg}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps({"error": error_msg}),
                    })
                    continue

                # Execute
                tool_result, tool_error = _execute_tool(tool_name, arguments, df)
                response.tool_calls_made.append({
                    "name": tool_name,
                    "arguments": arguments,
                    "success": tool_error is None,
                    "error": tool_error,
                })

                if tool_error:
                    response.warnings.append(f"{tool_name}: {tool_error}")
                    result_content = {"error": tool_error}
                else:
                    _collect_tool_output(tool_name, tool_result, response)
                    result_str = json.dumps(tool_result, default=str)
                    if len(result_str) > 20_000:
                        result_str = result_str[:20_000] + "... [truncated]"
                        response.warnings.append(f"Result for {tool_name!r} was truncated.")
                    result_content = json.loads(result_str)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(result_content),
                })

        else:
            response.answer = (
                f"Reached the maximum tool call limit ({settings.max_tool_calls}). "
                "Partial results are shown above."
            )
            response.warnings.append(f"Tool call limit reached ({settings.max_tool_calls}).")

    except requests.Timeout:
        response.error = "⏳ Request timed out. Please try again."
    except RuntimeError as exc:
        err_str = str(exc).replace(api_key, "[redacted]")
        logger.error("Groq API error: %s", err_str)
        lowered = err_str.lower()
        if "not_found" in lowered or "model" in lowered and "not available" in lowered:
            response.error = (
                f"❌ Model '{model}' is not available for your account. "
                "Try changing GROQ_MODEL in your .env file."
            )
        elif "permission_denied" in lowered or "denied access" in lowered:
            response.error = (
                "❌ Your Groq API key does not have permission to use this model. "
                "Check your Groq account and model access."
            )
        elif "api_key_invalid" in lowered or "unauthenticated" in lowered or "401" in lowered:
            response.error = (
                "❌ Invalid API key. Check GROQ_API_KEY in your .env file. "
                "Get a key at: https://console.groq.com/keys"
            )
        elif "429" in lowered or "rate limit" in lowered or "tokens per minute" in lowered:
            response.error = (
                "❌ Groq rate limit reached: the tokens-per-minute quota counts prompt and "
                "response tokens and is shared by all apps using your Groq organization, so "
                "it can happen even when you are not actively using this app. Wait for "
                "the quota window to reset, reduce dataset size or chat-history length, or "
                "use a model/account with more TPM capacity. GROQ_MAX_TOKENS only caps the "
                "response; changing it does not increase your organization's quota."
            )
        else:
            response.error = f"❌ Groq API error: {err_str[:200]}"
    except Exception as exc:
        logger.exception("Unexpected agent error")
        response.error = f"❌ Unexpected error ({type(exc).__name__}): {exc}"

    response.total_tool_calls = tool_call_count
    response.latency_ms = round((time.time() - start_time) * 1000, 1)
    logger.info("Agent done: %d tool calls in %.0f ms", tool_call_count, response.latency_ms)
    return response


# ---------------------------------------------------------------------------
# Output Collection
# ---------------------------------------------------------------------------

def _collect_tool_output(tool_name: str, tool_result: Any, response: AgentResponse) -> None:
    if not isinstance(tool_result, dict):
        return

    if tool_name == "make_chart_data":
        response.charts.append(tool_result)
        return

    if tool_name == "get_dataset_profile":
        numeric_summary = tool_result.get("numeric_summary", {})
        if numeric_summary:
            rows = [{"Column": col, **stats} for col, stats in numeric_summary.items()]
            response.tables.append({"title": "Numeric Column Summary", "data": rows})
        return

    if tool_name == "aggregate_data":
        results = tool_result.get("results", [])
        if results:
            response.tables.append({
                "title": (
                    f"{tool_result.get('operation', '').capitalize()} of "
                    f"{tool_result.get('value_column', '')} "
                    f"by {tool_result.get('group_by_column', '')}"
                ),
                "data": results,
            })
        return

    if tool_name == "top_n_analysis":
        results = tool_result.get("results", [])
        if results:
            response.tables.append({
                "title": (
                    f"Top {tool_result.get('n', '')} {tool_result.get('category_column', '')} "
                    f"by {tool_result.get('operation', '')} of {tool_result.get('value_column', '')}"
                ),
                "data": results,
            })
        return

    if tool_name == "filter_data":
        results = tool_result.get("results", [])
        if results:
            response.tables.append({
                "title": (
                    f"Filter: {tool_result.get('column', '')} "
                    f"{tool_result.get('operator', '')} '{tool_result.get('value', '')}'"
                ),
                "data": results,
            })
        return

    if tool_name == "get_missing_values":
        per_col = tool_result.get("per_column_count", {})
        per_pct = tool_result.get("per_column_pct", {})
        rows = [
            {"Column": col, "Missing Count": count, "Missing %": per_pct.get(col, 0)}
            for col, count in per_col.items()
            if count > 0
        ]
        if rows:
            response.tables.append({"title": "Missing Values by Column", "data": rows})
        return

    if tool_name == "get_correlation":
        pairs = tool_result.get("top_pairs", [])
        if pairs:
            response.tables.append({
                "title": f"Top Correlated Pairs ({tool_result.get('method', 'pearson')})",
                "data": pairs,
            })
        corr_matrix = tool_result.get("correlation_matrix")
        if corr_matrix:
            response.charts.append({
                "chart_type": "heatmap",
                "columns": tool_result.get("columns", []),
                "correlation_matrix": corr_matrix,
                "method": tool_result.get("method", "pearson"),
            })
        return

    if tool_name == "detect_outliers":
        per_col = tool_result.get("per_column_details", {})
        if per_col:
            rows = [
                {
                    "Column": col,
                    "Outlier Count": detail.get("count", 0),
                    "Lower Fence": detail.get("lower_fence"),
                    "Upper Fence": detail.get("upper_fence"),
                }
                for col, detail in per_col.items()
            ]
            response.tables.append({
                "title": "Outlier Detection Results (IQR Method)",
                "data": rows,
            })
        return
