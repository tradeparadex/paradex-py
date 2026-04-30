"""Cross-margin (XM) calculations for perpetuals, futures, and options.

All margin-policy fields (``imf_base``, ``mmf_factor``, option ``long_itm`` /
``premium_multiplier`` / ``short_itm`` / ``short_otm`` / ``short_put_cap``)
must come from the live exchange config — see ``delta1_cross_margin_params``
and ``option_cross_margin_params`` on each market. Missing values raise
``ValueError`` rather than silently defaulting.
"""

from ._utils import _req_dict, _req_f, _req_str
from .config import normalise_delta1_margin_params, normalise_option_margin_params
from .types import (
    Balance,
    Delta1MarginParams,
    MarginResult,
    MarketData,
    MarketSpec,
    OptionMarginParams,
    OptionMarginSideParams,
    Order,
    Position,
    RawDict,
    XMMarginResult,
    XMOrderDetail,
    XMPositionDetail,
)


def _xm_option_margin(
    params: OptionMarginSideParams,
    mark: float,
    spot: float,
    strike: float,
    is_call: bool,
    is_long: bool,
    size: float,
) -> float:
    """Compute XM margin for one side (imf or mmf) of an option position.

    Long:  min(mark x premium_multiplier, long_itm x spot) x size
    Short: max(short_itm x spot - otm_amount, short_otm x spot) x size,
           capped at short_put_cap x spot x size for puts.
    """
    if is_long:
        return min(mark * params["premium_multiplier"], params["long_itm"] * spot) * size

    otm_amt = max(0.0, (strike - spot) if is_call else (spot - strike))
    raw = max(params["short_itm"] * spot - otm_amt, params["short_otm"] * spot)
    if not is_call:
        raw = min(raw, params["short_put_cap"] * spot)
    return raw * size


def xm_perp_margin(size: float, price: float, params: Delta1MarginParams | RawDict) -> MarginResult:
    """IMR/MMR for a single perp/future leg: ``IMR = |size| * price * imf_base``.

    The ``imf_factor`` and ``imf_shift`` fields on the API response are
    deprecated (always 0 — see ``Delta1CrossMarginParams`` in the OpenAPI
    spec) and not part of the formula.
    """
    typed_params = normalise_delta1_margin_params(params)
    imr = abs(size) * price * typed_params["imf_base"]
    return {"imr": imr, "mmr": imr * typed_params["mmf_factor"]}


def xm_option_margin(
    is_buy: bool,
    is_call: bool,
    size: float,
    strike: float,
    spot: float,
    mark_price: float,
    params: OptionMarginParams | RawDict,
) -> MarginResult:
    """Backtester-shaped helper: IMR/MMR for a single option leg.

    `params` must have nested {"imf": {...}, "mmf": {...}} param dicts.
    """
    typed_params = normalise_option_margin_params(params)
    return {
        "imr": _xm_option_margin(typed_params["imf"], mark_price, spot, strike, is_call, is_buy, size),
        "mmr": _xm_option_margin(typed_params["mmf"], mark_price, spot, strike, is_call, is_buy, size),
    }


def _xm_instrument(
    item: Position,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
    *,
    price: float | None = None,
) -> XMMarginResult:
    sym = item["market"]
    side = item["side"]
    size = abs(float(item["size"]))
    try:
        md = market_data[sym]
    except KeyError as e:
        raise ValueError(f"missing market data for XM instrument {sym!r}") from e
    try:
        spec = market_specs[sym]
    except KeyError as e:
        raise ValueError(f"missing market spec for XM instrument {sym!r}") from e

    mark = md["mark_price"] if price is None else price
    signed_size = size if side in ("BUY", "LONG") else -size
    delta_contrib = md["delta"] * signed_size
    notional = size * mark
    asset_kind = spec.get("asset_kind", "")

    if asset_kind in ("PERP", "FUTURE"):
        params = normalise_delta1_margin_params(_req_dict(spec, "delta1_cross_margin_params", sym), sym)
        r = xm_perp_margin(size, mark, params)
        imr, mmr = r["imr"], r["mmr"]
    elif asset_kind in ("OPTION", "PERP_OPTION"):
        ocp = normalise_option_margin_params(_req_dict(spec, "option_cross_margin_params", sym), sym)
        spot = md["underlying_price"]
        strike = _req_f(spec, "strike_price", sym)
        is_call = _req_str(spec, "option_type", sym) == "CALL"
        is_long = side in ("BUY", "LONG")
        imr = _xm_option_margin(ocp["imf"], mark, spot, strike, is_call, is_long, size)
        mmr = _xm_option_margin(ocp["mmf"], mark, spot, strike, is_call, is_long, size)
    else:
        raise ValueError(f"unsupported asset_kind {asset_kind!r} for {sym}")

    return {
        "imr": imr,
        "mmr": mmr,
        "delta_contrib": delta_contrib,
        "mark_price": mark,
        "notional": notional,
    }


def xm_position(
    pos: Position,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> XMMarginResult:
    """Compute cross-margin IMR/MMR for a single position."""
    return _xm_instrument(pos, market_data, market_specs)


def xm_order(
    order: Order,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> XMMarginResult:
    """Compute cross-margin IMR/MMR for a single open order."""
    return _xm_instrument(order, market_data, market_specs, price=order["price"])


def spot_balance_margin(balances: list[Balance], market_data: dict[str, MarketData]) -> float:
    """Non-USDC spot token balances charged at 100% USD value."""
    sbm = 0.0
    for b in balances:
        token = b["token"]
        if token == "USDC":  # noqa: S105
            continue
        md = market_data.get(f"{token}-USD-PERP") or market_data.get(f"{token}-USD")
        if md is None:
            raise ValueError(f"missing market data for spot balance token {token!r}")
        price = md["mark_price"] or md["underlying_price"]
        sbm += abs(b["size"]) * price
    return sbm


def compute_xm(
    positions: list[Position],
    orders: list[Order],
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
    balances: list[Balance] | None = None,
) -> dict[str, object]:
    """Compute total cross-margin IMR/MMR for all positions.

    Returns full breakdown including per-position detail and portfolio delta.
    """
    spot_bm = spot_balance_margin(balances or [], market_data)
    total_imr = spot_bm
    total_mmr = spot_bm
    port_delta = 0.0
    position_detail: list[XMPositionDetail] = []
    order_detail: list[XMOrderDetail] = []

    for pos in positions:
        r = xm_position(pos, market_data, market_specs)
        total_imr += r["imr"]
        total_mmr += r["mmr"]
        port_delta += r["delta_contrib"]
        position_detail.append({**pos, **r})

    for order in orders:
        r = xm_order(order, market_data, market_specs)
        total_imr += r["imr"]
        total_mmr += r["mmr"]
        port_delta += r["delta_contrib"]
        order_detail.append({**order, **r})

    return {
        "IMR": total_imr,
        "MMR": total_mmr,
        "portfolio_delta": port_delta,
        "spot_balance_margin": spot_bm,
        "positions": position_detail,
        "orders": order_detail,
    }
