"""Typed shapes used by the pure margin calculators.

Generated API models describe transport payloads, where most fields are
optional because endpoints and market kinds vary. The margin math should see a
smaller, validated schema with required numeric fields already converted.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

Side: TypeAlias = Literal["BUY", "SELL", "LONG", "SHORT"]
AssetKind: TypeAlias = Literal["PERP", "FUTURE", "OPTION", "PERP_OPTION", "SPOT"]
RawDict: TypeAlias = dict[str, object]


class Position(TypedDict):
    market: str
    side: Side
    size: float


class Order(Position):
    price: float


class Balance(TypedDict):
    token: str
    size: float


class MarketData(TypedDict):
    mark_price: float
    delta: float
    mark_iv: float | None
    underlying_price: float
    funding_rate: float
    interest_rate: float
    fee_rate: float


class Delta1MarginParams(TypedDict):
    imf_base: float
    mmf_factor: float


class OptionMarginSideParams(TypedDict):
    long_itm: float
    premium_multiplier: float
    short_itm: float
    short_otm: float
    short_put_cap: float


class OptionMarginParams(TypedDict):
    imf: OptionMarginSideParams
    mmf: OptionMarginSideParams


class MarketSpec(TypedDict, total=False):
    symbol: str
    asset_kind: AssetKind | str
    delta1_cross_margin_params: Delta1MarginParams | RawDict | None
    option_cross_margin_params: OptionMarginParams | RawDict | None
    strike_price: float | str
    option_type: str
    interest_rate: float | str
    fee_config: RawDict
    expiry_at: int


class PMScenario(TypedDict):
    spot_shock: float
    vol_shock: float
    weight: float


class VolShockParams(TypedDict):
    dte_floor_days: float
    vega_power_short_dte: float
    vega_power_long_dte: float
    min_vol_shock_up: float


class PMConfig(TypedDict, total=False):
    base_asset: str
    hedged_margin_factor: float
    unhedged_margin_factor: float
    mmf_factor: float
    scenarios: list[PMScenario | RawDict]
    vol_shock_params: VolShockParams | RawDict
    funding_provision_hour: float


class SyntheticPosition(TypedDict, total=False):
    leg_type: Literal["perp", "option"]
    legType: Literal["perp", "option"]
    market: str
    symbol: str
    side: Side
    size: float
    current_price: float
    currentPrice: float
    current_delta: float
    currentDelta: float
    strike: float
    is_call: bool
    isCall: bool
    dte_at_entry: float
    dteAtEntry: float
    bars_held: float
    barsHeld: float


class MarginResult(TypedDict):
    imr: float
    mmr: float


class LiquidationResult(TypedDict):
    down: float | None
    up: float | None
    nearest: float | None
    dist_pct: float | None
