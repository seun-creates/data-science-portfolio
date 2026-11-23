"""Command-line entry point.

python -m etl.cli load data/raw/orders.jsonl --db data/warehouse.db
python -m etl.cli report --db data/warehouse.db
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from etl.pipeline import connect, load_file, load_queries


def cmd_load(args: argparse.Namespace) -> int:
    if not args.source.is_file():
        raise SystemExit(f"source file not found: {args.source}")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as conn:
        s = load_file(conn, args.source)
    print(
        f"run {s.run_id}: {s.lines_read:,} lines read -> {s.loaded:,} loaded, "
        f"{s.rejected:,} rejected, {s.duplicates:,} duplicates skipped"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if not args.db.is_file():
        raise SystemExit(f"database not found: {args.db} (run the load command first)")
    pd.set_option("display.width", 120)
    with connect(args.db) as conn:
        for name, sql in load_queries().items():
            print(f"\n== {name} ==")
            print(pd.read_sql_query(sql, conn).to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sales ETL into SQLite.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_load = sub.add_parser("load", help="load a JSONL file into the warehouse")
    p_load.add_argument("source", type=Path)
    p_load.add_argument("--db", type=Path, required=True)
    p_load.set_defaults(func=cmd_load)

    p_report = sub.add_parser("report", help="run the analytics queries")
    p_report.add_argument("--db", type=Path, required=True)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
