#!/usr/bin/env python3
"""
Code generator: reads paradex_1_0.xml → emits paradex_py/api/sbe/codec.py

Usage:
    uv run python scripts/generate_sbe_decoder.py \\
        --schema /path/to/paradex_1_0.xml \\
        --output paradex_py/api/sbe/codec.py
    uv run ruff check --fix paradex_py/api/sbe/codec.py
    uv run ruff format paradex_py/api/sbe/codec.py

The ruff passes are part of the procedure, not a cleanup: the emitter writes
Optional[X] and does not wrap long literals, so the committed codec is
generator output that has been through both. Skipping them leaves a diff that
looks like a schema change.
"""

import argparse
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SBE_NS = "http://fixprotocol.io/2016/sbe"

# ── Type system ────────────────────────────────────────────────────────────

# Primitive type → struct char
_PRIM_TO_CHAR = {
    "int64": "q",
    "uint8": "B",
    "uint16": "H",
    "int8": "b",
    "int16": "h",
    "uint32": "I",
    "uint64": "Q",
}

# Primitives that carry a null sentinel when the field is presence="optional".
# Only int64 has one (MinInt64); anything else would need its own sentinel and
# is rejected rather than silently decoded as a plain value.
_OPTIONAL_PRIM = {
    "int64": ("_i64n({v})", "Optional[int]"),
}

# Composite name → (struct_char, helper_call_template, python_type_str)
# helper_call_template uses {v} for value variable
_COMPOSITE_INFO = {
    "Price8": ("q", "_f8({v})", "str"),
    "Price8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Qty8": ("q", "_f8({v})", "str"),
    "Qty8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Value8": ("q", "_f8({v})", "str"),
    "Value8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Rate8": ("q", "_f8({v})", "str"),
    "Rate8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Rate12": ("q", "_f12({v})", "str"),
    "Rate12NULL": ("q", "_f12n({v})", "Optional[str]"),
    "Timestamp": ("q", "_ts({v})", "int"),
}

# Fixed-length byte fields → (struct_char, helper_call_template, python_type_str)
_FIXED_FIELDS = {
    "AccountAddress": ("32s", "_addr({v})", "str"),
}

# Set/bitset types → (struct_char, helper_call_template, python_type_str)
# The helper name matches the generated _decode_{setname_lower}() function.
_SET_FIELDS = {
    "OrderFlags": ("B", "_decode_orderflags({v})", "list[str]"),
    "FillFlags": ("B", "_decode_fillflags({v})", "list[str]"),
}


def _to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def parse_schema(schema_path: str):  # noqa: C901
    """Parse the XML schema and return (enums, messages, schema_meta)."""
    tree = ET.parse(schema_path)
    root = tree.getroot()

    schema_id = root.get("id", "1")
    schema_version = root.get("version", "0")
    root.get("description", "")
    released = "2026-03-31"

    # Parse enums
    enums = {}  # name → {int_val: python_val}
    for elem in root.iter("enum"):
        name = elem.get("name")
        values = {}
        for vv in elem.findall("validValue"):
            val_name = vv.get("name")
            val_int = int(vv.text.strip())
            if val_name == "NON_REPRESENTABLE":
                values[val_int] = None
            else:
                values[val_int] = val_name
        enums[name] = values

    # Determine enum encoding types (for struct char)
    enum_encoding = {}  # name → struct_char
    for elem in root.iter("enum"):
        name = elem.get("name")
        enc = elem.get("encodingType", "uint8")
        enum_encoding[name] = _PRIM_TO_CHAR.get(enc, "B")

    # Parse set types (bitsets like OrderFlags)
    sets = {}  # name → {bit_pos: flag_name}
    for elem in root.iter("set"):
        name = elem.get("name")
        bits = {}
        for choice in elem.findall("choice"):
            flag_name = choice.get("name")
            bit_pos = int(choice.text.strip())
            bits[bit_pos] = flag_name
        sets[name] = bits

    # Parse messages
    messages = []
    for msg in root.iter(f"{{{SBE_NS}}}message"):
        msg_id = int(msg.get("id"))
        msg_name = msg.get("name")
        description_msg = msg.get("description", "")

        fields = []
        for field in msg.findall("field"):
            field_name = field.get("name")
            field_type = field.get("type")
            fields.append(
                {
                    "name": field_name,
                    "type": field_type,
                    "since": int(field.get("sinceVersion", "0")),
                    "optional": field.get("presence") == "optional",
                }
            )

        groups = []
        for group in msg.findall("group"):
            group_name = group.get("name")
            group_fields = []
            for gf in group.findall("field"):
                group_fields.append({"name": gf.get("name"), "type": gf.get("type")})
            groups.append({"name": group_name, "fields": group_fields})

        data_fields = []
        for data in msg.findall("data"):
            data_fields.append({"name": data.get("name"), "since": int(data.get("sinceVersion", "0"))})

        messages.append(
            {
                "id": msg_id,
                "name": msg_name,
                "description": description_msg,
                "fields": fields,
                "groups": groups,
                "data": data_fields,
            }
        )

    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "released": released,
        "enums": enums,
        "enum_encoding": enum_encoding,
        "sets": sets,
        "messages": messages,
    }


