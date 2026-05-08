"""Paradex protocol invariants used by the margin engine.

These are values fixed by the Paradex protocol/spec — not exchange-margin-policy
parameters. Margin-policy values (scenarios, scaling factors, vol shock floor,
margin factors) MUST be fetched live from ``/system/portfolio-margin-config``
and from the per-market ``delta1_cross_margin_params`` /
``option_cross_margin_params``. Hard-coded fallbacks for those would silently
mask exchange-side updates and can produce dangerously wrong margin numbers —
the engine raises ``ValueError`` if those fields are missing at call time.
"""

YEAR_IN_DAYS = 365
OPTION_EXPIRY_HOUR = 8  # Paradex options expire at 08:00 UTC
TWAP_SETTLEMENT_MIN = 30  # Settlement TWAP window in minutes
OPTION_FEE_CAP = 0.125  # PM fee provision option cap (spec §8.2): min(HFR·spot, 12.5%·mark)
