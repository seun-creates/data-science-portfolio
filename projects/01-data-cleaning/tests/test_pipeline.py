from datetime import date

import pandas as pd
import pytest
from cleaning.cli import main
from cleaning.generate import generate
from cleaning.pipeline import clean_customers, escape_formulas

TODAY = date(2026, 1, 1)


def _row(**overrides):
    row = {
        "customer_id": "C00001",
        "full_name": "jane doe",
        "email": "Jane@Example.com",
        "phone": "415-555-0123",
        "state": "California",
        "signup_date": "2021-03-04",
        "lifetime_value": "$100.00",
    }
    row.update(overrides)
    return row


def test_clean_row_is_fully_standardized():
    result = clean_customers(pd.DataFrame([_row()]), today=TODAY)
    rec = result.clean.iloc[0]
    assert rec["full_name"] == "Jane Doe"
    assert rec["email"] == "jane@example.com"
    assert rec["phone"] == "+14155550123"
    assert rec["state"] == "CA"
    assert rec["signup_date"] == pd.Timestamp("2021-03-04")
    assert rec["lifetime_value"] == 100.0


def test_invalid_email_is_rejected_with_reason():
    result = clean_customers(pd.DataFrame([_row(email="nope")]), today=TODAY)
    assert result.clean.empty
    assert result.rejected.iloc[0]["rejection_reason"] == "invalid_email"


def test_duplicates_keep_most_complete_record():
    raw = pd.DataFrame([_row(phone="n/a"), _row(customer_id="C00002", email=" JANE@example.com ")])
    result = clean_customers(raw, today=TODAY)
    assert len(result.clean) == 1
    assert result.clean.iloc[0]["phone"] == "+14155550123"
    assert result.report["duplicates_removed"] == 1


def test_input_is_not_mutated():
    raw = pd.DataFrame([_row()])
    snapshot = raw.copy()
    clean_customers(raw, today=TODAY)
    pd.testing.assert_frame_equal(raw, snapshot)


def test_missing_columns_raise():
    with pytest.raises(ValueError, match="missing required columns"):
        clean_customers(pd.DataFrame([{"email": "a@b.co"}]))


def test_escape_formulas_neutralizes_injection():
    df = pd.DataFrame(
        {"name": ["=HYPERLINK(\"x\")", "@SUM(A1)", "-2+3", "+14155550123", "Normal"],
         "n": [1, 2, 3, 4, 5]}
    )  # fmt: skip
    safe = escape_formulas(df)
    assert safe["name"].tolist() == [
        "'=HYPERLINK(\"x\")", "'@SUM(A1)", "'-2+3", "+14155550123", "Normal"
    ]  # fmt: skip
    assert safe["n"].tolist() == [1, 2, 3, 4, 5]


def test_generated_data_end_to_end(tmp_path):
    raw = generate(n=500, seed=1)
    result = clean_customers(raw.astype(str))
    r = result.report
    assert r["rows_in"] == len(raw)
    assert r["rows_clean"] + r["rows_rejected"] + r["duplicates_removed"] == r["rows_in"]
    assert result.clean["email"].is_unique
    assert result.clean["customer_id"].is_unique
    assert r["duplicates_removed"] > 0


def test_cli_writes_outputs(tmp_path):
    src = tmp_path / "raw.csv"
    generate(n=200, seed=3).to_csv(src, index=False)
    assert main([str(src), "--out-dir", str(tmp_path / "out")]) == 0
    for name in ["customers_clean.csv", "customers_rejected.csv", "quality_report.md"]:
        assert (tmp_path / "out" / name).exists()
