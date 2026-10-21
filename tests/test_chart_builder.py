"""
tests/test_chart_builder.py - Chart Generation Tests
=====================================================
Tests for chart_builder.py using pre-built chart_data dicts.
No LLM calls required.
"""

import pytest
import plotly.graph_objects as go

from chart_builder import (
    ChartBuilderError,
    build_chart,
    build_bar_chart,
    build_line_chart,
    build_scatter_chart,
    build_histogram,
    build_heatmap,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bar_data():
    return {
        "chart_type": "bar",
        "x_column": "Product",
        "y_column": "Revenue",
        "x_values": ["Laptop", "Monitor", "Mouse"],
        "y_values": [7200.0, 2250.0, 389.85],
        "point_count": 3,
        "aggregated": True,
        "agg_operation": "sum",
    }


@pytest.fixture
def line_data():
    return {
        "chart_type": "line",
        "x_column": "Month",
        "y_column": "Revenue",
        "x_values": ["Jan", "Feb", "Mar", "Apr"],
        "y_values": [5000.0, 6200.0, 4800.0, 7100.0],
        "point_count": 4,
        "aggregated": True,
        "agg_operation": "sum",
    }


@pytest.fixture
def scatter_data():
    return {
        "chart_type": "scatter",
        "x_column": "Quantity",
        "y_column": "Revenue",
        "x_values": [3, 15, 8, 5],
        "y_values": [3600.0, 389.85, 719.92, 2250.0],
        "point_count": 4,
        "aggregated": False,
        "agg_operation": None,
    }


@pytest.fixture
def histogram_data():
    return {
        "chart_type": "histogram",
        "x_column": "Revenue",
        "values": [3600.0, 389.85, 719.92, 2250.0, 3600.0],
        "count": 5,
    }


@pytest.fixture
def heatmap_data():
    return {
        "chart_type": "heatmap",
        "columns": ["Quantity", "Revenue"],
        "correlation_matrix": {
            "Quantity": {"Quantity": 1.0, "Revenue": 0.42},
            "Revenue": {"Quantity": 0.42, "Revenue": 1.0},
        },
        "method": "pearson",
    }


# ---------------------------------------------------------------------------
# 1. Bar chart
# ---------------------------------------------------------------------------

class TestBarChart:
    def test_returns_figure(self, bar_data):
        fig = build_bar_chart(bar_data)
        assert isinstance(fig, go.Figure)

    def test_bar_chart_has_data(self, bar_data):
        fig = build_bar_chart(bar_data)
        assert len(fig.data) > 0

    def test_title_in_layout(self, bar_data):
        bar_data_no_agg = {**bar_data, "agg_operation": ""}
        fig = build_bar_chart(bar_data_no_agg, title="Test Title")
        assert fig.layout.title.text == "Test Title"

    def test_empty_x_raises(self, bar_data):
        bar_data["x_values"] = []
        bar_data["y_values"] = []
        with pytest.raises(ChartBuilderError):
            build_bar_chart(bar_data)

    def test_mismatched_lengths_raises(self, bar_data):
        bar_data["y_values"] = [1.0, 2.0]  # Only 2 instead of 3
        with pytest.raises(ChartBuilderError):
            build_bar_chart(bar_data)


# ---------------------------------------------------------------------------
# 2. Line chart
# ---------------------------------------------------------------------------

class TestLineChart:
    def test_returns_figure(self, line_data):
        fig = build_line_chart(line_data)
        assert isinstance(fig, go.Figure)

    def test_has_scatter_trace(self, line_data):
        fig = build_line_chart(line_data)
        assert len(fig.data) > 0

    def test_empty_data_raises(self, line_data):
        line_data["x_values"] = []
        line_data["y_values"] = []
        with pytest.raises(ChartBuilderError):
            build_line_chart(line_data)


# ---------------------------------------------------------------------------
# 3. Scatter chart
# ---------------------------------------------------------------------------

class TestScatterChart:
    def test_returns_figure(self, scatter_data):
        fig = build_scatter_chart(scatter_data)
        assert isinstance(fig, go.Figure)

    def test_markers_present(self, scatter_data):
        fig = build_scatter_chart(scatter_data)
        trace = fig.data[0]
        assert "markers" in trace.mode

    def test_empty_data_raises(self, scatter_data):
        scatter_data["x_values"] = []
        scatter_data["y_values"] = []
        with pytest.raises(ChartBuilderError):
            build_scatter_chart(scatter_data)


# ---------------------------------------------------------------------------
# 4. Histogram
# ---------------------------------------------------------------------------

class TestHistogram:
    def test_returns_figure(self, histogram_data):
        fig = build_histogram(histogram_data)
        assert isinstance(fig, go.Figure)

    def test_empty_values_raises(self, histogram_data):
        histogram_data["values"] = []
        with pytest.raises(ChartBuilderError):
            build_histogram(histogram_data)

    def test_custom_bins(self, histogram_data):
        fig = build_histogram(histogram_data, nbins=10)
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# 5. Heatmap
# ---------------------------------------------------------------------------

class TestHeatmap:
    def test_returns_figure(self, heatmap_data):
        fig = build_heatmap(heatmap_data)
        assert isinstance(fig, go.Figure)

    def test_heatmap_has_heatmap_trace(self, heatmap_data):
        fig = build_heatmap(heatmap_data)
        assert isinstance(fig.data[0], go.Heatmap)

    def test_empty_heatmap_data_raises(self):
        with pytest.raises(ChartBuilderError):
            build_heatmap({"chart_type": "heatmap", "columns": [], "correlation_matrix": {}})


# ---------------------------------------------------------------------------
# 6. Dispatcher: build_chart
# ---------------------------------------------------------------------------

class TestBuildChart:
    def test_dispatches_bar(self, bar_data):
        fig = build_chart(bar_data)
        assert isinstance(fig, go.Figure)

    def test_dispatches_line(self, line_data):
        fig = build_chart(line_data)
        assert isinstance(fig, go.Figure)

    def test_dispatches_scatter(self, scatter_data):
        fig = build_chart(scatter_data)
        assert isinstance(fig, go.Figure)

    def test_dispatches_histogram(self, histogram_data):
        fig = build_chart(histogram_data)
        assert isinstance(fig, go.Figure)

    def test_dispatches_heatmap(self, heatmap_data):
        fig = build_chart(heatmap_data)
        assert isinstance(fig, go.Figure)

    def test_unknown_type_raises(self, bar_data):
        bar_data["chart_type"] = "pie"
        with pytest.raises(ChartBuilderError, match="[Nn]o chart builder"):
            build_chart(bar_data)

    def test_missing_chart_type_raises(self):
        with pytest.raises(ChartBuilderError):
            build_chart({"x_values": [1], "y_values": [2]})
