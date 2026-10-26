"""Command-line interface for the analysis pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wireless_analyzer.ingest import DatasetError
from wireless_analyzer.pipeline import run_pipeline
from wireless_analyzer.validation import SchemaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wireless-analyzer",
        description=(
            "Profile and analyze a WiGLE CSV export. Reports contain aggregates, "
            "not network identifiers or raw coordinate values."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input CSV or gzip-compressed CSV file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory (default: ./output).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_pipeline(args.input, args.output)
    except (DatasetError, SchemaError) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Unable to write analysis output ({type(exc).__name__}).", file=sys.stderr)
        return 2

    print(
        "Analysis complete: "
        f"{report['accepted_rows']} accepted, "
        f"{report['rejected_rows']} rejected, "
        f"{report['duplicate_rows']} duplicates."
    )
    print(f"Aggregate report: {args.output / 'report.json'}")
    print(f"Charts generated: {len(report['charts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
