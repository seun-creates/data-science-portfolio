"""Cleaning pipeline: standardize -> validate -> deduplicate -> report."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from cleaning import standardize as st

REQUIRED_COLUMNS = [
    "customer_id", "full_name", "email", "phone", "state", "signup_date", "lifetime_value",
]  # fmt: skip
ID_RE = re.compile(r"^C\d{5}$")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
PLAIN_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")  # e.g. "+14155550123" is data, not a formula


@dataclass
class CleaningResult:
    clean: pd.DataFrame
    rejected: pd.DataFrame
    report: dict = field(default_factory=dict)


def _standardize_id(value: object) -> str | None:
    text = st.clean_text(value)
    if text is None:
        return None
    text = text.upper()
    return text if ID_RE.fullmatch(text) else None


def clean_customers(raw: pd.DataFrame, *, today: date | None = None) -> CleaningResult:
    """Clean a raw customer table. Never modifies the input DataFrame."""
    missing = set(REQUIRED_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {sorted(missing)}")

    df = raw[REQUIRED_COLUMNS].copy()
    out = pd.DataFrame(index=df.index)
    out["customer_id"] = df["customer_id"].map(_standardize_id)
    out["full_name"] = df["full_name"].map(st.standardize_name)
    out["email"] = df["email"].map(st.standardize_email)
    out["phone"] = df["phone"].map(st.standardize_phone)
    out["state"] = df["state"].map(st.standardize_state)
    out["signup_date"] = df["signup_date"].map(lambda v: st.parse_date(v, today=today))
    out["lifetime_value"] = df["lifetime_value"].map(st.parse_money)

    # Negative lifetime value is a data-entry error in this domain.
    out.loc[out["lifetime_value"] < 0, "lifetime_value"] = None

    # Field-level validity, measured where the raw value was present.
    validity = {}
    for col in REQUIRED_COLUMNS:
        present = ~df[col].map(st.is_missing)
        n_present = int(present.sum())
        n_valid = int((present & out[col].notna()).sum())
        validity[col] = round(n_valid / n_present, 4) if n_present else None

    # Row-level rules: id, email and name are required; everything else may be null.
    reasons = pd.Series("", index=out.index)
    reasons[out["customer_id"].isna()] += "invalid_customer_id;"
    reasons[out["email"].isna()] += "invalid_email;"
    reasons[out["full_name"].isna()] += "missing_name;"
    bad = reasons != ""
    rejected = raw.loc[bad].copy()
    rejected["rejection_reason"] = reasons[bad].str.rstrip(";")
    good = out.loc[~bad].copy()

    # Deduplicate on email: keep the most complete record, then the lowest id.
    good["_completeness"] = good.notna().sum(axis=1)
    good = good.sort_values(
        ["email", "_completeness", "customer_id"], ascending=[True, False, True]
    )
    before = len(good)
    good = good.drop_duplicates(subset="email", keep="first")
    good = good.drop_duplicates(subset="customer_id", keep="first")
    duplicates_removed = before - len(good)
    good = good.drop(columns="_completeness").sort_values("customer_id").reset_index(drop=True)
    good["signup_date"] = pd.to_datetime(good["signup_date"])

    report = {
        "rows_in": len(raw),
        "rows_clean": len(good),
        "rows_rejected": int(bad.sum()),
        "duplicates_removed": duplicates_removed,
        "rejection_reasons": rejected["rejection_reason"]
        .str.split(";")
        .explode()
        .value_counts()
        .to_dict(),
        "field_validity_rate": validity,
        "null_rate_after": {c: round(float(good[c].isna().mean()), 4) for c in good.columns},
    }
    return CleaningResult(clean=good, rejected=rejected, report=report)


def escape_formulas(df: pd.DataFrame) -> pd.DataFrame:
    """Neutralize spreadsheet formula injection (CWE-1236) before writing CSV.

    A cell starting with = + - @ can execute as a formula when a CSV is opened in
    Excel or Google Sheets. Prefixing a single quote makes it plain text.
    """

    def escape(v: object) -> object:
        if isinstance(v, str) and v.startswith(FORMULA_PREFIXES) and not PLAIN_NUMBER.match(v):
            return f"'{v}"
        return v

    safe = df.copy()
    for col in safe.columns:
        if safe[col].dtype == object or pd.api.types.is_string_dtype(safe[col]):
            safe[col] = safe[col].map(escape)
    return safe
