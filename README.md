Wireless Dataset Analyzer

A Python pipeline for cleaning, validating, and analyzing WiGLE wireless network exports. This project combines data engineering fundamentals with my interest in wardriving.

Features

Reads CSV and gzip-compressed CSV (.csv.gz) files.

Detects common delimiters and handles UTF-8 BOM and WiGLE metadata rows.

Validates network identifiers, row structure, numeric fields, and geographic coordinates.

Detects exact duplicate records.

Generates an aggregate JSON report and up to four charts covering signal strength, authentication modes, channels, and geographic density.

Includes automated tests using synthetic datasets.

Privacy

All processing is local. The application does not upload data, send telemetry, or call external services. It does not export cleaned row-level records.

Reports and geographic heatmaps can still reveal sensitive information. Keep raw datasets and generated outputs private, and review any files before sharing them. The project does not include real WiGLE exports.

Requirements and installation

Python 3.10 or newer

Matplotlib

Create a virtual environment and install the project from the repository root:

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

Usage

Pass a WiGLE CSV or .csv.gz file to the command-line interface:

.\.venv\Scripts\wireless-analyzer.exe --input "C:\path\to\export.csv.gz" --output output

The default output directory is output. The command reports accepted, rejected, and duplicate record counts, along with the generated report and charts.

Output

The pipeline generates report.json, containing aggregate counts, column completeness statistics, exclusion reasons, numeric summaries, and generated chart filenames.

Available charts:

signal_strength.png — RSSI distribution.

authentication_modes.png — authentication categories.

channels.png — observations by channel.

geographic_density.png — geographic density heatmap when usable coordinates are available.

The heatmap uses coarse geographic bins. This reduces coordinate precision but does not guarantee anonymity.

Validation

The pipeline rejects invalid schemas, missing network identifiers, malformed rows, invalid coordinate pairs, and invalid nonblank numeric values in recognized fields. Records without coordinates are retained when both coordinate fields are blank.

Exact duplicate rows are counted and excluded, keeping the first occurrence. Structural CSV parsing errors stop the run rather than being treated as ordinary rejected records.

Tests

Run the test suite with:

.\.venv\Scripts\python.exe -m unittest discover -s tests -v

Tests use temporary synthetic CSV and gzip data. GitHub Actions automatically runs the test suite on Python 3.10 and 3.14.

Project structure

src/wireless_analyzer/ingest.py — input parsing.

src/wireless_analyzer/validation.py — validation and duplicate detection.

src/wireless_analyzer/reports.py — reports and charts.

src/wireless_analyzer/pipeline.py — pipeline orchestration.

src/wireless_analyzer/cli.py — command-line interface.

tests/ — automated tests.

Limitations and future work

The pipeline keeps parsed records in memory and is intended for modest datasets. It does not geocode, publish, or store data in a database.

Potential next steps include PostgreSQL/PostGIS integration and an interactive map using FastAPI and Leaflet.

License

MIT. See LICENSE.