from datetime import date

import pytest
from cleaning import standardize as st


@pytest.mark.parametrize("value", [None, float("nan"), "", "  ", "N/A", "null", "?"])
def test_is_missing(value):
    assert st.is_missing(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  mary-ann   O'NEIL ", "Mary-Ann O'Neil"),
        ("JOSE GARCIA", "Jose Garcia"),
        ("josé NÚÑEZ", "José Núñez"),
        ('=HYPERLINK("http://x")', None),
        ("123", None),
        ("", None),
    ],
)
def test_standardize_name(raw, expected):
    assert st.standardize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" John.Smith@Gmail.COM ", "john.smith@gmail.com"),
        ("not-an-email", None),
        ("john@", None),
        ("a@b.c", None),
    ],
)
def test_standardize_email(raw, expected):
    assert st.standardize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["(415) 555-0123", "415-555-0123", "415.555.0123", "+1 415 555 0123", "14155550123",
     "415-555-0123 ext 12"],
)  # fmt: skip
def test_standardize_phone_formats(raw):
    assert st.standardize_phone(raw) == "+14155550123"


@pytest.mark.parametrize("raw", ["12345", "000-000-0000", "n/a", "phone"])
def test_standardize_phone_invalid(raw):
    assert st.standardize_phone(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("California", "CA"), ("ca", "CA"), ("Calif.", "CA"), ("TX.", "TX"),
     ("new york", "NY"), ("Atlantis", None), ("", None)],
)  # fmt: skip
def test_standardize_state(raw, expected):
    assert st.standardize_state(raw) == expected


TODAY = date(2025, 1, 1)


@pytest.mark.parametrize(
    "raw", ["2021-03-04", "03/04/2021", "04 Mar 2021", "Mar 04, 2021", "2021/03/04"]
)
def test_parse_date_formats(raw):
    assert st.parse_date(raw, today=TODAY) == date(2021, 3, 4)


@pytest.mark.parametrize("raw", ["2099-01-01", "31/31/2020", "yesterday", "1900-01-01"])
def test_parse_date_rejects_bad_or_future(raw):
    assert st.parse_date(raw, today=TODAY) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,234.50", 1234.5), ("USD 99.99", 99.99), (" 12 ", 12.0), ("(25.00)", -25.0),
     ("abc", None), ("N/A", None), ("nan", None), ("inf", None)],
)  # fmt: skip
def test_parse_money(raw, expected):
    assert st.parse_money(raw) == expected
