"""Synthetic subscription-customer dataset with a realistic churn mechanism.

Churn is driven by known effects (contract type, tenure, price, support tickets,
payment method) plus noise, so we can check that the model recovers them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate(n: int = 7000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    contract = rng.choice(["month-to-month", "one-year", "two-year"], size=n, p=[0.55, 0.25, 0.20])
    internet = rng.choice(["fiber", "dsl", "none"], size=n, p=[0.45, 0.35, 0.20])
    payment = rng.choice(
        ["electronic-check", "credit-card", "bank-transfer", "mailed-check"],
        size=n,
        p=[0.35, 0.25, 0.25, 0.15],
    )
    tenure = np.clip(rng.gamma(1.6, 18, size=n), 0, 72).round().astype(int)
    base_price = np.select([internet == "fiber", internet == "dsl"], [75.0, 55.0], 25.0)
    monthly = np.round(base_price + rng.normal(0, 12, size=n), 2).clip(18, 120)
    tickets = rng.poisson(np.where(internet == "fiber", 1.4, 0.8))
    senior = rng.random(n) < 0.16
    paperless = rng.random(n) < 0.6
    products = rng.integers(1, 5, size=n)

    # The "true" churn mechanism (log-odds).
    logit = (
        -1.6
        + np.select([contract == "month-to-month", contract == "one-year"], [1.3, 0.0], -1.4)
        - 0.045 * tenure
        + 0.022 * (monthly - 60)
        + 0.35 * tickets
        + 0.55 * (payment == "electronic-check")
        + 0.30 * senior
        + 0.20 * paperless
        - 0.25 * (products - 1)
        + 0.4 * ((internet == "fiber") & (tickets >= 3))  # interaction effect
    )
    churned = rng.random(n) < 1 / (1 + np.exp(-logit))

    total = np.round(monthly * tenure * rng.normal(1.0, 0.03, size=n), 2)
    df = pd.DataFrame(
        {
            "customer_id": [f"CUST-{i:05d}" for i in range(n)],
            "tenure_months": tenure,
            "monthly_charges": monthly,
            "total_charges": total,
            "contract": contract,
            "internet_service": internet,
            "payment_method": payment,
            "support_tickets_90d": tickets,
            "senior_citizen": senior.astype(int),
            "paperless_billing": paperless.astype(int),
            "num_products": products,
            "churned": churned.astype(int),
        }
    )
    # Real data has gaps: brand-new customers have no billing history yet,
    # and some payment methods were never recorded.
    df.loc[df["tenure_months"] == 0, "total_charges"] = np.nan
    df.loc[rng.random(n) < 0.02, "payment_method"] = None
    return df
