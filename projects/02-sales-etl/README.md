# 02 · Sales ETL and SQL Analytics

Loads a raw feed of order events (JSON Lines) into a SQLite star schema with strict
validation, an audit trail and idempotent re-runs, then answers business questions
with SQL window functions.

## Architecture
```
*orders.jsonl
**extract (size cap, JSON parse)
***alidate (pydantic data contract)
*****load (one transaction, parameterized SQL)
****** dim_customer, dim_product        (upserts)
******* fact_order, fact_order_item      (insert-once)
******** etl_run, etl_reject              (audit trail)
********* analytics.sql (window functions)
```

## Design decisions
- **Data contract:**
- **Idempotent:**
- **Atomic:**
- **Exact money:**
- **Secure SQL:**

## Results (seed 7)
| Metric | Value |
| --- | --- |
| Lines read | 5,202 |
| Orders loaded | 5,000 |
| Rejected (with reason) | 152 |
| Duplicates skipped | 50 |
| Second run loaded | 0 (idempotent) |

Sample insights from `make etl`: web is 49% of revenue; the Mechanical Keyboard is the top
product by revenue; about 75–80% of customers order again in the following quarter.

## Run it
```bash
make etl          # from the repo root
pytest projects/02-sales-etl -q
```

## Skills shown
ETL design · data contracts (pydantic) · relational modeling (star schema) · SQL window
functions (LAG, RANK, SUM OVER) · cohort analysis · transactions · SQL-injection safety
