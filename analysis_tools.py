"""
analysis_tools.py - Deterministic Pandas Analysis Tools
=========================================================
Every public function in this module:
  1. Validates its arguments strictly before touching the DataFrame.
  2. Performs all calculations with Pandas/NumPy — no LLM involvement.
  3. Returns a JSON-serialisable dict.
  4. Never evaluates user-supplied Python or shell commands.

The agent calls these functions through the tool registry in agent.py.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ToolError(ValueError):
    """Raised when a tool cannot complete due to bad arguments or data."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

ALLOWED_AGG_OPS = {"sum", "mean", "min", "max", "count", "median"}

ALLOWED_FILTER_OPS = {
    "eq", "ne", "gt", "lt", "gte", "lte",
    "is_missing", "is_not_missing", "contains",
}


def _require_column(df: pd.DataFrame, column: str) -> None:
    """Raise ToolError if column is not in the DataFrame."""
    if column not in df.columns:
        raise ToolError(
            f"Column {column!r} not found.  "
            f"Available columns: {list(df.columns)}"
        )


def _require_numeric_column(df: pd.DataFrame, column: str) -> None:
    """Raise ToolError if column exists but is not numeric."""
    _require_column(df, column)
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ToolError(
            f"Column {column!r} is not numeric (dtype: {df[column].dtype}).  "
            "Please choose a numeric column for this operation."
        )


def _safe_float(value) -> Optional[float]:
    """Convert a value to float, returning None for non-finite results."""
    try:
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _df_to_records(df: pd.DataFrame, max_rows: int) -> list[dict]:
    """Convert a DataFrame to a list of JSON-safe dicts, limited to max_rows."""
    limited = df.head(max_rows)
    records = []
    for _, row in limited.iterrows():
        record = {}
        for col, val in row.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                record[col] = None
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = _safe_float(val)
            elif isinstance(val, (np.bool_,)):
                record[col] = bool(val)
            else:
                record[col] = val
        records.append(record)
    return records


# ===========================================================================
# Tool 1: get_dataset_profile
# ===========================================================================


def get_dataset_profile(df: pd.DataFrame) -> dict[str, Any]:
    """
    Return a comprehensive profile of the dataset.

    Returns
    -------
    dict containing:
        - dimensions
        - column_names
        - dtypes
        - missing_value_stats
        - duplicate_rows
        - numeric_summary
        - categorical_summary
    """
    if df is None or df.empty:
        raise ToolError("Dataset is empty — cannot generate profile.")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

    # Missing values
    missing_per_col = {col: int(df[col].isna().sum()) for col in df.columns}
    missing_pct = {
        col: round(missing_per_col[col] / len(df) * 100, 2) for col in df.columns
    }

    # Numeric summary
    numeric_summary: dict[str, dict] = {}
    for col in numeric_cols:
        s = df[col].dropna()
        if s.empty:
            numeric_summary[col] = {"count": 0, "note": "all values missing"}
            continue
        numeric_summary[col] = {
            "count": int(s.count()),
            "mean": _safe_float(s.mean()),
            "std": _safe_float(s.std()),
            "min": _safe_float(s.min()),
            "25%": _safe_float(s.quantile(0.25)),
            "50%": _safe_float(s.quantile(0.50)),
            "75%": _safe_float(s.quantile(0.75)),
            "max": _safe_float(s.max()),
        }

    # Categorical summary
    categorical_summary: dict[str, dict] = {}
    for col in categorical_cols:
        s = df[col].dropna()
        top_vals = s.value_counts().head(5).to_dict()
        categorical_summary[col] = {
            "unique_count": int(s.nunique()),
            "top_5_values": {str(k): int(v) for k, v in top_vals.items()},
            "missing_count": missing_per_col[col],
        }

    return {
        "dimensions": {"rows": len(df), "columns": len(df.columns)},
        "column_names": list(df.columns),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "missing_value_stats": {
            "total_missing": sum(missing_per_col.values()),
            "per_column_count": missing_per_col,
            "per_column_pct": missing_pct,
        },
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "numeric_summary": numeric_summary,
        "categorical_summary": categorical_summary,
    }


