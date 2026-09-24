"""Guards on the schemas generated from paradex_py.api.models."""

from collections.abc import Iterator
from dataclasses import make_dataclass

import marshmallow_dataclass
import pytest

from paradex_py.api import models


def _top_level_schemas() -> list[tuple[str, type]]:
    # The `Schema` suffix is load-bearing: a generated schema bound to a name
    # that does not end in it gets no coverage here. Every schema in the module
    # follows the convention, but nothing enforces it.
    return sorted((name, getattr(models, name)) for name in dir(models) if name.endswith("Schema"))


def _subfields(field) -> Iterator[object]:
    """Yield the sub-fields of a container field.

    Each container keeps them under its own attribute: List under `inner`,
    Tuple under `tuple_fields`, Dict split across `key_field`/`value_field`,
    and marshmallow_dataclass's Union under `union_fields`.
    """
    inner = getattr(field, "inner", None)
    if inner is not None:
        yield inner
    yield from getattr(field, "tuple_fields", None) or ()
    for attr in ("key_field", "value_field"):
        sub = getattr(field, attr, None)
        if sub is not None:
            yield sub
    for _, sub in getattr(field, "union_fields", None) or ():
        yield sub


def _walk(schema, seen: set[int]) -> Iterator[tuple[str, object]]:
    """Yield a schema and every schema reachable from it through its fields."""
    seen.add(id(schema))
    yield type(schema).__name__, schema
    stack = list(schema.fields.values())
    while stack:
        field = stack.pop()
        stack.extend(_subfields(field))
        nested = getattr(field, "schema", None)
        if nested is not None and id(nested) not in seen:
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


@pytest.mark.parametrize(
    "container",
    [
        pytest.param(lambda leaf: dict[str, leaf], id="dict"),
        pytest.param(lambda leaf: tuple[leaf, str], id="tuple"),
        pytest.param(lambda leaf: list[dict[str, leaf]], id="list_of_dict"),
    ],
)
def test_walk_reaches_models_nested_in_any_container(container):
    """The guard above is only as good as what _walk can see.

    A model reached through a dict, a tuple or a nested container is just as
    able to reintroduce the unknown-field failure as one reached through a
    list, so missing it here would make the guard pass while the SDK breaks.
    """
    leaf = make_dataclass("Leaf", [("a", str)])
    outer = make_dataclass("Outer", [("f", container(leaf))])

    reached = [schema_name for schema_name, _ in _walk(marshmallow_dataclass.class_schema(outer)(), set())]

    assert "Leaf" in reached, f"_walk did not reach a model nested in {container(leaf)}: {reached}"
