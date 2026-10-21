"""
chart_builder.py - Plotly Chart Generation
============================================
Builds interactive Plotly charts from validated chart data produced by
analysis_tools.make_chart_data().

Rules:
- Charts are ALWAYS built from Python-computed data, never from raw LLM text.
- Chart configs are validated before any Plotly call.
- No arbitrary column values are rendered as HTML or JavaScript.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from config import settings

logger = logging.getLogger(__name__)

# Set a professional default template
pio.templates.default = "plotly_dark"

# Colour palette consistent with the app theme
BRAND_COLORS = [
    "#6366f1",  # indigo
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#14b8a6",  # teal
    "#f59e0b",  # amber
    "#10b981",  # emerald
    "#3b82f6",  # blue
    "#ef4444",  # red
]


class ChartBuilderError(ValueError):
    """Raised when a chart cannot be generated from the supplied data."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_parallel_lists(x_vals: list, y_vals: list, chart_type: str) -> None:
    if len(x_vals) != len(y_vals):
        raise ChartBuilderError(
            f"x and y value lists have different lengths ({len(x_vals)} vs {len(y_vals)}) "
            f"for chart type {chart_type!r}."
        )
    if len(x_vals) == 0:
        raise ChartBuilderError(f"No data points to plot for chart type {chart_type!r}.")


def _apply_common_layout(fig: go.Figure, title: str, x_label: str, y_label: str) -> go.Figure:
    """Apply consistent professional styling to any Plotly figure."""
    fig.update_layout(
        title={
            "text": title,
            "font": {"size": 18, "color": "#e2e8f0"},
            "x": 0.01,
        },
        paper_bgcolor="#0f172a",
        plot_bgcolor="#1e293b",
        font={"color": "#94a3b8", "family": "Inter, sans-serif"},
        xaxis={
            "title": x_label,
            "gridcolor": "#334155",
            "zerolinecolor": "#334155",
        },
        yaxis={
            "title": y_label,
            "gridcolor": "#334155",
            "zerolinecolor": "#334155",
        },
        margin={"l": 60, "r": 30, "t": 60, "b": 60},
        legend={"bgcolor": "rgba(0,0,0,0)", "bordercolor": "#334155"},
        hoverlabel={"bgcolor": "#1e293b", "bordercolor": "#6366f1"},
    )
    return fig


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def build_bar_chart(
    chart_data: dict[str, Any],
    title: Optional[str] = None,
) -> go.Figure:
    """Build a bar chart from aggregated chart data."""
    x_vals = chart_data.get("x_values", [])
    y_vals = chart_data.get("y_values", [])
    x_col = chart_data.get("x_column", "Category")
    y_col = chart_data.get("y_column", "Value")

    _validate_parallel_lists(x_vals, y_vals, "bar")

    chart_title = title or f"{y_col} by {x_col}"
    agg_op = chart_data.get("agg_operation", "")
    if agg_op:
        chart_title = f"{agg_op.capitalize()} of {y_col} by {x_col}"

    fig = go.Figure(
        data=[
            go.Bar(
                x=x_vals,
                y=y_vals,
                marker_color=BRAND_COLORS[0],
                marker_line_color=BRAND_COLORS[1],
                marker_line_width=1,
                hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
            )
        ]
    )

    _apply_common_layout(fig, chart_title, x_col, y_col)
    return fig


def build_line_chart(
    chart_data: dict[str, Any],
    title: Optional[str] = None,
) -> go.Figure:
    """Build a line chart — typically used for time-series data."""
    x_vals = chart_data.get("x_values", [])
    y_vals = chart_data.get("y_values", [])
    x_col = chart_data.get("x_column", "X")
    y_col = chart_data.get("y_column", "Y")

    _validate_parallel_lists(x_vals, y_vals, "line")

    chart_title = title or f"{y_col} over {x_col}"

    fig = go.Figure(
        data=[
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="lines+markers",
                line={"color": BRAND_COLORS[0], "width": 2},
                marker={"color": BRAND_COLORS[1], "size": 6},
                hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
            )
        ]
    )

    _apply_common_layout(fig, chart_title, x_col, y_col)
    return fig


