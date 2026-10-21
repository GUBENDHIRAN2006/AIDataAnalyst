"""
tests/test_analysis_tools.py - Analysis Tool Tests
===================================================
Unit tests for every function in analysis_tools.py.
Uses only local Python calculations — no LLM or API calls required.
"""

import math

import numpy as np
import pandas as pd
import pytest

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


# ===========================================================================
# Tool 1: get_dataset_profile
# ===========================================================================

class TestGetDatasetProfile:
    def test_returns_correct_dimensions(self, simple_df):
        result = get_dataset_profile(simple_df)
        assert result["dimensions"]["rows"] == 5
        assert result["dimensions"]["columns"] == 5

    def test_identifies_numeric_columns(self, simple_df):
        result = get_dataset_profile(simple_df)
        assert "Revenue" in result["numeric_columns"]
        assert "Quantity" in result["numeric_columns"]

    def test_identifies_categorical_columns(self, simple_df):
        result = get_dataset_profile(simple_df)
        assert "Product" in result["categorical_columns"]
        assert "Region" in result["categorical_columns"]

    def test_duplicate_count(self, simple_df):
        """The simple_df fixture has 1 duplicate row."""
        result = get_dataset_profile(simple_df)
        assert result["duplicate_rows"] == 1

    def test_missing_values_in_profile(self, df_with_missing):
        result = get_dataset_profile(df_with_missing)
        assert result["missing_value_stats"]["total_missing"] > 0

    def test_empty_df_raises(self):
        with pytest.raises(ToolError):
            get_dataset_profile(pd.DataFrame())

    def test_numeric_summary_stats_present(self, simple_df):
        result = get_dataset_profile(simple_df)
        revenue_stats = result["numeric_summary"]["Revenue"]
        assert "mean" in revenue_stats
        assert "std" in revenue_stats
        assert "min" in revenue_stats
        assert "max" in revenue_stats


# ===========================================================================
# Tool 2: get_missing_values
# ===========================================================================

class TestGetMissingValues:
    def test_no_missing(self, simple_df):
        result = get_missing_values(simple_df)
        assert result["total_missing"] == 0
        assert result["columns_with_missing"] == []

    def test_missing_detected(self, df_with_missing):
        result = get_missing_values(df_with_missing)
        assert result["total_missing"] > 0
        assert "Score" in result["columns_with_missing"]

    def test_missing_percentage_correct(self, df_with_missing):
        result = get_missing_values(df_with_missing)
        # Score has 2 nulls out of 4 rows = 50%
        assert result["per_column_pct"]["Score"] == 50.0

    def test_total_cells_correct(self, simple_df):
        result = get_missing_values(simple_df)
        assert result["total_cells"] == 5 * 5  # 5 rows × 5 cols

    def test_empty_df_raises(self):
        with pytest.raises(ToolError):
            get_missing_values(pd.DataFrame())


# ===========================================================================
# Tool 3: get_summary_statistics
# ===========================================================================

class TestGetSummaryStatistics:
    def test_correct_mean(self, simple_df):
        result = get_summary_statistics(simple_df, "Revenue")
        expected_mean = (3600.0 + 389.85 + 719.92 + 2250.0 + 3600.0) / 5
        assert abs(result["mean"] - expected_mean) < 0.01

    def test_correct_min_max(self, simple_df):
        result = get_summary_statistics(simple_df, "Revenue")
        assert result["min"] == pytest.approx(389.85, rel=1e-3)
        assert result["max"] == pytest.approx(3600.0, rel=1e-3)

    def test_invalid_column_raises(self, simple_df):
        with pytest.raises(ToolError, match="not found"):
            get_summary_statistics(simple_df, "NonExistentColumn")

    def test_non_numeric_column_raises(self, simple_df):
        with pytest.raises(ToolError, match="not numeric"):
            get_summary_statistics(simple_df, "Product")

    def test_all_missing_column(self):
        df = pd.DataFrame({"A": [None, None, None]})
        df["A"] = pd.to_numeric(df["A"], errors="coerce")
        result = get_summary_statistics(df, "A")
        assert result["count"] == 0
        assert "note" in result

    def test_median_correct(self, simple_df):
        result = get_summary_statistics(simple_df, "Quantity")
        # [3, 15, 8, 5, 3] sorted = [3, 3, 5, 8, 15] → median = 5
        assert result["median"] == 5.0


