"""Portfolio Margin (PM) — 4-step scenario scan.

All margin-policy inputs (scenarios, vol-shock parameters, hedged/unhedged
margin factors, MMR factor) MUST come from the live exchange config —
``/system/portfolio-margin-config`` (use
``paradex_py.margin.config.pm_config_for_compute`` or pass the raw API block
directly). The engine raises ``ValueError`` if the required fields are
missing rather than silently using stale local defaults.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import cast

from ._utils import _req_dict, _req_f, _req_str
from .black_scholes import bs_price
from .config import validate_pm_config
from .constants import OPTION_FEE_CAP, TWAP_SETTLEMENT_MIN, YEAR_IN_DAYS
from .cross_margin import spot_balance_margin
from .markets import parse_market
from .types import Balance, MarketData, MarketSpec, Order, Position, RawDict


def _live_frac(expiry: datetime, now: datetime) -> float:
    """TWAP settlement scaling factor.

    During the final TWAP_SETTLEMENT_MIN minutes before expiry, PnL is scaled
    from 1.0 (full) down toward 0 as the option approaches settlement. Returns
    1.0 outside that window.
    """
    ste = (expiry - now).total_seconds()
    tw = TWAP_SETTLEMENT_MIN * 60
    if ste <= 0 or ste > tw:
        return 1.0
    return ste / tw


def _scenario_price(
    symbol: str,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
    spot: float,
    basis: float,
    ss: float,
    vs: float,
    now: datetime,
    pm_params: dict[str, float],
) -> float:
    """Reprice a single instrument under a (spot_shock, vol_shock) scenario.

    ``pm_params`` must supply ``interest_rate``, ``dte_floor``, ``vp_short``,
    ``vp_long``, ``min_vol_shock_up`` (built by :func:`compute_pm` from the
    live PM config).
    """
    try:
        md = market_data[symbol]
    except KeyError as e:
        raise ValueError(f"missing market data for scenario price {symbol!r}") from e
    p = parse_market(symbol, market_specs.get(symbol))
    if not p:
        raise ValueError(f"cannot parse market symbol for PM scenario pricing: {symbol!r}")

    s_shock = spot * (1 + ss)

    if p["type"] == "perp":
        return s_shock * (1 + basis)

    if p["type"] == "dated_option":
        exp = p.get("expiry")
        if not exp:
            raise ValueError(f"missing option expiry for PM scenario pricing: {symbol!r}")
        dte = (exp - now).total_seconds() / 86400
        tte = dte / YEAR_IN_DAYS
        iv = md["mark_iv"]
        if iv is None:
            raise ValueError(f"missing mark_iv for PM option scenario pricing: {symbol!r}")
        vp = pm_params["vp_short"] if dte < 30 else pm_params["vp_long"]
        mult = (30 / max(pm_params["dte_floor"], dte)) ** vp
        iv_shocked = iv * (1 + vs * mult)
        # Spec §2.3: upward vol shocks are floored at vol_shock_params.min_vol_shock_up
        if vs > 0:
            iv_shocked = max(iv_shocked, pm_params["min_vol_shock_up"])
        return bs_price(s_shock, p["strike"], tte, pm_params["interest_rate"], iv_shocked, p["is_call"])

    raise ValueError(f"unsupported market type for PM scenario pricing: {symbol!r}")


def _fee_provision(
    sym: str,
    size: float,
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
) -> float:
    """Per-instrument fee provision (spec §8.2).

    Non-option: HFR x size x mark_price
    Option:     min(HFR x spot, OPTION_FEE_CAP x mark) x size
    """
    try:
        md = market_data[sym]
    except KeyError as e:
        raise ValueError(f"missing market data for fee provision {sym!r}") from e
    hfr = md["fee_rate"]
    if not hfr or not size:
        return 0.0
    mark = md["mark_price"]
    if market_specs.get(sym, {}).get("asset_kind", "") in ("OPTION", "PERP_OPTION"):
        spot = md["underlying_price"]
        return min(hfr * spot, OPTION_FEE_CAP * mark) * size
    return hfr * size * mark


def compute_pm(  # noqa: C901
    positions: list[Position],
    orders: list[Order],
    market_data: dict[str, MarketData],
    market_specs: dict[str, MarketSpec],
    pm_config: RawDict,
    balances: list[Balance] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Compute Portfolio Margin IMR/MMR via the 4-step scenario scan.

    Mirrors the exchange PM Calculator. ``pm_config`` is the per-underlying
    block from ``/system/portfolio-margin-config`` (see
    :func:`paradex_py.margin.config.pm_config_for_compute`). It must contain
    ``scenarios``, ``hedged_margin_factor``, ``unhedged_margin_factor``,
    ``mmf_factor``, and ``vol_shock_params`` with ``vega_power_short_dte``,
    ``vega_power_long_dte``, ``dte_floor_days``, ``min_vol_shock_up``.
    Missing fields raise ``ValueError`` — there are no local fallbacks.
    """
    if pm_config is None:
        raise ValueError(
            "compute_pm requires pm_config from /system/portfolio-margin-config; "
            "see paradex_py.margin.config.pm_config_for_compute"
        )
    if now is None:
        now = datetime.now(timezone.utc)

    validate_pm_config(pm_config)
    vsp = _req_dict(pm_config, "vol_shock_params", "pm_config")
    hedged_mf = _req_f(pm_config, "hedged_margin_factor", "pm_config")
    unhedged_mf = _req_f(pm_config, "unhedged_margin_factor", "pm_config")
    mmr_factor_eff = _req_f(pm_config, "mmf_factor", "pm_config")
    raw_sc = pm_config["scenarios"]
    if not isinstance(raw_sc, Sequence) or isinstance(raw_sc, str | bytes | bytearray):
        raise TypeError("pm_config.scenarios must be a sequence")
    scenario_maps = [cast(Mapping[str, object], s) for s in raw_sc if isinstance(s, Mapping)]
    scenarios_eff = [
        [
            _req_f(s, "spot_shock", f"pm_config.scenarios[{i}]"),
            _req_f(s, "vol_shock", f"pm_config.scenarios[{i}]"),
            _req_f(s, "weight", f"pm_config.scenarios[{i}]"),
        ]
        for i, s in enumerate(scenario_maps)
    ]
    weights_eff = [s[2] for s in scenarios_eff]
    n_sc_eff = len(scenarios_eff)

    pm_params = {
        "interest_rate": 0.0,
        "dte_floor": _req_f(vsp, "dte_floor_days", "pm_config.vol_shock_params"),
        "vp_short": _req_f(vsp, "vega_power_short_dte", "pm_config.vol_shock_params"),
        "vp_long": _req_f(vsp, "vega_power_long_dte", "pm_config.vol_shock_params"),
        "min_vol_shock_up": _req_f(vsp, "min_vol_shock_up", "pm_config.vol_shock_params"),
    }

    spot_bm = spot_balance_margin(balances or [], market_data)

    # Detect underlying perp (for spot/basis/funding). Prefer the selected PM
    # config base asset, then live positions/orders.
    base_asset = _req_str(pm_config, "base_asset", "pm_config").upper()
    ul_sym = f"{base_asset}-USD-PERP"
    for item in [*positions, *orders]:
        sym = item["market"]
        if sym.endswith("-PERP"):
            ul_sym = sym
            break
        parsed = parse_market(sym, market_specs.get(sym))
        if parsed and parsed["type"] == "dated_option":
            parts = sym.split("-")
            ul_sym = f"{parts[0]}-{parts[1]}-PERP"
            break

    try:
        perp_md = market_data[ul_sym]
    except KeyError as e:
        raise ValueError(f"missing underlying perp market data for PM: {ul_sym!r}") from e
    spot = perp_md["underlying_price"]
    if spot <= 0:
        raise ValueError(f"underlying spot must be positive for PM: {ul_sym!r}")
    perp_mk = perp_md["mark_price"]
    basis = (perp_mk - spot) / spot if spot else 0
    fr8h = perp_md["funding_rate"]
    pm_params["interest_rate"] = perp_md["interest_rate"]

    all_markets = {p["market"] for p in positions} | {o["market"] for o in orders}
    sc_prices = {
        sym: [
            _scenario_price(sym, market_data, market_specs, spot, basis, ss, vs, now, pm_params)
            for (ss, vs, _) in scenarios_eff
        ]
        for sym in all_markets
    }

    # Step 1: scenario scan
    pos_pnls = [0.0] * n_sc_eff
    pos_deltas = []
    for pos in positions:
        sym = pos["market"]
        try:
            md = market_data[sym]
        except KeyError as e:
            raise ValueError(f"missing market data for PM position {sym!r}") from e
        mark = md["mark_price"]
        size = abs(float(pos["size"]))
        signed = size if pos["side"] in ("BUY", "LONG") else -size
        sc = sc_prices.get(sym, [mark] * n_sc_eff)
        parsed = parse_market(sym, market_specs.get(sym))
        exp = parsed.get("expiry") if parsed else None
        lf = _live_frac(exp, now) if exp else 1.0
        for i in range(n_sc_eff):
            pos_pnls[i] += lf * (sc[i] - mark) * weights_eff[i] * signed
        pos_deltas.append(md["delta"] * signed)

    ord_pnls = [0.0] * n_sc_eff
    ord_deltas = []
    for o in orders:
        sym = o["market"]
        try:
            md = market_data[sym]
        except KeyError as e:
            raise ValueError(f"missing market data for PM order {sym!r}") from e
        size = o["size"]
        price = o["price"]
        is_buy = o["side"] == "BUY"
        sc = sc_prices.get(sym, [price] * n_sc_eff)
        parsed = parse_market(sym, market_specs.get(sym))
        exp = parsed.get("expiry") if parsed else None
        lf = _live_frac(exp, now) if exp else 1.0
        for i in range(n_sc_eff):
            gap = (price - sc[i]) if is_buy else (sc[i] - price)
            ord_pnls[i] += -size * lf * max(0, gap) * weights_eff[i]
        ord_deltas.append(md["delta"] * size * (1 if is_buy else -1))

    total_pnls = [pos_pnls[i] + ord_pnls[i] for i in range(n_sc_eff)]
    losses = [max(0.0, -p) for p in total_pnls]
    worst_loss = max(losses) if losses else 0.0
    worst_idx = losses.index(worst_loss) if losses else 0

    # Step 2: delta-min floor
    mL = sum(d for d in pos_deltas if d > 0)
    mS = sum(abs(d) for d in pos_deltas if d < 0)
    loO = sum(d for d in ord_deltas if d > 0)
    soO = sum(abs(d) for d in ord_deltas if d < 0)
    maxL = mL + loO
    maxS = mS + soO
    maxU = max(0.0, max(maxL - mS, maxS - mL))
    hedged = max(0.0, max(maxL, maxS) - maxU)
    delta_min = (hedged * hedged_mf + maxU * unhedged_mf) * spot

    # Step 3: funding provision (positions + orders netted before max(0))
    pos_fund_sum = sum(
        -fr8h * (abs(float(p["size"])) * (1 if p["side"] in ("BUY", "LONG") else -1)) * spot
        for p in positions
        if p["market"].endswith("-PERP")
    )
    ord_fund_sum = sum(
        fr8h * o["size"] * (1 if o["side"] == "BUY" else -1) * spot for o in orders if o["market"].endswith("-PERP")
    )
    total_funding = pos_fund_sum + ord_fund_sum
    fund_p = max(0.0, -total_funding)
    pF = max(0.0, -pos_fund_sum)

    # Step 4: fee provision
    fee_pos = sum(_fee_provision(p["market"], abs(float(p["size"])), market_data, market_specs) for p in positions)
    fee_ord = sum(_fee_provision(o["market"], o["size"], market_data, market_specs) for o in orders)
    fee_imr = fee_pos + fee_ord
    fee_mmr = fee_pos

    net_im = max(worst_loss, delta_min)
    IMR = net_im + fund_p + fee_imr + spot_bm

    pos_losses = [max(0.0, -p) for p in pos_pnls]
    pos_worst = max(pos_losses) if pos_losses else 0.0
    p_nd = sum(pos_deltas)
    p_gd = sum(abs(d) for d in pos_deltas)
    pH = (p_gd - abs(p_nd)) / 2
    p_dm = (unhedged_mf * abs(p_nd) + hedged_mf * pH) * spot
    pos_ni = max(pos_worst, p_dm)
    MMR = pos_ni * mmr_factor_eff + pF + fee_mmr + spot_bm

    return {
        "IMR": IMR,
        "MMR": MMR,
        "portfolio_delta": sum(pos_deltas),
        "spot_balance_margin": spot_bm,
        "worst_loss": worst_loss,
        "worst_idx": worst_idx,
        "worst_scenario": scenarios_eff[worst_idx],
        "delta_min": delta_min,
        "fund_p": fund_p,
        "fee_provision_imr": fee_imr,
        "fee_provision_mmr": fee_mmr,
        "maxL": maxL,
        "maxS": maxS,
        "maxU": maxU,
        "hedged": hedged,
        "spot": spot,
    }
