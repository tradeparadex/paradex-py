# Generated from Paradex API spec version 1.106.0

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TransferFeeConfigResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    fee_percentage: Annotated[
        float | None, Field(description="Fee percentage charged on transfers (e.g., 0.01 = 1%)")
    ] = None
