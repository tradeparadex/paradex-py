"""Adapters from Paradex API payloads to :mod:`paradex_py.margin` inputs.

The margin engine intentionally stays pure: it computes from plain dicts and
does not fetch auth/account state. This module is the reusable glue for SDK
examples, skills, and MCP tools that already have API responses in hand.
"""

# pyright: reportPrivateUsage=false, reportUnnecessaryCast=false

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ._utils import _opt_f, _req_f, _req_str
from .config import fee_rate_for_market, select_pm_config
from .types import Balance, MarketData, MarketSpec, Order, Position, RawDict, Side

ACTIVE_MARGIN_ORDER_STATUSES = {None, "NEW", "OPEN"}

__all__ = [
    "MarginInputs",
    "append_what_if_positions",
    "fee_rate_for_market",
    "infer_underlying",
    "market_specs_by_symbol",
    "normalise_balances",
    "normalise_market_data",
    "normalise_orders",
    "normalise_positions",
]


@dataclass
class MarginInputs:
    """Canonical input bundle accepted by :func:`paradex_py.margin.compute`."""

    positions: list[Position]
    orders: list[Order]
    market_data: dict[str, MarketData]
    market_specs: dict[str, MarketSpec]
    balances: list[Balance]
    pm_config: RawDict | None = None
    underlying: str | None = None

    def compute_kwargs(self) -> dict[str, object]:
        return {
            "positions": self.positions,
            "orders": self.orders,
            "market_data": self.market_data,
            "market_specs": self.market_specs,
            "balances": self.balances,
            "pm_config": self.pm_config,
        }

    @classmethod
    def from_api_responses(
        cls,
        *,
        positions_resp: object | None = None,
        orders_resp: object | None = None,
        balances_resp: object | None = None,
        markets_summary_resp: object | None = None,
        markets_resp: object | None = None,
        pm_config_resp: object | None = None,
        account_info_resp: Mapping[str, object] | None = None,
        what_if: list[RawDict] | None = None,
        underlying: str | None = None,
        require_pm_config: bool = False,
    ) -> MarginInputs:
        """Build canonical margin inputs from raw REST responses.

        ``what_if`` entries use the same shape as positions:
        ``{"market": "...", "side": "BUY"|"SELL", "size": ...}``.
        """
        market_specs = market_specs_by_symbol(_results(markets_resp))
        market_data = normalise_market_data(
            _results(markets_summary_resp),
            market_specs=market_specs,
            account_info=account_info_resp,
        )
        positions = normalise_positions(_results(positions_resp))
        if what_if:
            positions.extend(normalise_positions(what_if, require_open_status=False))
        orders = normalise_orders(_results(orders_resp))
        balances = normalise_balances(_results(balances_resp))
        inferred_underlying = underlying or infer_underlying(positions, orders)
        pm_config = (
            select_pm_config(pm_config_resp, inferred_underlying, missing_ok=not require_pm_config)
            if pm_config_resp is not None
            else None
        )
        if require_pm_config and pm_config is None:
            label = inferred_underlying or "<unknown>"
            raise ValueError(f"portfolio margin config for {label} is missing")
        return cls(
            positions=positions,
            orders=orders,
            market_data=market_data,
            market_specs=market_specs,
            balances=balances,
            pm_config=pm_config,
            underlying=inferred_underlying,
        )


def _asdict(value: object) -> RawDict:
    if isinstance(value, dict):
        return cast(RawDict, value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        if isinstance(dumped, dict):
            return cast(RawDict, dumped)
    return {}


def _results(payload: object | None) -> list[RawDict]:
    if payload is None:
        return []
    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes | bytearray):
        return [_asdict(item) for item in payload]
    data = _asdict(payload)
    results = data.get("results")
    if results in (None, ""):
        results = data.get("result")
    if results in (None, ""):
        return []
    if isinstance(results, Sequence) and not isinstance(results, str | bytes | bytearray):
        return [_asdict(item) for item in results]
    return [_asdict(results)] if results else []


def _side(value: object, *, ctx: str) -> Side:
    side = str(value)
    if side not in ("BUY", "SELL", "LONG", "SHORT"):
        raise ValueError(f"invalid side {side!r} ({ctx})")
    return cast(Side, side)


