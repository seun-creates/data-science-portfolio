"""Pure functions that turn one messy value into one clean value (or None).

Every function here is small, has no side effects, and returns None for values it
cannot interpret, so the pipeline can decide what to do with bad data.
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Letters (any language) separated by single spaces, hyphens, apostrophes or periods.
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '.-]{1,2}[^\W\d_]+)*\.?$")
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-", "?", "unknown"}

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}  # fmt: skip
STATE_CODES = set(US_STATES.values())
STATE_ALIASES = {"calif": "CA", "cali": "CA", "mass": "MA", "penn": "PA", "wash": "WA"}

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d")


def is_missing(value: object) -> bool:
    """True for None, NaN and common placeholder strings like 'N/A'."""
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN is the only value != itself
        return True
    return str(value).strip().lower() in MISSING_TOKENS


def clean_text(value: object) -> str | None:
    """Trim and collapse internal whitespace."""
    if is_missing(value):
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def standardize_name(value: object) -> str | None:
    """'  mary-ann  O'NEIL ' -> "Mary-Ann O'Neil"."""
    text = clean_text(value)
    if text is None or len(text) > 100 or not NAME_RE.fullmatch(text):
        return None

    def cap(word: str) -> str:
        # Capitalize each part split on hyphens and apostrophes.
        return re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), word)

    return " ".join(cap(w) for w in text.split(" "))


def standardize_email(value: object) -> str | None:
    """Lower-case and validate; returns None if it is not a plausible address."""
    text = clean_text(value)
    if text is None:
        return None
    text = text.lower().replace(" ", "")
    if len(text) > 254 or not EMAIL_RE.fullmatch(text):
        return None
    return text


def standardize_phone(value: object) -> str | None:
    """Any common US format -> E.164 ('+15551234567'); None if not 10 digits."""
    text = clean_text(value)
    if text is None:
        return None
    text = re.split(r"(?i)\s*(?:x|ext\.?)\s*\d+$", text)[0]  # drop extensions
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return None
    return f"+1{digits}"


def standardize_state(value: object) -> str | None:
    """'calif.', 'California', 'ca ' -> 'CA'."""
    text = clean_text(value)
    if text is None:
        return None
    key = text.lower().rstrip(".")
    if key.upper() in STATE_CODES:
        return key.upper()
    return US_STATES.get(key) or STATE_ALIASES.get(key)


def parse_date(value: object, *, today: date | None = None) -> date | None:
    """Parse several common formats; reject impossible or future dates."""
    text = clean_text(value)
    if text is None:
        return None
    today = today or date.today()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if date(1990, 1, 1) <= parsed <= today:
            return parsed
        return None
    return None


def parse_money(value: object) -> float | None:
    """'$1,234.50', '1234.5', '(20.00)' -> float. Accounting parentheses mean negative."""
    text = clean_text(value)
    if text is None:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[,$\s()]", "", text)
    if text.lower().startswith("usd"):
        text = text[3:]
    try:
        amount = float(text)
    except ValueError:
        return None
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None
    return round(-amount if negative else amount, 2)
