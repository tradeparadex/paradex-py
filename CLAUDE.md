# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Installation

```bash
# Install dependencies using uv (fast Python package manager)
make install
# Or directly with uv:
uv sync
```

### Code Quality and Testing

```bash
# Run all code quality checks (linting, type checking, dependency checks)
make check

# Run tests with coverage
make test
# Or run a single test:
uv run pytest tests/path/to/test_file.py::test_function_name

# Run pre-commit hooks manually
uv run pre-commit run -a

# Type checking
uv run mypy --check-untyped-defs paradex_py
```

### Build and Documentation

```bash
# Build the package
make build

# Build and serve documentation locally
make docs
# Or test documentation build
make docs-test
```

## Architecture Overview

### Project Structure

- **paradex_py/**: Main package directory
  - **account/**: L1/L2 account management, Starknet integration, and typed data signing
  - **api/**: REST and WebSocket clients
    - **generated/**: Auto-generated models from OpenAPI spec (do not edit manually)
  - **message/**: Message signing for authentication, orders, onboarding, and block trades
  - **common/**: Shared utilities and models

### Key Components

1. **Paradex Client** (`paradex_py/paradex.py`): Main entry point

   - Initializes with environment (prod/testnet)
   - Manages account, API client, and WebSocket client
   - Loads system configuration on initialization

2. **Account Management** (`paradex_py/account/`):

   - Derives L2 keys from L1 private key or uses provided L2 key
   - Handles Starknet account abstractions
   - Manages JWT authentication

3. **API Clients**:

   - **REST API** (`api_client.py`): Synchronous HTTP client with automatic auth refresh
   - **WebSocket** (`ws_client.py`): Async WebSocket client with subscription management

4. **Message Signing** (`paradex_py/message/`):
   - Typed data structures for EIP-712 signing
   - Order creation and signing
   - Authentication headers generation

### Environment Configuration

- Uses `paradex_py.environment.Environment` enum: `PROD` or `TESTNET`
- API URLs are automatically configured based on environment

### Model Generation

The `api/generated/` directory contains auto-generated Pydantic models from the OpenAPI specification. To regenerate:

```bash
uv run python scripts/generate_models_simple.py
```

### Testing Strategy

- Unit tests in `tests/` mirror the source structure
- Mock clients available in `tests/mocks/`
- Test coverage is tracked via codecov

### Dependencies

- **starknet-py**: Starknet integration
- **eth-account**: Ethereum account management
- **httpx**: HTTP client
- **websockets**: WebSocket support
- **pydantic**: Data validation and settings