def _raw_var(field: dict) -> str:
    """Name of the local holding a field's undecoded value.

    Keyed off the XML spelling, so ts/seq stay ts_raw/seq_raw even though the
    model renames them to timestamp/seq_no.
    """
    return f"{_to_snake(field['name'])}_raw"


def _absent_by_version(python_type: str, since: int) -> str:
    """Annotate a field that a frame negotiated below `since` will not carry."""
    if since == 0:
        return python_type
    if not python_type.startswith("Optional["):
        python_type = f"Optional[{python_type}]"
    return f"{python_type} = None"


def _tiers(fields: list) -> list:
    """Split fields into consecutive runs of equal sinceVersion.

    Appended fields always sit at the end of the block, so the runs come out in
    ascending version order and each one starts where the previous ended.
    """
    tiers: list = []
    for f in fields:
        since = f["since"]
        if not tiers or tiers[-1][0] != since:
            if tiers and since < tiers[-1][0]:
                raise ValueError(f"sinceVersion must not decrease within a message: {f['name']}")
            tiers.append((since, []))
        tiers[-1][1].append(f)
    return tiers


def _field_struct_char(field_type: str, enums: dict, enum_encoding: dict) -> str:
    """Return the struct char for a field type."""
    if field_type in _FIXED_FIELDS:
        return _FIXED_FIELDS[field_type][0]
    if field_type in _SET_FIELDS:
        return _SET_FIELDS[field_type][0]
    if field_type in _COMPOSITE_INFO:
        return _COMPOSITE_INFO[field_type][0]
    if field_type in _PRIM_TO_CHAR:
        return _PRIM_TO_CHAR[field_type]
    if field_type in enums:
        return enum_encoding.get(field_type, "B")
    raise ValueError(f"Unknown field type: {field_type}")


def _field_helper(field_type: str, var: str, enums: dict, optional: bool = False) -> str:
    """Return the Python expression to convert a raw value."""
    if optional:
        if field_type not in _OPTIONAL_PRIM:
            raise ValueError(f'presence="optional" is not supported for type {field_type}')
        return _OPTIONAL_PRIM[field_type][0].replace("{v}", var)
    if field_type in _FIXED_FIELDS:
        tmpl = _FIXED_FIELDS[field_type][1]
        return tmpl.replace("{v}", var)
    if field_type in _SET_FIELDS:
        tmpl = _SET_FIELDS[field_type][1]
        return tmpl.replace("{v}", var)
    if field_type in _COMPOSITE_INFO:
        tmpl = _COMPOSITE_INFO[field_type][1]
        return tmpl.replace("{v}", var)
    if field_type in _PRIM_TO_CHAR:
        return var
    if field_type in enums:
        enum_name = f"_ENUM_{field_type.upper()}"
        return f"{enum_name}.get({var})"
    return var