# ===========================================================================
# Tool 2: get_missing_values
# ===========================================================================


def get_missing_values(df: pd.DataFrame) -> dict[str, Any]:
    """
    Return missing-value statistics for every column.

    Returns
    -------
    dict with per-column missing counts, percentages, and totals.
    """
    if df is None or df.empty:
        raise ToolError("Dataset is empty.")

    total_cells = len(df) * len(df.columns)
    per_col_count = {col: int(df[col].isna().sum()) for col in df.columns}
    per_col_pct = {
        col: round(count / len(df) * 100, 2) if len(df) > 0 else 0.0
        for col, count in per_col_count.items()
    }
    cols_with_missing = [c for c, v in per_col_count.items() if v > 0]

    return {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "total_cells": total_cells,
        "total_missing": sum(per_col_count.values()),
        "total_missing_pct": round(sum(per_col_count.values()) / max(total_cells, 1) * 100, 2),
        "columns_with_missing": cols_with_missing,
        "per_column_count": per_col_count,
        "per_column_pct": per_col_pct,
    }


# ===========================================================================
# Tool 3: get_summary_statistics
# ===========================================================================


def get_summary_statistics(df: pd.DataFrame, column: str) -> dict[str, Any]:
    """
    Return descriptive statistics for a single numeric column.

    Parameters
    ----------
    column : str
        Name of the numeric column to summarise.
    """
    _require_numeric_column(df, column)

    series = df[column].dropna()

    if series.empty:
        return {
            "column": column,
            "count": 0,
            "note": "Column contains no valid numeric values (all missing or non-numeric).",
        }

    result = {
        "column": column,
        "count": int(series.count()),
        "mean": _safe_float(series.mean()),
        "median": _safe_float(series.median()),
        "std": _safe_float(series.std()),
        "variance": _safe_float(series.var()),
        "min": _safe_float(series.min()),
        "max": _safe_float(series.max()),
        "range": _safe_float(series.max() - series.min()),
        "q1": _safe_float(series.quantile(0.25)),
        "q3": _safe_float(series.quantile(0.75)),
        "iqr": _safe_float(series.quantile(0.75) - series.quantile(0.25)),
        "skewness": _safe_float(series.skew()),
        "kurtosis": _safe_float(series.kurtosis()),
        "missing_count": int(df[column].isna().sum()),
        "missing_pct": round(df[column].isna().sum() / len(df) * 100, 2),
    }

    return result


# ===========================================================================
# Tool 4: aggregate_data
# ===========================================================================


