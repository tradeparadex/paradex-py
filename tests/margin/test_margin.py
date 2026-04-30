"""Unit tests for paradex_py.margin.

Fixtures use real Paradex market data and a snapshot of the BTC PM config
from ``/system/portfolio-margin-config`` (2026-04-22) so any drift versus the
exchange-reported IMR/MMR is caught immediately. All tests use fixed input
dicts; no auth, no network calls.

Margin-policy values (scenarios, vega powers, vol shock floor, hedged/unhedged
factors) are explicit fixtures here on purpose — the production engine
refuses to use local fallbacks (see paradex_py/margin/constants.py docstring).
"""

import math
from datetime import datetime, timezone

from paradex_py.margin import (
    MarginInputs,
    _fee_provision,
    _live_frac,
    _scenario_price,
    _xm_option_margin,
    bs_delta,
    bs_gamma,
    bs_price,
    bs_vega,
    compute,
    compute_pm,
    delta_hedge_size,
    delta_hedge_size_for_market,
    find_liquidation_price,
    funding_index_at,
    funding_pnl_from_index,
    funding_rate_8h_from_index,
    norm_cdf,
    normalise_synthetic_pm_config,
    normalise_synthetic_position,
    parse_expiry,
    parse_market,
    pm_config_from_snapshot,
    select_pm_config,
    spot_balance_margin,
    synthetic_fee_provision,
    synthetic_margin_at_spot,
    xm_position,
)
from paradex_py.margin.adapters import fee_rate_for_market, infer_underlying, normalise_market_data, normalise_orders
from paradex_py.margin.config import normalise_option_margin_side_params
from paradex_py.margin.cross_margin import compute_xm

# ── Fixtures ───────────────────────────────────────────────────────────────

MARKET_DATA = {
    "BTC-USD-PERP": {
        "mark_price": 77888.84,
        "delta": 0.99934658,
        "mark_iv": None,
        "underlying_price": 77939.768,
        "funding_rate": -0.00017403,
        "interest_rate": 0.0,
        "fee_rate": 0.0,
    },
    "BTC-USD-8MAY26-78000-C": {
        "mark_price": 2455.661,
        "delta": 0.47715119,
        "mark_iv": 0.42746687,
        "underlying_price": 77939.768,
        "funding_rate": 0.0,
        "interest_rate": 0.0,
        "fee_rate": 0.0,
    },
}

MARKET_SPECS = {
    "BTC-USD-PERP": {
        "asset_kind": "PERP",
        "delta1_cross_margin_params": {"imf_base": "0.02", "mmf_factor": "0.5"},
        "option_cross_margin_params": None,
        "order_size_increment": "0.00001",
    },
    "BTC-USD-8MAY26-78000-C": {
        "asset_kind": "OPTION",
        "option_type": "CALL",
        "strike_price": "78000",
        "delta1_cross_margin_params": None,
        "option_cross_margin_params": {
            "imf": {
                "long_itm": "0.2",
                "premium_multiplier": "1",
                "short_itm": "0.15",
                "short_otm": "0.1",
                "short_put_cap": "0.5",
            },
            "mmf": {
                "long_itm": "0.1",
                "premium_multiplier": "0.5",
                "short_itm": "0.075",
                "short_otm": "0.05",
                "short_put_cap": "0.5",
            },
        },
        "order_size_increment": "0.001",
    },
}

POSITIONS = [
    {"market": "BTC-USD-PERP", "side": "SELL", "size": 0.0005},
    {"market": "BTC-USD-8MAY26-78000-C", "side": "BUY", "size": 0.001},
]

BALANCES = [{"token": "USDC", "size": 10.25}]

# Snapshot of GET /system/portfolio-margin-config?base_asset=BTC (2026-04-22).
# Refresh against the live exchange when running these tests against a new
# release — the engine will not silently fall back to local defaults.
PM_CONFIG = {
    "base_asset": "BTC",
    "hedged_margin_factor": 0.01,
    "unhedged_margin_factor": 0.02,
    "mmf_factor": 0.50,
    "vol_shock_params": {
        "vega_power_short_dte": 0.30,
        "vega_power_long_dte": 0.13,
        "dte_floor_days": 1,
        "min_vol_shock_up": 0.40,
    },
    "scenarios": [
        {"spot_shock": ss, "vol_shock": vs, "weight": w}
        for ss, vs, w in [
            (0.16, 0.40, 1),
            (0.12, 0.40, 1),
            (0.12, -0.22, 1),
            (0.08, 0.40, 1),
            (0.08, -0.22, 1),
            (0.04, 0.40, 1),
            (0.04, -0.22, 1),
            (0.0, 0.40, 1),
            (0.0, -0.22, 1),
            (-0.04, 0.40, 1),
            (-0.04, -0.22, 1),
            (-0.08, 0.40, 1),
            (-0.08, -0.22, 1),
            (-0.12, 0.40, 1),
            (-0.12, -0.22, 1),
            (-0.16, 0.40, 1),
            (-0.66, 0.40, 0.18),
            (-0.33, 0.40, 0.36),
            (0.50, 0.40, 0.24),
            (1.0, 0.40, 0.12),
            (2.0, 0.40, 0.06),
            (3.0, 0.40, 0.04),
            (4.0, 0.40, 0.03),
            (5.0, 0.40, 0.024),
        ]
    ],
}