def build_scatter_chart(
    chart_data: dict[str, Any],
    title: Optional[str] = None,
) -> go.Figure:
    """Build a scatter plot."""
    x_vals = chart_data.get("x_values", [])
    y_vals = chart_data.get("y_values", [])
    x_col = chart_data.get("x_column", "X")
    y_col = chart_data.get("y_column", "Y")

    _validate_parallel_lists(x_vals, y_vals, "scatter")

    chart_title = title or f"{x_col} vs {y_col}"

    fig = go.Figure(
        data=[
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                marker={
                    "color": BRAND_COLORS[0],
                    "size": 8,
                    "opacity": 0.7,
                    "line": {"color": BRAND_COLORS[1], "width": 1},
                },
                hovertemplate=(
                    f"{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>"
                ),
            )
        ]
    )

    _apply_common_layout(fig, chart_title, x_col, y_col)
    return fig


def build_histogram(
    chart_data: dict[str, Any],
    title: Optional[str] = None,
    nbins: int = 30,
) -> go.Figure:
    """Build a histogram from raw numeric values."""
    values = chart_data.get("values", [])
    x_col = chart_data.get("x_column", "Value")

    if not values:
        raise ChartBuilderError("No values provided for histogram.")

    chart_title = title or f"Distribution of {x_col}"

    fig = go.Figure(
        data=[
            go.Histogram(
                x=values,
                nbinsx=nbins,
                marker_color=BRAND_COLORS[0],
                marker_line_color=BRAND_COLORS[1],
                marker_line_width=1,
                opacity=0.85,
                hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>",
            )
        ]
    )

    _apply_common_layout(fig, chart_title, x_col, "Count")
    return fig


def build_heatmap(
    chart_data: dict[str, Any],
    title: Optional[str] = None,
) -> go.Figure:
    """Build a correlation heatmap from correlation matrix data."""
    columns = chart_data.get("columns", [])
    corr_matrix = chart_data.get("correlation_matrix", {})
    method = chart_data.get("method", "pearson")

    if not columns or not corr_matrix:
        raise ChartBuilderError("Insufficient data for heatmap.")

    z_vals = [[corr_matrix[c].get(r) for c in columns] for r in columns]

    chart_title = title or f"Correlation Heatmap ({method.capitalize()})"

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z_vals,
                x=columns,
                y=columns,
                colorscale="RdBu",
                zmid=0,
                zmin=-1,
                zmax=1,
                text=[[f"{v:.2f}" if v is not None else "N/A" for v in row] for row in z_vals],
                texttemplate="%{text}",
                textfont={"size": 10},
                hovertemplate="%{y} ↔ %{x}<br>Correlation: %{z:.3f}<extra></extra>",
            )
        ]
    )

    fig.update_layout(
        title={"text": chart_title, "font": {"size": 18, "color": "#e2e8f0"}, "x": 0.01},
        paper_bgcolor="#0f172a",
        plot_bgcolor="#1e293b",
        font={"color": "#94a3b8", "family": "Inter, sans-serif"},
        margin={"l": 100, "r": 30, "t": 60, "b": 100},
    )
    return fig


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

CHART_BUILDERS = {
    "bar": build_bar_chart,
    "line": build_line_chart,
    "scatter": build_scatter_chart,
    "histogram": build_histogram,
    "heatmap": build_heatmap,
}


def build_chart(chart_data: dict[str, Any], title: Optional[str] = None) -> go.Figure:
    """
    Dispatch to the correct chart builder based on chart_type in chart_data.

    Parameters
    ----------
    chart_data : dict
        Output from analysis_tools.make_chart_data().
    title : str, optional
        Override the chart title.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    chart_type = chart_data.get("chart_type", "").lower()

    builder = CHART_BUILDERS.get(chart_type)
    if builder is None:
        raise ChartBuilderError(
            f"No chart builder registered for type {chart_type!r}.  "
            f"Supported types: {sorted(CHART_BUILDERS.keys())}"
        )

    try:
        return builder(chart_data, title=title)
    except ChartBuilderError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chart building failed for type %r", chart_type)
        raise ChartBuilderError(
            f"Failed to build {chart_type} chart: {exc}"
        ) from exc
