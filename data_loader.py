"""
data_loader.py - Multi-Format Data Ingestion and Validation
=============================================================
Supports: CSV, XLSX/XLS, PDF (table extraction)

Responsibilities:
- Validate file size, row/column limits, encoding.
- Parse CSV, Excel, and PDF files safely.
- Detect duplicate column names, missing headers, and corrupt files.
- Return a validated DatasetInfo object or raise a descriptive DataLoaderError.

Security:
- CSV/Excel/PDF cell content is NEVER evaluated or executed.
- Files are size-checked before parsing.
- Column names are sanitised.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import chardet
import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

# Supported file formats
SUPPORTED_FORMATS = {
    ".csv": "CSV",
    ".xlsx": "Excel",
    ".xls": "Excel (Legacy)",
    ".pdf": "PDF",
}


class DataLoaderError(ValueError):
    """Raised for any data ingestion or validation failure."""


@dataclass
class DatasetInfo:
    """
    Immutable snapshot of a loaded and validated dataset.
    The DataFrame is stored here and passed to analysis tools.
    """

    df: pd.DataFrame
    filename: str
    file_format: str           # CSV, Excel, PDF
    row_count: int
    column_count: int
    column_names: list[str]
    dtypes: dict[str, str]
    missing_counts: dict[str, int]
    duplicate_row_count: int
    file_size_bytes: int
    encoding_detected: str
    warnings: list[str] = field(default_factory=list)

    @property
    def has_missing(self) -> bool:
        return any(v > 0 for v in self.missing_counts.values())

    @property
    def total_missing(self) -> int:
        return sum(self.missing_counts.values())

    def schema_summary(self) -> dict:
        """Return compact schema for sending to LLM — NEVER includes cell values."""
        return {
            "filename": self.filename,
            "file_format": self.file_format,
            "rows": self.row_count,
            "columns": self.column_count,
            "column_names": self.column_names,
            "dtypes": self.dtypes,
            "missing_counts": self.missing_counts,
            "duplicate_rows": self.duplicate_row_count,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SAFE_COLUMN_NAME_RE = re.compile(r"[^\w\s\-\./()[\]%#@&]", re.UNICODE)


def _sanitise_column_name(name: str) -> str:
    return _SAFE_COLUMN_NAME_RE.sub("", str(name)).strip()


def _detect_encoding(raw_bytes: bytes) -> str:
    result = chardet.detect(raw_bytes[:50_000])
    encoding = result.get("encoding") or "utf-8"
    return encoding


def _read_raw_bytes(file_obj) -> bytes:
    raw = file_obj.read()
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    size = len(raw)
    limit = settings.max_upload_size_bytes

    if size == 0:
        raise DataLoaderError("The uploaded file is empty.")

    if size > limit:
        limit_mb = settings.max_upload_size_mb
        actual_mb = size / (1024 * 1024)
        raise DataLoaderError(
            f"File size {actual_mb:.1f} MB exceeds the {limit_mb:.0f} MB limit. "
            "Please upload a smaller file."
        )
    return raw


def _validate_parsed_df(df: pd.DataFrame, filename: str) -> list[str]:
    warnings: list[str] = []

    if df.empty:
        raise DataLoaderError("The file contains no data rows.")

    if len(df) > settings.max_rows:
        raise DataLoaderError(
            f"Dataset contains {len(df):,} rows which exceeds the limit of "
            f"{settings.max_rows:,} rows. Please upload a smaller file."
        )

    if len(df.columns) > settings.max_columns:
        raise DataLoaderError(
            f"Dataset contains {len(df.columns)} columns which exceeds the limit of "
            f"{settings.max_columns} columns."
        )

    if len(df.columns) == 0:
        raise DataLoaderError("The file contains no columns.")

    col_list = list(df.columns)
    seen: set[str] = set()
    dupes: list[str] = []
    for c in col_list:
        if c in seen:
            dupes.append(c)
        seen.add(c)
    if dupes:
        raise DataLoaderError(
            f"Duplicate column names detected: {dupes}. "
            "Please ensure every column has a unique name."
        )

    all_null = [c for c in df.columns if df[c].isna().all()]
    if all_null:
        warnings.append(f"These columns contain only missing values: {all_null}")

    return warnings


def _finalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Apply type inference and cleanup to a parsed DataFrame."""
    # Sanitise column names
    original_columns = list(df.columns)
    clean_columns = [_sanitise_column_name(str(c)) for c in original_columns]

    if len(set(clean_columns)) != len(clean_columns):
        raise DataLoaderError(
            "Duplicate column names detected after sanitisation. "
            "Please rename columns to be unique."
        )
    df.columns = clean_columns

    # Infer numeric dtypes on object columns
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() / max(len(df), 1) > 0.8:
            df[col] = converted

    # Replace inf values
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df


