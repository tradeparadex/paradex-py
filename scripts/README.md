# Scripts

This directory contains utility scripts for the Paradex Python SDK.

## Model Generation

### `generate_models_simple.py`

Fetches the Paradex API OpenAPI specification and generates Pydantic models.

**Usage:**

```bash
uv run python scripts/generate_models_simple.py
```

**What it does:**

1. Fetches the Swagger 2.0 spec from `https://api.prod.paradex.trade/swagger/doc.json`
2. Attempts to convert it to OpenAPI 3.0 using `swagger2openapi` (if available)
3. Generates Pydantic v2 models using `datamodel-code-generator`
4. Outputs models to `paradex_py/api/generated/`
5. Cleans up temporary files

**Generated files:**

- `paradex_py/api/generated/model.py` - Base models
- `paradex_py/api/generated/requests.py` - Request models
- `paradex_py/api/generated/responses.py` - Response models
- `paradex_py/api/generated/__init__.py` - Package initialization

## Dependencies

The model generation requires:

- `datamodel-code-generator>=0.30.1` (dev dependency)
- `httpx` (for fetching the API spec)
- `swagger2openapi` (optional, for better conversion)

These are automatically installed when running `uv sync` with dev dependencies.