def _field_python_type(field_type: str, enums: dict, optional: bool = False) -> str:
    """Return the Python type annotation string."""
    if optional:
        if field_type not in _OPTIONAL_PRIM:
            raise ValueError(f'presence="optional" is not supported for type {field_type}')
        return _OPTIONAL_PRIM[field_type][1]
    if field_type in _FIXED_FIELDS:
        return _FIXED_FIELDS[field_type][2]
    if field_type in _SET_FIELDS:
        return _SET_FIELDS[field_type][2]
    if field_type in _COMPOSITE_INFO:
        return _COMPOSITE_INFO[field_type][2]
    if field_type in _PRIM_TO_CHAR:
        return "int"
    if field_type in enums:
        return "Optional[str]"
    return "Any"


# ── Enum value prefixes ─────────────────────────────────────────────────────
#
# SBE stores enum values bare ("PARADEX") because the schema already scopes
# them by type, but the JSON feed sends the full protobuf spelling
# ("SOURCE_PARADEX").  Callbacks must see the same value on both transports,
# so these enums get their prefix restored when the codec is generated.
# Enums absent from this table are emitted bare, which is what the JSON API
# sends for them (order status, fill type and so on).
_ENUM_VALUE_PREFIX = {
    "AssetKind": "ASSET_KIND_",
    "FundingRateSource": "SOURCE_",
}

# Note on FillType value 3. The schema and both server feeds (JSON and SBE)
# spell it UNWIND_TRANSFER, renamed server-side in July 2026. The SDK's
# generated REST model still carries the old TRANSFER spelling because it is
# generated from an older API spec, so paradex_py/api/generated/responses.py
# and this codec disagree until that spec is refreshed. The codec follows the
# wire, which is what a callback actually receives; do not "fix" it back to
# TRANSFER to match the stale REST model.


# ── Channel routing (hardcoded per message) ─────────────────────────────────

_CHANNEL_BY_ID = {
    1: ('return "trades." + market, ', "market"),
    2: ('return "bbo." + market, ', "market"),
    3: ('return "order_book." + market, ', "market"),
    4: ('return "markets_summary." + market, ', "market"),
    5: ('return "funding_data." + market, ', "market"),
    # The subscription channel carries a refresh-rate suffix
    # ("funding_rate_comparison.ALL@1000ms") that the frame does not encode, so
    # emit the base name and let _resolve_sbe_channel's prefix scan match it.
    # The symbol still reaches the caller as a field on the model.
    6: ('return "funding_rate_comparison", ', "market"),
    20: ('return "orders." + market, ', "market"),
    21: ('return "fills." + market, ', "market"),
    22: ('return "positions", ', None),
    23: ('return "account", ', None),
    40: None,
    41: None,
}