# Convenience: pre-flattened scenarios in [ss, vs, weight] form (matches
# what compute_pm builds internally) for the worst-scenario test.
_SCENARIOS_FLAT = [[s["spot_shock"], s["vol_shock"], s["weight"]] for s in PM_CONFIG["scenarios"]]

# pm_params dict for direct _scenario_price calls (mirrors what compute_pm
# builds from PM_CONFIG.vol_shock_params).
_PM_PARAMS = {
    "interest_rate": 0.0,
    "dte_floor": PM_CONFIG["vol_shock_params"]["dte_floor_days"],
    "vp_short": PM_CONFIG["vol_shock_params"]["vega_power_short_dte"],
    "vp_long": PM_CONFIG["vol_shock_params"]["vega_power_long_dte"],
    "min_vol_shock_up": PM_CONFIG["vol_shock_params"]["min_vol_shock_up"],
}


def assert_close(a, b, tol=0.01, label=""):
    assert abs(a - b) <= tol, f"{label}: expected ~{b:.6f}, got {a:.6f} (diff {a - b:+.6f})"


# ── Black-Scholes ──────────────────────────────────────────────────────────


def test_norm_cdf_symmetry():
    assert_close(norm_cdf(0), 0.5, tol=1e-9, label="norm_cdf(0)")
    for x in [0.5, 1.0, 1.96, 2.5]:
        assert_close(norm_cdf(-x), 1 - norm_cdf(x), tol=1e-9, label=f"symmetry({x})")


def test_bs_price_intrinsic_at_expiry():
    assert_close(bs_price(100, 90, 0, 0, 0.3, True), 10.0, tol=1e-9, label="call ITM")
    assert_close(bs_price(100, 110, 0, 0, 0.3, True), 0.0, tol=1e-9, label="call OTM")
    assert_close(bs_price(100, 110, 0, 0, 0.3, False), 10.0, tol=1e-9, label="put ITM")
    assert_close(bs_price(100, 90, 0, 0, 0.3, False), 0.0, tol=1e-9, label="put OTM")


def test_bs_price_atm_positive():
    price = bs_price(100, 100, 1.0, 0, 0.5, True)
    assert price > 0, f"ATM call should be positive, got {price}"


def test_bs_price_known_value():
    """S=100, K=100, T=1, r=0, o=0.2 → 7.9656."""
    price = bs_price(100, 100, 1.0, 0, 0.2, True)
    assert_close(price, 7.9656, tol=0.01, label="known BS call price")


def test_bs_put_call_parity():
    S, K, T, r, sigma = 100, 95, 0.5, 0.05, 0.3
    call = bs_price(S, K, T, r, sigma, True)
    put = bs_price(S, K, T, r, sigma, False)
    assert_close(call - put, S - K * math.exp(-r * T), tol=1e-6, label="put-call parity")


def test_bs_inputs_validate_domain():
    import pytest

    invalid_inputs = [
        (0.0, 100.0, 1.0, 0.0, 0.2),
        (100.0, 0.0, 1.0, 0.0, 0.2),
        (100.0, 100.0, -1e-9, 0.0, 0.2),
        (100.0, 100.0, 1.0, 0.0, -0.2),
        (math.inf, 100.0, 1.0, 0.0, 0.2),
    ]
    for S, K, T, r, sigma in invalid_inputs:
        with pytest.raises(ValueError):
            bs_price(S, K, T, r, sigma, True)
        with pytest.raises(ValueError):
            bs_delta(S, K, T, r, sigma, True)
        with pytest.raises(ValueError):
            bs_gamma(S, K, T, r, sigma)
        with pytest.raises(ValueError):
            bs_vega(S, K, T, r, sigma)


# ── Market parsing ─────────────────────────────────────────────────────────


def test_parse_market_perp():
    assert parse_market("BTC-USD-PERP")["type"] == "perp"


def test_parse_market_dated_call():
    r = parse_market("BTC-USD-8MAY26-78000-C")
    assert r["type"] == "dated_option"
    assert r["is_call"] is True
    assert r["strike"] == 78000.0
    assert r["expiry"] == datetime(2026, 5, 8, 8, tzinfo=timezone.utc)


