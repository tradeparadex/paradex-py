"""Submit a TWAP algo order on Paradex.

Usage:
    uv run python examples/twap_order.py --market DIME-USD --side BUY --notional-usd 5000 --duration 24h
    uv run python examples/twap_order.py --market DIME-USD --side BUY --notional-usd 500 --duration 1h30m
    uv run python examples/twap_order.py --market DIME-USD --side BUY --notional-usd 500 --duration 7200

Environment variables (option A — L2 key directly):
    PARADEX_ADDRESS - Your Paradex (L2/Starknet) account address
    L2_PRIVATE_KEY  - Your L2 private key (hex)

Environment variables (option B — derive from L1):
    L1_ADDRESS      - Your L1 (Ethereum) address
    L1_PRIVATE_KEY  - Your L1 private key (hex)
"""

import argparse
import math
import os
import re
import sys
from decimal import ROUND_DOWN, Decimal

from paradex_py import Paradex
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import PROD, TESTNET

DEFAULT_FREQUENCY = 30  # default seconds between child orders


def parse_duration(value: str) -> int:
    """Parse duration string like '1h30m', '2h', '30m', '340s', '7200' into seconds."""
    if re.fullmatch(r"\d+", value):
        return int(value)

    pattern = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
    if not pattern or not any(pattern.groups()):
        raise argparse.ArgumentTypeError(f"invalid duration: '{value}' (use e.g. 1h30m, 2h, 30m, 340s, or 7200)")

    hours = int(pattern.group(1) or 0)
    minutes = int(pattern.group(2) or 0)
    seconds = int(pattern.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a TWAP algo order on Paradex")
    parser.add_argument("--market", required=True, help="Market symbol (e.g. DIME-USD)")
    parser.add_argument("--side", required=True, choices=["BUY", "SELL"], help="Order side")
    parser.add_argument("--notional-usd", required=True, type=float, help="Total notional in USD")
    parser.add_argument(
        "--duration", required=True, type=parse_duration, help="Duration (e.g. 1h30m, 2h, 30m, 340s, 7200)"
    )
    parser.add_argument(
        "--min-child-notional",
        type=float,
        default=None,
        help="Minimum notional per child order in USD; frequency is derived from this (default: market min_notional)",
    )
    parser.add_argument("--env", default="prod", choices=["testnet", "prod"], help="Environment (default: prod)")
    return parser.parse_args()


def init_paradex(env_name: str) -> Paradex:
    """Initialize Paradex client from environment variables."""
    paradex_address = os.getenv("PARADEX_ADDRESS", "")
    l2_private_key = os.getenv("L2_PRIVATE_KEY", "")
    l1_address = os.getenv("L1_ADDRESS", "")
    l1_private_key = os.getenv("L1_PRIVATE_KEY", "")

    env = TESTNET if env_name == "testnet" else PROD

    if paradex_address and l2_private_key:
        paradex = Paradex(
            env=env,
            l1_address=paradex_address,
            l2_private_key=l2_private_key,
            auto_auth=False,
        )
        paradex.api_client.auto_auth = True
        paradex.api_client.auth()
        return paradex

    if l1_address and l1_private_key:
        from starknet_py.common import int_from_hex

        return Paradex(
            env=env,
            l1_address=l1_address,
            l1_private_key=int_from_hex(l1_private_key),
        )

    print("Error: set PARADEX_ADDRESS + L2_PRIVATE_KEY, or L1_ADDRESS + L1_PRIVATE_KEY")
    sys.exit(1)


def snap_duration(raw_seconds: int, frequency: int) -> int:
    """Snap duration to valid range (30-86400, multiple of frequency)."""
    duration = (raw_seconds // frequency) * frequency
    duration = max(frequency, min(86400, duration))
    if duration != raw_seconds:
        print(f"  Duration adjusted to {duration}s (must be {frequency}-86400, multiple of {frequency})")
    return duration


def compute_frequency(duration_seconds: int, notional: Decimal, min_child_notional: Decimal) -> int:
    """Compute child order frequency so each child meets min_child_notional."""
    if min_child_notional <= 0:
        return DEFAULT_FREQUENCY

    # frequency = duration / num_children
    # num_children = notional / min_child_notional (rounded down)
    num_children = int(notional / min_child_notional)
    if num_children <= 0:
        num_children = 1

    raw_frequency = duration_seconds / num_children
    # Round up to nearest multiple of 30 so child notional >= min_child_notional
    frequency = math.ceil(raw_frequency / DEFAULT_FREQUENCY) * DEFAULT_FREQUENCY
    frequency = max(DEFAULT_FREQUENCY, min(duration_seconds, frequency))
    return frequency


def main() -> None:
    args = parse_args()
    notional = Decimal(str(args.notional_usd))

    print(f"Connecting to Paradex ({args.env})...")
    paradex = init_paradex(args.env)

    # Fetch market info
    markets_resp = paradex.api_client.fetch_markets(params={"market": args.market})
    results = markets_resp.get("results", [])
    if not results:
        print(f"Error: market '{args.market}' not found")
        sys.exit(1)
    market_info = results[0]

    order_size_increment = Decimal(market_info["order_size_increment"])
    min_notional = Decimal(market_info.get("min_notional", "0"))
    max_order_size = Decimal(market_info.get("max_order_size", "0"))

    min_child_notional = Decimal(str(args.min_child_notional)) if args.min_child_notional else min_notional

    print(f"Market: {args.market}")
    print(f"  order_size_increment: {order_size_increment}")
    print(f"  min_notional: {min_notional}")
    print(f"  max_order_size: {max_order_size}")
    print(f"  min_child_notional: {min_child_notional}")

    # Get current price from BBO
    bbo = paradex.api_client.fetch_bbo(market=args.market)
    ask_price = Decimal(bbo.get("ask", "0"))
    bid_price = Decimal(bbo.get("bid", "0"))
    if ask_price == 0 or bid_price == 0:
        print("Error: could not get current price from BBO")
        sys.exit(1)
    mid_price = (ask_price + bid_price) / 2
    print(f"  current mid price: {mid_price}")

    frequency = compute_frequency(args.duration, notional, min_child_notional)
    duration_seconds = snap_duration(args.duration, frequency)

    # Calculate size from notional
    raw_size = notional / mid_price
    size = (raw_size / order_size_increment).to_integral_value(rounding=ROUND_DOWN) * order_size_increment

    if size <= 0:
        print(f"Error: calculated size is 0 (notional={notional}, price={mid_price})")
        sys.exit(1)

    if max_order_size > 0 and size > max_order_size:
        print(f"Error: size {size} exceeds max_order_size {max_order_size}")
        sys.exit(1)

    estimated_notional = size * mid_price
    num_children = duration_seconds // frequency
    child_size = size / num_children
    child_notional = child_size * mid_price

    print("\nOrder to submit:")
    print(f"  market:           {args.market}")
    print(f"  side:             {args.side}")
    print("  type:             MARKET")
    print("  algo_type:        TWAP")
    print(f"  size:             {size}")
    print(f"  notional:         ${estimated_notional:.2f}")
    print(f"  duration:         {duration_seconds}s ({duration_seconds / 3600:.1f}h)")
    print(f"  frequency:        {frequency}s ({frequency / 60:.1f}min)")
    print(f"  child orders:     {num_children}")
    print(f"  per child:        {child_size:.4f} (~${child_notional:.2f})")

    if min_notional > 0 and estimated_notional < min_notional:
        print(f"\nWarning: total notional ${estimated_notional:.2f} is below min_notional ${min_notional}")

    # Build and submit the order
    order_side = OrderSide.Buy if args.side == "BUY" else OrderSide.Sell
    order = Order(
        market=args.market,
        order_type=OrderType.Market,
        order_side=order_side,
        size=size,
        limit_price=Decimal(0),
    )

    print("\nSubmitting TWAP algo order...")
    response = paradex.api_client.submit_algo_order(
        order=order,
        algo_type="TWAP",
        duration_seconds=duration_seconds,
        frequency=frequency,
    )

    algo_id = response.get("id")
    if algo_id:
        print("\nAlgo order submitted successfully!")
        print(f"  id:               {algo_id}")
        print(f"  status:           {response.get('status')}")
        print(f"  market:           {response.get('market')}")
        print(f"  side:             {response.get('side')}")
        print(f"  size:             {response.get('size')}")
        print(f"  remaining_size:   {response.get('remaining_size')}")
        print(f"  algo_type:        {response.get('algo_type')}")
        print(f"  created_at:       {response.get('created_at')}")
        print(f"  end_at:           {response.get('end_at')}")
        print("\nMonitor with: paradex.api_client.fetch_algo_orders()")
        print(f"Cancel with:  paradex.api_client.cancel_algo_order('{algo_id}')")
    else:
        print(f"\nAlgo order response (no ID found): {response}")


if __name__ == "__main__":
    main()
