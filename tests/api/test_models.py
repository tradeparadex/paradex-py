"""Guards on the schemas generated from paradex_py.api.models."""

from collections.abc import Iterator

import pytest

from paradex_py.api import models


def _top_level_schemas() -> list[tuple[str, type]]:
    return sorted((name, getattr(models, name)) for name in dir(models) if name.endswith("Schema"))


def _walk(schema, seen: set[int]) -> Iterator[tuple[str, object]]:
    """Yield a schema and every schema reachable from it through its fields."""
    yield type(schema).__name__, schema
    for field in schema.fields.values():
        # Unwrap List/Tuple containers down to the element field.
        while hasattr(field, "inner"):
            field = field.inner
        nested = getattr(field, "schema", None)
        if nested is not None and id(nested) not in seen:
            seen.add(id(nested))
            yield from _walk(nested, seen)


@pytest.mark.parametrize("name,schema_cls", _top_level_schemas())
def test_schema_excludes_unknown_fields_at_every_level(name, schema_cls):
    """Every level of a response model must tolerate fields the server adds.

    `unknown` passed to load() does not reach nested schemas, so each model
    declares `Meta.unknown` itself. A nested dataclass added later without one
    would silently reintroduce the failure this guards against -- and
    fetch_system_config() runs during client initialization, so the breakage
    lands at startup rather than at the call that needs the new field.
    """
    for schema_name, schema in _walk(schema_cls(), set()):
        assert schema.opts.unknown == "exclude", (
            f"{schema_name} (reachable from {name}) does not exclude unknown fields; "
            'add `class Meta: unknown = "exclude"` to its dataclass in paradex_py/api/models.py'
        )