def generate_codec(schema: dict) -> str:  # noqa: C901
    """Generate the codec.py source as a string."""
    schema_id = schema["schema_id"]
    schema_version = schema["schema_version"]
    released = schema["released"]
    enums = schema["enums"]
    enum_encoding = schema["enum_encoding"]
    sets = schema["sets"]
    messages = schema["messages"]

    lines = []

    # Header
    lines += [
        "# AUTO-GENERATED by scripts/generate_sbe_decoder.py from paradex_1_0.xml",
        f"# Schema ID={schema_id} Version={schema_version}  Released {released}  —  DO NOT EDIT MANUALLY",
        "#",
        "# Channel name note: XML comments say orders.{account}/fills.{account} but",
        "# the SDK subscribes with orders.{market}/fills.{market}; codec routes by market.",
        "#",
        "# BookEvent note: SBE produces bids/asks arrays; JSON channel produces",
        "# inserts/updates/deletes — the field shapes differ.",
        "#",
        "# Field name divergence from JSON API:",
        "#   SBE trade_id   ↔ JSON id",
        "#   SBE order_type ↔ JSON type",
        "#   SBE seq_no     ↔ JSON seq",
        "# order_book prefix scan: if a user subscribes two depth levels for the same",
        "# market simultaneously the prefix scan in ws_client may be ambiguous.",
        "from __future__ import annotations",
        "",
        "import struct",
        "from typing import Optional",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        f"_SCHEMA_ID = {schema_id}",
        f"_SCHEMA_VERSION = {schema_version}",
        '_HEADER = struct.Struct("<HHHH")',
        "",
        "INT64_MIN = -9223372036854775808",
        "",
        "",
        "# ── Helpers ──────────────────────────────────────────────────────────────",
        "",
        "def _ts(x: int) -> int:",
        '    """Convert microseconds to milliseconds."""',
        "    return x // 1000",
        "",
        "",
        "def _f8(x: int) -> str:",
        '    """Decode fixed-point int64 with exponent -8 to decimal string."""',
        '    sign = "-" if x < 0 else ""',
        "    x_abs = abs(x)",
        "    integer_part = x_abs // 100_000_000",
        "    frac_part = x_abs % 100_000_000",
        '    return f"{sign}{integer_part}.{frac_part:08d}"',
        "",
        "",
        "def _f8n(x: int) -> Optional[str]:",
        '    """Nullable _f8; INT64_MIN sentinel → None."""',
        "    return None if x == INT64_MIN else _f8(x)",
        "",
        "",
        "def _i64n(x: int) -> Optional[int]:",
        '    """Nullable int64; INT64_MIN sentinel → None."""',
        "    return None if x == INT64_MIN else x",
        "",
        "",
        "def _f12(x: int) -> str:",
        '    """Decode fixed-point int64 with exponent -12 to decimal string."""',
        '    sign = "-" if x < 0 else ""',
        "    x_abs = abs(x)",
        "    integer_part = x_abs // 1_000_000_000_000",
        "    frac_part = x_abs % 1_000_000_000_000",
        '    return f"{sign}{integer_part}.{frac_part:012d}"',
        "",
        "",
        "def _f12n(x: int) -> Optional[str]:",
        '    """Nullable _f12; INT64_MIN sentinel → None."""',
        "    return None if x == INT64_MIN else _f12(x)",
        "",
        "",
        '_GROUP_HDR = struct.Struct("<HH")',
        "",
        "",
        "def _addr(b: bytes) -> str:",
        '    """Decode 32-byte big-endian AccountAddress to 0x-prefixed hex string."""',
        '    val = int.from_bytes(b, "big")',
        '    return "0x" + format(val, "x") if val else "0x0"',
        "",
        "",
    ]

    # Sets (bitsets like OrderFlags)
    for set_name, bits in sets.items():
        f"_{''.join(c if c.isupper() or c.isdigit() else '_' if c == '_' else '' for c in set_name).upper().rstrip('_')}_FLAG_NAMES"
        # Build {bit_pos: "FLAG_NAME", ...}
        parts = [f'{bit}: "{name}"' for bit, name in sorted(bits.items())]
        lines += [
            f"# ── {set_name} bitset ──────────────────────────────────────────────────────",
            "",
            f"_{set_name.upper()}_FLAG_NAMES = {{{', '.join(parts)}}}",
            "",
            "",
            f"def _decode_{set_name.lower()}(flags: int) -> list[str]:",
            f"    return [name for bit, name in _{set_name.upper()}_FLAG_NAMES.items() if flags & (1 << bit)]",
            "",
            "",
        ]

    # Enum maps
    lines += ["# ── Enum maps ────────────────────────────────────────────────────────────", ""]
    # Special SIDE_LONG_SHORT for PositionEvent
    lines += [
        "# PositionEvent.side uses LONG/SHORT semantics (BUY=LONG, SELL=SHORT per XML comment)",
        '_ENUM_SIDE_LONG_SHORT = {1: "LONG", 2: "SHORT", 254: None}',
    ]
    for enum_name, values in enums.items():
        prefix = _ENUM_VALUE_PREFIX.get(enum_name, "")
        parts = []
        for k, v in sorted(values.items()):
            if v is None:
                parts.append(f"{k}: None")
            else:
                parts.append(f'{k}: "{prefix}{v}"')
        enum_var = f"_ENUM_{enum_name.upper()}"
        lines.append(f"{enum_var} = {{{', '.join(parts)}}}")
    lines += ["", ""]

    # Models
    lines += ["# ── Pydantic models ──────────────────────────────────────────────────────", ""]

    # Helper to read var strings
    # Bounds-checked so a frame shorter than the layout says raises the error
    # the ws client already handles, instead of an IndexError that escapes
    # _process_binary_message and gets logged as a connection failure.
    READ_STR_HELPER = """\
def _read_str(buf: bytes, pos: int) -> tuple[str, int]:
    if pos >= len(buf):
        raise SbeDecodeError(f"Truncated frame: var-length field at {pos}, payload is {len(buf)} bytes")
    end = pos + 1 + buf[pos]
    if end > len(buf):
        raise SbeDecodeError(f"Truncated frame: var-length field needs {end} bytes, payload is {len(buf)}")
    return buf[pos + 1 : end].decode(), end
"""

    # Build a per-message model
    for msg in messages:
        msg_id = msg["id"]
        msg_name = msg["name"]
        model_name = f"{msg_name}Data"
        fields = msg["fields"]
        groups = msg["groups"]
        data_fields = msg["data"]

        # Skip heartbeat/subscribed - still generate but minimal
        if msg_id in (40, 41):
            lines += [
                f"class {model_name}(BaseModel):",
                f'    """Decoded {msg_name} (templateId={msg_id}). Channel: discarded."""',
                '    model_config = ConfigDict(extra="allow", populate_by_name=True)',
                "    timestamp: int",
                "    seq_no: int",
            ]
            if msg_id == 41:
                lines += ["    status: int", "    channel: str"]
            lines += ["", ""]
            continue

        # Generate model fields. Anything carrying sinceVersion can be absent
        # from a frame negotiated at an earlier version, so it is optional with
        # a None default — None means "this frame predates the field", which is
        # not the same as a field the server sent empty.
        model_fields = []
        for f in fields:
            fname = _to_snake(f["name"])
            ftype = f["type"]
            # Special case: ts → timestamp, seq → seq_no
            if fname == "ts":
                fname = "timestamp"
            elif fname == "seq":
                fname = "seq_no"
            python_type = _field_python_type(ftype, enums, f["optional"])
            model_fields.append((fname, _absent_by_version(python_type, f["since"])))

        for g in groups:
            model_fields.append((g["name"], "list[list[str]]"))

        for d in data_fields:
            model_fields.append((_to_snake(d["name"]), _absent_by_version("str", d["since"])))

        lines += [
            f"class {model_name}(BaseModel):",
            f'    """Decoded {msg_name} (templateId={msg_id})."""',
            '    model_config = ConfigDict(extra="allow", populate_by_name=True)',
        ]
        for fname, ftype in model_fields:
            lines.append(f"    {fname}: {ftype}")
        lines += ["", ""]

    # Decode functions
    lines += [
        "# ── Decode functions ──────────────────────────────────────────────────────",
        "",
        READ_STR_HELPER,
    ]

    for msg in messages:
        msg_id = msg["id"]
        msg_name = msg["name"]
        model_name = f"{msg_name}Data"
        fields = msg["fields"]
        groups = msg["groups"]
        data_fields = msg["data"]

        # Build one struct per sinceVersion tier. The base tier is the block
        # every client receives; each later tier is appended after it and is
        # only present when block_len reaches that far, because the server trims
        # the block to the negotiated version's length.
        struct_var = f"_{msg_name.upper()}_STRUCT"
        tier_structs = []
        tier_offset = 0
        for since, tier_fields in _tiers(fields):
            fmt_chars = "".join(_field_struct_char(f["type"], enums, enum_encoding) for f in tier_fields)
            tier_var = struct_var if since == 0 else f"{struct_var}_V{since}"
            lines.append(f'{tier_var} = struct.Struct("<{fmt_chars}")')
            tier_size = struct.calcsize(f"<{fmt_chars}")
            tier_structs.append(
                {
                    "since": since,
                    "var": tier_var,
                    "offset": tier_offset,
                    "end": tier_offset + tier_size,
                    "fields": tier_fields,
                }
            )
            tier_offset += tier_size
        lines.append("")

        if msg_id in (40, 41):
            lines += [
                f"def _decode_{msg_id}(payload: bytes, block_len: int, version: int) -> tuple[None, None]:",
                f'    """Discard {msg_name} — no callback routing."""',
                "    return None, None",
                "",
                "",
            ]
            continue

        # Determine return type
        ret_type = "tuple[None, None]" if msg_id in (40, 41) else f"tuple[str, {model_name}]"

        lines += [
            f"def _decode_{msg_id}(payload: bytes, block_len: int, version: int) -> {ret_type}:",
        ]

        # Unpack the base tier, then each appended tier the frame is long enough
        # to carry. Absent tiers leave their raw vars as None.
        base = tier_structs[0]
        base_vars = ", ".join(_raw_var(f) for f in base["fields"])
        lines += [
            f"    {base_vars} = \\",
            f"        {base['var']}.unpack_from(payload, 0)",
        ]
        for tier in tier_structs[1:]:
            tier_vars = [_raw_var(f) for f in tier["fields"]]
            for v in tier_vars:
                lines.append(f"    {v} = None")
            lines.append(f"    # Appended in schema version {tier['since']}; a frame negotiated below it")
            lines.append(f"    # carries only the first {tier['offset']} bytes of block.")
            lines.append(f"    if block_len >= {tier['end']}:")
            if len(tier_vars) == 1:
                lines.append(f"        {tier_vars[0]} = {tier['var']}.unpack_from(payload, {tier['offset']})[0]")
            else:
                lines.append(f"        {', '.join(tier_vars)} = {tier['var']}.unpack_from(payload, {tier['offset']})")
        lines.append("    offset = block_len")

        # Groups
        for g in groups:
            gname = g["name"]
            gfields = g["fields"]
            gfmt = "".join(_field_struct_char(gf["type"], enums, enum_encoding) for gf in gfields)
            lines += [
                f"    # {gname} group",
                f"    _grp_blk, _num_{gname} = _GROUP_HDR.unpack_from(payload, offset)",
                "    offset += 4",
                f"    {gname}: list[list[str]] = []",
                f'    _entry_{gname} = struct.Struct("<{gfmt}")',
                f"    for _ in range(_num_{gname}):",
            ]
            gvars = [f"_{gf['name']}_raw" for gf in gfields]
            lines.append(f"        {', '.join(gvars)} = _entry_{gname}.unpack_from(payload, offset)")
            # For book entries, both price and size use _f8
            gexprs = [_field_helper(gf["type"], f"_{gf['name']}_raw", enums) for gf in gfields]
            lines.append(f"        {gname}.append([{', '.join(gexprs)}])")
            lines.append("        offset += _grp_blk")

        # Data fields. Var-length data sits after the block, so trimming the
        # block does not remove it — the server cuts the var-data section
        # instead, and the negotiated version in the header is what says where.
        for d in data_fields:
            dname = _to_snake(d["name"])
            if d["since"] == 0:
                lines.append(f"    {dname}, offset = _read_str(payload, offset)")
            else:
                lines += [
                    f"    {dname} = None",
                    f"    if version >= {d['since']}:",
                    f"        {dname}, offset = _read_str(payload, offset)",
                ]

        # Channel
        channel_info = _CHANNEL_BY_ID.get(msg_id)
        if channel_info is None:
            lines.append("    return None, None")
        else:
            ret_prefix, _ = channel_info
            # Build model constructor
            model_args = []
            for f in fields:
                fname = _to_snake(f["name"])
                raw_var = _raw_var(f)
                # Map field name
                if fname == "ts":
                    model_fname = "timestamp"
                elif fname == "seq":
                    model_fname = "seq_no"
                else:
                    model_fname = fname

                # Special case: PositionEvent.side uses LONG_SHORT
                if msg_id == 22 and fname == "side":
                    expr = f"_ENUM_SIDE_LONG_SHORT.get({raw_var})"
                else:
                    expr = _field_helper(f["type"], raw_var, enums, f["optional"])
                # A version-gated field is None when the frame predates it, and
                # the decode helpers take an int, so guard before converting.
                if f["since"] > 0:
                    expr = f"None if {raw_var} is None else {expr}"
                model_args.append(f"{model_fname}={expr}")

            for g in groups:
                model_args.append(f"{g['name']}={g['name']}")

            for d in data_fields:
                dname = _to_snake(d["name"])
                model_args.append(f"{dname}={dname}")

            lines.append(f"    {ret_prefix}{model_name}(")
            for i, arg in enumerate(model_args):
                comma = "," if i < len(model_args) - 1 else ""
                lines.append(f"        {arg}{comma}")
            lines.append("    )")

        lines += ["", ""]

    # Dispatcher
    [msg["id"] for msg in messages]
    lines += [
        "# ── Dispatcher ────────────────────────────────────────────────────────────",
        "",
        "_DECODERS: dict[int, object] = {",
    ]
    for msg in messages:
        lines.append(f"    {msg['id']}: _decode_{msg['id']},")
    lines += ["}", "", ""]

    lines += [
        "class SbeDecodeError(Exception):",
        '    """Raised when an SBE binary frame cannot be decoded."""',
        "",
        "",
        "def decode_frame(data: bytes) -> tuple[str | None, BaseModel | None]:",
        '    """Decode a binary SBE WebSocket frame.',
        "",
        "    Returns:",
        "        (channel_name, model) — channel is None for heartbeat/subscribed ack.",
        "",
        "    Raises:",
        "        SbeDecodeError: on malformed or unsupported frames.",
        '    """',
        "    if len(data) < 8:",
        '        raise SbeDecodeError(f"Frame too short: {len(data)} bytes")',
        "    block_len, tmpl_id, schema_id, version = _HEADER.unpack_from(data, 0)",
        "    if schema_id != _SCHEMA_ID:",
        '        raise SbeDecodeError(f"Unsupported schemaId {schema_id}, expected {_SCHEMA_ID}")',
        "    dec = _DECODERS.get(tmpl_id)",
        "    if dec is None:",
        '        raise SbeDecodeError(f"Unknown templateId {tmpl_id}")',
        # ty (not mypy) is what CI runs, so the suppression must use its
        # syntax; a `type: ignore` here leaves the diagnostic unsuppressed.
        "    return dec(data[8:], block_len, version)  # ty: ignore[call-non-callable]",
        "",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate paradex_py/api/sbe/codec.py from SBE XML schema")
    parser.add_argument(
        "--schema",
        required=True,
        help="Path to paradex_1_0.xml",
    )
    parser.add_argument(
        "--output",
        default="paradex_py/api/sbe/codec.py",
        help="Output path for generated codec (default: paradex_py/api/sbe/codec.py)",
    )
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"Error: schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Parsing schema: {schema_path}")
    schema = parse_schema(str(schema_path))

    print(f"Generating codec: {output_path}")
    code = generate_codec(schema)
    output_path.write_text(code)

    print(f"Done. Wrote {len(code)} bytes to {output_path}")


if __name__ == "__main__":
    main()
