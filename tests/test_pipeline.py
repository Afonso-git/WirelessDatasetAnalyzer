from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wireless_analyzer.ingest import Dataset, DatasetError, ParsedRow, parse_csv
from wireless_analyzer.pipeline import run_pipeline
from wireless_analyzer import reports
from wireless_analyzer.validation import SchemaError, clean_dataset

COLUMNS = [
    "MAC",
    "SSID",
    "AuthMode",
    "FirstSeen",
    "Channel",
    "RSSI",
    "CurrentLatitude",
    "CurrentLongitude",
    "Type",
]

VALID_ROW = [
    "00:11:22:33:44:55",
    "Synthetic network",
    "WPA2",
    "2026-01-01 12:00:00",
    "6",
    "-55",
    "47.123456",
    "-122.123456",
    "WIFI",
]


def write_wigle_csv(path: Path, rows: list[list[str]], compressed: bool) -> None:
    opener = gzip.open if compressed else open
    with opener(path, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["WigleWifi-1.6", "appRelease=test"])
        writer.writerow(COLUMNS)
        writer.writerows(rows)


class IngestionTests(unittest.TestCase):
    def test_reads_plain_csv_with_metadata_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.csv"
            write_wigle_csv(path, [VALID_ROW], compressed=False)
            dataset = parse_csv(path)

        self.assertEqual(dataset.columns, COLUMNS)
        self.assertTrue(dataset.metadata_row_present)
        self.assertEqual(len(dataset.rows), 1)

    def test_reads_gzip_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.csv.gz"
            write_wigle_csv(path, [VALID_ROW], compressed=True)
            dataset = parse_csv(path)

        self.assertEqual(len(dataset.rows), 1)
        self.assertEqual(dataset.rows[0].values[0], VALID_ROW[0])

    def test_rejects_empty_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(DatasetError):
                parse_csv(path)

    def test_detects_semicolon_delimiter(self) -> None:
        for delimiter in (";", "|"):
            with self.subTest(delimiter=delimiter):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "export.csv"
                    path.write_text(
                        delimiter.join(["MAC", "SSID", "AuthMode"])
                        + "\n"
                        + delimiter.join(
                            ["00:11:22:33:44:55", "Synthetic", "WPA2"]
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    dataset = parse_csv(path)

                self.assertEqual(dataset.columns, ["MAC", "SSID", "AuthMode"])
                self.assertEqual(dataset.rows[0].values[2], "WPA2")

    def test_reads_utf8_bom_and_tab_delimiter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.csv"
            path.write_text(
                "\ufeffMAC\tSSID\tAuthMode\n"
                "00:11:22:33:44:55\tSynthetic\tWPA2\n",
                encoding="utf-8",
            )

            dataset = parse_csv(path)

        self.assertEqual(dataset.columns, ["MAC", "SSID", "AuthMode"])
        self.assertEqual(dataset.rows[0].values[0], VALID_ROW[0])

    def test_rejects_malformed_quoting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "malformed.csv"
            path.write_text('MAC,SSID\n"unterminated,value\n', encoding="utf-8")

            with self.assertRaises(DatasetError):
                parse_csv(path)


class ValidationTests(unittest.TestCase):
    def dataset_for(self, rows: list[list[str]]):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.csv"
            write_wigle_csv(path, rows, compressed=False)
            return parse_csv(path)

    def test_counts_duplicate_malformed_and_invalid_records(self) -> None:
        missing_identifier = VALID_ROW.copy()
        missing_identifier[0] = ""
        bad_coordinate = VALID_ROW.copy()
        bad_coordinate[6] = "91"
        bad_rssi = VALID_ROW.copy()
        bad_rssi[5] = "not-a-number"
        partial_coordinate = VALID_ROW.copy()
        partial_coordinate[7] = ""
        wrong_width = VALID_ROW[:-1]

        dataset = self.dataset_for(
            [
                VALID_ROW,
                VALID_ROW,
                missing_identifier,
                bad_coordinate,
                bad_rssi,
                partial_coordinate,
                wrong_width,
            ]
        )
        result = clean_dataset(dataset)

        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(result.malformed_row_count, 1)
        self.assertEqual(
            result.rejection_counts,
            {
                "duplicate_record": 1,
                "incomplete_coordinate_pair": 1,
                "invalid_numeric_value": 1,
                "invalid_coordinate": 1,
                "missing_network_identifier": 1,
                "wrong_column_count": 1,
            },
        )

    def test_rejects_non_numeric_and_non_finite_coordinates(self) -> None:
        bad_coordinates = []
        for latitude, longitude in [
            ("north", "-122"),
            ("NaN", "-122"),
            ("47", "Infinity"),
        ]:
            row = VALID_ROW.copy()
            row[6] = latitude
            row[7] = longitude
            bad_coordinates.append(row)

        result = clean_dataset(self.dataset_for(bad_coordinates))

        self.assertEqual(result.accepted, [])
        self.assertEqual(result.rejection_counts, {"invalid_coordinate": 3})

    def test_requires_network_identifier_column(self) -> None:
        dataset = Dataset(
            columns=["SSID", "AuthMode"],
            rows=[ParsedRow(record_number=1, values=["example", "WPA2"])],
            metadata_row_present=False,
        )
        with self.assertRaises(SchemaError):
            clean_dataset(dataset)

    def test_allows_both_coordinates_to_be_missing(self) -> None:
        missing_coordinates = VALID_ROW.copy()
        missing_coordinates[6] = ""
        missing_coordinates[7] = "N/A"
        dataset = self.dataset_for([missing_coordinates])

        result = clean_dataset(dataset)

        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.rejection_counts, {})

    def test_allows_missing_optional_numeric_values(self) -> None:
        dataset = Dataset(
            columns=["MAC", "Channel", "Frequency", "RSSI"],
            rows=[
                ParsedRow(
                    record_number=1,
                    values=["00:11:22:33:44:55", "", "N/A", "null"],
                )
            ],
            metadata_row_present=False,
        )

        result = clean_dataset(dataset)

        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.rejection_counts, {})

    def test_distinct_observations_with_different_timestamps_are_not_duplicates(
        self,
    ) -> None:
        later_observation = VALID_ROW.copy()
        later_observation[3] = "2026-01-01 12:01:00"
        dataset = self.dataset_for([VALID_ROW, later_observation])

        result = clean_dataset(dataset)

        self.assertEqual(len(result.accepted), 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_whitespace_difference_in_ssid_is_not_normalized_for_deduplication(
        self,
    ) -> None:
        whitespace_variant = VALID_ROW.copy()
        whitespace_variant[1] = " Synthetic network "

        result = clean_dataset(self.dataset_for([VALID_ROW, whitespace_variant]))

        self.assertEqual(len(result.accepted), 2)
        self.assertEqual(result.duplicate_count, 0)


class OutputTests(unittest.TestCase):
    def test_channel_chart_orders_numeric_categories(self) -> None:
        dataset = Dataset(
            columns=["MAC", "Channel"],
            rows=[
                ParsedRow(record_number=1, values=["first", "10"]),
                ParsedRow(record_number=2, values=["second", "2"]),
            ],
            metadata_row_present=False,
        )
        result = clean_dataset(dataset)
        captured_labels: list[str] = []

        def draw_and_capture(_path: Path, draw) -> None:
            draw()
            import matplotlib.pyplot as plt

            try:
                captured_labels.extend(
                    label.get_text() for label in plt.gca().get_xticklabels()
                )
            finally:
                plt.close()

        with patch(
            "wireless_analyzer.reports._save_chart",
            side_effect=draw_and_capture,
        ):
            reports._make_charts(dataset, result, Path("."))

        self.assertEqual(captured_labels, ["2", "10"])

    def test_geographic_chart_respects_grid_cap_at_world_extremes(self) -> None:
        dataset = Dataset(
            columns=["MAC", "CurrentLatitude", "CurrentLongitude"],
            rows=[
                ParsedRow(1, ["synthetic-a", "-90", "-180"]),
                ParsedRow(2, ["synthetic-b", "90", "180"]),
            ],
            metadata_row_present=False,
        )
        result = clean_dataset(dataset)
        captured_grid_sizes: list[int] = []

        def capture_histogram(_path: Path, draw) -> None:
            import matplotlib.pyplot as plt

            original_hist2d = plt.hist2d

            def capture_hist2d_bins(x, y, bins, **kwargs):
                captured_grid_sizes.extend(len(edges) - 1 for edges in bins)
                return original_hist2d(x, y, bins=bins, **kwargs)

            with patch("matplotlib.pyplot.hist2d", side_effect=capture_hist2d_bins):
                try:
                    draw()
                finally:
                    plt.close()

        with patch(
            "wireless_analyzer.reports._save_chart",
            side_effect=capture_histogram,
        ):
            reports._make_charts(dataset, result, Path("."))

        self.assertEqual(len(captured_grid_sizes), 2)
        self.assertTrue(
            all(
                size <= reports.MAX_DENSITY_GRID_CELLS_PER_AXIS
                for size in captured_grid_sizes
            )
        )

    def test_pipeline_writes_aggregate_report_and_charts_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "sample.csv.gz"
            output_dir = root / "output"
            second_row = VALID_ROW.copy()
            second_row[0] = "00:11:22:33:44:66"
            second_row[1] = "Another synthetic network"
            second_row[5] = "-70"
            second_row[6] = "47.124"
            second_row[7] = "-122.124"
            write_wigle_csv(input_path, [VALID_ROW, second_row], compressed=True)

            report = run_pipeline(input_path, output_dir)

            report_text = (output_dir / "report.json").read_text(encoding="utf-8")
            parsed = json.loads(report_text)
            self.assertEqual(report["accepted_rows"], 2)
            self.assertEqual(parsed["rejected_rows"], 0)
            self.assertEqual(parsed["valid_coordinate_rows"], 2)
            self.assertEqual(parsed["numeric_summaries"]["RSSI"]["mean"], -62.5)
            self.assertNotIn("CurrentLatitude", parsed["numeric_summaries"])
            self.assertNotIn("CurrentLongitude", parsed["numeric_summaries"])
            self.assertIn("geographic_density.png", parsed["charts"])
            self.assertTrue((output_dir / "signal_strength.png").is_file())
            self.assertTrue((output_dir / "authentication_modes.png").is_file())
            self.assertTrue((output_dir / "channels.png").is_file())
            self.assertTrue((output_dir / "geographic_density.png").is_file())
            self.assertNotIn(VALID_ROW[0], report_text)
            self.assertNotIn(VALID_ROW[1], report_text)
            self.assertNotIn(VALID_ROW[6], report_text)
            self.assertNotIn(VALID_ROW[7], report_text)

    def test_geographic_chart_coarsens_for_wide_extent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "wide.csv"
            output_dir = root / "output"
            distant_row = VALID_ROW.copy()
            distant_row[0] = "00:11:22:33:44:77"
            distant_row[6] = "-89"
            distant_row[7] = "179"
            write_wigle_csv(input_path, [VALID_ROW, distant_row], compressed=False)

            report = run_pipeline(input_path, output_dir)

            self.assertIn("geographic_density.png", report["charts"])
            self.assertTrue((output_dir / "geographic_density.png").is_file())

    def test_rerun_removes_obsolete_analyzer_charts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "sample.csv"
            output_dir = root / "output"
            write_wigle_csv(input_path, [VALID_ROW], compressed=False)
            run_pipeline(input_path, output_dir)
            self.assertTrue((output_dir / "geographic_density.png").exists())

            columns_without_coordinates = [
                column
                for column in COLUMNS
                if column not in {"CurrentLatitude", "CurrentLongitude"}
            ]
            row_without_coordinates = [
                value
                for column, value in zip(COLUMNS, VALID_ROW)
                if column in columns_without_coordinates
            ]
            with input_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns_without_coordinates)
                writer.writerow(row_without_coordinates)
            report = run_pipeline(input_path, output_dir)

            self.assertNotIn("geographic_density.png", report["charts"])
            self.assertFalse((output_dir / "geographic_density.png").exists())
            self.assertTrue((output_dir / "signal_strength.png").exists())


if __name__ == "__main__":
    unittest.main()