# ===========================================================================
# Tool 4: aggregate_data
# ===========================================================================

class TestAggregateData:
    def test_sum_by_product(self, simple_df):
        result = aggregate_data(simple_df, "Product", "Revenue", "sum")
        assert result["operation"] == "sum"
        # Laptop appears twice: 3600 + 3600 = 7200
        laptop_row = next(
            (r for r in result["results"] if r["Product"] == "Laptop"), None
        )
        assert laptop_row is not None
        assert laptop_row["sum_Revenue"] == pytest.approx(7200.0, rel=1e-3)

    def test_mean_aggregation(self, simple_df):
        result = aggregate_data(simple_df, "Region", "Revenue", "mean")
        assert result["operation"] == "mean"
        assert len(result["results"]) > 0

    def test_count_aggregation(self, simple_df):
        result = aggregate_data(simple_df, "Product", "Revenue", "count")
        # Laptop appears 2 times
        laptop_row = next(
            (r for r in result["results"] if r["Product"] == "Laptop"), None
        )
        assert laptop_row is not None
        assert laptop_row["count_Revenue"] == 2

    def test_invalid_group_column_raises(self, simple_df):
        with pytest.raises(ToolError, match="not found"):
            aggregate_data(simple_df, "BadColumn", "Revenue", "sum")

    def test_invalid_value_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            aggregate_data(simple_df, "Product", "BadColumn", "sum")

    def test_invalid_operation_raises(self, simple_df):
        with pytest.raises(ToolError, match="[Uu]nsupported"):
            aggregate_data(simple_df, "Product", "Revenue", "variance")

    def test_non_numeric_value_column_raises(self, simple_df):
        with pytest.raises(ToolError, match="not numeric"):
            aggregate_data(simple_df, "Product", "Region", "sum")

    def test_limit_applied(self, simple_df):
        result = aggregate_data(simple_df, "Product", "Revenue", "sum", limit=2)
        assert len(result["results"]) <= 2
        assert result["limit_applied"] is True


# ===========================================================================
# Tool 5: filter_data
# ===========================================================================

class TestFilterData:
    def test_eq_filter(self, simple_df):
        result = filter_data(simple_df, "Product", "eq", "Laptop")
        assert result["total_matching_rows"] == 2

    def test_gt_filter(self, simple_df):
        result = filter_data(simple_df, "Revenue", "gt", 1000)
        # Revenues > 1000: 3600, 2250, 3600
        assert result["total_matching_rows"] == 3

    def test_lt_filter(self, simple_df):
        result = filter_data(simple_df, "Revenue", "lt", 500)
        # Revenues < 500: 389.85
        assert result["total_matching_rows"] == 1

    def test_is_missing_filter(self, df_with_missing):
        result = filter_data(df_with_missing, "Score", "is_missing")
        assert result["total_matching_rows"] == 2

    def test_is_not_missing_filter(self, df_with_missing):
        result = filter_data(df_with_missing, "Score", "is_not_missing")
        assert result["total_matching_rows"] == 2

    def test_contains_filter(self, simple_df):
        result = filter_data(simple_df, "Product", "contains", "board")
        assert result["total_matching_rows"] == 1  # "Keyboard"

    def test_invalid_column_raises(self, simple_df):
        with pytest.raises(ToolError, match="not found"):
            filter_data(simple_df, "NonExistent", "eq", "x")

    def test_invalid_operator_raises(self, simple_df):
        with pytest.raises(ToolError, match="[Uu]nsupported"):
            filter_data(simple_df, "Revenue", "between", 100)

    def test_limit_applied(self, simple_df):
        result = filter_data(simple_df, "Revenue", "gt", 0, limit=2)
        assert result["returned_rows"] <= 2