def test_parse_market_prefers_exchange_expiry():
    expiry_at = int(datetime(2026, 5, 8, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
    r = parse_market("BTC-USD-8MAY26-78000-C", {"expiry_at": expiry_at})
    assert r["expiry"] == datetime(2026, 5, 8, 10, 30, tzinfo=timezone.utc)


def test_parse_market_dated_put():
    r = parse_market("BTC-USD-8MAY26-78000-P")
    assert r["type"] == "dated_option"
    assert r["is_call"] is False


def test_parse_expiry():
    assert parse_expiry("8MAY26") == datetime(2026, 5, 8, 8, tzinfo=timezone.utc)
    assert parse_expiry("31DEC25") == datetime(2025, 12, 31, 8, tzinfo=timezone.utc)
    assert parse_expiry("invalid") is None


# ── XM margin ─────────────────────────────────────────────────────────────


def test_xm_perp_short():
    pos = {"market": "BTC-USD-PERP", "side": "SELL", "size": 0.0005}
    r = xm_position(pos, MARKET_DATA, MARKET_SPECS)
    assert_close(r["imr"], 0.7789, tol=0.001, label="perp short IMR")
    assert_close(r["mmr"], 0.3894, tol=0.001, label="perp short MMR")
    assert_close(r["delta_contrib"], -0.000500, tol=1e-5, label="perp short delta")


def test_xm_long_call():
    pos = {"market": "BTC-USD-8MAY26-78000-C", "side": "BUY", "size": 0.001}
    r = xm_position(pos, MARKET_DATA, MARKET_SPECS)
    assert_close(r["imr"], 2.455661, tol=0.001, label="long call IMR")
    assert_close(r["mmr"], 1.227830, tol=0.001, label="long call MMR")
    assert r["delta_contrib"] > 0


def test_xm_total():
    """Exchange-reported: IMR $3.2504, MMR $1.6339 (within $0.02 fee provision)."""
    result = compute_xm(POSITIONS, [], MARKET_DATA, MARKET_SPECS, BALANCES)
    assert_close(result["IMR"], 3.2504, tol=0.02, label="total IMR vs exchange")
    assert_close(result["MMR"], 1.6339, tol=0.02, label="total MMR vs exchange")


def test_xm_total_includes_order_imr_but_not_mmr():
    result = compute_xm(
        [],
        [{"market": "BTC-USD-PERP", "side": "BUY", "size": 0.1, "price": MARKET_DATA["BTC-USD-PERP"]["mark_price"]}],
        MARKET_DATA,
        MARKET_SPECS,
    )
    assert_close(result["IMR"], 155.77768, tol=0.001, label="order IMR")
    assert_close(result["MMR"], 0.0, tol=0.001, label="order MMR")
    assert result["portfolio_delta"] > 0
    assert len(result["orders"]) == 1


def test_xm_perp_orders_net_by_market_side_and_charge_open_loss():
    result = compute_xm(
        [{"market": "BTC-USD-PERP", "side": "SELL", "size": 1.0}],
        [
            {"market": "BTC-USD-PERP", "side": "BUY", "size": 3.0, "price": 90000.0},
            {"market": "BTC-USD-PERP", "side": "SELL", "size": 2.0, "price": 88000.0},
        ],
        {
            "BTC-USD-PERP": {
                **MARKET_DATA["BTC-USD-PERP"],
                "mark_price": 90000.0,
                "underlying_price": 90000.0,
                "fee_rate": 0.0003,
            }
        },
        MARKET_SPECS,
    )
    market = result["markets"]["BTC-USD-PERP"]
    assert_close(market["buy_open_size"], 2.0, tol=1e-9, label="buy open size")
    assert_close(market["sell_open_size"], 3.0, tol=1e-9, label="sell open size")
    assert_close(result["net_imr"], 5400.0, tol=0.001, label="side-netted net IMR")
    assert_close(result["fee_provision_imr"], 81.0, tol=0.001, label="IMR fee on open size")
    assert_close(result["MMR"], 927.0, tol=0.001, label="MMR excludes open orders")


def test_xm_aggressive_order_charges_open_loss():
    result = compute_xm(
        [],
        [{"market": "BTC-USD-PERP", "side": "BUY", "size": 0.1, "price": 80000.0}],
        MARKET_DATA,
        MARKET_SPECS,
    )
    expected_open_loss = (80000.0 - MARKET_DATA["BTC-USD-PERP"]["mark_price"]) * 0.1
    assert_close(result["open_loss"], expected_open_loss, tol=0.001, label="open loss")
    assert result["IMR"] > result["net_imr"]


def test_spot_balance_margin_usdc_excluded():
    sbm = spot_balance_margin([{"token": "USDC", "size": 100.0}], MARKET_DATA)
    assert sbm == 0.0


def test_spot_balance_margin_non_usdc():
    md = {"ETH-USD-PERP": {"mark_price": 2000.0}}
    sbm = spot_balance_margin([{"token": "ETH", "size": 0.5}], md)
    assert_close(sbm, 1000.0, tol=0.01, label="ETH spot margin")


# ── Delta hedge ────────────────────────────────────────────────────────────


def test_delta_hedge_positive_delta():
    side, size = delta_hedge_size(0.01, 1.0, size_increment=0.00001)
    assert side == "SELL"
    assert_close(size, 0.01, tol=0.00001, label="sell size")


def test_delta_hedge_negative_delta():
    side, size = delta_hedge_size(-0.01, 1.0, size_increment=0.00001)
    assert side == "BUY"
    assert_close(size, 0.01, tol=0.00001, label="buy size")


def test_delta_hedge_rounds_down():
    _, size = delta_hedge_size(0.00047, 1.0, size_increment=0.00001)
    assert size == 0.00047


def test_delta_hedge_near_zero():
    side, size = delta_hedge_size(0.000005, 1.0, size_increment=0.00001)
    assert side == "NONE"
    assert size == 0.0


def test_delta_hedge_uses_market_size_increment():
    side, size = delta_hedge_size_for_market(
        0.01234,
        1.0,
        {"symbol": "BTC-USD-PERP", "order_size_increment": "0.001"},
    )
    assert side == "SELL"
    assert size == 0.012


# ── compute() dispatcher ───────────────────────────────────────────────────


def test_compute_cross_margin_routes_to_xm():
    r = compute(POSITIONS, [], MARKET_DATA, MARKET_SPECS, margin_methodology="cross_margin", balances=BALANCES)
    assert r["margin_methodology"] == "cross_margin"
    assert "IMR" in r and "MMR" in r
    assert r["IMR"] > 0


def test_compute_pm_routes_to_scenario_scan():
    r = compute(
        POSITIONS,
        [],
        MARKET_DATA,
        MARKET_SPECS,
        margin_methodology="portfolio_margin",
        balances=BALANCES,
        pm_config=PM_CONFIG,
    )
    assert r["margin_methodology"] == "portfolio_margin"
    assert "worst_loss" in r
    assert "delta_min" in r


def test_compute_pm_requires_pm_config():
    """PM mode without pm_config must raise — never silently fall back."""
    import pytest

    with pytest.raises(ValueError, match="pm_config"):
        compute(POSITIONS, [], MARKET_DATA, MARKET_SPECS, margin_methodology="portfolio_margin")


def test_compute_pm_worst_scenario_is_vol_crush():
    r = compute(
        POSITIONS,
        [],
        MARKET_DATA,
        MARKET_SPECS,
        margin_methodology="portfolio_margin",
        pm_config=PM_CONFIG,
    )
    worst_sc = _SCENARIOS_FLAT[r["worst_idx"]]
    assert worst_sc[1] < 0, (
        f"Expected negative vol shock for long-vol position, got scenario #{r['worst_idx'] + 1}: {worst_sc}"
    )


def test_compute_pm_portfolio_delta_includes_orders():
    r = compute_pm(
        POSITIONS,
        [{"market": "BTC-USD-PERP", "side": "BUY", "size": 0.01, "price": 78000.0}],
        MARKET_DATA,
        MARKET_SPECS,
        PM_CONFIG,
    )
    assert_close(r["order_delta"], MARKET_DATA["BTC-USD-PERP"]["delta"] * 0.01, tol=1e-9, label="order delta")
    assert_close(r["portfolio_delta"], r["position_delta"] + r["order_delta"], tol=1e-9, label="portfolio delta")


def test_compute_what_if_increases_imr():
    base = compute(POSITIONS, [], MARKET_DATA, MARKET_SPECS, pm_config=PM_CONFIG)
    what_if_pos = [*POSITIONS, {"market": "BTC-USD-PERP", "side": "BUY", "size": 0.01}]
    with_pos = compute(what_if_pos, [], MARKET_DATA, MARKET_SPECS, pm_config=PM_CONFIG)
    assert with_pos["IMR"] > base["IMR"]


# ── XM option margin formulas ─────────────────────────────────────────────

_IMF_PARAMS = normalise_option_margin_side_params(
    {
        "long_itm": "0.2",
        "premium_multiplier": "1",
        "short_itm": "0.15",
        "short_otm": "0.1",
        "short_put_cap": "0.5",
    }
)


def test_xm_long_call_otm_uses_mark():
    mark, spot, size = 2455.661, 77939.768, 0.001
    imr = _xm_option_margin(_IMF_PARAMS, mark, spot, strike=78000, is_call=True, is_long=True, size=size)
    assert_close(imr, mark * 1.0 * size, tol=0.001, label="OTM long call IMR")


def test_xm_long_call_deep_itm_capped_by_long_itm():
    mark, spot, size, strike = 20000.0, 95000.0, 0.01, 50000.0
    imr = _xm_option_margin(_IMF_PARAMS, mark, spot, strike, is_call=True, is_long=True, size=size)
    expected = 0.2 * spot * size
    assert_close(imr, expected, tol=0.01, label="deep ITM call capped")


def test_xm_short_call_otm_continuous():
    spot, strike, size = 77939.768, 78000.0, 0.001
    otm_amt = max(0, strike - spot)
    expected = max(0.15 * spot - otm_amt, 0.1 * spot) * size
    imr = _xm_option_margin(_IMF_PARAMS, mark=0.0, spot=spot, strike=strike, is_call=True, is_long=False, size=size)
    assert_close(imr, expected, tol=0.001, label="OTM short call IMR")


def test_xm_short_put_cap():
    spot, strike, size = 77939.768, 90000.0, 0.01
    otm_amt = max(0, spot - strike)
    raw = max(0.15 * spot - otm_amt, 0.1 * spot)
    cap = 0.5 * spot
    expected = min(raw, cap) * size
    imr = _xm_option_margin(_IMF_PARAMS, mark=0.0, spot=spot, strike=strike, is_call=False, is_long=False, size=size)
    assert_close(imr, expected, tol=0.01, label="short put IMR capped")
    assert imr <= 0.5 * spot * size + 0.001


def test_xm_perp_imf_linear_in_size():
    """IMR = |size| * mark * imf_base; same per-unit IMR at any size."""
    specs = {
        "BTC-USD-PERP": {
            "asset_kind": "PERP",
            "delta1_cross_margin_params": {"imf_base": "0.02", "mmf_factor": "0.5"},
        }
    }
    md = {"BTC-USD-PERP": {"mark_price": 80000.0, "delta": 1.0, "underlying_price": 80000.0}}
    r_small = xm_position({"market": "BTC-USD-PERP", "side": "BUY", "size": 1.0}, md, specs)
    r_large = xm_position({"market": "BTC-USD-PERP", "side": "BUY", "size": 100.0}, md, specs)
    assert_close(r_small["imr"], 1.0 * 80000.0 * 0.02, tol=0.001, label="small IMR")
    assert_close(r_large["imr"] / 100.0, r_small["imr"], tol=0.001, label="per-unit IMR matches")


def test_xm_perp_missing_imf_base_raises():
    """Production safety: missing margin-policy fields must raise loudly."""
    import pytest

    specs = {"BTC-USD-PERP": {"asset_kind": "PERP", "delta1_cross_margin_params": {"mmf_factor": "0.5"}}}
    md = {"BTC-USD-PERP": {"mark_price": 80000.0, "delta": 1.0, "underlying_price": 80000.0}}
    pos = {"market": "BTC-USD-PERP", "side": "BUY", "size": 1.0}
    with pytest.raises(ValueError, match="imf_base"):
        xm_position(pos, md, specs)


# ── Fee provision ──────────────────────────────────────────────────────────


def test_fee_provision_perp():
    md = {"BTC-USD-PERP": {"mark_price": 80000.0, "underlying_price": 80000.0, "fee_rate": 0.0003}}
    sp = {"BTC-USD-PERP": {"asset_kind": "PERP"}}
    fp = _fee_provision("BTC-USD-PERP", 0.01, md, sp)
    assert_close(fp, 0.0003 * 0.01 * 80000.0, tol=0.001, label="perp fee provision")


def test_fee_provision_option_capped():
    md = {
        "BTC-USD-8MAY26-78000-C": {
            "mark_price": 2455.661,
            "underlying_price": 77939.768,
            "fee_rate": 0.0003,
        }
    }
    sp = {"BTC-USD-8MAY26-78000-C": {"asset_kind": "OPTION"}}
    fp = _fee_provision("BTC-USD-8MAY26-78000-C", 0.001, md, sp)
    expected = min(0.0003 * 77939.768, 0.125 * 2455.661) * 0.001
    assert_close(fp, expected, tol=0.001, label="option fee provision")


def test_fee_provision_zero_if_no_rate():
    fp = _fee_provision("BTC-USD-PERP", 0.01, MARKET_DATA, MARKET_SPECS)
    assert fp == 0.0


# ── Min vol shock floor ────────────────────────────────────────────────────


def test_min_vol_shock_up_floor():
    now = datetime(2026, 4, 22, 0, 0, tzinfo=timezone.utc)
    md = {
        "BTC-USD-8MAY26-78000-C": {
            "mark_price": 1000.0,
            "delta": 0.4,
            "mark_iv": 0.05,
            "underlying_price": 77939.768,
        }
    }
    price = _scenario_price(
        "BTC-USD-8MAY26-78000-C",
        md,
        {},
        spot=77939.768,
        basis=0.0,
        ss=0.0,
        vs=0.40,
        now=now,
        pm_params=_PM_PARAMS,
    )
    intrinsic = max(0, 77939.768 - 78000)
    assert price > intrinsic + 100, f"Upward vol shock floor not applied: price={price:.2f}"


def test_no_vol_shock_floor_for_downward():
    now = datetime(2026, 4, 22, 0, 0, tzinfo=timezone.utc)
    md = {
        "BTC-USD-8MAY26-78000-C": {
            "mark_price": 100.0,
            "delta": 0.4,
            "mark_iv": 0.80,
            "underlying_price": 77939.768,
        }
    }
    price_down = _scenario_price(
        "BTC-USD-8MAY26-78000-C",
        md,
        {},
        spot=77939.768,
        basis=0.0,
        ss=0.0,
        vs=-0.22,
        now=now,
        pm_params=_PM_PARAMS,
    )
    price_up = _scenario_price(
        "BTC-USD-8MAY26-78000-C",
        md,
        {},
        spot=77939.768,
        basis=0.0,
        ss=0.0,
        vs=0.40,
        now=now,
        pm_params=_PM_PARAMS,
    )
    assert price_down < price_up


# ── TWAP live fraction ─────────────────────────────────────────────────────


def test_live_frac_outside_twap_window():
    now = datetime(2026, 5, 8, 7, 0, 0, tzinfo=timezone.utc)
    exp = datetime(2026, 5, 8, 8, 0, 0, tzinfo=timezone.utc)
    assert _live_frac(exp, now) == 1.0


def test_live_frac_inside_twap_window():
    now = datetime(2026, 5, 8, 7, 45, 0, tzinfo=timezone.utc)
    exp = datetime(2026, 5, 8, 8, 0, 0, tzinfo=timezone.utc)
    assert_close(_live_frac(exp, now), 0.5, tol=0.01, label="TWAP live frac at 15 min")


def test_live_frac_at_expiry():
    exp = datetime(2026, 5, 8, 8, 0, 0, tzinfo=timezone.utc)
    assert _live_frac(exp, exp) == 0.0


# ── PM funding netting ───────────────────────────────────────────────────


def test_pm_funding_netted_across_positions_and_orders():
    md = {
        "BTC-USD-PERP": {
            "mark_price": 80000.0,
            "underlying_price": 80000.0,
            "funding_rate": 0.001,
            "delta": 1.0,
            "mark_iv": None,
            "interest_rate": 0.0,
            "fee_rate": 0.0,
        }
    }
    sp = {
        "BTC-USD-PERP": {
            "asset_kind": "PERP",
            "delta1_cross_margin_params": {"imf_base": "0.02", "mmf_factor": "0.5"},
        }
    }
    pos = [{"market": "BTC-USD-PERP", "side": "BUY", "size": 1.0}]
    order = [{"market": "BTC-USD-PERP", "side": "SELL", "size": 1.0, "price": 80000.0}]
    r_noorder = compute_pm(pos, [], md, sp, PM_CONFIG)
    r_withorder = compute_pm(pos, order, md, sp, PM_CONFIG)
    assert r_noorder["fund_p"] >= 0
    assert r_withorder["fund_p"] >= 0


def test_compute_pm_missing_pm_config_field_raises():
    """Production safety: a partial pm_config (missing required field) must raise."""
    import pytest

    bad_cfg = {**PM_CONFIG, "vol_shock_params": {"vega_power_short_dte": 0.30}}  # missing 3 fields
    with pytest.raises(ValueError, match=r"vega_power_long_dte|dte_floor_days|min_vol_shock_up"):
        compute_pm([], [], MARKET_DATA, MARKET_SPECS, bad_cfg)


# ── Liquidation finder ─────────────────────────────────────────────────────


def test_find_liquidation_long_perp_drops_to_floor():
    """A 1 BTC long with $10k cash should liquidate roughly at the price where
    cash + (test_spot - entry) * size == MMR."""
    entry = 80000.0
    cash = 10000.0
    size = 1.0
    mmr_rate = 0.005

    def account_value_at(test_spot: float) -> float:
        return cash + (test_spot - entry) * size

    def mmr_at(test_spot: float) -> float:
        return mmr_rate * test_spot * size

    out = find_liquidation_price(entry, account_value_at, mmr_at)
    assert out["down"] is not None, "expected a downside liquidation root"
    assert out["down"] < entry
    # Closed-form: cash + (s - entry) = mmr_rate * s  →  s = (cash - entry) / (mmr_rate - 1)
    expected = (cash - entry) / (mmr_rate - 1)
    assert_close(out["down"], expected, tol=1.0, label="long-perp liq price")


def test_find_liquidation_no_root_returns_none():
    """Account that is healthy across the entire bracket has no liquidation."""
    spot = 80000.0
    out = find_liquidation_price(
        spot,
        account_value_at=lambda _: 1e9,  # always solvent
        mmr_at=lambda s: 0.01 * s,
    )
    assert out["down"] is None
    assert out["up"] is None
    assert out["nearest"] is None


def test_find_liquidation_scans_non_monotonic_health_curve():
    """Option-like health curves can cross twice below spot with healthy endpoints."""
    out = find_liquidation_price(
        100.0,
        account_value_at=lambda s: (s - 50.0) * (s - 90.0),
        mmr_at=lambda _s: 0.0,
        scan_points=600,
    )

    assert_close(out["down"], 90.0, tol=1e-6, label="nearest downside root")
    assert out["up"] is None


# ── API adapters / config helpers ──────────────────────────────────────────


def test_parse_expiry_is_case_and_locale_independent():
    assert parse_expiry("8MAY26") == datetime(2026, 5, 8, 8, tzinfo=timezone.utc)
    assert parse_expiry("8may26") is None


def test_select_pm_config_validates_and_matches_underlying():
    pm_resp = {"results": [PM_CONFIG, {**PM_CONFIG, "base_asset": "ETH"}]}
    assert select_pm_config(pm_resp, "btc")["base_asset"] == "BTC"


def test_pm_config_snapshot_requires_complete_policy():
    import pytest

    bad = {**PM_CONFIG, "vol_shock_params": {"dte_floor_days": 1}}
    with pytest.raises(ValueError, match=r"vega_power_short_dte"):
        pm_config_from_snapshot(bad)


def test_fee_rate_for_market_prefers_account_specific_tier():
    market = {
        "asset_kind": "OPTION",
        "fee_config": {"api_fee": {"taker_fee": {"fee": "0.001"}}},
    }
    account_info = {"fees": {"dated_option_taker_rate": "0.0002", "taker_rate": "0.0005"}}
    assert fee_rate_for_market(market, account_info=account_info) == 0.0002


def test_fee_rate_for_market_requires_explicit_source():
    import pytest

    with pytest.raises(ValueError, match="fee rate is missing"):
        fee_rate_for_market({"symbol": "BTC-USD-PERP", "asset_kind": "PERP"})

    assert fee_rate_for_market({"symbol": "BTC-USD-PERP", "asset_kind": "PERP"}, default=0.0005) == 0.0005


def test_normalise_market_data_enriches_fee_and_interest_rate():
    summaries = [
        {
            "symbol": "BTC-USD-PERP",
            "mark_price": "80000",
            "greeks": {"delta": "1"},
            "underlying_price": "80010",
            "funding_rate": "0.0001",
        }
    ]
    specs = {
        "BTC-USD-PERP": {
            "asset_kind": "PERP",
            "interest_rate": "0.03",
            "fee_config": {"api_fee": {"taker_fee": {"fee": "0.0004"}}},
        }
    }
    md = normalise_market_data(summaries, market_specs=specs, account_info={"fees": {"taker_rate": "0.0003"}})
    assert md["BTC-USD-PERP"]["fee_rate"] == 0.0003
    assert md["BTC-USD-PERP"]["interest_rate"] == 0.03


def test_margin_inputs_from_api_responses_builds_compute_kwargs():
    mi = MarginInputs.from_api_responses(
        positions_resp={
            "results": [
                {"market": "BTC-USD-PERP", "side": "LONG", "size": "0.1", "status": "OPEN"},
                {"market": "BTC-USD-PERP", "side": "LONG", "size": "0", "status": "OPEN"},
            ]
        },
        orders_resp={
            "results": [{"market": "BTC-USD-PERP", "side": "SELL", "remaining_size": "0.01", "price": "80000"}]
        },
        balances_resp={"results": [{"token": "USDC", "size": "100"}]},
        markets_summary_resp={
            "results": [{"symbol": "BTC-USD-PERP", "mark_price": "80000", "underlying_price": "80000"}]
        },
        account_info_resp={"fees": {"taker_rate": "0.0003"}},
        markets_resp={"results": [{"symbol": "BTC-USD-PERP", "asset_kind": "PERP"}]},
        pm_config_resp={"results": [PM_CONFIG]},
        require_pm_config=True,
    )
    assert mi.underlying == "BTC"
    assert len(mi.positions) == 1
    assert len(mi.orders) == 1
    assert mi.pm_config["base_asset"] == "BTC"
    assert set(mi.compute_kwargs()) >= {"positions", "orders", "market_data", "market_specs", "balances", "pm_config"}


def test_normalise_orders_filters_inactive_statuses():
    orders = normalise_orders(
        [
            {"market": "BTC-USD-PERP", "side": "BUY", "remaining_size": "0.1", "price": "80000"},
            {"market": "BTC-USD-PERP", "side": "BUY", "remaining_size": "0.2", "price": "80000", "status": "NEW"},
            {"market": "BTC-USD-PERP", "side": "SELL", "remaining_size": "0.3", "price": "81000", "status": "OPEN"},
            {
                "market": "BTC-USD-PERP",
                "side": "SELL",
                "remaining_size": "0.4",
                "price": "82000",
                "status": "UNTRIGGERED",
            },
            {"market": "BTC-USD-PERP", "side": "SELL", "remaining_size": "0.5", "price": "83000", "status": "CLOSED"},
        ]
    )
    assert orders == [
        {"market": "BTC-USD-PERP", "side": "BUY", "size": 0.1, "price": 80000.0},
        {"market": "BTC-USD-PERP", "side": "BUY", "size": 0.2, "price": 80000.0},
        {"market": "BTC-USD-PERP", "side": "SELL", "size": 0.3, "price": 81000.0},
    ]


def test_margin_inputs_accepts_pydantic_payloads():
    from pydantic import BaseModel

    class Payload(BaseModel):
        results: list[dict]

    mi = MarginInputs.from_api_responses(
        positions_resp=Payload(results=[{"market": "BTC-USD-PERP", "side": "LONG", "size": "0.1"}]),
        markets_summary_resp=Payload(
            results=[{"symbol": "BTC-USD-PERP", "mark_price": "80000", "underlying_price": "80000"}]
        ),
        account_info_resp={"fees": {"taker_rate": "0.0003"}},
        markets_resp=Payload(results=[{"symbol": "BTC-USD-PERP", "asset_kind": "PERP"}]),
    )
    assert mi.positions == [{"market": "BTC-USD-PERP", "side": "LONG", "size": 0.1}]
    assert mi.market_data["BTC-USD-PERP"]["mark_price"] == 80000.0


def test_infer_underlying_considers_orders_when_no_positions():
    assert infer_underlying([], [{"market": "ETH-USD-PERP"}]) == "ETH"


# ── Synthetic/backtester adapter ───────────────────────────────────────────


def test_normalise_synthetic_pm_config_accepts_api_config():
    cfg = normalise_synthetic_pm_config(PM_CONFIG)
    assert cfg["hedged_mf"] == PM_CONFIG["hedged_margin_factor"]
    assert cfg["min_vol_shock_up"] == PM_CONFIG["vol_shock_params"]["min_vol_shock_up"]


def test_synthetic_margin_at_spot_xm_uses_sdk_formulas():
    margin_config = {
        "mode": "XM",
        "perp_params": {"BTC-USD-PERP": {"imf_base": "0.02", "mmf_factor": "0.5"}},
        "option_params": {},
        "fee_rate": 0.0,
    }
    positions = [{"leg_type": "perp", "side": "BUY", "size": 0.1, "current_price": 80000.0}]
    out = synthetic_margin_at_spot(positions, 80000.0, 0.5, 0.0, margin_config, "BTC")
    assert_close(out["imr"], 160.0, tol=0.001, label="synthetic XM IMR")
    assert_close(out["mmr"], 80.0, tol=0.001, label="synthetic XM MMR")


def test_synthetic_position_accepts_html_backtester_keys():
    pos = normalise_synthetic_position({"legType": "perp", "side": "BUY", "size": 0.1, "currentPrice": 80000.0})
    assert pos["leg_type"] == "perp"
    assert pos["current_price"] == 80000.0

    out = synthetic_margin_at_spot(
        [{"legType": "perp", "side": "BUY", "size": 0.1, "currentPrice": 80000.0}],
        80000.0,
        0.5,
        0.0,
        {
            "mode": "XM",
            "perpParams": {"BTC-USD-PERP": {"imf_base": "0.02", "mmf_factor": "0.5"}},
            "feeRate": 0.0,
        },
        "BTC",
    )
    assert_close(out["imr"], 160.0, tol=0.001, label="camel synthetic XM IMR")


def test_synthetic_fee_provision_uses_option_cap_and_market_hfr():
    pos = {
        "legType": "option",
        "market": "BTC-USD-8MAY26-78000-C",
        "side": "BUY",
        "size": 2,
        "currentPrice": 1000.0,
    }
    fee = synthetic_fee_provision(
        pos,
        80000.0,
        {"feeRate": 0.005, "marketHFR": {"BTC-USD-8MAY26-78000-C": 0.001}},
    )
    assert_close(fee, 160.0, tol=0.001, label="synthetic capped option fee")


def test_synthetic_fee_provision_requires_fee_source():
    import pytest

    with pytest.raises(ValueError, match="fee rate is missing"):
        synthetic_fee_provision(
            {"legType": "perp", "side": "BUY", "size": 1, "currentPrice": 80000.0},
            80000.0,
            {},
        )


def test_funding_index_helpers_use_latest_prior_index():
    series = [
        {"created_at": 0, "funding_index": "100"},
        {"created_at": 8 * 60 * 60 * 1000, "funding_index": "180"},
        {"created_at": 16 * 60 * 60 * 1000, "funding_index": "140"},
    ]

    assert funding_index_at(series, 9 * 60 * 60 * 1000) == 180.0
    assert_close(
        funding_rate_8h_from_index(series, 8 * 60 * 60 * 1000, 80000.0),
        0.001,
        tol=1e-12,
        label="8h funding rate",
    )
    assert_close(
        funding_pnl_from_index(100.0, 180.0, side="BUY", size=0.01),
        -0.8,
        tol=1e-12,
        label="long funding pnl",
    )
    assert_close(
        funding_pnl_from_index(100.0, 180.0, side="SELL", size=0.01),
        0.8,
        tol=1e-12,
        label="short funding pnl",
    )


def test_synthetic_margin_at_spot_pm_requires_complete_config():
    import pytest

    positions = [
        {
            "leg_type": "option",
            "side": "BUY",
            "size": 0.01,
            "current_price": 1000.0,
            "current_delta": 0.4,
            "strike": 80000.0,
            "is_call": True,
            "dte_at_entry": 14.0,
            "bars_held": 0,
        }
    ]
    margin_config = {"mode": "PM", "pm_config": {**PM_CONFIG, "vol_shock_params": {"dte_floor_days": 1}}}
    with pytest.raises(ValueError, match=r"vega_power_short_dte"):
        synthetic_margin_at_spot(positions, 80000.0, 0.5, 0.0, margin_config, "BTC")
