"""Paradex margin calculations.

Pure margin-math functions (no I/O, no auth). Inputs are plain dicts so the
same engine works against the Paradex REST API, a JSON snapshot, a backtester,
or a unit-test fixture.

All margin-policy parameters (scenarios, scaling factors, IMF/MMF) MUST be
fetched from the live exchange config — this module no longer ships local
fallback values for them. See
:mod:`paradex_py.margin.config` for fetch helpers.

Quick start::

    from paradex_py.margin import compute
    from paradex_py.margin.config import pm_config_for_compute

    pm_cfg = pm_config_for_compute(client, "BTC")
    result = compute(
        positions=[{"market": "BTC-USD-PERP", "side": "BUY", "size": 0.1}],
        orders=[],
        market_data={...},
        market_specs={...},
        margin_methodology="portfolio_margin",
        pm_config=pm_cfg,
    )
    # result["IMR"], result["MMR"], result["portfolio_delta"], ...
"""

from .adapters import (
    MarginInputs,
    append_what_if_positions,
    infer_underlying,
    market_specs_by_symbol,
    normalise_balances,
    normalise_market_data,
    normalise_orders,
    normalise_positions,
)
from .black_scholes import bs_delta, bs_gamma, bs_price, bs_vega, norm_cdf, norm_pdf
from .compute import compute
from .config import (
    fee_rate_for_market,
    normalise_delta1_margin_params,
    normalise_option_margin_params,
    normalise_option_margin_side_params,
    normalise_pm_config,
    pm_config_for_compute,
    pm_config_from_snapshot,
    select_pm_config,
    validate_pm_config,
)
from .constants import OPTION_EXPIRY_HOUR, OPTION_FEE_CAP, TWAP_SETTLEMENT_MIN, YEAR_IN_DAYS
from .cross_margin import (
    _xm_option_margin,
    compute_xm,
    spot_balance_margin,
    xm_option_margin,
    xm_perp_margin,
    xm_position,
)
from .hedging import delta_hedge_size, delta_hedge_size_for_market
from .liquidation import find_liquidation_price
from .markets import market_expiry, parse_expiry, parse_market
from .portfolio_margin import _fee_provision, _live_frac, _scenario_price, compute_pm
from .synthetic import (
    funding_index_at,
    funding_pnl_from_index,
    funding_rate_8h_from_index,
    normalise_synthetic_pm_config,
    normalise_synthetic_position,
    synthetic_fee_provision,
    synthetic_margin_at_spot,
    synthetic_pm_margin_at_spot,
)
from .types import Balance, MarketData, MarketSpec, Order, PMConfig, Position, RawDict, SyntheticPosition

__all__ = [
    # Public API
    "compute",
    "compute_xm",
    "compute_pm",
    "xm_position",
    "xm_perp_margin",
    "xm_option_margin",
    "spot_balance_margin",
    "delta_hedge_size",
    "delta_hedge_size_for_market",
    "find_liquidation_price",
    "parse_market",
    "parse_expiry",
    "market_expiry",
    # API response adapters
    "MarginInputs",
    "normalise_positions",
    "normalise_orders",
    "normalise_balances",
    "normalise_market_data",
    "market_specs_by_symbol",
    "infer_underlying",
    "append_what_if_positions",
    "fee_rate_for_market",
    "normalise_delta1_margin_params",
    "normalise_option_margin_params",
    "normalise_option_margin_side_params",
    "normalise_pm_config",
    "Position",
    "Order",
    "Balance",
    "MarketData",
    "MarketSpec",
    "PMConfig",
    "SyntheticPosition",
    "RawDict",
    # PM config helpers
    "pm_config_for_compute",
    "pm_config_from_snapshot",
    "select_pm_config",
    "validate_pm_config",
    # Synthetic/backtester helpers
    "normalise_synthetic_pm_config",
    "normalise_synthetic_position",
    "synthetic_fee_provision",
    "synthetic_pm_margin_at_spot",
    "synthetic_margin_at_spot",
    "funding_index_at",
    "funding_pnl_from_index",
    "funding_rate_8h_from_index",
    # Black-Scholes
    "bs_price",
    "bs_delta",
    "bs_gamma",
    "bs_vega",
    "norm_cdf",
    "norm_pdf",
    # Protocol invariants (NOT exchange-config policy values)
    "YEAR_IN_DAYS",
    "OPTION_EXPIRY_HOUR",
    "TWAP_SETTLEMENT_MIN",
    "OPTION_FEE_CAP",
    # Internal helpers (re-exported for tests)
    "_xm_option_margin",
    "_fee_provision",
    "_live_frac",
    "_scenario_price",
]
