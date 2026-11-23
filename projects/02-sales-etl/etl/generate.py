"""Generate synthetic order events as JSON Lines, including realistic bad records.

Run:  python -m etl.generate --out data/raw/orders.jsonl
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

CATALOG = [
    ("SKU-1001", "Wireless Mouse", "Electronics", 24.99),
    ("SKU-1002", "Mechanical Keyboard", "Electronics", 89.00),
    ("SKU-1003", "USB-C Hub", "Electronics", 39.50),
    ("SKU-2001", "Standing Desk Mat", "Office", 45.00),
    ("SKU-2002", "Desk Lamp", "Office", 32.00),
    ("SKU-2003", "Notebook 3-Pack", "Office", 12.99),
    ("SKU-3001", "Pour-Over Coffee Kit", "Kitchen", 54.00),
    ("SKU-3002", "Insulated Bottle", "Kitchen", 27.00),
    ("SKU-3003", "Tea Sampler", "Kitchen", 19.00),
    # A hostile product name: must be stored as plain text, never executed.
    ("SKU-9999", "Robert'); DROP TABLE fact_order;--", "Office", 1.00),
]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "AU"]
CHANNELS = ["web", "web", "mobile", "marketplace"]


def _item(p: int, quantity: int) -> dict:
    sku, name, category, price = CATALOG[p]
    return {"sku": sku, "name": name, "category": category, "unit_price": price,
            "quantity": quantity}  # fmt: skip


def generate(n_orders: int = 5000, n_customers: int = 800, seed: int = 7) -> list[str]:
    """Return JSONL lines. About 3% are deliberately invalid."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 1)
    customers = [
        {
            "id": f"CUST-{i:04d}",
            "email": f"customer{i}@example.com",
            "country": str(rng.choice(COUNTRIES)),
        }
        for i in range(n_customers)
    ]
    # Customers join over two years and only order after joining.
    joined_day = np.sort(rng.integers(0, 700, size=n_customers))
    joined_day[0] = 0  # someone is always available to place the first order

    lines: list[str] = []
    for i in range(n_orders):
        # sqrt of a uniform draw -> order volume grows steadily over the two years
        day = int(730 * np.sqrt(rng.random()))
        eligible = int(np.searchsorted(joined_day, day, side="right"))
        c = int(rng.integers(eligible))
        ts = start + timedelta(days=day, minutes=int(rng.integers(0, 1440)))
        picks = rng.choice(len(CATALOG) - 1, size=int(rng.integers(1, 4)), replace=False)
        items = [_item(int(p), int(rng.integers(1, 4))) for p in picks]
        if rng.random() < 0.002:
            items.append(_item(len(CATALOG) - 1, 1))  # the hostile product name
        event = {
            "order_id": f"ORD-{i:06d}",
            "order_ts": ts.isoformat(),
            "channel": str(rng.choice(CHANNELS)),
            "customer": customers[c],
            "items": items,
        }
        lines.append(json.dumps(event))

    # --- bad records, the kind every real feed contains ---------------------
    bad: list[str] = [
        '{"order_id": "ORD-BROKEN", "order_ts": ',  # truncated JSON
        "not json at all",
    ]
    for j in range(int(n_orders * 0.03)):
        ev = json.loads(lines[int(rng.integers(len(lines)))])
        ev["order_id"] = f"ORD-9{j:05d}"  # valid id, invalid content
        problem = j % 4
        if problem == 0:
            ev["items"][0]["quantity"] = -1
        elif problem == 1:
            ev["items"][0]["unit_price"] = "free"
        elif problem == 2:
            del ev["customer"]
        else:
            ev["channel"] = "carrier-pigeon"
        bad.append(json.dumps(ev))
    # Re-sent duplicates: the same order delivered twice by the upstream system.
    dupes = [lines[int(k)] for k in rng.choice(len(lines), size=50, replace=False)]

    everything = lines + bad + dupes
    return [everything[int(k)] for k in rng.permutation(len(everything))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--orders", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = generate(args.orders, seed=args.seed)
    args.out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(lines):,} events to {args.out}")


if __name__ == "__main__":
    main()
