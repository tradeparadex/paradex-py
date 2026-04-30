"""Synthetic-position margin helpers for backtests.

These helpers are intentionally separate from the live account calculator.
Backtests often work with generated option legs that do not correspond to a
listed market symbol at every historical bar. The functions here reuse SDK
Black-Scholes and XM formulas while accepting a flat synthetic leg schema.
"""

from __future__ import annotations

import math
from bisect import bisect_right

from ._utils import _req_f
from .black_scholes import bs_price
from .config import validate_pm_config
from .constants import OPTION_FEE_CAP, YEAR_IN_DAYS
from .cross_margin import xm_option_margin, xm_perp_margin


def _api_pm_to_synthetic(pm_config: dict) -> dict:
    validate_pm_config(pm_config)
    vsp = pm_config["vol_shock_params"]
    return {
        "scenarios": [
            [
                _req_f(s, "spot_shock", "pm_config.scenarios"),
                _req_f(s, "vol_shock", "pm_config.scenarios"),
                _req_f(s, "weight", "pm_config.scenarios"),
            ]
            for s in pm_config["scenarios"]
        ],
        "unhedged_mf": _req_f(pm_config, "unhedged_margin_factor", "pm_config"),
        "hedged_mf": _req_f(pm_config, "hedged_margin_factor", "pm_config"),
        "mmr_factor": _req_f(pm_config, "mmf_factor", "pm_config"),
        "vega_power_st": _req_f(vsp, "vega_power_short_dte", "pm_config.vol_shock_params"),
        "vega_power_lt": _req_f(vsp, "vega_power_long_dte", "pm_config.vol_shock_params"),
        "dte_floor": _req_f(vsp, "dte_floor_days", "pm_config.vol_shock_params"),
        "min_vol_shock_up": _req_f(vsp, "min_vol_shock_up", "pm_config.vol_shock_params"),
    }


def normalise_synthetic_pm_config(pm_config: dict) -> dict:
    """Return backtester-shaped PM config, validating all policy fields.

    Accepts either the raw API-style PM config or a backtester-shaped dict with
    ``hedged_mf`` / ``unhedged_mf`` keys. Missing policy values raise instead
    of falling back to stale constants.
    """
    if "hedged_margin_factor" in pm_config:
        return _api_pm_to_synthetic(pm_config)

    required = (
        "scenarios",
        "unhedged_mf",
        "hedged_mf",
        "mmr_factor",
        "vega_power_st",
        "vega_power_lt",
        "dte_floor",
        "min_vol_shock_up",
    )
    for key in required:
        value = pm_config.get(key)
        if value is None or value == "":
            raise ValueError(f"required synthetic PM config field {key!r} is missing")
    return pm_config


def _first_present(data: dict, *keys: str):
    for key in keys:
        if key in data:
            return data[key]
    return None


def normalise_synthetic_position(pos: dict) -> dict:
    """Return a snake-case synthetic position, accepting HTML backtester keys."""
    out = dict(pos)
    aliases = {
        "leg_type": ("leg_type", "legType"),
        "current_price": ("current_price", "currentPrice"),
        "current_delta": ("current_delta", "currentDelta"),
        "dte_at_entry": ("dte_at_entry", "dteAtEntry"),
        "bars_held": ("bars_held", "barsHeld"),
        "is_call": ("is_call", "isCall"),
        "market": ("market", "symbol"),
    }
    for target, keys in aliases.items():
        value = _first_present(pos, *keys)
        if value is not None:
            out[target] = value
    return out


def _normalise_positions(positions: list[dict]) -> list[dict]:
    return [normalise_synthetic_position(pos) for pos in positions]


def _cfg_value(config: dict, snake: str, camel: str | None = None, default=None):
    if snake in config:
        return config[snake]
    if camel and camel in config:
        return config[camel]
    return default


def _market_hfr_for_position(pos: dict, margin_config: dict, default: float | None = None) -> float:
    market_hfr = _cfg_value(margin_config, "market_hfr", "marketHFR", {}) or {}
    market = pos.get("market")
    if market and market in market_hfr:
        return float(market_hfr[market] or 0)

    leg_type = pos.get("leg_type")
    for sym, hfr in market_hfr.items():
        if leg_type == "perp" and str(sym).endswith("-PERP"):
            return float(hfr or 0)
        if leg_type == "option" and (str(sym).endswith("-C") or str(sym).endswith("-P")):
            return float(hfr or 0)

    fallback = _cfg_value(margin_config, "fee_rate", "feeRate", default)
    if fallback is None or fallback == "":
        label = market or leg_type or "<unknown>"
        raise ValueError(f"fee rate is missing for synthetic position {label!r}")
    return float(fallback)


