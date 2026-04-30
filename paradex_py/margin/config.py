"""Reshape Paradex API responses into the dict shape consumed by the margin
engine.

Raw HTTP lives on :class:`paradex_py.api.api_client.ParadexApiClient` —
``fetch_markets`` and ``fetch_portfolio_margin_config``. This module is a
thin convenience layer that picks the per-underlying PM block and (for the
backtester) bundles XM perp/option params + PM config into one dict.
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from ._utils import _req_dict, _req_f
from .types import RawDict

_FEE_FIELD_BY_ASSET_KIND: dict[str, str] = {
    "SPOT": "spot_taker_rate",
    "OPTION": "dated_option_taker_rate",
    "PERP_OPTION": "perp_option_taker_rate",
}


def _asdict(value: object) -> RawDict:
    if isinstance(value, dict):
        return cast(RawDict, value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        if isinstance(dumped, dict):
            return cast(RawDict, dumped)
    return {}


def _pm_results(pm_data: object | None) -> list[RawDict]:
    if pm_data is None:
        return []
    if isinstance(pm_data, Sequence) and not isinstance(pm_data, str | bytes | bytearray):
        return [_asdict(item) for item in pm_data]
    results = _asdict(pm_data).get("results")
    if not isinstance(results, Sequence) or isinstance(results, str | bytes | bytearray):
        return []
    return [_asdict(item) for item in results]


def select_pm_config(
    pm_data: object | None,
    underlying: str | None,
    *,
    missing_ok: bool = False,
) -> RawDict | None:
    """Select one underlying's PM config from an API response or list.

    Args:
        pm_data: ``{"results": [...]}`` from ``/system/portfolio-margin-config``
            or a plain list of per-underlying config dicts.
        underlying: Base asset such as ``"BTC"``. Matching is case-insensitive.
        missing_ok: Return ``None`` when absent instead of raising ``ValueError``.

    Returns:
        The raw API-style PM config block, validated for required policy fields.
    """
    results = _pm_results(pm_data)
    target = (underlying or "").upper()
    cfg = next(
        (c for c in results if str(c.get("base_asset") or "").upper() == target),
        None,
    )
    if cfg is None:
        if missing_ok:
            return None
        label = target or "<unknown>"
        raise ValueError(f"portfolio margin config for {label} is missing")
    return validate_pm_config(cfg)


def validate_pm_config(pm_config: RawDict) -> RawDict:
    """Validate that a PM config block contains all live policy fields.

    This intentionally does not mutate or fill missing values. Callers that
    need offline replay should pass a complete snapshot of the live API block.
    """
    _req_f(pm_config, "hedged_margin_factor", "pm_config")
    _req_f(pm_config, "unhedged_margin_factor", "pm_config")
    _req_f(pm_config, "mmf_factor", "pm_config")
    scenarios = pm_config.get("scenarios")
    if not scenarios:
        raise ValueError("pm_config.scenarios is missing or empty")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, str | bytes | bytearray):
        raise TypeError("pm_config.scenarios must be a sequence")
    for i, scenario in enumerate(scenarios):
        if not isinstance(scenario, Mapping):
            raise TypeError(f"pm_config.scenarios[{i}] must be a mapping")
        scenario = cast(Mapping[str, object], scenario)
        _req_f(scenario, "spot_shock", f"pm_config.scenarios[{i}]")
        _req_f(scenario, "vol_shock", f"pm_config.scenarios[{i}]")
        _req_f(scenario, "weight", f"pm_config.scenarios[{i}]")
    vsp = _req_dict(pm_config, "vol_shock_params", "pm_config")
    _req_f(vsp, "dte_floor_days", "pm_config.vol_shock_params")
    _req_f(vsp, "vega_power_short_dte", "pm_config.vol_shock_params")
    _req_f(vsp, "vega_power_long_dte", "pm_config.vol_shock_params")
    _req_f(vsp, "min_vol_shock_up", "pm_config.vol_shock_params")
    return pm_config


def pm_config_from_snapshot(
    snapshot: Mapping[str, object],
    underlying: str | None = None,
    *,
    missing_ok: bool = False,
) -> RawDict | None:
    """Return a validated PM config from an explicit offline snapshot.

    ``snapshot`` may be a raw per-underlying PM config or the full API response
    with a ``results`` list. This helper is for tests/backtests: it keeps
    offline replay explicit without restoring hard-coded production fallbacks.
    """
    data = _asdict(snapshot)
    if "results" in data:
        return select_pm_config(data, underlying, missing_ok=missing_ok)
    if underlying and str(data.get("base_asset") or "").upper() != underlying.upper():
        if missing_ok:
            return None
        raise ValueError(f"snapshot base_asset {data.get('base_asset')!r} does not match {underlying!r}")
    return validate_pm_config(data)


def pm_config_for_compute(client: Any, underlying: str, *, missing_ok: bool = True) -> RawDict | None:
    """Return the per-underlying PM config block for ``compute(..., pm_config=...)``.

    The returned dict has the API-style keys that :func:`compute_pm` reads
    directly (``hedged_margin_factor``, ``unhedged_margin_factor``,
    ``mmf_factor``, ``scenarios``, ``vol_shock_params``). Returns ``None``
    when no PM config is published for the underlying.
    """
    try:
        pm_data = client.fetch_portfolio_margin_config()
    except Exception:
        if not missing_ok:
            raise
        return None
    return select_pm_config(pm_data, underlying, missing_ok=missing_ok)


def _market_fee_config_rate(market_spec: Mapping[str, object]) -> float | None:
    fee_cfg_raw = market_spec.get("fee_config") or {}
    fee_cfg = cast(Mapping[str, object], fee_cfg_raw) if isinstance(fee_cfg_raw, Mapping) else {}
    best = 0.0
    for cat_key in ("interactive_fee", "api_fee", "rpi_fee"):
        try:
            cat_raw = fee_cfg.get(cat_key) or {}
            if not isinstance(cat_raw, Mapping):
                continue
            cat = cast(Mapping[str, object], cat_raw)
            taker_raw = cat.get("taker_fee") or {}
            if not isinstance(taker_raw, Mapping):
                continue
            taker = cast(Mapping[str, object], taker_raw)
            fee = taker.get("fee")
            if fee not in (None, ""):
                best = max(best, float(cast(float | str, fee)))
        except (TypeError, ValueError):
            continue
    return best or None


def fee_rate_for_market(
    market_spec: Mapping[str, object],
    *,
    account_info: Mapping[str, object] | None = None,
    default: float | None = None,
) -> float:
    """Return the best available taker fee rate for a market.

    Account-specific fee tiers win. If unavailable, fall back to the market's
    published fee config. Callers may pass an explicit ``default`` for offline
    replay; live calculations should not silently assume a fee rate.
    """
    asset_kind = str(market_spec.get("asset_kind") or "")
    fees_raw = (account_info or {}).get("fees") or {}
    fees = cast(Mapping[str, object], fees_raw) if isinstance(fees_raw, Mapping) else {}
    fee_field = _FEE_FIELD_BY_ASSET_KIND.get(asset_kind, "taker_rate")
    for key in (fee_field, "taker_rate"):
        try:
            value = fees.get(key)
            if value is not None and value != "":
                return float(cast(float | str, value))
        except (TypeError, ValueError):
            pass

    market_fee_rate = _market_fee_config_rate(market_spec)
    if market_fee_rate is not None:
        return market_fee_rate
    if default is not None:
        return default
    symbol = market_spec.get("symbol") or "<unknown>"
    raise ValueError(f"fee rate is missing for market {symbol!r}")


def fetch_margin_config(
    client: Any,
    underlying: str,
    *,
    log: Any = None,
    account_info: Mapping[str, object] | None = None,
) -> RawDict:
    """Fetch XM and PM margin parameters and reshape them for the backtester.

    The SDK margin engine itself reads the raw API responses directly (via
    :func:`pm_config_for_compute` for PM and the per-market
    ``delta1_cross_margin_params`` / ``option_cross_margin_params`` blocks
    for XM). This helper exists for the strategy backtester, whose own
    ``pm_margin_at_spot`` reads the snake-case keys built below.

    Returns:
        ::

            {
                "mode":          "PM" | "XM",
                "perp_params":   {symbol: {imf_base, mmf_factor}},
                "option_params": {symbol: {imf: {...}, mmf: {...}}},
                "pm_config":     {scenarios, hedged_mf, unhedged_mf, mmr_factor,
                                  vega_power_st, vega_power_lt, dte_floor,
                                  min_vol_shock_up, funding_period_hours} | None,
                "fee_rate":      float (highest taker fee across categories),
            }
    """
    log = log or (lambda *_a, **_k: None)
    perp_params: dict[str, dict[str, float]] = {}
    option_params: dict[str, dict[str, dict[str, float]]] = {}
    fee_rate: float | None = None
    config: RawDict = {
        "mode": "XM",
        "perp_params": perp_params,
        "option_params": option_params,
        "pm_config": None,
    }

    try:
        markets_payload = client.fetch_markets() or {}
    except Exception as e:
        log(f"  Markets fetch failed: {e}")
        return config

    all_mkts_raw = markets_payload.get("results") or [] if isinstance(markets_payload, Mapping) else []
    all_mkts = all_mkts_raw if isinstance(all_mkts_raw, Sequence) else []

    for raw_market in all_mkts:
        m = _asdict(raw_market)
        sym = m.get("symbol")
        if not sym:
            continue
        sym = str(sym)
        xm_raw = m.get("delta1_cross_margin_params")
        if isinstance(xm_raw, Mapping):
            xm = cast(Mapping[str, object], xm_raw)
            perp_params[sym] = {
                "imf_base": _req_f(xm, "imf_base", sym),
                "mmf_factor": _req_f(xm, "mmf_factor", sym),
            }
        oxm_raw = m.get("option_cross_margin_params")
        if isinstance(oxm_raw, Mapping):
            oxm = cast(Mapping[str, object], oxm_raw)
            imf = _req_dict(oxm, "imf", sym)
            mmf = _req_dict(oxm, "mmf", sym)
            option_params[sym] = {
                "imf": {str(k): float(cast(float | str, v)) for k, v in imf.items()},
                "mmf": {str(k): float(cast(float | str, v)) for k, v in mmf.items()},
            }
        market_fee_rate = fee_rate_for_market(m, account_info=account_info)
        fee_rate = market_fee_rate if fee_rate is None else max(fee_rate, market_fee_rate)
        config["fee_rate"] = fee_rate

    try:
        ul_cfg = pm_config_for_compute(client, underlying)
    except Exception as e:
        log(f"  PM config fetch failed (XM still available): {e}")
        return config

    if ul_cfg:
        vsp = _req_dict(ul_cfg, "vol_shock_params", "pm_config")
        scenarios_raw = ul_cfg.get("scenarios")
        scenarios = scenarios_raw if isinstance(scenarios_raw, Sequence) else []
        flat_scenarios = [
            [
                _req_f(cast(Mapping[str, object], s), "spot_shock", "pm_config.scenarios"),
                _req_f(cast(Mapping[str, object], s), "vol_shock", "pm_config.scenarios"),
                _req_f(cast(Mapping[str, object], s), "weight", "pm_config.scenarios"),
            ]
            for s in scenarios
            if isinstance(s, Mapping)
        ]
        config["mode"] = "PM"
        pm_config = {
            "scenarios": flat_scenarios,
            "unhedged_mf": _req_f(ul_cfg, "unhedged_margin_factor", "pm_config"),
            "hedged_mf": _req_f(ul_cfg, "hedged_margin_factor", "pm_config"),
            "mmr_factor": _req_f(ul_cfg, "mmf_factor", "pm_config"),
            "vega_power_st": _req_f(vsp, "vega_power_short_dte", "pm_config.vol_shock_params"),
            "vega_power_lt": _req_f(vsp, "vega_power_long_dte", "pm_config.vol_shock_params"),
            "dte_floor": _req_f(vsp, "dte_floor_days", "pm_config.vol_shock_params"),
            "min_vol_shock_up": _req_f(vsp, "min_vol_shock_up", "pm_config.vol_shock_params"),
            "funding_period_hours": ul_cfg.get("funding_provision_hour"),
        }
        config["pm_config"] = pm_config
        log(f"  PM config: {len(flat_scenarios)} scenarios, MMF={pm_config['mmr_factor']}")
    return config