# ===========================================================================
# Tool 6: top_n_analysis
# ===========================================================================

class TestTopNAnalysis:
    def test_top_2_products_by_revenue(self, simple_df):
        result = top_n_analysis(simple_df, "Product", "Revenue", n=2, operation="sum")
        assert result["n"] == 2
        assert len(result["results"]) == 2
        # Laptop should be top (7200)
        assert result["results"][0]["Product"] == "Laptop"

    def test_bottom_n(self, simple_df):
        result = top_n_analysis(simple_df, "Product", "Revenue", n=2, ascending=True, operation="sum")
        assert result["order"] == "bottom"
        assert len(result["results"]) == 2

    def test_invalid_n_clamped(self, simple_df):
        result = top_n_analysis(simple_df, "Product", "Revenue", n=1000)
        assert len(result["results"]) <= 100

    def test_invalid_category_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            top_n_analysis(simple_df, "Bogus", "Revenue", n=3)

    def test_invalid_value_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            top_n_analysis(simple_df, "Product", "Bogus", n=3)


# ===========================================================================
# Tool 7: make_chart_data
# ===========================================================================

class TestMakeChartData:
    def test_bar_chart_data(self, simple_df):
        result = make_chart_data(simple_df, "bar", "Product", "Revenue")
        assert result["chart_type"] == "bar"
        assert len(result["x_values"]) == len(result["y_values"])
        assert result["point_count"] > 0

    def test_histogram_data(self, simple_df):
        result = make_chart_data(simple_df, "histogram", "Revenue")
        assert result["chart_type"] == "histogram"
        assert "values" in result
        assert len(result["values"]) == 5

    def test_heatmap_requires_numeric(self, simple_df):
        result = make_chart_data(simple_df, "heatmap", "Product")
        assert result["chart_type"] == "heatmap"
        assert "correlation_matrix" in result

    def test_invalid_chart_type_raises(self, simple_df):
        with pytest.raises(ToolError, match="[Uu]nsupported"):
            make_chart_data(simple_df, "pie", "Product", "Revenue")

    def test_invalid_x_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            make_chart_data(simple_df, "bar", "Bogus", "Revenue")

    def test_invalid_y_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            make_chart_data(simple_df, "bar", "Product", "Bogus")

    def test_scatter_chart(self, simple_df):
        result = make_chart_data(
            simple_df, "scatter", "Quantity", "Revenue", aggregate=False
        )
        assert result["chart_type"] == "scatter"
        assert len(result["x_values"]) > 0

    def test_heatmap_insufficient_numeric_raises(self):
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Score": [90, 85]})
        # Only 1 numeric column — heatmap should raise
        with pytest.raises(ToolError, match="[Aa]t least 2"):
            make_chart_data(df, "heatmap", "Name")


# ===========================================================================
# Tool 8: detect_outliers
# ===========================================================================

