"""Guards on the vendored SBE schema and the codec generated from it.

The schema is a copy of the one the servers encode with, and v0.7.1 shipped a
1:2 copy that had gone stale without anything noticing. check_sbe_schema.py is
what compares it with upstream; these tests pin down that its comparison sees
schema changes and ignores prose curation, and that codec.py is what the XML
generates.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "paradex_py" / "api" / "sbe" / "paradex_1_0.xml"
CODEC = ROOT / "paradex_py" / "api" / "sbe" / "codec.py"

sys.path.insert(0, str(ROOT / "scripts"))
import check_sbe_schema  # noqa: E402
import generate_sbe_decoder  # noqa: E402


@pytest.fixture(scope="module")
def schema_text() -> str:
    return SCHEMA.read_text()


def test_comment_only_changes_are_not_drift(schema_text: str):
    """The public copy curates comments; that must never read as drift."""
    recommented = re.sub(r"<!--.*?-->", "<!-- rewritten -->", schema_text, flags=re.DOTALL)
    assert recommented != schema_text
    assert check_sbe_schema.compare(schema_text, recommented) == []


def test_description_prose_is_not_drift_but_deprecation_is(schema_text: str):
    """Descriptions are curated like comments, except for the DEPRECATED marker."""
    reworded = schema_text.replace('description="Fill flags bitset"', 'description="Reworded for readers"')
    assert reworded != schema_text
    assert check_sbe_schema.compare(reworded, schema_text) == []

    undeprecated = schema_text.replace('description="DEPRECATED, use tradeIdStr.', 'description="Use tradeIdStr.')
    assert undeprecated != schema_text
    assert check_sbe_schema.compare(undeprecated, schema_text) != []


def test_missing_field_is_drift(schema_text: str):
    """The v0.7.1 failure: upstream gained tradeIdStr and the copy did not."""
    stale = re.sub(r'<data\s+id="10"\s+name="tradeIdStr".*?/>', "", schema_text, flags=re.DOTALL)
    assert stale != schema_text
    diff = check_sbe_schema.compare(stale, schema_text)
    assert any("tradeIdStr" in line and line.startswith("-") for line in diff)


def test_changed_since_version_is_drift(schema_text: str):
    moved = schema_text.replace(
        'name="lastSeenNotification" type="Timestamp" sinceVersion="2"',
        'name="lastSeenNotification" type="Timestamp" sinceVersion="3"',
    )
    assert moved != schema_text
    assert check_sbe_schema.compare(moved, schema_text) != []


def test_header_version_matches_schema_attribute(schema_text: str):
    """The comment header is hand-maintained, so check it against the real attribute."""
    header_version = re.search(r"^\s*Version\s*:\s*(\d+)", schema_text, re.MULTILINE).group(1)
    attr_version = re.search(r'<sbe:messageSchema[^>]*\sversion="(\d+)"', schema_text, re.DOTALL).group(1)
    assert header_version == attr_version


@pytest.mark.skipif(importlib.util.find_spec("ruff") is None, reason="ruff not installed")
def test_codec_is_generated_from_the_schema(tmp_path: Path):
    """codec.py must be exactly what the committed XML and generator produce.

    Syncing the XML without regenerating, or hand-editing codec.py, fails here.
    """
    raw = generate_sbe_decoder.generate_codec(generate_sbe_decoder.parse_schema(str(SCHEMA)))
    name = "paradex_py/api/sbe/codec.py"  # so ruff picks up this file's config
    fixed = subprocess.run(  # noqa: S603 - fixed argv, runs the repo's own ruff
        [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", "--exit-zero", "--stdin-filename", name, "-"],
        input=raw,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    formatted = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "format", "--quiet", "--stdin-filename", name, "-"],
        input=fixed,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    assert formatted == CODEC.read_text(), "codec.py is stale: rerun scripts/generate_sbe_decoder.py and ruff"
