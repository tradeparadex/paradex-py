#!/usr/bin/env python3
"""
Code generator: reads paradex_1_0.xml → emits paradex_py/api/sbe/codec.py

Usage:
    uv run python scripts/generate_sbe_decoder.py \\
        --schema /path/to/paradex_1_0.xml \\
        --output paradex_py/api/sbe/codec.py
"""
import argparse
import re
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
    "uint32": "I",
}

# Composite name → (struct_char, helper_call_template, python_type_str)
# helper_call_template uses {v} for value variable
_COMPOSITE_INFO = {
    "Price8": ("q", "_f8({v})", "str"),
    "Price8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Qty8": ("q", "_f8({v})", "str"),
    "Value8": ("q", "_f8({v})", "str"),
    "Value8NULL": ("q", "_f8n({v})", "Optional[str]"),
    "Rate8": ("q", "_f8({v})", "str"),
    "Rate12": ("q", "_f12({v})", "str"),
    # Rate12NULL not in schema but added for completeness
    "Rate12NULL": ("q", "_f12n({v})", "Optional[str]"),
    "Timestamp": ("q", "_ts({v})", "int"),
}


def _to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def parse_schema(schema_path: str):
    """Parse the XML schema and return (enums, messages, schema_meta)."""
    tree = ET.parse(schema_path)
    root = tree.getroot()

    schema_id = root.get("id", "1")
    schema_version = root.get("version", "0")
    root.get("description", "")
    released = "2026-03-13"  # from XML comments

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
            fields.append({"name": field_name, "type": field_type})

        groups = []
        for group in msg.findall("group"):
            group_name = group.get("name")
            group_fields = []
            for gf in group.findall("field"):
                group_fields.append({"name": gf.get("name"), "type": gf.get("type")})
            groups.append({"name": group_name, "fields": group_fields})

        data_fields = []
        for data in msg.findall("data"):
            data_fields.append(data.get("name"))

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
        "messages": messages,
    }


def _field_struct_char(field_type: str, enums: dict, enum_encoding: dict) -> str:
    """Return the struct char for a field type."""
    if field_type in _COMPOSITE_INFO:
        return _COMPOSITE_INFO[field_type][0]
    if field_type in _PRIM_TO_CHAR:
        return _PRIM_TO_CHAR[field_type]
    if field_type in enums:
        return enum_encoding.get(field_type, "B")
    raise ValueError(f"Unknown field type: {field_type}")


def _field_helper(field_type: str, var: str, enums: dict) -> str:
    """Return the Python expression to convert a raw value."""
    if field_type in _COMPOSITE_INFO:
        tmpl = _COMPOSITE_INFO[field_type][1]
        return tmpl.replace("{v}", var)
    if field_type in ("int64", "uint8", "uint16"):
        return var
    if field_type in enums:
        enum_name = f"_ENUM_{field_type.upper()}"
        return f"{enum_name}.get({var})"
    return var


def _field_python_type(field_type: str, enums: dict) -> str:
    """Return the Python type annotation string."""
    if field_type in _COMPOSITE_INFO:
        return _COMPOSITE_INFO[field_type][2]
    if field_type in ("int64",):
        return "int"
    if field_type in ("uint8", "uint16"):
        return "int"
    if field_type in enums:
        return "Optional[str]"
    return "Any"


# ── Channel routing (hardcoded per message) ─────────────────────────────────

