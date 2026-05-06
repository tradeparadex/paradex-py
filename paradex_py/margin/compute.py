"""Top-level dispatcher routing to cross-margin or portfolio-margin."""

from datetime import datetime

from .cross_margin import compute_xm
from .portfolio_margin import compute_pm
from .types import Balance, MarketData, MarketSpec, Order, Position, RawDict


def compute(
    positions: list[Position],
    orders: list[Order],
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
    margin_methodology: str = "cross_margin",
    balances: list[Balance] | None = None,
    pm_config: RawDict | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Compute IMR/MMR using the requested methodology.

    Args:
        positions: list of {market, side, size}
        orders: list of {market, side, size, price}
        market_data: {symbol → {mark_price, delta, mark_iv, ...}}
        market_specs: {symbol → {asset_kind, delta1_cross_margin_params, ...}}
        margin_methodology: "cross_margin" or "portfolio_margin"
        balances: list of {token, size} (optional)
        pm_config: live PM config from /system/portfolio-margin-config —
            **required** when ``margin_methodology="portfolio_margin"``
        now: evaluation timestamp for option DTE — defaults to UTC now

    Returns:
        Dict with `IMR`, `MMR`, `portfolio_delta`, `margin_methodology`, and
        methodology-specific detail (per-position breakdown for XM; worst-case
        scenario, delta-min, funding/fee provisions for PM).
    """
    if margin_methodology == "portfolio_margin":
        if pm_config is None:
            raise ValueError("portfolio_margin requires pm_config from /system/portfolio-margin-config")
        result = compute_pm(
            positions,
            orders,
            market_data,
            market_specs,
            pm_config,
            balances=balances,
            now=now,
        )
    else:
        result = compute_xm(positions, orders, market_data, market_specs, balances)

    result["margin_methodology"] = margin_methodology
    return result
