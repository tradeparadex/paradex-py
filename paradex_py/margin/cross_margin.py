"""Cross-margin (XM) calculations for perpetuals, futures, and options.

All margin-policy fields (``imf_base``, ``mmf_factor``, option ``long_itm`` /
``premium_multiplier`` / ``short_itm`` / ``short_otm`` / ``short_put_cap``)
must come from the live exchange config — see ``delta1_cross_margin_params``
and ``option_cross_margin_params`` on each market. Missing values raise
``ValueError`` rather than silently defaulting.
"""

from typing import cast

from ._utils import _req_dict, _req_f, _req_str
from .types import Balance, MarginResult, MarketData, MarketSpec, Order, Position


def _xm_option_margin(
    params: dict[str, object],
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
        return min(mark * _req_f(params, "premium_multiplier"), _req_f(params, "long_itm") * spot) * size

    otm_amt = max(0.0, (strike - spot) if is_call else (spot - strike))
    raw = max(_req_f(params, "short_itm") * spot - otm_amt, _req_f(params, "short_otm") * spot)
    if not is_call:
        raw = min(raw, _req_f(params, "short_put_cap") * spot)
    return raw * size


def xm_perp_margin(size: float, price: float, params: dict[str, object]) -> MarginResult:
    """IMR/MMR for a single perp/future leg: ``IMR = |size| * price * imf_base``.

    The ``imf_factor`` and ``imf_shift`` fields on the API response are
    deprecated (always 0 — see ``Delta1CrossMarginParams`` in the OpenAPI
    spec) and not part of the formula.
    """
    imr = abs(size) * price * _req_f(params, "imf_base")
    return {"imr": imr, "mmr": imr * _req_f(params, "mmf_factor")}


def xm_option_margin(
    is_buy: bool,
    is_call: bool,
    size: float,
    strike: float,
    spot: float,
    mark_price: float,
    params: dict[str, object],
) -> MarginResult:
    """Backtester-shaped helper: IMR/MMR for a single option leg.

    `params` must have nested {"imf": {...}, "mmf": {...}} param dicts.
    """
    return {
        "imr": _xm_option_margin(dict(_req_dict(params, "imf")), mark_price, spot, strike, is_call, is_buy, size),
        "mmr": _xm_option_margin(dict(_req_dict(params, "mmf")), mark_price, spot, strike, is_call, is_buy, size),
    }


def xm_position(
    pos: Position,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> dict[str, object]:
    """Compute cross-margin IMR/MMR for a single position.

    Returns: {imr, mmr, delta_contrib, mark_price, notional}
    """
    sym = pos["market"]
    side = pos["side"]
    size = abs(float(pos["size"]))
    try:
        md = market_data[sym]
    except KeyError as e:
        raise ValueError(f"missing market data for position {sym!r}") from e
    try:
        spec = market_specs[sym]
    except KeyError as e:
        raise ValueError(f"missing market spec for position {sym!r}") from e

    mark = md["mark_price"]
    signed_size = size if side in ("BUY", "LONG") else -size
    delta_contrib = md["delta"] * signed_size
    notional = size * mark
    asset_kind = spec.get("asset_kind", "")

    if asset_kind in ("PERP", "FUTURE"):
        params = _req_dict(spec, "delta1_cross_margin_params", sym)
        r = xm_perp_margin(size, mark, dict(params))
        imr, mmr = r["imr"], r["mmr"]
    elif asset_kind in ("OPTION", "PERP_OPTION"):
        ocp = _req_dict(spec, "option_cross_margin_params", sym)
        spot = md["underlying_price"]
        strike = _req_f(spec, "strike_price", sym)
        is_call = _req_str(spec, "option_type", sym) == "CALL"
        is_long = side in ("BUY", "LONG")
        imr = _xm_option_margin(dict(_req_dict(ocp, "imf", sym)), mark, spot, strike, is_call, is_long, size)
        mmr = _xm_option_margin(dict(_req_dict(ocp, "mmf", sym)), mark, spot, strike, is_call, is_long, size)
    else:
        raise ValueError(f"unsupported asset_kind {asset_kind!r} for {sym}")

    return {
        "imr": imr,
        "mmr": mmr,
        "delta_contrib": delta_contrib,
        "mark_price": mark,
        "notional": notional,
    }


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
    position_detail: list[dict[str, object]] = []

    for pos in positions:
        r = xm_position(pos, market_data, market_specs)
        total_imr += cast(float, r["imr"])
        total_mmr += cast(float, r["mmr"])
        port_delta += cast(float, r["delta_contrib"])
        position_detail.append({**pos, **r})

    return {
        "IMR": total_imr,
        "MMR": total_mmr,
        "portfolio_delta": port_delta,
        "spot_balance_margin": spot_bm,
        "positions": position_detail,
    }
