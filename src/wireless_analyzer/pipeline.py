"""End-to-end dataset analysis orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wireless_analyzer.ingest import DatasetError, parse_csv
from wireless_analyzer.reports import write_outputs
from wireless_analyzer.validation import clean_dataset, profile_dataset


def run_pipeline(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if not input_path.is_file():
        raise DatasetError("Input path does not point to a file.")
    dataset = parse_csv(input_path)
    profile = profile_dataset(dataset)
    result = clean_dataset(dataset)
    return write_outputs(dataset, profile, result, output_dir)
