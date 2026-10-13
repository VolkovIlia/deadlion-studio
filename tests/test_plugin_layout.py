#!/usr/bin/env python3
"""
Layout checks for the marketplace and every plugin under plugins/.

Frontmatter is parsed with a minimal stdlib reader that understands the
three forms used in this repo: plain scalars, double-quoted scalars and
folded/literal blocks (`>-`, `>`, `|`).

Usage:
    pytest tests/test_plugin_layout.py -v
"""

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PLUGINS = PROJECT_ROOT / "plugins"
MARKETPLACE = PROJECT_ROOT / ".claude-plugin" / "marketplace.json"
CORE = "deadlion"
NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
FORBIDDEN_RE = re.compile(r"ds-run\.sh|context-store|ds-telemetry|Anchor")
MAX_BODY = {True: 150, False: 500}  # keyed by "is core plugin"

SKILLS = sorted(PLUGINS.glob("*/skills/*/SKILL.md"))


def split_frontmatter(text):
    """Return (frontmatter lines, body lines); fail if the fence is missing."""
    lines = text.splitlines()
    assert lines and lines[0] == "---", "missing opening ---"
    end = lines.index("---", 1)
    return lines[1:end], lines[end + 1:]


def scalar(raw):
    """Decode a one-line YAML scalar: double-quoted or plain."""
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return json.loads(raw)
    return raw


def parse_frontmatter(lines):
    """Map top-level keys to string values, folding indented block scalars."""
    meta, key, block = {}, None, None
    for line in lines:
        if block is not None and (line.startswith(" ") or not line):
            block.append(line.strip())
            continue
        if block is not None:
            meta[key], block = " ".join(filter(None, block)), None
        key, _, value = line.partition(":")
        if value.strip() in (">-", ">", "|", "|-"):
            block = []
        else:
            meta[key] = scalar(value)
    if block is not None:
        meta[key] = " ".join(filter(None, block))
    return meta


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: str(p.relative_to(PLUGINS)))
def test_skill_frontmatter_and_body(skill):
    head, body = split_frontmatter(skill.read_text())
    meta = parse_frontmatter(head)
    name = meta.get("name", "")
    assert name == skill.parent.name
    assert NAME_RE.match(name)
    assert 1 <= len(meta.get("description", "")) <= 1024
    is_core = skill.relative_to(PLUGINS).parts[0] == CORE
    assert len(body) <= MAX_BODY[is_core]


def test_no_v3_strings_under_plugins():
    hits = [
        f"{path.relative_to(PROJECT_ROOT)}:{n}"
        for path in PLUGINS.rglob("*")
        if path.is_file()
        for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if FORBIDDEN_RE.search(line)
    ]
    assert hits == []


def test_marketplace_sources_match_plugins():
    market = json.loads(MARKETPLACE.read_text())
    assert market["plugins"]
    for entry in market["plugins"]:
        source = (PROJECT_ROOT / entry["source"]).resolve()
        assert source.is_dir(), entry["source"]
        manifest = json.loads((source / ".claude-plugin" / "plugin.json").read_text())
        assert manifest["name"] == entry["name"]


def test_every_plugin_is_listed():
    listed = {e["name"] for e in json.loads(MARKETPLACE.read_text())["plugins"]}
    assert {p.name for p in PLUGINS.iterdir() if p.is_dir()} == listed
