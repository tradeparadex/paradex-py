---
hide:
  - navigation
---

# Paradex Python SDK

!!! warning
    **Experimental SDK, library API is subject to change**

::: paradex_py.paradex.Paradex
    handler: python
    options:
      show_source: false
      show_root_heading: true

## L2-Only Authentication (Subkeys)

For users who only have L2 credentials (subkeys) and don't need L1 onboarding:

::: paradex_py.paradex_subkey.ParadexSubkey
    handler: python
    options:
      show_source: false
      show_root_heading: true

### Usage Examples

**L1 + L2 Authentication (Traditional):**
```python
from paradex_py import Paradex
from paradex_py.environment import Environment

# Requires both L1 and L2 credentials
paradex = Paradex(
    env=Environment.TESTNET,
    l1_address="0x...",
    l1_private_key="0x..."
)
```

**L2-Only Authentication (Subkeys):**
```python
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment

# Only requires L2 credentials - no L1 needed
paradex = ParadexSubkey(
    env=Environment.TESTNET,
    l2_private_key="0x...",
    l2_address="0x..."
)

# Use exactly like regular Paradex
await paradex.init_account()  # Already initialized
markets = await paradex.api_client.get_markets()
```

**WebSocket Usage:**
```python
async def on_message(ws_channel, message):
    print(ws_channel, message)

await paradex.ws_client.connect()
await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY, callback=on_message)
```

### When to Use Each Approach

**Use `Paradex` (L1 + L2) when:**
- You have both L1 (Ethereum) and L2 (Starknet) credentials
- You have never logged in to Paradex using this account before
- You need to perform on-chain operations (transfers, withdrawals)

**Use `ParadexSubkey` (L2-only) when:**
- You only have L2 credentials
- The account has already been onboarded (You have logged in to Paradex before)
- You do not need on-chain operations (withdrawals, transfers)

### Key Differences

| Feature | `Paradex` | `ParadexSubkey` |
|---------|-----------|-----------------|
| **Authentication** | L1 + L2 | L2-only |
| **Onboarding** | ✅ Supported | ❌ Blocked |
| **On-chain Operations** | ✅ Supported | ❌ Blocked |
| **API Access** | ✅ Full access | ✅ Full access |
| **WebSocket** | ✅ Supported | ✅ Supported |
| **Order Management** | ✅ Supported | ✅ Supported |

## Session Keys (Experimental)

!!! warning
    **Experimental.** Session keys are rolling out on the server and `POST /v2/sessions` is not live yet;
    names and payloads may change.

An account owner signs one `SessionGrant` (EIP-712, or SNIP-12 for Stark owners) that lets a scoped,
expiring Stark session key trade the anchor account and any listed sub-accounts. A session can never
withdraw. `SessionAccounts` then keeps a JWT (at most 15 minutes, never past the session's expiry),
a REST client and a websocket per account, routes calls by account, and drops every account at once
when the session expires or is revoked.

```python
from paradex_py import SessionAccounts
from paradex_py.message.session import Limits, SessionGrant
from paradex_py.session_accounts import LocalOwnerSigner, new_session_key, register_session

session_private_key, session_public_key = new_session_key()
grant = SessionGrant.new(
    paradex_chain="PRIVATE_SN_PARACLEAR_TESTNET",
    environment="testnet",
    account="0x<main-account>",
    subaccounts=["0x<sub-account>"],
    session_key=session_public_key,
    label="my bot",
    scopes=["trade"],
    limits=Limits("25000", "100000", "500000", "5000", "10", ["BTC-USD-PERP"]),
    ttl_seconds=7 * 24 * 3600,
)
# Any OwnerSigner works here, e.g. an MPC service that signs the EIP-712 typed data itself.
register_session("testnet", grant, LocalOwnerSigner("0x<owner-eth-key>"))

session = SessionAccounts(env="testnet", grant=grant, session_private_key=session_private_key)
session.submit_order("0x<sub-account>", order)
await session.connect_ws()
```

::: paradex_py.session_accounts.SessionAccounts
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.api.protocols.OwnerSigner
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.message.session.SessionGrant
    handler: python
    options:
      show_source: false
      show_root_heading: true

## API Documentation Links

Full details for REST API & WebSocket JSON-RPC API can be found at the following links:

- [Environment - Testnet](https://docs.api.testnet.paradex.trade){:target="_blank"}
- [Environment - Prod](https://docs.api.prod.paradex.trade){:target="_blank"}

::: paradex_py.api.api_client.ParadexApiClient
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.api.ws_client.ParadexWebsocketChannel
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.api.ws_client.WsRpcError
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.api.ws_client.ParadexWebsocketClient
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.account.account.ParadexAccount
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.account.subkey_account.SubkeyAccount
    handler: python
    options:
      show_source: false
      show_root_heading: true
