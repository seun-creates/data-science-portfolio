"""Extract -> validate -> load, with an audit trail of every run.

Security notes:
- Every SQL statement uses ? placeholders. User data is never formatted into SQL.
- Input lines are size-capped before parsing to avoid memory exhaustion.
- Rejected lines are stored truncated, so a giant or hostile line can't bloat the DB.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from etl.models import OrderEvent

SQL_DIR = Path(__file__).parent / "sql"
MAX_LINE_BYTES = 64 * 1024


@dataclass
class LoadStats:
    run_id: int
    lines_read: int = 0
    loaded: int = 0
    rejected: int = 0
    duplicates: int = 0


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the warehouse and make sure the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((SQL_DIR / "schema.sql").read_text())
    return conn


def read_events(path: Path) -> Iterator[tuple[int, OrderEvent | None, str | None, str]]:
    """Yield (line_no, event, error, raw_line). Exactly one of event/error is set."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            if len(raw.encode()) > MAX_LINE_BYTES:
                yield line_no, None, "line too large", raw
                continue
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_no, None, f"invalid JSON: {exc.msg}", line
                continue
            try:
                yield line_no, OrderEvent.model_validate(payload), None, line
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"])
                yield line_no, None, f"{where}: {first['msg']}", line


def _insert_event(cur: sqlite3.Cursor, ev: OrderEvent, run_id: int) -> bool:
    """Insert one order. Returns False if the order_id was already loaded."""
    cur.execute(
        "INSERT INTO dim_customer (customer_id, email, country) VALUES (?, ?, ?) "
        "ON CONFLICT (customer_id) DO UPDATE SET email = excluded.email, "
        "country = excluded.country",
        (ev.customer.id, ev.customer.email.lower(), ev.customer.country),
    )
    cur.execute(
        "INSERT INTO fact_order (order_id, customer_id, order_ts, order_date, channel, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (order_id) DO NOTHING",
        (
            ev.order_id,
            ev.customer.id,
            ev.order_ts.isoformat(),
            ev.order_ts.date().isoformat(),
            ev.channel,
            run_id,
        ),
    )
    if cur.rowcount == 0:
        return False  # duplicate: orders are immutable, the first copy wins
    for item in ev.items:
        cur.execute(
            "INSERT INTO dim_product (sku, name, category) VALUES (?, ?, ?) "
            "ON CONFLICT (sku) DO UPDATE SET name = excluded.name, category = excluded.category",
            (item.sku, item.name, item.category),
        )
        cur.execute(
            "INSERT INTO fact_order_item (order_id, sku, quantity, unit_price_cents) "
            "VALUES (?, ?, ?, ?)",
            (ev.order_id, item.sku, item.quantity, int(item.unit_price * 100)),
        )
    return True


def load_file(conn: sqlite3.Connection, path: Path) -> LoadStats:
    """Load one JSONL file in a single transaction: all of it lands, or none of it."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO etl_run (source_file, started_at) VALUES (?, ?)", (path.name, now)
    )
    stats = LoadStats(run_id=int(cur.lastrowid or 0))
    try:
        with conn:  # commits on success, rolls back on any exception
            for line_no, event, error, raw in read_events(path):
                stats.lines_read += 1
                if event is None:
                    stats.rejected += 1
                    conn.execute(
                        "INSERT INTO etl_reject (run_id, line_no, error, raw_excerpt) "
                        "VALUES (?, ?, ?, ?)",
                        (stats.run_id, line_no, error, raw[:500]),
                    )
                elif _insert_event(conn.cursor(), event, stats.run_id):
                    stats.loaded += 1
                else:
                    stats.duplicates += 1
    finally:
        with conn:
            conn.execute(
                "UPDATE etl_run SET finished_at = ?, lines_read = ?, loaded = ?, "
                "rejected = ?, duplicates = ? WHERE run_id = ?",
                (
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    stats.lines_read,
                    stats.loaded,
                    stats.rejected,
                    stats.duplicates,
                    stats.run_id,
                ),
            )
    return stats


def load_queries() -> dict[str, str]:
    """Parse analytics.sql into {name: sql}. Only these fixed queries are ever run."""
    parts = re.split(r"^-- name: (\w+)\s*$", (SQL_DIR / "analytics.sql").read_text(), flags=re.M)
    # parts = [preamble, name1, body1, name2, body2, ...]
    return {name: body.strip() for name, body in zip(parts[1::2], parts[2::2], strict=True)}