def aggregate_data(
    df: pd.DataFrame,
    group_by_column: str,
    value_column: str,
    operation: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Group the DataFrame by one column and apply an aggregation to another.

    Parameters
    ----------
    group_by_column : str
        Column to group by.
    value_column : str
        Numeric column to aggregate.
    operation : str
        One of: sum, mean, min, max, count, median.
    limit : int
        Maximum number of result rows to return (default 20).
    """
    _require_column(df, group_by_column)

    if operation not in ALLOWED_AGG_OPS:
        raise ToolError(
            f"Unsupported operation {operation!r}.  "
            f"Allowed operations: {sorted(ALLOWED_AGG_OPS)}"
        )

    # count does not require a numeric column
    if operation != "count":
        _require_numeric_column(df, value_column)
    else:
        _require_column(df, value_column)

    limit = max(1, min(int(limit), settings.max_result_rows))

    grouped = df.groupby(group_by_column, dropna=False)

    agg_map = {
        "sum": "sum",
        "mean": "mean",
        "min": "min",
        "max": "max",
        "count": "count",
        "median": "median",
    }

    result_series = getattr(grouped[value_column], agg_map[operation])()
    result_series = result_series.sort_values(ascending=False)

    total_groups = len(result_series)
    result_series = result_series.head(limit)

    records = [
        {
            group_by_column: str(k) if k is not None and not (isinstance(k, float) and math.isnan(k)) else None,
            f"{operation}_{value_column}": _safe_float(v) if not isinstance(v, int) else int(v),
        }
        for k, v in result_series.items()
    ]

    return {
        "group_by_column": group_by_column,
        "value_column": value_column,
        "operation": operation,
        "total_groups": total_groups,
        "returned_groups": len(records),
        "limit_applied": total_groups > limit,
        "results": records,
    }


# ===========================================================================
# Tool 5: filter_data
# ===========================================================================


def filter_data(
    df: pd.DataFrame,
    column: str,
    operator: str,
    value: Any = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Filter rows using a restricted, explicit set of operators.

    Parameters
    ----------
    column : str
        Column to filter on.
    operator : str
        One of: eq, ne, gt, lt, gte, lte, is_missing, is_not_missing, contains.
    value : Any
        Comparison value (not required for is_missing / is_not_missing).
    limit : int
        Maximum rows to return.

    Security
    --------
    Operators are validated against an explicit allowlist.
    Arbitrary Python expressions are never evaluated.
    """
    _require_column(df, column)

    if operator not in ALLOWED_FILTER_OPS:
        raise ToolError(
            f"Unsupported filter operator {operator!r}.  "
            f"Allowed operators: {sorted(ALLOWED_FILTER_OPS)}"
        )

    limit = max(1, min(int(limit), settings.max_result_rows))

    col = df[column]

    if operator == "is_missing":
        mask = col.isna()
    elif operator == "is_not_missing":
        mask = col.notna()
    elif operator == "contains":
        if value is None:
            raise ToolError("'contains' operator requires a value.")
        mask = col.astype(str).str.contains(str(value), case=False, na=False)
    else:
        if value is None:
            raise ToolError(f"Operator {operator!r} requires a comparison value.")
        try:
            numeric_col = pd.to_numeric(col, errors="coerce")
            numeric_val = float(value)
            op_map = {
                "eq": numeric_col == numeric_val,
                "ne": numeric_col != numeric_val,
                "gt": numeric_col > numeric_val,
                "lt": numeric_col < numeric_val,
                "gte": numeric_col >= numeric_val,
                "lte": numeric_col <= numeric_val,
            }
            mask = op_map[operator]
        except (ValueError, TypeError):
            # Fall back to string comparison
            str_col = col.astype(str)
            str_val = str(value)
            op_map_str = {
                "eq": str_col == str_val,
                "ne": str_col != str_val,
                "gt": str_col > str_val,
                "lt": str_col < str_val,
                "gte": str_col >= str_val,
                "lte": str_col <= str_val,
            }
            mask = op_map_str[operator]

    filtered = df[mask]
    total_matches = len(filtered)
    limited = filtered.head(limit)

    return {
        "column": column,
        "operator": operator,
        "value": value,
        "total_matching_rows": total_matches,
        "returned_rows": len(limited),
        "limit_applied": total_matches > limit,
        "results": _df_to_records(limited, limit),
    }


# ===========================================================================
# Tool 6: top_n_analysis
# ===========================================================================


def top_n_analysis(
    df: pd.DataFrame,
    category_column: str,
    value_column: str,
    n: int = 10,
    ascending: bool = False,
    operation: str = "sum",
) -> dict[str, Any]:
    """
    Return the top (or bottom) N categories by aggregated value.

    Parameters
    ----------
    category_column : str
        Column containing category labels.
    value_column : str
        Numeric column to aggregate.
    n : int
        Number of results to return (1–100).
    ascending : bool
        If True, return bottom-N instead of top-N.
    operation : str
        Aggregation to apply before ranking (sum, mean, count, etc.)
    """
    _require_column(df, category_column)

    if operation not in ALLOWED_AGG_OPS:
        raise ToolError(
            f"Unsupported operation {operation!r}.  "
            f"Allowed: {sorted(ALLOWED_AGG_OPS)}"
        )

    if operation != "count":
        _require_numeric_column(df, value_column)
    else:
        _require_column(df, value_column)

    n = max(1, min(int(n), 100))

    grouped = getattr(df.groupby(category_column, dropna=False)[value_column], operation)()
    ranked = grouped.sort_values(ascending=ascending).head(n)

    label = "bottom" if ascending else "top"
    result_col_name = f"{operation}_{value_column}"

    records = [
        {category_column: str(k), result_col_name: _safe_float(v)}
        for k, v in ranked.items()
    ]

    return {
        "category_column": category_column,
        "value_column": value_column,
        "operation": operation,
        "n": n,
        "order": label,
        "results": records,
    }


# ===========================================================================
# Tool 7: make_chart_data
# ===========================================================================

SUPPORTED_CHART_TYPES = {"bar", "line", "scatter", "histogram", "heatmap"}


def make_chart_data(
    df: pd.DataFrame,
    chart_type: str,
    x_column: str,
    y_column: Optional[str] = None,
    color_column: Optional[str] = None,
    aggregate: bool = True,
    agg_operation: str = "sum",
    limit: int = 50,
) -> dict[str, Any]:
    """
    Build validated chart data from the DataFrame.

    Parameters
    ----------
    chart_type : str
        One of: bar, line, scatter, histogram, heatmap.
    x_column : str
        Column for the X axis.
    y_column : str, optional
        Column for the Y axis (not required for histogram).
    color_column : str, optional
        Column used for color grouping.
    aggregate : bool
        If True, aggregate y_column by x_column before plotting.
    agg_operation : str
        Aggregation operation (sum, mean, count, etc.) when aggregate=True.
    limit : int
        Maximum distinct x-axis categories.
    """
    if chart_type not in SUPPORTED_CHART_TYPES:
        raise ToolError(
            f"Unsupported chart type {chart_type!r}.  "
            f"Supported types: {sorted(SUPPORTED_CHART_TYPES)}"
        )

    _require_column(df, x_column)
    if y_column:
        _require_column(df, y_column)
    if color_column:
        _require_column(df, color_column)

    limit = max(2, min(int(limit), settings.max_chart_categories))

    if chart_type == "histogram":
        _require_numeric_column(df, x_column)
        values = df[x_column].dropna().tolist()
        return {
            "chart_type": "histogram",
            "x_column": x_column,
            "values": values[:10_000],  # hard cap for serialisation
            "count": len(values),
        }

    if chart_type == "heatmap":
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) < 2:
            raise ToolError("Correlation heatmap requires at least 2 numeric columns.")
        corr = df[numeric_cols].corr(method="pearson")
        # Convert to JSON-safe structure
        corr_data = {
            col: {
                row: _safe_float(corr.loc[row, col])
                for row in corr.index
            }
            for col in corr.columns
        }
        return {
            "chart_type": "heatmap",
            "columns": numeric_cols,
            "correlation_matrix": corr_data,
            "method": "pearson",
        }

    # Bar / Line / Scatter
    if y_column is None:
        raise ToolError(f"y_column is required for chart type {chart_type!r}.")

    if aggregate and chart_type in {"bar", "line"}:
        if agg_operation not in ALLOWED_AGG_OPS:
            raise ToolError(f"Invalid agg_operation: {agg_operation!r}.")
        if agg_operation != "count":
            _require_numeric_column(df, y_column)
        grouped = getattr(df.groupby(x_column, dropna=False)[y_column], agg_operation)()
        grouped = grouped.sort_values(ascending=False).head(limit)
        x_vals = [str(k) for k in grouped.index]
        y_vals = [_safe_float(v) for v in grouped.values]
    else:
        sample = df[[x_column, y_column]].dropna().head(limit * 10)
        x_vals = sample[x_column].tolist()
        y_vals = sample[y_column].tolist()

    return {
        "chart_type": chart_type,
        "x_column": x_column,
        "y_column": y_column,
        "x_values": x_vals,
        "y_values": y_vals,
        "point_count": len(x_vals),
        "aggregated": aggregate,
        "agg_operation": agg_operation if aggregate else None,
    }


