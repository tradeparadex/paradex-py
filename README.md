# Paradex Python SDK

[![Release](https://img.shields.io/github/v/release/tradeparadex/paradex-py)](https://img.shields.io/github/v/release/tradeparadex/paradex-py)
[![Build status](https://img.shields.io/github/actions/workflow/status/tradeparadex/paradex-py/main.yml?branch=main)](https://github.com/tradeparadex/paradex-py/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tradeparadex/paradex-py/branch/main/graph/badge.svg)](https://codecov.io/gh/tradeparadex/paradex-py)
[![Commit activity](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)
[![License](https://img.shields.io/github/license/tradeparadex/paradex-py)](https://img.shields.io/github/license/tradeparadex/paradex-py)

Paradex Python SDK provides a simple interface to interact with the Paradex REST and WS API.

## Examples

```python
from paradex_py import Paradex
from paradex_py.environment import Environment

paradex = Paradex(env=Environment.TESTNET, l1_address="0x...", l1_private_key="0x...")
print(paradex.account.l2_address) # 0x...
print(paradex.account.l2_public_key) # 0x...
print(paradex.account.l2_private_key) # 0x...

paradex.api_client.fetch_system_config() # { ..., "paraclear_decimals": 8, ... }

async def on_message(ws_channel, message):
    print(ws_channel, message)

await paradex.ws_client.connect()
await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY, callback=on_message)
```

📖 For complete documentation refer to [tradeparadex.github.io/paradex-py](https://tradeparadex.github.io/paradex-py/)

💻 For comprehensive examples refer to following files:

- API: [examples/call_rest_api.py](examples/call_rest_api.py)
- WS: [examples/call_rest_api.py](examples/connect_ws_api.py)

## Development

```bash
make install
make check
make test
make build
make clean-build
make publish
make build-and-publish
make docs-test
make docs
make help
```

The CI/CD pipeline will be triggered when a new pull request is opened, code is merged to main, or when new release is created.

## Notes

> [!WARNING]
> Experimental SDK, library API is subject to change
