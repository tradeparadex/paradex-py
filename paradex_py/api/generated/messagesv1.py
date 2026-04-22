# Generated from Paradex API spec version 1.119.0

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NftPrice(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    currency: str | None = None
    decimals: int | None = None
    value: str | None = None
