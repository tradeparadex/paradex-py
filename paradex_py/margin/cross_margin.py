"""Cross-margin (XM) calculations for perpetuals, futures, and options.

All margin-policy fields (``imf_base``, ``mmf_factor``, option ``long_itm`` /
``premium_multiplier`` / ``short_itm`` / ``short_otm`` / ``short_put_cap``)
must come from the live exchange config — see ``delta1_cross_margin_params``
and ``option_cross_margin_params`` on each market. Missing values raise
``ValueError`` rather than silently defaulting.
"""

# pyright: reportPrivateUsage=false

from ._utils import _req_dict, _req_f, _req_str
from .config import normalise_delta1_margin_params, normalise_option_margin_params
from .constants import OPTION_FEE_CAP
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

    mark = md["mark_price"]
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
    """Compute standalone cross-margin detail for a single open order.

    Margin formulas use mark price; aggressive limit prices are charged through
    ``open_loss`` at the portfolio aggregation layer.
    """
    return _xm_instrument(order, market_data, market_specs)


def _signed_size(item: Position) -> float:
    size = abs(float(item["size"]))
    return size if item["side"] in ("BUY", "LONG") else -size


def _xm_fee_provision(
    sym: str,
    size: float,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> float:
    if not size:
        return 0.0
    md = market_data[sym]
    hfr = md["fee_rate"]
    if not hfr:
        return 0.0
    mark = md["mark_price"]
    if market_specs.get(sym, {}).get("asset_kind", "") in ("OPTION", "PERP_OPTION"):
        return min(hfr * md["underlying_price"], OPTION_FEE_CAP * mark) * size
    return hfr * size * mark


def _xm_order_open_loss(order: Order, mark: float) -> float:
    size = abs(float(order["size"]))
    if order["side"] in ("BUY", "LONG"):
        return max(0.0, order["price"] - mark) * size
    return max(0.0, mark - order["price"]) * size


def _group_by_market(items: list[Position]) -> dict[str, list[Position]]:
    grouped: dict[str, list[Position]] = {}
    for item in items:
        grouped.setdefault(item["market"], []).append(item)
    return grouped


def _group_orders_by_market(items: list[Order]) -> dict[str, list[Order]]:
    grouped: dict[str, list[Order]] = {}
    for item in items:
        grouped.setdefault(item["market"], []).append(item)
    return grouped


def _xm_market_margin(
    sym: str,
    positions: list[Position],
    orders: list[Order],
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> dict[str, float]:
    try:
        md = market_data[sym]
    except KeyError as e:
        raise ValueError(f"missing market data for XM market {sym!r}") from e
    try:
        spec = market_specs[sym]
    except KeyError as e:
        raise ValueError(f"missing market spec for XM market {sym!r}") from e

    mark = md["mark_price"]
    signed_position_size = sum(_signed_size(pos) for pos in positions)
    buy_order_size = sum(abs(float(order["size"])) for order in orders if order["side"] in ("BUY", "LONG"))
    sell_order_size = sum(abs(float(order["size"])) for order in orders if order["side"] not in ("BUY", "LONG"))
    buy_open_size = max(0.0, buy_order_size + signed_position_size)
    sell_open_size = max(0.0, sell_order_size - signed_position_size)
    open_size = max(buy_open_size, sell_open_size)

    asset_kind = spec.get("asset_kind", "")
    if asset_kind in ("PERP", "FUTURE"):
        params = normalise_delta1_margin_params(_req_dict(spec, "delta1_cross_margin_params", sym), sym)
        buy_imr = buy_open_size * mark * params["imf_base"]
        sell_imr = sell_open_size * mark * params["imf_base"]
        net_imr = max(buy_imr, sell_imr)
        net_mmr = abs(signed_position_size) * mark * params["imf_base"] * params["mmf_factor"]
    elif asset_kind in ("OPTION", "PERP_OPTION"):
        ocp = normalise_option_margin_params(_req_dict(spec, "option_cross_margin_params", sym), sym)
        spot = md["underlying_price"]
        strike = _req_f(spec, "strike_price", sym)
        is_call = _req_str(spec, "option_type", sym) == "CALL"
        buy_imr = _xm_option_margin(ocp["imf"], mark, spot, strike, is_call, True, buy_open_size)
        sell_imr = _xm_option_margin(ocp["imf"], mark, spot, strike, is_call, False, sell_open_size)
        net_imr = max(buy_imr, sell_imr)
        net_mmr = (
            _xm_option_margin(
                ocp["mmf"],
                mark,
                spot,
                strike,
                is_call,
                signed_position_size > 0,
                abs(signed_position_size),
            )
            if signed_position_size
            else 0.0
        )
    else:
        raise ValueError(f"unsupported asset_kind {asset_kind!r} for {sym}")

    fee_imr = _xm_fee_provision(sym, open_size, market_data, market_specs)
    fee_mmr = _xm_fee_provision(sym, abs(signed_position_size), market_data, market_specs)
    open_loss = sum(_xm_order_open_loss(order, mark) for order in orders)
    return {
        "net_imr": net_imr,
        "net_mmr": net_mmr,
        "fee_provision_imr": fee_imr,
        "fee_provision_mmr": fee_mmr,
        "open_loss": open_loss,
        "imr": net_imr + fee_imr + open_loss,
        "mmr": net_mmr + fee_mmr,
        "buy_open_size": buy_open_size,
        "sell_open_size": sell_open_size,
        "open_size": open_size,
        "open_notional": open_size * mark,
        "signed_position_size": signed_position_size,
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
    """Compute total cross-margin IMR/MMR for all positions and orders.

    Returns full breakdown including per-position detail and portfolio delta.
    """
    spot_bm = spot_balance_margin(balances or [], market_data)
    port_delta = 0.0
    position_detail: list[XMPositionDetail] = []
    order_detail: list[XMOrderDetail] = []

    for pos in positions:
        r = xm_position(pos, market_data, market_specs)
        port_delta += r["delta_contrib"]
        position_detail.append({**pos, **r})

    for order in orders:
        r = xm_order(order, market_data, market_specs)
        port_delta += r["delta_contrib"]
        order_detail.append({**order, **r, "mmr": 0.0})

    positions_by_market = _group_by_market(positions)
    orders_by_market = _group_orders_by_market(orders)
    markets: dict[str, dict[str, float]] = {}
    for sym in sorted(positions_by_market.keys() | orders_by_market.keys()):
        markets[sym] = _xm_market_margin(
            sym,
            positions_by_market.get(sym, []),
            orders_by_market.get(sym, []),
            market_data,
            market_specs,
        )

    net_imr = sum(m["net_imr"] for m in markets.values())
    net_mmr = sum(m["net_mmr"] for m in markets.values())
    fee_imr = sum(m["fee_provision_imr"] for m in markets.values())
    fee_mmr = sum(m["fee_provision_mmr"] for m in markets.values())
    open_loss = sum(m["open_loss"] for m in markets.values())
    total_imr = spot_bm + net_imr + fee_imr + open_loss
    total_mmr = spot_bm + net_mmr + fee_mmr

    return {
        "IMR": total_imr,
        "MMR": total_mmr,
        "portfolio_delta": port_delta,
        "spot_balance_margin": spot_bm,
        "net_imr": net_imr,
        "net_mmr": net_mmr,
        "fee_provision_imr": fee_imr,
        "fee_provision_mmr": fee_mmr,
        "open_loss": open_loss,
        "positions": position_detail,
        "orders": order_detail,
        "markets": markets,
    }