_CHANNEL_BY_ID = {
    1: ('return "trades." + market, ', "market"),
    2: ('return "bbo." + market, ', "market"),
    3: ('return "order_book." + market, ', "market"),
    4: ('return "markets_summary." + market, ', "market"),
    5: ('return "funding_data." + market, ', "market"),
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
    ]

    # Enum maps
    lines += ["# ── Enum maps ────────────────────────────────────────────────────────────", ""]
    # Special SIDE_LONG_SHORT for PositionEvent
    lines += [
        "# PositionEvent.side uses LONG/SHORT semantics (BUY=LONG, SELL=SHORT per XML comment)",
        '_ENUM_SIDE_LONG_SHORT = {1: "LONG", 2: "SHORT", 254: None}',
    ]
    for enum_name, values in enums.items():
        parts = []
        for k, v in sorted(values.items()):
            if v is None:
                parts.append(f"{k}: None")
            else:
                parts.append(f'{k}: "{v}"')
        enum_var = f"_ENUM_{enum_name.upper()}"
        lines.append(f'{enum_var} = {{{", ".join(parts)}}}')
    lines += ["", ""]

    # Models
    lines += ["# ── Pydantic models ──────────────────────────────────────────────────────", ""]

    # Helper to read var strings
    READ_STR_HELPER = """\
def _read_str(buf: bytes, pos: int) -> tuple[str, int]:
    ln = buf[pos]
    return buf[pos + 1 : pos + 1 + ln].decode(), pos + 1 + ln
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

        # Generate model fields
        model_fields = []
        for f in fields:
            fname = _to_snake(f["name"])
            ftype = f["type"]
            # Special case: ts → timestamp, seq → seq_no
            if fname == "ts":
                fname = "timestamp"
            elif fname == "seq":
                fname = "seq_no"
            python_type = _field_python_type(ftype, enums)
            model_fields.append((fname, python_type))

        for g in groups:
            model_fields.append((g["name"], "list[list[str]]"))

        for d in data_fields:
            model_fields.append((_to_snake(d), "str"))

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

        # Build struct format
        fmt_chars = ""
        for f in fields:
            fmt_chars += _field_struct_char(f["type"], enums, enum_encoding)
        struct_var = f"_{msg_name.upper()}_STRUCT"
        lines += [
            f'{struct_var} = struct.Struct("<{fmt_chars}")',
            "",
        ]

        if msg_id in (40, 41):
            lines += [
                f"def _decode_{msg_id}(payload: bytes, block_len: int) -> tuple[None, None]:",
                f'    """Discard {msg_name} — no callback routing."""',
                "    return None, None",
                "",
                "",
            ]
            continue

        # Unpack vars (rename ts→timestamp_raw, seq→seq_raw for clarity in decode)
        var_names = []
        for f in fields:
            fname = _to_snake(f["name"])
            if fname == "ts":
                var_names.append("ts_raw")
            elif fname == "seq":
                var_names.append("seq_raw")
            else:
                var_names.append(f"{fname}_raw")

        # Determine return type
        ret_type = "tuple[None, None]" if msg_id in (40, 41) else f"tuple[str, {model_name}]"

        lines += [
            f"def _decode_{msg_id}(payload: bytes, block_len: int) -> {ret_type}:",
        ]

        # Unpack line
        vars_str = ", ".join(var_names)
        lines += [
            f"    {vars_str} = \\",
            f"        {struct_var}.unpack_from(payload, 0)",
            "    offset = block_len",
        ]

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

        # Data fields
        for d in data_fields:
            dname = _to_snake(d)
            lines.append(f"    {dname}, offset = _read_str(payload, offset)")

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
                raw_var = "ts_raw" if fname == "ts" else ("seq_raw" if fname == "seq" else f"{fname}_raw")
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
                    expr = _field_helper(f["type"], raw_var, enums)
                model_args.append(f"{model_fname}={expr}")

            for g in groups:
                model_args.append(f"{g['name']}={g['name']}")

            for d in data_fields:
                dname = _to_snake(d)
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
        "    block_len, tmpl_id, schema_id, _ = _HEADER.unpack_from(data, 0)",
        "    if schema_id != _SCHEMA_ID:",
        '        raise SbeDecodeError(f"Unsupported schemaId {schema_id}, expected {_SCHEMA_ID}")',
        "    dec = _DECODERS.get(tmpl_id)",
        "    if dec is None:",
        '        raise SbeDecodeError(f"Unknown templateId {tmpl_id}")',
        "    return dec(data[8:], block_len)  # type: ignore[operator]",
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