# ===========================================================================
# Tool 8: detect_outliers
# ===========================================================================


def detect_outliers(
    df: pd.DataFrame,
    columns: Optional[list[str]] = None,
    method: str = "iqr",
    preview_limit: int = 20,
) -> dict[str, Any]:
    """
    Detect outliers in numeric columns using the IQR method.

    Outlier = value < Q1 - 1.5*IQR  OR  value > Q3 + 1.5*IQR

    Parameters
    ----------
    columns : list[str], optional
        Specific columns to analyse.  Defaults to all numeric columns.
    method : str
        Only 'iqr' is supported in this version.
    preview_limit : int
        Maximum number of outlier rows returned for preview.
    """
    if method != "iqr":
        raise ToolError(
            f"Method {method!r} is not supported.  Only 'iqr' is currently available."
        )

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if columns:
        for col in columns:
            _require_column(df, col)
            if col not in numeric_cols:
                raise ToolError(f"Column {col!r} is not numeric.")
        target_cols = columns
    else:
        target_cols = numeric_cols

    if not target_cols:
        raise ToolError("No numeric columns found in the dataset.")

    preview_limit = max(1, min(int(preview_limit), settings.max_result_rows))
    outlier_details: dict[str, dict] = {}
    all_outlier_indices: set[int] = set()

    for col in target_cols:
        series = df[col].dropna()
        if series.empty:
            outlier_details[col] = {"count": 0, "note": "all values missing"}
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outlier_mask = (df[col] < lower) | (df[col] > upper)
        outlier_indices = df[outlier_mask].index.tolist()
        all_outlier_indices.update(outlier_indices)

        outlier_details[col] = {
            "count": len(outlier_indices),
            "q1": _safe_float(q1),
            "q3": _safe_float(q3),
            "iqr": _safe_float(iqr),
            "lower_fence": _safe_float(lower),
            "upper_fence": _safe_float(upper),
        }

    # Build a preview of the rows that contain at least one outlier
    preview_rows = (
        _df_to_records(df.loc[list(all_outlier_indices)].head(preview_limit), preview_limit)
        if all_outlier_indices
        else []
    )

    return {
        "method": "IQR (Q1 - 1.5×IQR, Q3 + 1.5×IQR)",
        "columns_analysed": target_cols,
        "total_outlier_rows": len(all_outlier_indices),
        "per_column_details": outlier_details,
        "preview": preview_rows,
        "note": "Outliers are not removed.  Review the preview to decide on treatment.",
    }


