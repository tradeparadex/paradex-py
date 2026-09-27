# Scripts

This directory contains utility scripts for the Paradex Python SDK.

## Model Generation

### `generate_models_simple.py`

Fetches the Paradex API OpenAPI specification and generates Pydantic models.

**Usage:**

```bash
# Fetch from API (default)
uv run python scripts/generate_models_simple.py

# Use local spec file
uv run python scripts/generate_models_simple.py --spec-file path/to/spec.json

# Use local spec file with custom output directory
uv run python scripts/generate_models_simple.py --spec-file path/to/spec.json --output-dir custom/output
```

**Options:**

- `--spec-file`: Path to local JSON spec file (if not provided, fetches from API)
- `--output-dir`: Output directory for generated models (default: `paradex_py/api/generated`)

**What it does:**

1. Fetches the Swagger 2.0 spec from `https://api.prod.paradex.trade/swagger/doc.json` OR uses a provided JSON file
2. Attempts to convert it to OpenAPI 3.0 using `swagger2openapi` (if available)
3. Generates Pydantic v2 models using `datamodel-code-generator`
4. Outputs models to `paradex_py/api/generated/` (or custom directory)
5. Cleans up temporary files

**Generated files:**

- `paradex_py/api/generated/model.py` - Base models
- `paradex_py/api/generated/requests.py` - Request models
- `paradex_py/api/generated/responses.py` - Response models
- `paradex_py/api/generated/__init__.py` - Package initialization

## SBE schema

`paradex_py/api/sbe/paradex_1_0.xml` is a **copy** of the schema the Paradex
servers encode with, which is maintained upstream, outside this repo, and
`paradex_py/api/sbe/codec.py` is generated from it. Upstream can change the
schema without any PR here, so the copy can go stale silently: v0.7.1 shipped a
1:2 copy missing six fields the server had added to 1:2 in place.

> **Before any SBE release, and whenever the server's schema changes, run:**
>
> ```bash
> uv run python scripts/check_sbe_schema.py --upstream-file /path/to/upstream/paradex_1_0.xml
> ```
>
> It must print `OK`. With a git checkout of the upstream repo, use
> `--upstream-git <checkout> --upstream-path <path>` instead; it fetches and
> compares with `origin/main`.

The copy is deliberately not byte-identical: its prose (XML comments and
`description` attributes) is curated for public readers. Everything else —
every element, attribute, `sinceVersion` and value, plus whether a field is
marked `DEPRECATED` — must match, and that is exactly what the check compares.

### Syncing

1. Copy the upstream file over `paradex_py/api/sbe/paradex_1_0.xml`.
2. Re-apply the public prose edits (`git diff` shows them) and update the
   header: version history, `Released`, `Status`.
3. Regenerate the codec (the ruff passes are part of the procedure):

   ```bash
   uv run python scripts/generate_sbe_decoder.py --schema paradex_py/api/sbe/paradex_1_0.xml
   uv run ruff check --fix paradex_py/api/sbe/codec.py
   uv run ruff format paradex_py/api/sbe/codec.py
   ```

4. `check_sbe_schema.py` passes, and `tests/api/test_sbe_schema.py` passes
   (it fails if `codec.py` is not what the XML generates).
5. Only after the decoder reads the new version, raise
   `NEGOTIATED_SCHEMA_VERSION` in `paradex_py/api/sbe/__init__.py`, and only
   once every environment serves it.

### What catches drift

| Check                          | Runs                              | Catches                                                                                   | Misses                                                                                        |
| ------------------------------ | --------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `check_sbe_schema.py`          | by hand, before every SBE release | any schema difference from upstream `main`                                                | prose/header staleness; changes not yet merged upstream                                       |
| `check_sbe_wire.py`            | by hand, no credentials           | fixed fields or var-data the live server sends that the schema lacks, on public templates | private templates (orders, fills, positions, account); fields the server has not deployed yet |
| `tests/api/test_sbe_schema.py` | every test run                    | `codec.py` out of step with the XML                                                       | anything upstream                                                                             |

Neither script runs in CI, so nothing notices on its own when the upstream
schema changes: that is how v0.7.1 went stale. Run both before any SBE release.

```bash
# Live check against a public feed, at the decoder's schema version by default
uv run python scripts/check_sbe_wire.py --env prod
uv run python scripts/check_sbe_wire.py --env nightly --version 1 --min-trades 0
```

## Dependencies

The model generation requires:

- `datamodel-code-generator>=0.30.1` (dev dependency)
- `httpx` (for fetching the API spec)
- `swagger2openapi` (optional, for better conversion)

These are automatically installed when running `uv sync` with dev dependencies.