def synthetic_fee_provision(pos: dict, spot: float, margin_config: dict) -> float:
    """Backtester-shaped fee provision.

    Mirrors the exchange fee add-on used by PM:
    - option: ``min(HFR * spot, OPTION_FEE_CAP * mark) * size``
    - non-option: ``HFR * size * spot``

    ``pos`` may use snake_case or the HTML backtester camelCase field names.
    """
    p = normalise_synthetic_position(pos)
    size = abs(float(p.get("size") or 0))
    if not size:
        return 0.0
    hfr = _market_hfr_for_position(p, margin_config)
    if not hfr:
        return 0.0
    if p.get("leg_type") == "option":
        mark = float(p.get("current_price") or 0)
        return min(hfr * spot, OPTION_FEE_CAP * mark) * size
    return hfr * size * spot


def _funding_point(row) -> tuple[int | float, float] | None:
    if isinstance(row, dict):
        t = _first_present(row, "t", "timestamp", "created_at", "createdAt")
        idx = _first_present(row, "funding_index", "fundingIndex", "index")
    else:
        try:
            t, idx = row[0], row[1]
        except (TypeError, IndexError):
            return None
    if t is None or idx is None:
        return None
    return float(t), float(idx)


def funding_index_at(series: list, timestamp: int | float) -> float | None:
    """Return the latest cumulative funding index at or before ``timestamp``."""
    points = sorted(point for row in series if (point := _funding_point(row)) is not None)
    if not points:
        return None
    times = [p[0] for p in points]
    idx = bisect_right(times, float(timestamp)) - 1
    return points[idx][1] if idx >= 0 else None


def funding_pnl_from_index(
    entry_index: float | None,
    current_index: float | None,
    *,
    side: str,
    size: float,
) -> float:
    """Funding PnL from cumulative funding-index values.

    Positive return value means PnL received by the position; long perps pay
    positive index deltas, shorts receive them.
    """
    if entry_index is None or current_index is None:
        return 0.0
    delta = float(current_index) - float(entry_index)
    signed_cost = delta * abs(float(size))
    return -signed_cost if side in ("BUY", "LONG") else signed_cost


def funding_rate_8h_from_index(series: list, timestamp: int | float, spot: float) -> float:
    """Derive an 8h fractional funding rate from cumulative funding index."""
    if not spot:
        return 0.0
    now = funding_index_at(series, timestamp)
    then = funding_index_at(series, float(timestamp) - 8 * 60 * 60 * 1000)
    if now is None or then is None:
        return 0.0
    return (now - then) / float(spot)