# ===========================================================================
# Tool 9: get_correlation
# ===========================================================================


def get_correlation(
    df: pd.DataFrame,
    columns: Optional[list[str]] = None,
    method: str = "pearson",
) -> dict[str, Any]:
    """
    Compute the correlation matrix for numeric columns.

    Parameters
    ----------
    columns : list[str], optional
        Subset of numeric columns.  Defaults to all numeric columns.
    method : str
        'pearson', 'spearman', or 'kendall'.
    """
    allowed_methods = {"pearson", "spearman", "kendall"}
    if method not in allowed_methods:
        raise ToolError(
            f"Method {method!r} is not supported.  "
            f"Allowed methods: {sorted(allowed_methods)}"
        )

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if columns:
        for col in columns:
            _require_column(df, col)
            if col not in numeric_cols:
                raise ToolError(f"Column {col!r} is not numeric.")
        target_cols = columns
    else:
        target_cols = numeric_cols

    if len(target_cols) < 2:
        raise ToolError(
            "Correlation requires at least 2 numeric columns.  "
            f"Found: {target_cols}"
        )

    corr_df = df[target_cols].corr(method=method)

    # Flatten to JSON-safe dict
    corr_matrix = {
        col: {
            row: _safe_float(corr_df.loc[row, col])
            for row in corr_df.index
        }
        for col in corr_df.columns
    }

    # Find strongest pairs (excluding self-correlations)
    pairs = []
    for i, c1 in enumerate(target_cols):
        for c2 in target_cols[i + 1:]:
            val = corr_df.loc[c1, c2]
            if val is not None and not math.isnan(val):
                pairs.append({"col1": c1, "col2": c2, "correlation": _safe_float(val)})

    pairs.sort(key=lambda x: abs(x["correlation"] or 0), reverse=True)

    return {
        "method": method,
        "columns": target_cols,
        "correlation_matrix": corr_matrix,
        "top_pairs": pairs[:10],
        "note": (
            "Values near +1 indicate strong positive correlation, "
            "near -1 strong negative correlation, "
            "near 0 little linear relationship."
        ),
    }


