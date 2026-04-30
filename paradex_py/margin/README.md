# Margin Engine Overview

This package is a pure, offline margin engine plus a thin adapter layer for
Paradex API payloads. Core calculations should not fetch network data, mutate
account state, or depend on authenticated clients.

## Shape

- `compute.py`: public dispatcher for cross margin and portfolio margin.
- `cross_margin.py`: XM formulas for perps, futures, options, and spot balances.
- `portfolio_margin.py`: PM scenario scan, delta-min floor, funding provision,
  and fee provision.
- `black_scholes.py`: option pricing and Greeks shared by PM and backtests.
- `markets.py`: market metadata helpers and symbol parsing fallbacks.
- `config.py`: PM policy selection and validation from live/snapshot config.
- `adapters.py`: reusable normalization from REST payloads to `compute` inputs.
- `synthetic.py`: strategy/backtester helpers for generated legs.
- `hedging.py` and `liquidation.py`: small portfolio utilities.

## Data Flow

Live callers should fetch positions, open orders, balances, markets, market
summaries, account info, and PM config, then build:

```python
inputs = MarginInputs.from_api_responses(
    positions_resp=positions,
    orders_resp=orders,
    balances_resp=balances,
    markets_summary_resp=markets_summary,
    markets_resp=markets,
    pm_config_resp=pm_config,
    account_info_resp=account_info,
)
result = compute(**inputs.compute_kwargs(), margin_methodology="portfolio_margin")
```

Skills and MCP tools should reuse `MarginInputs` instead of rebuilding dict
normalization locally.

## Policy Inputs

Margin policy fields must come from live API responses or explicit snapshots.
Do not add local production defaults for PM scenarios, vol shock params,
hedged/unhedged factors, MMF factors, or XM per-market margin params. Missing
policy fields should raise.

## Market Expiry

When market metadata is available, use `expiry_at` from the market response.
Symbol parsing is only a fallback for offline/synthetic inputs. This avoids
hard-coding assumptions about listing conventions or settlement time into live
calculations.

## Models And Types

The compute core accepts plain dicts to stay lightweight and reusable by SDK,
skills, and MCP code. Generated Pydantic API models are useful at the API
boundary, but avoid coupling core formulas directly to generated classes.
Adapters may accept either dicts or generated models and should convert them to
the canonical compute shape before calling formulas.
