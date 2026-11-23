"""Command-line entry point.

Run:  python -m cleaning.cli data/raw/customers_messy.csv --out-dir data/clean
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from cleaning.pipeline import clean_customers, escape_formulas

MAX_INPUT_BYTES = 50 * 1024 * 1024  # refuse unexpectedly huge files


def render_markdown(report: dict) -> str:
    lines = [
        "# Data quality report",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Rows in | {report['rows_in']:,} |",
        f"| Clean rows out | {report['rows_clean']:,} |",
        f"| Rejected rows | {report['rows_rejected']:,} |",
        f"| Duplicates removed | {report['duplicates_removed']:,} |",
        "",
        "## Rejection reasons",
        "",
        "| Reason | Rows |",
        "| --- | --- |",
        *[f"| {k} | {v} |" for k, v in report["rejection_reasons"].items()],
        "",
        "## Field validity (share of non-empty raw values that could be standardized)",
        "",
        "| Field | Valid |",
        "| --- | --- |",
        *[
            f"| {k} | {'n/a' if v is None else f'{v:.1%}'} |"
            for k, v in report["field_validity_rate"].items()
        ],
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean a messy customer CSV.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if not args.input.is_file():
        parser.error(f"input file not found: {args.input}")
    if args.input.stat().st_size > MAX_INPUT_BYTES:
        parser.error("input file is larger than 50 MB")

    # dtype=str: read everything as text so pandas never guesses types for us.
    raw = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    result = clean_customers(raw)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    escape_formulas(result.clean).to_csv(args.out_dir / "customers_clean.csv", index=False)
    escape_formulas(result.rejected).to_csv(args.out_dir / "customers_rejected.csv", index=False)
    (args.out_dir / "quality_report.json").write_text(json.dumps(result.report, indent=2))
    (args.out_dir / "quality_report.md").write_text(render_markdown(result.report))

    r = result.report
    print(
        f"{r['rows_in']:,} rows in -> {r['rows_clean']:,} clean, "
        f"{r['rows_rejected']:,} rejected, {r['duplicates_removed']:,} duplicates removed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
