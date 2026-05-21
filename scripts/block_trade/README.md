# Block Trade CLI

A single CLI that drives both sides of a block trade between two accounts on
Paradex. The subcommand determines the role:

| Subcommand    | Role               | Description                                         |
| ------------- | ------------------ | --------------------------------------------------- |
| `whoami`      | either             | Print your Starknet account address                 |
| `create`      | seller / initiator | Create a new block trade                            |
| `offer`       | buyer / offerer    | Submit an offer to an existing block trade          |
| `status`      | either             | Inspect a block trade                               |
| `list-offers` | seller             | List offers submitted to a block trade              |
| `execute`     | seller             | Execute the block trade with all collected offers   |
| `cancel`      | either             | Cancel a block trade (initiator) or offer (offerer) |

All signing / typed-data plumbing lives in `paradex_py.account.account`
(`build_block_trade_signature`, `build_block_trade_offer_signature`,
`build_executor_signatures_for_offers`) — this CLI is a thin wrapper.

## Prerequisites

1. **Generate test accounts** (one-time):

   ```bash
   uv run generate_test_keys.py
   ```

   This creates `test_accounts.json` with at least 2 accounts.

2. **Fund the accounts** on the Paradex testnet (or prod) with collateral.

3. **Install dependencies**:
   ```bash
   make install
   ```

## Workflow

The seller and buyer run in separate terminals using different
`--account-index` values. The only value they share is the `block_trade_id`.

### Step 1 — Buyer gets their Starknet address

```bash
uv run scripts/block_trade/cli.py --account-index 1 whoami
```

Give the printed address to the seller.

### Step 2 — Seller creates the block trade

```bash
uv run scripts/block_trade/cli.py --account-index 0 create \
    --market ETH-USD-PERP \
    --side SELL \
    --size 1 \
    --price 1956 \
    --required-signer 0x<buyer_address>
```

This prints the `block_trade_id`. `--side` is the buy/sell switch — it picks
the side the initiator takes (the offerer takes the opposite by default).

### Step 3 — Buyer submits an offer

```bash
uv run scripts/block_trade/cli.py --account-index 1 offer \
    --block-trade-id <block_trade_id>
```

By default the buyer takes the opposite side of the block trade at the block
trade's price and size. Each can be overridden:

```bash
uv run scripts/block_trade/cli.py --account-index 1 offer \
    --block-trade-id <block_trade_id> \
    --side BUY \
    --price 1950 \
    --size 0.5
```

### Step 4 — Seller executes

```bash
uv run scripts/block_trade/cli.py --account-index 0 execute \
    --block-trade-id <block_trade_id>
```

### Cancellation

Cancel a block trade (initiator only):

```bash
uv run scripts/block_trade/cli.py --account-index 0 cancel \
    --block-trade-id <block_trade_id>
```

Cancel an offer (offerer only — pass `--offer-id`):

```bash
uv run scripts/block_trade/cli.py --account-index 1 cancel \
    --block-trade-id <block_trade_id> \
    --offer-id <offer_id>
```

## Global options

| Flag              | Default   | Description                                          |
| ----------------- | --------- | ---------------------------------------------------- |
| `--env`           | `testnet` | Paradex environment: `prod`, `testnet`, or `nightly` |
| `--account-index` | `0`       | Index into `test_accounts.json`                      |

Example targeting mainnet:

```bash
uv run scripts/block_trade/cli.py --env prod --account-index 0 create \
    --market ETH-USD-PERP --side SELL --size 1 --price 1956 \
    --required-signer 0x<buyer_address>
```

## Logging

Logging is configured by `examples/utils.py:get_logger()`. Two env vars are
honored:

- `LOGGING_LEVEL` — log level (default `INFO`)
- `LOG_FILE=true` — write to `logs/<script>_<timestamp>.log` instead of stdout
