"""Data contracts: every incoming event must match these schemas exactly."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
Sku = Annotated[str, StringConstraints(pattern=r"^SKU-\d{4}$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]


class Strict(BaseModel):
    # extra="forbid": unexpected fields are an error, not silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Customer(Strict):
    id: Annotated[str, StringConstraints(pattern=r"^CUST-\d{4}$")]
    email: Annotated[str, StringConstraints(max_length=254, pattern=EMAIL_PATTERN)]
    country: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class LineItem(Strict):
    sku: Sku
    name: ShortText
    category: Literal["Electronics", "Office", "Kitchen"]
    unit_price: Annotated[Decimal, Field(ge=0, le=100_000, max_digits=10, decimal_places=2)]
    quantity: Annotated[int, Field(ge=1, le=1_000)]


class OrderEvent(Strict):
    order_id: Annotated[str, StringConstraints(pattern=r"^ORD-\d{6}$")]
    order_ts: datetime
    channel: Literal["web", "mobile", "marketplace"]
    customer: Customer
    items: Annotated[list[LineItem], Field(min_length=1, max_length=100)]

    @field_validator("order_ts")
    @classmethod
    def not_in_future(cls, v: datetime) -> datetime:
        if v.replace(tzinfo=None) > datetime.now():
            raise ValueError("order_ts is in the future")
        return v
