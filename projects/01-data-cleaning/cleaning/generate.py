"""Generate a realistic, deliberately messy customer CSV (synthetic, seeded).

Run:  python -m cleaning.generate --out data/raw/customers_messy.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FIRST = ["james", "mary", "robert", "patricia", "john", "jennifer", "michael", "linda",
         "david", "elizabeth", "maria", "jose", "wei", "aisha", "mary-ann", "sean"]  # fmt: skip
LAST = ["smith", "johnson", "garcia", "o'neil", "nguyen", "brown", "lee", "patel",
        "martinez", "davis", "kim", "lopez", "wilson", "anderson", "thomas"]  # fmt: skip
STATES = [("California", "CA"), ("Texas", "TX"), ("New York", "NY"), ("Florida", "FL"),
          ("Washington", "WA"), ("Illinois", "IL"), ("Massachusetts", "MA")]  # fmt: skip
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "example.org"]


def _messy_phone(rng: np.random.Generator, digits: str) -> str:
    a, b, c = digits[:3], digits[3:6], digits[6:]
    styles = [f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}",
              f"1{a}{b}{c}", f"{a}{b}{c}", f"{a}-{b}-{c} ext 12"]  # fmt: skip
    return styles[rng.integers(len(styles))]


def _messy_date(rng: np.random.Generator, d: pd.Timestamp) -> str:
    styles = [d.strftime("%Y-%m-%d"), d.strftime("%m/%d/%Y"), d.strftime("%d %b %Y"),
              d.strftime("%b %d, %Y"), d.strftime("%Y/%m/%d")]  # fmt: skip
    return styles[rng.integers(len(styles))]


def _messy_money(rng: np.random.Generator, x: float) -> str:
    styles = [f"${x:,.2f}", f"{x:.2f}", f"{x:,.0f}", f"USD {x:.2f}", f" {x} "]
    return styles[rng.integers(len(styles))]


def generate(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Return n clean-ish customers plus injected duplicates and errors."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        state_name, state_code = STATES[rng.integers(len(STATES))]
        digits = f"{rng.integers(201, 989)}{rng.integers(200, 999)}{rng.integers(0, 9999):04d}"
        signup = pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(rng.integers(0, 2000)))
        rows.append(
            {
                "customer_id": f"C{i:05d}",
                "full_name": f"{first} {last}",
                "email": f"{first}.{last}{i}@{rng.choice(DOMAINS)}".replace("'", ""),
                "phone": digits,
                "state": state_name if rng.random() < 0.5 else state_code,
                "signup_date": signup,
                "lifetime_value": round(float(rng.gamma(2.0, 250.0)), 2),
            }
        )
    df = pd.DataFrame(rows)

    # --- make it messy -------------------------------------------------------
    df["full_name"] = [
        rng.choice([s.upper(), s.title(), f"  {s}  ", s.replace(" ", "   ")])
        for s in df["full_name"]
    ]
    df["email"] = [e.upper() if rng.random() < 0.2 else f" {e} " for e in df["email"]]
    df["phone"] = [_messy_phone(rng, p) for p in df["phone"]]
    df["state"] = [
        rng.choice([s, s.lower(), f"{s}.", "Calif." if s in ("CA", "California") else s])
        for s in df["state"]
    ]
    df["signup_date"] = [_messy_date(rng, d) for d in df["signup_date"]]
    df["lifetime_value"] = [_messy_money(rng, v) for v in df["lifetime_value"]]

    def corrupt(col: str, frac: float, values: list[str]) -> None:
        idx = rng.choice(len(df), size=int(len(df) * frac), replace=False)
        df.loc[idx, col] = rng.choice(values, size=len(idx))

    corrupt("email", 0.03, ["not-an-email", "john@", "N/A", ""])
    corrupt("phone", 0.03, ["12345", "n/a", "000-000-0000"])
    corrupt("state", 0.02, ["Atlantis", "??", ""])
    corrupt("signup_date", 0.02, ["2099-01-01", "31/31/2020", "yesterday"])
    corrupt("lifetime_value", 0.02, ["N/A", "abc", "(25.00)"])
    # Spreadsheet formula injection attempts: must never reach Excel unescaped.
    corrupt("full_name", 0.005, ['=HYPERLINK("http://evil.example","click")', "@SUM(A1)"])

    # Duplicates: same person re-entered with different formatting.
    dupes = df.sample(frac=0.06, random_state=seed).copy()
    dupes["email"] = dupes["email"].str.upper().str.strip()
    dupes["full_name"] = dupes["full_name"].str.lower()
    df = pd.concat([df, dupes], ignore_index=True)
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df = generate(args.rows, args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df):,} messy rows to {args.out}")


if __name__ == "__main__":
    main()
