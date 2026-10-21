"""
tests/conftest.py - Shared Pytest Fixtures
==========================================
Provides reusable fixtures for all test modules.
"""

import io
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from data_loader import DatasetInfo, load_csv


# ---------------------------------------------------------------------------
# Minimal test DataFrame
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_df() -> pd.DataFrame:
    """A small, clean DataFrame with mixed column types."""
    return pd.DataFrame({
        "Product": ["Laptop", "Mouse", "Keyboard", "Monitor", "Laptop"],
        "Region": ["North", "East", "West", "South", "North"],
        "Quantity": [3, 15, 8, 5, 3],
        "UnitPrice": [1200.0, 25.99, 89.99, 450.0, 1200.0],
        "Revenue": [3600.0, 389.85, 719.92, 2250.0, 3600.0],
    })


@pytest.fixture
def df_with_missing() -> pd.DataFrame:
    """DataFrame with deliberate missing values."""
    return pd.DataFrame({
        "Name": ["Alice", "Bob", None, "Dave"],
        "Score": [95.0, None, 78.0, None],
        "Grade": ["A", "B", "C", None],
    })


@pytest.fixture
def df_all_numeric() -> pd.DataFrame:
    """DataFrame with only numeric columns."""
    np.random.seed(42)
    return pd.DataFrame({
        "A": np.random.normal(100, 15, 50),
        "B": np.random.normal(200, 30, 50),
        "C": np.random.normal(50, 10, 50),
    })


@pytest.fixture
def df_with_outliers() -> pd.DataFrame:
    """DataFrame with clear outlier values."""
    values = [10.0, 11.0, 10.5, 12.0, 9.5, 10.2, 11.1, 9.8, 10.7, 1000.0]
    return pd.DataFrame({"Value": values})


@pytest.fixture
def sample_dataset_info(simple_df) -> DatasetInfo:
    """A DatasetInfo object wrapping the simple_df fixture."""
    return DatasetInfo(
        df=simple_df,
        filename="test.csv",
        row_count=len(simple_df),
        column_count=len(simple_df.columns),
        column_names=list(simple_df.columns),
        dtypes={col: str(simple_df[col].dtype) for col in simple_df.columns},
        missing_counts={col: int(simple_df[col].isna().sum()) for col in simple_df.columns},
        duplicate_row_count=int(simple_df.duplicated().sum()),
        file_size_bytes=1024,
        encoding_detected="utf-8",
        warnings=[],
    )


@pytest.fixture
def sample_csv_bytes(simple_df) -> bytes:
    """CSV bytes of the simple_df fixture."""
    buf = io.BytesIO()
    simple_df.to_csv(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def sample_csv_file(simple_df):
    """File-like object containing simple_df as CSV."""
    buf = io.BytesIO()
    simple_df.to_csv(buf, index=False)
    buf.seek(0)
    return buf


@pytest.fixture
def sales_csv_path() -> str:
    """Path to the sample sales CSV fixture."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "sample_data", "sample_sales.csv")
