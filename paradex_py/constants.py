from decimal import Decimal

# The STARK field
# https://docs.starknet.io/documentation/architecture_and_concepts/Cryptography/p-value/
PRIME = 2**251 + 17 * 2**192 + 1

PARACLEAR_DECIMALS = 8
USDC_DECIMALS = 6

BUY_SIDE = 1
SELL_SIDE = 2

WS_TIMEOUT = 20

# Bounds enforced by POST /account/mmp/{base_asset}. The server is authoritative;
# these mirror it so an out-of-range config fails before the request is sent.
MMP_MIN_INTERVAL_MS = 100
MMP_MAX_INTERVAL_MS = 3_600_000
# 0 is allowed and means "frozen until a manual reset", not "no freeze".
MMP_MIN_FROZEN_TIME_MS = 0
MMP_MAX_FROZEN_TIME_MS = 3_600_000
# Smallest step allowed on a limit. Removing a config is DELETE only, so there
# is no interval that removes one.
MMP_LIMIT_MIN_INCREMENT = Decimal("0.0001")
