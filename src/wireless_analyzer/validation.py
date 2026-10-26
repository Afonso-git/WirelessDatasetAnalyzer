"""Schema checks, privacy-safe profiling, and deterministic record cleaning."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from wireless_analyzer.ingest import Dataset, ParsedRow

IDENTIFIER_COLUMNS = {"mac", "bssid"}
LATITUDE_COLUMNS = {"currentlatitude", "latitude", "lat"}
LONGITUDE_COLUMNS = {"currentlongitude", "longitude", "lon", "lng"}
NUMERIC_COLUMNS = {
    "channel",
    "frequency",
    "rssi",
    "altitudemeters",
    "accuracymeters",
}
MISSING_VALUES = {"", "na", "n/a", "null", "none"}


class SchemaError(ValueError):
    """Raised when required dataset structure is absent or inconsistent."""


@dataclass(frozen=True)
class ValidationResult:
    """Accepted records and counts for every excluded-record reason."""

    accepted: list[dict[str, str]]
    rejection_counts: dict[str, int]
    duplicate_count: int
    malformed_row_count: int
    coordinate_columns: tuple[str, str] | None


def normalized_name(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())


def _find_column(columns: list[str], candidates: set[str]) -> str | None:
    for column in columns:
        if normalized_name(column) in candidates:
            return column
    return None


def validate_schema(columns: list[str]) -> tuple[str, tuple[str, str] | None]:
    identifier_column = _find_column(
        columns, {normalized_name(name) for name in IDENTIFIER_COLUMNS}
    )
    if identifier_column is None:
        raise SchemaError("A MAC or BSSID column is required.")

    latitude = _find_column(
        columns, {normalized_name(name) for name in LATITUDE_COLUMNS}
    )
    longitude = _find_column(
        columns, {normalized_name(name) for name in LONGITUDE_COLUMNS}
    )
    if (latitude is None) != (longitude is None):
        raise SchemaError("Latitude and longitude columns must be present together.")

    coordinates = (latitude, longitude) if latitude and longitude else None
    return identifier_column, coordinates


def profile_dataset(dataset: Dataset) -> dict[str, object]:
    column_profiles = []
    for index, name in enumerate(dataset.columns):
        non_empty = sum(
            index < len(row.values)
            and row.values[index].strip().casefold() not in MISSING_VALUES
            for row in dataset.rows
        )
        column_profiles.append(
            {
                "name": name,
                "non_empty_values": non_empty,
                "missing_values": len(dataset.rows) - non_empty,
            }
        )
    return {
        "columns": dataset.columns,
        "column_profiles": column_profiles,
        "input_rows": len(dataset.rows),
        "wigle_metadata_row_present": dataset.metadata_row_present,
    }


def _row_rejection(
    row: ParsedRow,
    columns: list[str],
    identifier_column: str,
    coordinate_columns: tuple[str, str] | None,
) -> str | None:
    if len(row.values) != len(columns):
        return "wrong_column_count"

    values = dict(zip(columns, row.values))
    if values[identifier_column].strip().casefold() in MISSING_VALUES:
        return "missing_network_identifier"

    for column in columns:
        if normalized_name(column) not in NUMERIC_COLUMNS:
            continue
        text = values[column].strip()
        if text.casefold() in MISSING_VALUES:
            continue
        try:
            numeric_value = float(text)
        except ValueError:
            return "invalid_numeric_value"
        if not math.isfinite(numeric_value):
            return "invalid_numeric_value"

    if coordinate_columns:
        latitude_text = values[coordinate_columns[0]].strip()
        longitude_text = values[coordinate_columns[1]].strip()
        latitude_missing = latitude_text.casefold() in MISSING_VALUES
        longitude_missing = longitude_text.casefold() in MISSING_VALUES
        if latitude_missing and longitude_missing:
            return None
        if latitude_missing != longitude_missing:
            return "incomplete_coordinate_pair"
        try:
            latitude = float(latitude_text)
            longitude = float(longitude_text)
        except ValueError:
            return "invalid_coordinate"
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            return "invalid_coordinate"
    return None


def clean_dataset(dataset: Dataset) -> ValidationResult:
    identifier_column, coordinate_columns = validate_schema(dataset.columns)
    accepted: list[dict[str, str]] = []
    rejections: Counter[str] = Counter()
    seen_rows: set[tuple[str, ...]] = set()
    malformed_row_count = 0

    for row in dataset.rows:
        reason = _row_rejection(
            row, dataset.columns, identifier_column, coordinate_columns
        )
        if reason:
            rejections[reason] += 1
            if reason == "wrong_column_count":
                malformed_row_count += 1
            continue

        fingerprint = tuple(row.values)
        if fingerprint in seen_rows:
            rejections["duplicate_record"] += 1
            continue
        seen_rows.add(fingerprint)
        accepted.append(dict(zip(dataset.columns, row.values)))

    return ValidationResult(
        accepted=accepted,
        rejection_counts=dict(sorted(rejections.items())),
        duplicate_count=rejections["duplicate_record"],
        malformed_row_count=malformed_row_count,
        coordinate_columns=coordinate_columns,
    )
