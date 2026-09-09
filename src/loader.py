"""
Generic tabular data loader.
Works with any .csv or .xlsx file — no hardcoded column names or schema assumptions.
This is the piece that proves the pipeline is data-agnostic: swap the --data path
and everything downstream (narrative generation, indexing, retrieval) adapts automatically.
"""
from pathlib import Path

import pandas as pd


def load_tabular(path: str) -> list[dict]:
    """Load any CSV or Excel file into a list of row-dicts.

    Args:
        path: path to a .csv or .xlsx file.

    Returns:
        List of dicts, one per row, each tagged with a stable 'row_id'.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    elif suffix == ".csv":
        df = pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    # Drop fully empty rows/columns — real-world sheets are messy
    df = df.dropna(how="all").dropna(axis=1, how="all")

    records = df.to_dict(orient="records")
    for i, r in enumerate(records):
        r["row_id"] = f"row_{i:04d}"
    return records