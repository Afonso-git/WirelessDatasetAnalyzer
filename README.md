Motivation and Use Case

Wireless Dataset Analyzer was developed for two complementary purposes: as a practical data analysis project for my software development portfolio and as a personal tool for my interest in wardriving.

Wardriving involves collecting observations of nearby wireless networks while travelling through an area. This project focuses on the data analysis stage: processing WiGLE exports, validating records, identifying duplicates, summarising wireless network characteristics, and visualising signal strength, authentication modes, channel distribution, and geographic density.

The project provides hands-on experience with Python, data cleaning, validation, data processing pipelines, automated testing, and data visualisation, while helping me explore wireless network distributions in datasets collected for personal research.

Privacy: Dataset processing is performed locally. Do not publish raw datasets containing identifiable or sensitive information. Only collect and analyse wireless data in accordance with applicable laws and respect for others' privacy.




# Wireless Dataset Analyzer

A small, reproducible Python pipeline for profiling and analyzing WiGLE CSV
exports. The first version reads plain CSV and gzip-compressed CSV, validates
records, and produces aggregate reports and static charts. It does not modify
the input or export cleaned row-level data.

All processing happens locally. The application does not upload user data,
send telemetry, or call external services. No real export or bundled sample
dataset is included in the project; tests generate synthetic records at
runtime.

## Observed export format

The available full export was inspected without printing any record values. It
contains a WiGLE metadata row, then a 14-column header, followed by 11,411 data
records. The verified header is:

`MAC`, `SSID`, `AuthMode`, `FirstSeen`, `Channel`, `Frequency`, `RSSI`,
`CurrentLatitude`, `CurrentLongitude`, `AltitudeMeters`, `AccuracyMeters`,
`RCOIs`, `MfgrId`, `Type`.

A second available export contained the metadata and header but no data records.
The program recognizes the metadata-row format but does not assume that every
input has this exact set of columns. It requires a `MAC` or `BSSID` column.
Geographic processing is enabled only when a recognized latitude and longitude
column are both present.

## Requirements and installation

- Python 3.10 or newer.
- Matplotlib for chart generation.

From the project directory in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

The input reader and validator use only the Python standard library. Matplotlib
is the only runtime dependency; the automated tests use `unittest`.

## Run the pipeline

Pass the path to a `.csv` or `.csv.gz` file. The default output directory is
`output` under the current directory.

```powershell
.\.venv\Scripts\wireless-analyzer.exe --input "C:\path\to\WigleWifi_export.csv.gz" --output output
```

Equivalent module invocation:

```powershell
.\.venv\Scripts\python.exe -m wireless_analyzer.cli --input "C:\path\to\WigleWifi_export.csv.gz" --output output
```

The command prints aggregate accepted/rejected/duplicate counts, the report
location, and the number of charts generated. It does not print row values,
MAC addresses, SSIDs, or coordinates.

## Outputs

`output\report.json` contains:

- Header names and per-column present/missing counts, not column values.
- Input, accepted, and rejected row totals.
- Exclusion counts by reason, including malformed row widths and duplicates.
- Count, minimum, maximum, mean, and median for recognized non-geographic
  numeric fields (`Channel`, `Frequency`, `RSSI`, `AltitudeMeters`, and
  `AccuracyMeters`) when valid values are available.
- A count of accepted records with coordinate pairs.
- The names of generated chart files.

Charts are generated only when suitable columns and usable values are present:

- `signal_strength.png` — RSSI distribution.
- `authentication_modes.png` — most common authentication categories.
- `channels.png` — observations by channel.
- `geographic_density.png` — a coarse density heatmap, when both coordinate
  columns exist and accepted rows have usable coordinates.

The geographic heatmap aggregates points into bins no finer than 0.025 degrees
and hides axis tick values. For wide geographic extents, bins are made coarser
to cap the grid at 250 cells per axis. This reduces coordinate precision but
does not guarantee anonymity: location clusters can still be sensitive. Keep
reports and charts private and review them before sharing. Row-level input data
is never included in the report or exported to the output directory.

The project ignores CSV/CSV.GZ files, a `data/` directory, and directories
whose names start with `output` to reduce the chance of accidentally publishing
raw exports or generated reports. KML files and common virtual environment
directories are ignored as well. Ignore rules do not remove files already
tracked by Git; review the staged file list before publishing. Keep raw data
and generated reports/charts out of public repositories even when they are
coarse-grained or aggregate-only.

## Validation and cleaning rules

1. Detect comma, semicolon, tab, or pipe delimiters; read UTF-8 CSV, including an
   optional UTF-8 BOM. `.gz` files are decompressed while reading. A WiGLE
   metadata row beginning with `WigleWifi-` is skipped.
2. Reject files without a usable, unique header or without a `MAC`/`BSSID`
   column. If only one coordinate column is present, report a schema error.
3. Reject data rows whose field count differs from the header.
4. Reject rows with a blank network identifier.
5. If both coordinate values are blank, retain the record as non-geographic.
   Reject a half-present, nonnumeric, non-finite, or out-of-range coordinate
   pair (latitude outside -90..90 or longitude outside -180..180).
6. For recognized `Channel`, `Frequency`, `RSSI`, `AltitudeMeters`, and
   `AccuracyMeters` columns, allow blank values but reject nonnumeric or
   non-finite nonblank values. No undocumented value ranges are assumed.
7. Detect duplicates among otherwise valid rows by exact equality after
   CSV parsing, without trimming field values. Keep the first occurrence and
   count later copies as rejected duplicates. Whitespace differences in values
   such as SSIDs are retained as distinct records.

Other fields are preserved in memory for aggregate analysis but are not subject
to undocumented assumptions or range checks. Structural CSV parse errors fail the run explicitly rather than being treated
as ordinary bad records. Use separate output directories for concurrent runs;
on sequential reruns, obsolete analyzer-generated chart files are removed.

## Architecture

- `src/wireless_analyzer/ingest.py` — CSV/gzip parsing and header handling.
- `src/wireless_analyzer/validation.py` — schema checks, profiling, validation,
  duplicate detection, and cleaning.
- `src/wireless_analyzer/reports.py` — aggregate report and charts.
- `src/wireless_analyzer/pipeline.py` — end-to-end orchestration.
- `src/wireless_analyzer/cli.py` — command-line entry point.
- `tests/` — synthetic CSV/gzip fixtures and pipeline tests.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests create temporary synthetic input and do not need access to the real
export. They cover CSV and gzip parsing, schema requirements, validation,
duplicate and malformed-row counts, privacy-safe report contents, and output
chart generation.

## Limitations and next steps

This version keeps all parsed records in memory, so it is intended for modest
exports. It does not geocode observations, publish data, or connect to a
database. A future PostgreSQL/PostGIS integration can build on the validated
schema and aggregate outputs without being required to run this pipeline.
