"""
WebSocket message payload models based on AsyncAPI 2.6.0 specification.

These models represent the 'data' payload of WebSocket messages and are stricter
(required fields) than the REST API models to match the AsyncAPI spec.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# Base WebSocket message structure
class WebSocketMessage(BaseModel):
    """Base WebSocket message with params and data."""

    model_config = ConfigDict(extra="allow")

    params: dict[str, Any] = Field(..., description="Message parameters including channel")
    data: dict[str, Any] = Field(..., description="Message payload data")


# WebSocket payload models (required fields per AsyncAPI spec)


class BalanceEventResponse(BaseModel):
    """Balance event WebSocket payload."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    created_at: int = Field(..., description="Unix Millisecond timestamp at which the event occurred")
    fees: str = Field(..., description="Fees in USDC")
    fill_id: str = Field(..., description="Unique string ID for the fill")
    funding_index: str = Field(..., description="Funding index used for the fill")
    market: str = Field(..., description="Name of the market the update is referring to")
    realized_funding: str = Field(..., description="Fill's Realized Funding in USDC")
    realized_pnl: str = Field(..., description="Fill's realized PnL (excluding funding) in USDC")
    settlement_asset_balance_after: str = Field(..., description="Settlement asset balance after the fill")
    settlement_asset_balance_before: str = Field(..., description="Settlement asset balance before the fill")
    settlement_asset_price: str = Field(..., description="Settlement asset price")
    status: str = Field(..., description="Status of the fill")
    event_type: str = Field(alias="type", description="Type of the event")


class PriceBookUpdate(BaseModel):
    """Price book update WebSocket payload."""

    model_config = ConfigDict(extra="allow")

    best_ask_api: dict[str, Any] = Field(..., description="Size on the best ask from API (excluding RPI)")
    best_ask_interactive: dict[str, Any] = Field(..., description="Size on the best ask from UI")
    best_bid_api: dict[str, Any] = Field(..., description="Size on the best bid from API (excluding RPI)")
    best_bid_interactive: dict[str, Any] = Field(..., description="Size on the best bid from UI")
    deletes: list[dict[str, Any]] = Field(..., description="Deleted orders")
    inserts: list[dict[str, Any]] = Field(..., description="Inserted orders")
    last_updated_at: int = Field(..., description="Last update timestamp in milliseconds")
    market: str = Field(..., description="Market symbol")
    seq_no: int = Field(..., description="Sequence number")
    update_type: Literal["s", "d"] = Field(..., description="Update type")
    updates: list[dict[str, Any]] = Field(..., description="Updated orders")


# Type mapping for channel names to payload models
WS_PAYLOAD_MODELS = {
    "balance_events": BalanceEventResponse,
    "order_book": PriceBookUpdate,
}


def get_ws_payload_model(channel_name: str) -> type[BaseModel] | None:
    """Get the appropriate payload model for a WebSocket channel.

    Args:
        channel_name: The WebSocket channel name (e.g., "account", "bbo.BTC-USD-PERP")

    Returns:
        The corresponding payload model class, or None if not found
    """
    # Extract the base channel name (before any parameters)
    base_channel = channel_name.split(".")[0]
    return WS_PAYLOAD_MODELS.get(base_channel)


def validate_ws_payload(channel_name: str, payload: dict[str, Any]) -> BaseModel | None:
    """Validate a WebSocket payload against the appropriate model.

    Args:
        channel_name: The WebSocket channel name
        payload: The payload data to validate

    Returns:
        Validated model instance, or None if validation fails
    """
    model_class = get_ws_payload_model(channel_name)
    if model_class is None:
        return None

    try:
        return model_class.model_validate(payload)
    except Exception:
        return None