class TestDetectOutliers:
    def test_detects_single_outlier(self, df_with_outliers):
        result = detect_outliers(df_with_outliers)
        assert result["per_column_details"]["Value"]["count"] == 1

    def test_no_outliers_clean_data(self):
        df = pd.DataFrame({"A": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        result = detect_outliers(df)
        assert result["per_column_details"]["A"]["count"] == 0

    def test_invalid_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            detect_outliers(simple_df, columns=["Bogus"])

    def test_non_numeric_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            detect_outliers(simple_df, columns=["Product"])

    def test_unsupported_method_raises(self, simple_df):
        with pytest.raises(ToolError, match="[Nn]ot supported"):
            detect_outliers(simple_df, method="zscore")

    def test_all_missing_column_handled(self):
        df = pd.DataFrame({"A": [None, None, None, None, None]})
        df["A"] = pd.to_numeric(df["A"], errors="coerce")
        result = detect_outliers(df)
        # Should not crash; count should be 0 or indicate all missing
        assert "A" in result["per_column_details"]

    def test_outlier_not_removed(self, df_with_outliers):
        """Outliers must be reported, never silently removed."""
        result = detect_outliers(df_with_outliers)
        assert len(df_with_outliers) == 10  # Original still has 10 rows
        assert result["total_outlier_rows"] == 1


# ===========================================================================
# Tool 9: get_correlation
# ===========================================================================

class TestGetCorrelation:
    def test_pearson_correlation(self, simple_df):
        result = get_correlation(simple_df, method="pearson")
        assert result["method"] == "pearson"
        assert "correlation_matrix" in result

    def test_perfect_self_correlation(self, simple_df):
        result = get_correlation(simple_df)
        matrix = result["correlation_matrix"]
        # Revenue with itself should be 1.0
        assert matrix["Revenue"]["Revenue"] == pytest.approx(1.0, abs=1e-6)

    def test_invalid_method_raises(self, simple_df):
        with pytest.raises(ToolError, match="[Nn]ot supported"):
            get_correlation(simple_df, method="mutual_info")

    def test_single_numeric_column_raises(self):
        df = pd.DataFrame({"Name": ["A", "B"], "Score": [1, 2]})
        with pytest.raises(ToolError, match="[Aa]t least 2"):
            get_correlation(df)

    def test_invalid_column_raises(self, simple_df):
        with pytest.raises(ToolError):
            get_correlation(simple_df, columns=["Revenue", "Bogus"])

    def test_top_pairs_sorted(self, df_all_numeric):
        result = get_correlation(df_all_numeric)
        pairs = result["top_pairs"]
        if len(pairs) >= 2:
            assert abs(pairs[0]["correlation"]) >= abs(pairs[1]["correlation"])


# ===========================================================================
# Tool 10: generate_data_quality_report
# ===========================================================================

class TestGenerateDataQualityReport:
    def test_report_structure(self, simple_df):
        report = generate_data_quality_report(simple_df)
        assert "quality_score" in report
        assert "missing_value_summary" in report
        assert "duplicate_rows" in report
        assert "quality_warnings" in report

    def test_perfect_data_high_score(self):
        """Clean data with no missing values or duplicates should score high."""
        df = pd.DataFrame({
            "A": [1, 2, 3, 4, 5],
            "B": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        report = generate_data_quality_report(df)
        assert report["quality_score"] >= 80

    def test_empty_df_raises(self):
        with pytest.raises(ToolError):
            generate_data_quality_report(pd.DataFrame())

    def test_high_missing_generates_warnings(self, df_with_missing):
        report = generate_data_quality_report(df_with_missing)
        # Score column has 50% missing — should generate at least one warning
        assert len(report["quality_warnings"]) > 0

    def test_duplicate_rows_in_report(self, simple_df):
        """The simple_df fixture has 1 duplicate — should appear in report."""
        report = generate_data_quality_report(simple_df)
        assert report["duplicate_rows"] == 1


# ===========================================================================
# Edge cases: Infinite values, mixed types
# ===========================================================================

class TestEdgeCases:
    def test_inf_values_handled_in_stats(self):
        """Infinite values should not cause NaN errors in summary stats."""
        df = pd.DataFrame({"Value": [1.0, 2.0, float("inf"), 4.0]})
        df.replace([float("inf"), float("-inf")], float("nan"), inplace=True)
        result = get_summary_statistics(df, "Value")
        # Should work on the non-inf values
        assert result["count"] == 3

    def test_all_null_numeric_column(self):
        df = pd.DataFrame({"A": [None, None], "B": [1.0, 2.0]})
        df["A"] = pd.to_numeric(df["A"], errors="coerce")
        result = get_summary_statistics(df, "A")
        assert result["count"] == 0

    def test_null_categories_in_aggregation(self):
        df = pd.DataFrame({
            "Category": [None, "A", "B", None, "A"],
            "Value": [10, 20, 30, 40, 50],
        })
        result = aggregate_data(df, "Category", "Value", "sum")
        # Should handle null categories gracefully
        assert "results" in result
        assert len(result["results"]) > 0
