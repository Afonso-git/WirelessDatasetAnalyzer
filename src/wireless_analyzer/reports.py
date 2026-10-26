"""Aggregate-only reports and privacy-conscious visualizations."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from wireless_analyzer.ingest import Dataset
from wireless_analyzer.validation import (
    NUMERIC_COLUMNS,
    ValidationResult,
    normalized_name,
)

COARSE_COORDINATE_BIN_DEGREES = 0.025
MAX_DENSITY_GRID_CELLS_PER_AXIS = 250
GENERATED_CHARTS = {
    "signal_strength.png",
    "authentication_modes.png",
    "channels.png",
    "geographic_density.png",
}


def _column_by_names(columns: list[str], aliases: set[str]) -> str | None:
    for column in columns:
        if normalized_name(column) in aliases:
            return column
    return None


def _save_chart(path: Path, draw: Callable[[], None]) -> None:
    figure = plt.figure(figsize=(9, 5))
    try:
        draw()
        figure.tight_layout()
        figure.savefig(path, dpi=140)
    finally:
        plt.close(figure)


def _numeric_values(
    rows: list[dict[str, str]], column: str
) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row[column])
        except (ValueError, KeyError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def _numeric_summaries(
    dataset: Dataset, result: ValidationResult
) -> dict[str, dict[str, int | float]]:
    summaries = {}
    for column in dataset.columns:
        if normalized_name(column) not in NUMERIC_COLUMNS:
            continue
        values = _numeric_values(result.accepted, column)
        if not values:
            continue
        summaries[column] = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": mean(values),
            "median": median(values),
        }
    return summaries


def _make_charts(
    dataset: Dataset, result: ValidationResult, output_dir: Path
) -> list[str]:
    charts: list[str] = []
    accepted = result.accepted

    rssi_column = _column_by_names(dataset.columns, {"rssi", "signalstrength"})
    if rssi_column:
        values = _numeric_values(accepted, rssi_column)
        if values:
            def draw_rssi() -> None:
                plt.hist(values, bins=24, color="#276FBF", edgecolor="white")
                plt.title("Signal strength distribution")
                plt.xlabel("RSSI (dBm)")
                plt.ylabel("Observations")

            filename = "signal_strength.png"
            _save_chart(output_dir / filename, draw_rssi)
            charts.append(filename)

    auth_column = _column_by_names(
        dataset.columns, {"authmode", "authentication", "security"}
    )
    if auth_column:
        counts = Counter(
            row[auth_column].strip() or "(blank)" for row in accepted
        )
        if counts:
            common = counts.most_common(12)

            def draw_auth() -> None:
                labels, frequencies = zip(*common)
                plt.barh(list(reversed(labels)), list(reversed(frequencies)), color="#2A9D8F")
                plt.title("Most common authentication modes")
                plt.xlabel("Observations")

            filename = "authentication_modes.png"
            _save_chart(output_dir / filename, draw_auth)
            charts.append(filename)

    channel_column = _column_by_names(dataset.columns, {"channel"})
    if channel_column:
        counts = Counter(
            row[channel_column].strip()
            for row in accepted
            if row[channel_column].strip()
        )
        if counts:
            common = sorted(counts.items(), key=lambda item: float(item[0]))

            def draw_channels() -> None:
                labels, frequencies = zip(*common)
                plt.bar(labels, frequencies, color="#E76F51")
                plt.title("Observations by channel")
                plt.xlabel("Channel")
                plt.ylabel("Observations")
                plt.xticks(rotation=45, ha="right")

            filename = "channels.png"
            _save_chart(output_dir / filename, draw_channels)
            charts.append(filename)

    if result.coordinate_columns:
        lat_column, lon_column = result.coordinate_columns
        points = []
        for row in accepted:
            try:
                lat = float(row[lat_column])
                lon = float(row[lon_column])
            except (ValueError, KeyError):
                continue
            if math.isfinite(lat) and math.isfinite(lon):
                points.append((lat, lon))
        if points:
            def draw_geography() -> None:
                latitudes, longitudes = zip(*points)
                latitude_step = max(
                    COARSE_COORDINATE_BIN_DEGREES,
                    (max(latitudes) - min(latitudes))
                    / (MAX_DENSITY_GRID_CELLS_PER_AXIS - 1),
                )
                longitude_step = max(
                    COARSE_COORDINATE_BIN_DEGREES,
                    (max(longitudes) - min(longitudes))
                    / (MAX_DENSITY_GRID_CELLS_PER_AXIS - 1),
                )
                lat_bin_min = math.floor(min(latitudes) / latitude_step)
                lat_bin_max = math.floor(max(latitudes) / latitude_step)
                lon_bin_min = math.floor(min(longitudes) / longitude_step)
                lon_bin_max = math.floor(max(longitudes) / longitude_step)
                latitude_edges = [
                    index * latitude_step
                    for index in range(lat_bin_min, lat_bin_max + 2)
                ]
                longitude_edges = [
                    index * longitude_step
                    for index in range(lon_bin_min, lon_bin_max + 2)
                ]
                plt.hist2d(
                    longitudes,
                    latitudes,
                    bins=(longitude_edges, latitude_edges),
                    cmap="viridis",
                )
                plt.title("Coarse geographic observation density")
                plt.xlabel("Longitude (coarsened)")
                plt.ylabel("Latitude (coarsened)")
                plt.xticks([])
                plt.yticks([])

            filename = "geographic_density.png"
            _save_chart(output_dir / filename, draw_geography)
            charts.append(filename)

    return charts


def write_outputs(
    dataset: Dataset,
    profile: dict[str, object],
    result: ValidationResult,
    output_dir: Path,
) -> dict[str, object]:
    """Write deterministic aggregate output; raw records are never exported."""
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted_count = len(result.accepted)
    rejected_count = sum(result.rejection_counts.values())
    coordinate_count = 0
    if result.coordinate_columns:
        lat_column, lon_column = result.coordinate_columns
        coordinate_count = sum(
            row.get(lat_column, "").strip().casefold()
            not in {"", "na", "n/a", "null", "none"}
            and row.get(lon_column, "").strip().casefold()
            not in {"", "na", "n/a", "null", "none"}
            for row in result.accepted
        )

    charts = _make_charts(dataset, result, output_dir)
    for stale_chart in GENERATED_CHARTS.difference(charts):
        (output_dir / stale_chart).unlink(missing_ok=True)
    report: dict[str, object] = {
        **profile,
        "accepted_rows": accepted_count,
        "rejected_rows": rejected_count,
        "rejection_counts": result.rejection_counts,
        "duplicate_rows": result.duplicate_count,
        "malformed_rows": result.malformed_row_count,
        "numeric_summaries": _numeric_summaries(dataset, result),
        "valid_coordinate_rows": coordinate_count,
        "charts": charts,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