# ===========================================================================
# Tool 10: generate_data_quality_report
# ===========================================================================


def generate_data_quality_report(df: pd.DataFrame) -> dict[str, Any]:
    """
    Produce a structured data quality report combining profiling,
    missing values, duplicates, outlier summary, and quality warnings.

    All statistics are computed in Python — the LLM does not fabricate any values.
    """
    if df is None or df.empty:
        raise ToolError("Dataset is empty — cannot generate report.")

    # --- Profile ---
    profile = get_dataset_profile(df)

    # --- Missing values ---
    missing = get_missing_values(df)

    # --- Outlier summary ---
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    outlier_summary = {}
    if numeric_cols:
        try:
            outlier_result = detect_outliers(df, preview_limit=0)
            outlier_summary = outlier_result["per_column_details"]
        except ToolError:
            outlier_summary = {}

    # --- Quality warnings ---
    quality_warnings: list[str] = []

    # High missing %
    for col, pct in missing["per_column_pct"].items():
        if pct > 50:
            quality_warnings.append(
                f"Column {col!r} has {pct:.0f}% missing values — consider dropping or imputing."
            )
        elif pct > 20:
            quality_warnings.append(
                f"Column {col!r} has {pct:.0f}% missing values."
            )

    # Duplicate rows
    if profile["duplicate_rows"] > 0:
        dup_pct = round(profile["duplicate_rows"] / len(df) * 100, 1)
        quality_warnings.append(
            f"{profile['duplicate_rows']:,} duplicate rows detected ({dup_pct}% of total)."
        )

    # Constant columns
    for col in df.columns:
        if df[col].dropna().nunique() <= 1 and df[col].dropna().size > 0:
            quality_warnings.append(
                f"Column {col!r} has only one unique value — not useful for analysis."
            )

    # High outlier counts
    for col, detail in outlier_summary.items():
        count = detail.get("count", 0)
        if count > 0:
            pct = round(count / len(df) * 100, 1)
            if pct > 10:
                quality_warnings.append(
                    f"Column {col!r} has {count} outliers ({pct}% of values)."
                )

    # --- Overall score (simple heuristic 0–100) ---
    penalties = 0
    penalties += min(missing["total_missing_pct"] * 2, 40)  # missing values: up to 40
    dup_pct_val = profile["duplicate_rows"] / max(len(df), 1) * 100
    penalties += min(dup_pct_val * 2, 20)                   # duplicates: up to 20
    penalties += min(len(quality_warnings) * 5, 40)          # warnings: up to 40
    quality_score = max(0, round(100 - penalties, 0))

    return {
        "report_title": "Data Quality Report",
        "dimensions": profile["dimensions"],
        "quality_score": quality_score,
        "quality_score_note": (
            "Heuristic score 0–100.  100 = no issues detected.  "
            "Lower scores indicate missing data, duplicates, or other concerns."
        ),
        "missing_value_summary": missing,
        "duplicate_rows": profile["duplicate_rows"],
        "outlier_summary": outlier_summary,
        "quality_warnings": quality_warnings,
        "numeric_summary": profile["numeric_summary"],
        "categorical_summary": profile["categorical_summary"],
    }
