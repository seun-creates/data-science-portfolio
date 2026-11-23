-- Star schema for order analytics.
-- Money is stored as INTEGER cents to avoid floating-point rounding errors.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS etl_run (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file   TEXT    NOT NULL,
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    lines_read    INTEGER NOT NULL DEFAULT 0,
    loaded        INTEGER NOT NULL DEFAULT 0,
    rejected      INTEGER NOT NULL DEFAULT 0,
    duplicates    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS etl_reject (
    run_id      INTEGER NOT NULL REFERENCES etl_run (run_id),
    line_no     INTEGER NOT NULL,
    error       TEXT    NOT NULL,
    raw_excerpt TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    country     TEXT NOT NULL CHECK (length(country) = 2)
);

CREATE TABLE IF NOT EXISTS dim_product (
    sku       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL CHECK (category IN ('Electronics', 'Office', 'Kitchen'))
);

CREATE TABLE IF NOT EXISTS fact_order (
    order_id    TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES dim_customer (customer_id),
    order_ts    TEXT NOT NULL,
    order_date  TEXT NOT NULL,
    channel     TEXT NOT NULL CHECK (channel IN ('web', 'mobile', 'marketplace')),
    run_id      INTEGER NOT NULL REFERENCES etl_run (run_id)
);

CREATE TABLE IF NOT EXISTS fact_order_item (
    order_id         TEXT    NOT NULL REFERENCES fact_order (order_id) ON DELETE CASCADE,
    sku              TEXT    NOT NULL REFERENCES dim_product (sku),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, sku)
);

CREATE INDEX IF NOT EXISTS ix_order_date ON fact_order (order_date);
CREATE INDEX IF NOT EXISTS ix_order_customer ON fact_order (customer_id);
