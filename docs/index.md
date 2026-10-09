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

## Signing with a Key Held Elsewhere

`ExternalSignerAccount` signs through an `ExternalSigner`, so the L2 private key never enters
this process. `HeaderSigner` is the signer for a signing proxy that sits between the client and
Paradex. For each signed request it sends the message hash, base64-encoded, in a header you name,
and puts a stand-in where the signature goes. The proxy signs the hash and swaps in the real signature.

```python
from paradex_py.account import ExternalSignerAccount, HeaderSigner
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET

client = ParadexApiClient(env=TESTNET, api_base_url="https://your-signing-proxy/v1")
account = ExternalSignerAccount(
    config=client.fetch_system_config(),
    l2_address="0x...",
    l2_public_key="0x...",
    signer=HeaderSigner(header="X-Sign-Hash", signature="PROXY_SIGNATURE"),
)
client.init_account(account)
client.submit_order(order)
```

- It signs REST requests only. A WebSocket order has no headers, so the WebSocket client refuses it.
- Each request carries one signature. A batch of several orders, or an execute that accepts several
  offers, is refused before anything is sent.
- The account must already be onboarded, and on-chain operations are not supported.
- Share one account across threads only if they never sign and send at the same time.

::: paradex_py.account.external_signer.ExternalSignerAccount
    handler: python
    options:
      show_source: false
      show_root_heading: true

::: paradex_py.account.external_signer.HeaderSigner
    handler: python
    options:
      show_source: false
      show_root_heading: true
