# Block Trade Scripts

Two independent scripts for executing a block trade between two accounts on Paradex.

- **`seller.py`** — Creates the block trade, monitors offers, and executes.
- **`buyer.py`** — Responds to an existing block trade by submitting an offer.
- **`common.py`** — Shared utilities (not run directly).

## Prerequisites

1. **Generate test accounts** (one-time):
   ```bash
   uv run generate_test_keys.py
   ```
   This creates `test_accounts.json` with at least 2 accounts.

2. **Fund the accounts** on the Paradex testnet (or prod) so they have sufficient collateral for trading.

3. **Install dependencies**:
   ```bash
   make install
   ```

## Workflow

The seller and buyer run in separate terminals. The only value they share is the `block_trade_id`.

### Step 1 — Buyer gets their Starknet address

```bash
uv run scripts/block_trade/buyer.py whoami
```

Give the printed address to the seller.

### Step 2 — Seller creates the block trade

```bash
uv run scripts/block_trade/seller.py create \
    --market ETH-USD-PERP \
    --side SELL \
    --size 1 \
    --price 1956 \
    --required-signer 0x<buyer_address>
```

This prints the `block_trade_id`.

### Step 3 — Buyer submits an offer

```bash
uv run scripts/block_trade/buyer.py offer \
    --block-trade-id <block_trade_id>
```

By default the buyer matches the price and size from the block trade. To override:

```bash
uv run scripts/block_trade/buyer.py offer \
    --block-trade-id <block_trade_id> \
    --price 1950 \
    --size 0.5
```

### Step 4 — Seller executes

```bash
uv run scripts/block_trade/seller.py execute \
    --block-trade-id <block_trade_id>
```

## Other commands

| Script | Command | Description |
|--------|---------|-------------|
| seller | `whoami` | Print the seller's Starknet address |
| seller | `status --block-trade-id <id>` | Check block trade status and details |
| seller | `list-offers --block-trade-id <id>` | List all offers submitted by buyers |
| seller | `cancel --block-trade-id <id>` | Cancel the block trade |
| buyer  | `cancel --block-trade-id <id> --offer-id <oid>` | Cancel a submitted offer |

## Global options

Both scripts accept these flags before the subcommand:

| Flag | Default | Description |
|------|---------|-------------|
| `--env` | `testnet` | Paradex environment: `prod`, `testnet`, or `nightly` |
| `--account-index` | `0` (seller) / `1` (buyer) | Index into `test_accounts.json` |

Example targeting mainnet:

```bash
uv run scripts/block_trade/seller.py --env prod create --market ETH-USD-PERP --side SELL --size 1 --price 1956
```