def _build_dataset_info(
    df: pd.DataFrame,
    filename: str,
    file_format: str,
    file_size: int,
    encoding: str,
    warnings: list[str],
) -> DatasetInfo:
    dtypes = {col: str(df[col].dtype) for col in df.columns}
    missing_counts = {col: int(df[col].isna().sum()) for col in df.columns}
    dup_count = int(df.duplicated().sum())

    logger.info(
        "Loaded %s (%s): %d rows × %d cols | %d duplicates | %d missing cells",
        filename, file_format, len(df), len(df.columns),
        dup_count, sum(missing_counts.values()),
    )

    return DatasetInfo(
        df=df,
        filename=filename,
        file_format=file_format,
        row_count=len(df),
        column_count=len(df.columns),
        column_names=list(df.columns),
        dtypes=dtypes,
        missing_counts=missing_counts,
        duplicate_row_count=dup_count,
        file_size_bytes=file_size,
        encoding_detected=encoding,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# CSV Loader
# ---------------------------------------------------------------------------

def load_csv(file_obj, filename: str = "upload.csv") -> DatasetInfo:
    """Load and validate a CSV file."""
    logger.info("Loading CSV: %s", filename)

    raw = _read_raw_bytes(file_obj)
    file_size = len(raw)
    encoding = _detect_encoding(raw)

    # Decode
    text = None
    for enc in ("utf-8-sig", "utf-8", encoding):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        logger.warning("Could not cleanly decode file — using replacement characters.")
        text = raw.decode("utf-8", errors="replace")

    try:
        df = pd.read_csv(io.StringIO(text), low_memory=False)
    except pd.errors.EmptyDataError as exc:
        raise DataLoaderError("The CSV file has no parseable content.") from exc
    except pd.errors.ParserError as exc:
        raise DataLoaderError(f"CSV parsing failed: {exc}") from exc
    except Exception as exc:
        raise DataLoaderError(f"Unexpected error reading CSV: {exc}") from exc

    df = _finalise_df(df)
    warnings = _validate_parsed_df(df, filename)

    return _build_dataset_info(df, filename, "CSV", file_size, encoding, warnings)


# ---------------------------------------------------------------------------
# Excel Loader
# ---------------------------------------------------------------------------

def load_excel(file_obj, filename: str = "upload.xlsx") -> DatasetInfo:
    """Load and validate an Excel file (.xlsx or .xls)."""
    logger.info("Loading Excel: %s", filename)

    raw = _read_raw_bytes(file_obj)
    file_size = len(raw)

    try:
        # Try all sheets; use the first non-empty one
        excel_file = pd.ExcelFile(io.BytesIO(raw))
        sheet_names = excel_file.sheet_names
        logger.info("Excel file has %d sheet(s): %s", len(sheet_names), sheet_names)

        df = None
        used_sheet = sheet_names[0]
        for sheet in sheet_names:
            candidate = pd.read_excel(io.BytesIO(raw), sheet_name=sheet, dtype=str)
            # Drop completely empty rows/cols
            candidate = candidate.dropna(how="all").dropna(axis=1, how="all")
            if not candidate.empty:
                df = candidate
                used_sheet = sheet
                break

        if df is None:
            raise DataLoaderError("All sheets in the Excel file are empty.")

    except DataLoaderError:
        raise
    except Exception as exc:
        raise DataLoaderError(f"Failed to read Excel file: {exc}") from exc

    # Parse numerics
    df = _finalise_df(df)
    warnings = _validate_parsed_df(df, filename)
    if len(sheet_names) > 1:
        warnings.append(
            f"Excel file has {len(sheet_names)} sheets. "
            f"Loaded sheet: '{used_sheet}'. Other sheets: {[s for s in sheet_names if s != used_sheet]}"
        )

    return _build_dataset_info(df, filename, "Excel", file_size, "binary", warnings)


# ---------------------------------------------------------------------------
# PDF Loader
# ---------------------------------------------------------------------------

def load_pdf(file_obj, filename: str = "upload.pdf") -> DatasetInfo:
    """
    Load tabular data from a PDF file.
    Uses pdfplumber for table extraction, with fallback to text-based parsing.
    """
    logger.info("Loading PDF: %s", filename)

    raw = _read_raw_bytes(file_obj)
    file_size = len(raw)

    try:
        import pdfplumber
    except ImportError:
        raise DataLoaderError(
            "pdfplumber is not installed. Run: pip install pdfplumber"
        )

    tables_found = []
    text_content = []

    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            logger.info("PDF has %d page(s)", len(pdf.pages))
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract tables
                page_tables = page.extract_tables()
                for tbl in page_tables:
                    if tbl and len(tbl) > 1:
                        tables_found.append(tbl)

                # Also collect page text for fallback
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
    except Exception as exc:
        raise DataLoaderError(f"Failed to read PDF file: {exc}") from exc

    df = None

    # Strategy 1: Use the largest table found
    if tables_found:
        best_table = max(tables_found, key=lambda t: len(t) * len(t[0]))
        headers = [str(h).strip() if h else f"Column_{i}" for i, h in enumerate(best_table[0])]
        rows = []
        for row in best_table[1:]:
            if any(cell is not None and str(cell).strip() for cell in row):
                rows.append([str(cell).strip() if cell is not None else "" for cell in row])

        if rows:
            # Pad/trim rows to match header count
            n_cols = len(headers)
            padded_rows = [
                (row + [""] * n_cols)[:n_cols] for row in rows
            ]
            df = pd.DataFrame(padded_rows, columns=headers)
            logger.info("Extracted table with %d rows × %d columns from PDF", len(df), len(df.columns))

    # Strategy 2: Parse structured text (e.g., comma/tab separated)
    if df is None and text_content:
        full_text = "\n".join(text_content)
        # Try to parse as CSV
        try:
            df = pd.read_csv(io.StringIO(full_text), sep=None, engine="python")
            logger.info("Parsed PDF text as structured data: %d rows", len(df))
        except Exception:
            df = None

    # Strategy 3: Word-by-word fallback — create a single-column text DataFrame
    if df is None:
        if text_content:
            lines = [line.strip() for line in "\n".join(text_content).split("\n") if line.strip()]
            df = pd.DataFrame({"text_content": lines})
            logger.warning("Could not find tables in PDF — created single-column text DataFrame")
        else:
            raise DataLoaderError(
                "No extractable content found in the PDF. "
                "Please ensure the PDF contains selectable text or tables (not a scanned image)."
            )

    df = _finalise_df(df)
    warnings = _validate_parsed_df(df, filename)
    warnings.insert(0, "PDF data extraction may be imperfect. Please verify the data preview.")

    return _build_dataset_info(df, filename, "PDF", file_size, "binary", warnings)


# ---------------------------------------------------------------------------
# Public Dispatcher
# ---------------------------------------------------------------------------

def load_file(file_obj, filename: str) -> DatasetInfo:
    """
    Auto-detect file format and load accordingly.
    Supports: .csv, .xlsx, .xls, .pdf
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == ".csv":
        return load_csv(file_obj, filename)
    elif ext in (".xlsx", ".xls"):
        return load_excel(file_obj, filename)
    elif ext == ".pdf":
        return load_pdf(file_obj, filename)
    else:
        raise DataLoaderError(
            f"Unsupported file format: {ext!r}. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        )


def load_csv_from_path(path: str) -> DatasetInfo:
    """Convenience wrapper for loading a CSV from a file path."""
    with open(path, "rb") as f:
        return load_csv(f, filename=path.split("/")[-1].split("\\")[-1])


def load_records(
    records: list[dict],
    filename: str,
    file_format: str,
    file_size_bytes: int = 0,
    warnings: list[str] | None = None,
) -> DatasetInfo:
    """Validate records returned by the internal API using the shared loader path."""
    if not records:
        raise DataLoaderError("The selected database table contains no rows.")
    try:
        df = pd.DataFrame.from_records(records)
        df = _finalise_df(df)
        validation_warnings = _validate_parsed_df(df, filename)
    except DataLoaderError:
        raise
    except Exception as exc:
        raise DataLoaderError("The database returned data that could not be loaded.") from exc
    return _build_dataset_info(
        df,
        filename,
        file_format,
        file_size_bytes,
        "database",
        [*(warnings or []), *validation_warnings],
    )
