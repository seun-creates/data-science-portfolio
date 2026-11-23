import json
import sqlite3
from copy import deepcopy

import pytest
from etl.cli import main
from etl.generate import generate
from etl.models import OrderEvent
from etl.pipeline import MAX_LINE_BYTES, connect, load_file, load_queries
from pydantic import ValidationError

VALID = {
    "order_id": "ORD-000001",
    "order_ts": "2024-05-01T10:30:00",
    "channel": "web",
    "customer": {"id": "CUST-0001", "email": "a@example.com", "country": "US"},
    "items": [
        {"sku": "SKU-1001", "name": "Mouse", "category": "Electronics",
         "unit_price": 19.99, "quantity": 3},
    ],
}  # fmt: skip


def event(**changes):
    ev = deepcopy(VALID)
    ev.update(changes)
    return ev


def write_jsonl(path, events):
    path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in events))
    return path


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    yield c
    c.close()


# --- data contract ----------------------------------------------------------
def test_valid_event_parses():
    ev = OrderEvent.model_validate(VALID)
    assert ev.items[0].quantity == 3


@pytest.mark.parametrize(
    "bad",
    [
        event(channel="fax"),
        event(order_ts="2999-01-01T00:00:00"),
        event(items=[]),
        event(unexpected_field="x"),
        event(customer={"id": "CUST-0001", "email": "nope", "country": "US"}),
        event(items=[{**VALID["items"][0], "quantity": 0}]),
        event(items=[{**VALID["items"][0], "unit_price": -1}]),
    ],
)
def test_contract_rejects_bad_events(bad):
    with pytest.raises(ValidationError):
        OrderEvent.model_validate(bad)


# --- loading ----------------------------------------------------------------
def test_load_counts_and_money_in_cents(conn, tmp_path):
    src = write_jsonl(tmp_path / "e.jsonl", [VALID, "not json", event(channel="fax")])
    stats = load_file(conn, src)
    assert (stats.loaded, stats.rejected, stats.duplicates) == (1, 2, 0)
    cents = conn.execute("SELECT unit_price_cents FROM fact_order_item").fetchone()[0]
    assert cents == 1999  # exact integer cents, no float drift
    assert conn.execute("SELECT COUNT(*) FROM etl_reject").fetchone()[0] == 2


def test_reload_is_idempotent(conn, tmp_path):
    src = write_jsonl(tmp_path / "e.jsonl", [VALID, VALID])
    first = load_file(conn, src)
    second = load_file(conn, src)
    assert (first.loaded, first.duplicates) == (1, 1)
    assert (second.loaded, second.duplicates) == (0, 2)
    assert conn.execute("SELECT COUNT(*) FROM fact_order_item").fetchone()[0] == 1


def test_sql_injection_is_stored_as_plain_text(conn, tmp_path):
    hostile = "Robert'); DROP TABLE fact_order;--"
    ev = event(items=[{**VALID["items"][0], "name": hostile}])
    load_file(conn, write_jsonl(tmp_path / "e.jsonl", [ev]))
    assert conn.execute("SELECT name FROM dim_product").fetchone()[0] == hostile
    assert conn.execute("SELECT COUNT(*) FROM fact_order").fetchone()[0] == 1


def test_oversized_line_is_rejected(conn, tmp_path):
    huge = json.dumps(event(order_id="ORD-000002")) + " " * MAX_LINE_BYTES
    stats = load_file(conn, write_jsonl(tmp_path / "e.jsonl", [huge]))
    assert stats.rejected == 1
    excerpt = conn.execute("SELECT raw_excerpt FROM etl_reject").fetchone()[0]
    assert len(excerpt) <= 500


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fact_order_item (order_id, sku, quantity, unit_price_cents) "
            "VALUES ('ORD-404404', 'SKU-0000', 1, 100)"
        )


# --- analytics --------------------------------------------------------------
def test_generated_feed_and_all_queries(conn, tmp_path):
    src = write_jsonl(tmp_path / "orders.jsonl", generate(n_orders=600, seed=1))
    stats = load_file(conn, src)
    assert stats.loaded == 600
    assert stats.rejected > 0 and stats.duplicates > 0

    queries = load_queries()
    assert set(queries) == {
        "monthly_revenue", "top_products_by_category", "channel_mix", "cohort_retention",
    }  # fmt: skip
    for sql in queries.values():
        assert conn.execute(sql).fetchall()

    total_items = conn.execute(
        "SELECT SUM(quantity * unit_price_cents) / 100.0 FROM fact_order_item"
    ).fetchone()[0]
    monthly = conn.execute(queries["monthly_revenue"]).fetchall()
    assert sum(row[2] for row in monthly) == pytest.approx(total_items, abs=0.01)
    shares = conn.execute(queries["channel_mix"]).fetchall()
    assert sum(row[3] for row in shares) == pytest.approx(100, abs=0.2)


def test_cli_load_and_report(tmp_path, capsys):
    src = write_jsonl(tmp_path / "orders.jsonl", generate(n_orders=200, seed=2))
    db = tmp_path / "w.db"
    assert main(["load", str(src), "--db", str(db)]) == 0
    assert main(["report", "--db", str(db)]) == 0
    assert "monthly_revenue" in capsys.readouterr().out