def synthetic_pm_margin_at_spot(
    positions: list[dict],
    test_spot: float,
    pricing_vol: float,
    r: float,
    pm_config: dict,
    fund_rate_8h: float = 0.0,
    *,
    fee_rate: float | None = None,
    margin_config: dict | None = None,
) -> dict:
    """Compute PM IMR/MMR for synthetic backtest legs at ``test_spot``.

    Synthetic positions use the strategy-backtester shape:
    ``leg_type`` (``"perp"`` or ``"option"``), ``side``, ``size``,
    ``current_price``, ``current_delta``, and for options ``strike``,
    ``is_call``, ``dte_at_entry``, ``bars_held``.
    """
    positions = _normalise_positions(positions)
    cfg = normalise_synthetic_pm_config(pm_config)
    scenarios = cfg["scenarios"]
    pos_pnls = [0.0] * len(scenarios)
    pos_deltas: list[float] = []

    for pos in positions:
        signed = abs(float(pos["size"])) if pos["side"] in ("BUY", "LONG") else -abs(float(pos["size"]))
        current_price = float(pos.get("current_price") or 0)
        for i, (spot_shock, vol_shock, weight) in enumerate(scenarios):
            shocked_spot = test_spot * (1 + float(spot_shock))
            if pos["leg_type"] == "perp":
                sc_price = shocked_spot
            else:
                dte = max(0.0, float(pos["dte_at_entry"]) - float(pos.get("bars_held") or 0) / 24)
                tte = dte / YEAR_IN_DAYS
                vega_power = cfg["vega_power_st"] if dte < 30 else cfg["vega_power_lt"]
                iv_shock_scale = math.pow(30 / max(cfg["dte_floor"], dte), vega_power)
                shocked_vol = pricing_vol * (1 + float(vol_shock) * iv_shock_scale)
                if float(vol_shock) > 0:
                    shocked_vol = max(shocked_vol, cfg["min_vol_shock_up"])
                shocked_vol = max(0.01, shocked_vol)
                sc_price = bs_price(shocked_spot, pos["strike"], tte, r, shocked_vol, pos["is_call"])
            pos_pnls[i] += (sc_price - current_price) * float(weight) * signed
        pos_deltas.append(float(pos.get("current_delta") or 0) * signed)

    worst_loss = max([max(0.0, -p) for p in pos_pnls], default=0.0)
    net_delta = sum(pos_deltas)
    gross_delta = sum(abs(d) for d in pos_deltas)
    hedged = (gross_delta - abs(net_delta)) / 2
    delta_min = (cfg["unhedged_mf"] * abs(net_delta) + cfg["hedged_mf"] * hedged) * test_spot
    net_im = max(worst_loss, delta_min)

    fee_config = (
        margin_config if margin_config is not None else ({"fee_rate": fee_rate} if fee_rate is not None else {})
    )
    funding = 0.0
    fees = 0.0
    for pos in positions:
        size = abs(float(pos["size"]))
        if pos["leg_type"] == "perp":
            signed = size if pos["side"] in ("BUY", "LONG") else -size
            funding += -fund_rate_8h * signed * test_spot
        fees += synthetic_fee_provision(pos, test_spot, fee_config)
    fund_prov = max(0.0, -funding)
    return {
        "imr": net_im + fund_prov + fees,
        "mmr": net_im * cfg["mmr_factor"] + fund_prov + fees,
        "worst_loss": worst_loss,
        "delta_min": delta_min,
        "funding_provision": fund_prov,
        "fee_provision": fees,
    }


def synthetic_margin_at_spot(
    positions: list[dict],
    test_spot: float,
    pricing_vol: float,
    r: float,
    margin_config: dict,
    underlying: str,
    fund_rate_8h: float = 0.0,
) -> dict:
    """Compute XM or PM margin for strategy-backtester style positions."""
    positions = _normalise_positions(positions)
    mode = _cfg_value(margin_config, "mode", default="XM")
    pm_config = _cfg_value(margin_config, "pm_config", "pmConfig")
    if mode == "PM" and pm_config:
        return synthetic_pm_margin_at_spot(
            positions,
            test_spot,
            pricing_vol,
            r,
            pm_config,
            fund_rate_8h,
            fee_rate=(
                float(fee_value)
                if (fee_value := _cfg_value(margin_config, "fee_rate", "feeRate")) not in (None, "")
                else None
            ),
            margin_config=margin_config,
        )

    total_imr = total_mmr = 0.0
    perp_params = (_cfg_value(margin_config, "perp_params", "perpParams", {}) or {}).get(f"{underlying}-USD-PERP")
    option_params = _cfg_value(margin_config, "option_params", "optionParams", {}) or {}
    for pos in positions:
        if pos["leg_type"] == "perp" and perp_params:
            m = xm_perp_margin(pos["size"], test_spot, perp_params)
            total_imr += m["imr"]
            total_mmr += m["mmr"]
        elif pos["leg_type"] == "option":
            opt_params = next(
                (p for sym, p in option_params.items() if sym.startswith(f"{underlying}-USD-")),
                None,
            )
            if opt_params:
                dte = max(0.0, float(pos["dte_at_entry"]) - float(pos.get("bars_held") or 0) / 24)
                mark = bs_price(test_spot, pos["strike"], dte / YEAR_IN_DAYS, r, pricing_vol, pos["is_call"])
                m = xm_option_margin(
                    pos["side"] == "BUY",
                    pos["is_call"],
                    pos["size"],
                    pos["strike"],
                    test_spot,
                    mark,
                    opt_params,
                )
                total_imr += m["imr"]
                total_mmr += m["mmr"]
        fee = synthetic_fee_provision(pos, test_spot, margin_config)
        total_imr += fee
        total_mmr += fee
    return {"imr": total_imr, "mmr": total_mmr}
