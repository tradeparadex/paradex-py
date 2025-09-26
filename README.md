# Paradex Python SDK

[![Release](https://img.shields.io/github/v/release/tradeparadex/paradex-py)](https://img.shields.io/github/v/release/tradeparadex/paradex-py)
[![Build status](https://img.shields.io/github/actions/workflow/status/tradeparadex/paradex-py/main.yml?branch=main)](https://github.com/tradeparadex/paradex-py/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tradeparadex/paradex-py/branch/main/graph/badge.svg)](https://codecov.io/gh/tradeparadex/paradex-py)
[![Commit activity](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)
[![License](https://img.shields.io/github/license/tradeparadex/paradex-py)](https://img.shields.io/github/license/tradeparadex/paradex-py)

Paradex Python SDK provides a simple interface to interact with the Paradex REST and WS API.

## Examples

### L1 + L2 Authentication (Traditional)

```python
from paradex_py import Paradex
from paradex_py.environment import Environment

paradex = Paradex(env=Environment.TESTNET, l1_address="0x...", l1_private_key="0x...")
print(hex(paradex.account.l2_address)) # 0x...
print(hex(paradex.account.l2_public_key)) # 0x...
print(hex(paradex.account.l2_private_key)) # 0x...
```

### L2-Only Authentication (Subkey)

```python
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment

# Use ParadexSubkey for L2-only authentication
paradex = ParadexSubkey(
    env=Environment.TESTNET,
    l2_private_key="0x...",
    l2_address="0x..."
)
print(hex(paradex.account.l2_address)) # 0x...
print(hex(paradex.account.l2_public_key)) # 0x...
print(hex(paradex.account.l2_private_key)) # 0x...
```

### WebSocket Usage

```python
async def on_message(ws_channel, message):
    print(ws_channel, message)

await paradex.ws_client.connect()
await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY, callback=on_message)
```

📖 For complete documentation refer to [tradeparadex.github.io/paradex-py](https://tradeparadex.github.io/paradex-py/)

💻 For comprehensive examples refer to following files:

- API (L1+L2): [examples/call_rest_api.py](examples/call_rest_api.py)
- API (L2-only): [examples/subkey_rest_api.py](examples/subkey_rest_api.py)
- WS (L1+L2): [examples/connect_ws_api.py](examples/connect_ws_api.py)
- WS (L2-only): [examples/subkey_ws_api.py](examples/subkey_ws_api.py)
- Transfer: [examples/transfer_l2_usdc.py](examples/transfer_l2_usdc.py)

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

### Using uv

This project uses `uv` for managing dependencies and building. Below are instructions for installing `uv` and the basic workflow for development outside of using `make` commands.

### Installing uv

`uv` is a fast and modern Python package manager. You can install it using the standalone installer for macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

For other installation methods, refer to the [uv installation documentation](https://docs.astral.sh/uv/getting-started/installation/).

### Basic Workflow with uv

If you prefer not to use `make` commands, you can directly use `uv` for development tasks:

- **Install dependencies**: Sync your environment with the project's dependencies.
  ```bash
  uv sync
  ```
- **Run tests**: Execute the test suite using `pytest` within the `uv` environment.
  ```bash
  uv run pytest
  ```
- **Build the project**: Create a distribution package for the SDK.
  ```bash
  uv build
  ```

For more detailed information on using `uv`, refer to the [uv documentation](https://docs.astral.sh/uv/).

The CI/CD pipeline will be triggered when a new pull request is opened, code is merged to main, or when new release is created.

## Notes

> [!WARNING]
> Experimental SDK, library API is subject to change