def _optional_positive_size(row: Mapping[str, object], key: str, *, ctx: str) -> float:
    value = _req_f(row, key, ctx)
    if value < 0:
        raise ValueError(f"size must be non-negative ({ctx})")
    return value


def normalise_positions(raw: list[RawDict], *, require_open_status: bool = True) -> list[Position]:
    out: list[Position] = []
    for pos in raw:
        if require_open_status and pos.get("status") not in (None, "OPEN"):
            continue
        market = _req_str(pos, "market", "position")
        size = _optional_positive_size(pos, "size", ctx=f"position {market}")
        if size <= 0:
            continue
        out.append({"market": market, "side": _side(pos.get("side"), ctx=f"position {market}"), "size": size})
    return out


def normalise_orders(raw: list[RawDict]) -> list[Order]:
    out: list[Order] = []
    for order in raw:
        if order.get("status") not in ACTIVE_MARGIN_ORDER_STATUSES:
            continue
        market = _req_str(order, "market", "order")
        size_key = "remaining_size" if order.get("remaining_size") not in (None, "") else "size"
        size = _optional_positive_size(order, size_key, ctx=f"order {market}")
        if size <= 0:
            continue
        out.append(
            {
                "market": market,
                "side": _side(order.get("side"), ctx=f"order {market}"),
                "size": size,
                "price": _req_f(order, "price", f"order {market}"),
            }
        )
    return out


def normalise_balances(raw: list[RawDict]) -> list[Balance]:
    out: list[Balance] = []
    for balance in raw:
        token = balance.get("token")
        if not token:
            continue
        out.append({"token": str(token), "size": _req_f(balance, "size", f"balance {token}")})
    return out


def market_specs_by_symbol(raw_markets: list[RawDict]) -> dict[str, MarketSpec]:
    return {str(m["symbol"]): cast(MarketSpec, cast(object, m)) for m in raw_markets if m.get("symbol")}


def normalise_market_data(
    raw_summaries: list[RawDict],
    *,
    market_specs: dict[str, MarketSpec] | None = None,
    account_info: Mapping[str, object] | None = None,
    default_fee_rate: float | None = None,
) -> dict[str, MarketData]:
    specs = market_specs or {}
    out: dict[str, MarketData] = {}
    for summary in raw_summaries:
        sym = summary.get("symbol")
        if not sym:
            continue
        symbol = str(sym)
        spec = specs.get(symbol, {})
        greeks = summary.get("greeks")
        empty_greeks: Mapping[str, object] = {}
        greeks_map = cast(Mapping[str, object], greeks) if isinstance(greeks, Mapping) else empty_greeks
        greek_delta: object | None = greeks_map.get("delta")
        delta_value: object | None = greek_delta if greek_delta not in (None, "") else summary.get("delta")
        asset_kind = str(spec.get("asset_kind") or "")
        if delta_value in (None, "") and asset_kind in ("PERP", "FUTURE"):
            delta = 1.0
        elif delta_value in (None, ""):
            raise ValueError(f"required margin field 'delta' is missing (market summary {symbol})")
        else:
            delta = float(cast(float | str, delta_value))
        out[symbol] = {
            "mark_price": _req_f(summary, "mark_price", f"market summary {symbol}"),
            "delta": delta,
            "mark_iv": _opt_f(summary, "mark_iv"),
            "underlying_price": _req_f(summary, "underlying_price", f"market summary {symbol}"),
            "funding_rate": _opt_f(summary, "funding_rate") or 0.0,
            "interest_rate": _opt_f(summary, "interest_rate") or _opt_f(spec, "interest_rate") or 0.0,
            "fee_rate": fee_rate_for_market(spec, account_info=account_info, default=default_fee_rate),
        }
    return out


def infer_underlying(positions: list[Position] | None = None, orders: list[Order] | None = None) -> str | None:
    """Infer the base asset from position/order market symbols."""
    for item in [*(positions or []), *(orders or [])]:
        market = item.get("market") or ""
        if "-" in market:
            base = market.split("-", 1)[0]
            if base:
                return base
    return None


def append_what_if_positions(positions: list[Position], what_if: list[RawDict] | None) -> list[Position]:
    if not what_if:
        return list(positions)
    return [*positions, *normalise_positions(what_if, require_open_status=False)]
