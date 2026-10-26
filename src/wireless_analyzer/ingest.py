"""CSV and gzip ingestion for WiGLE-style exports."""

from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


class DatasetError(ValueError):
    """Raised when an input cannot be interpreted as a supported dataset."""


@dataclass(frozen=True)
class ParsedRow:
    """A row and its CSV record number, without exposing its contents in logs."""

    record_number: int
    values: list[str]


@dataclass(frozen=True)
class Dataset:
    """Parsed header and rows from a CSV input."""

    columns: list[str]
    rows: list[ParsedRow]
    metadata_row_present: bool


def _open_text(path: Path) -> TextIO:
    if path.suffix.casefold() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("rt", encoding="utf-8-sig", newline="")


def _is_wigle_metadata(row: list[str] | None) -> bool:
    return bool(row and row[0].strip().casefold().startswith("wiglewifi-"))


def parse_csv(path: Path) -> Dataset:
    """Read a CSV or gzip CSV, handling the optional WiGLE metadata row."""
    try:
        with _open_text(path) as stream:
            sample = stream.read(8192)
            stream.seek(0)
            sample_lines = sample.splitlines()
            if sample_lines and sample_lines[0].lstrip().casefold().startswith(
                "wiglewifi-"
            ):
                sample_lines = sample_lines[1:]
            sample = sample_lines[0] if sample_lines else sample
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error as exc:
                raise DatasetError("Unable to detect a supported CSV delimiter.") from exc
            reader = csv.reader(stream, dialect=dialect, strict=True)
            first_row = next(reader, None)
            if not first_row:
                raise DatasetError("Input is empty or has no CSV header.")

            metadata_present = _is_wigle_metadata(first_row)
            columns = next(reader, None) if metadata_present else first_row
            if not columns or not any(column.strip() for column in columns):
                raise DatasetError("Input is missing a usable CSV header.")

            cleaned_columns = [column.strip() for column in columns]
            normalized = [column.casefold() for column in cleaned_columns]
            if any(not column for column in cleaned_columns):
                raise DatasetError("CSV header contains an empty column name.")
            if len(set(normalized)) != len(normalized):
                raise DatasetError("CSV header contains duplicate column names.")

            rows = [
                ParsedRow(record_number=index, values=row)
                for index, row in enumerate(reader, start=1)
            ]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DatasetError(
            f"Unable to read CSV input ({type(exc).__name__})."
        ) from exc

    return Dataset(
        columns=cleaned_columns,
        rows=rows,
        metadata_row_present=metadata_present,
    )
