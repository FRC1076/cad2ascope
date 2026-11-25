"""Keep the documentation honest: quoted messages exist, shown commands parse, links resolve, config keys exist."""

from __future__ import annotations

import html
import json
import re
import shlex
from pathlib import Path

import pytest

from cad2ascope.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
PROCEDURES = ROOT / "templates" / "robot-repo" / "docs" / "robot-model"
DOCS = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").glob("*.md")), *sorted(PROCEDURES.glob("*.md"))]
SOURCE = "\n".join(p.read_text() for p in sorted((ROOT / "src" / "cad2ascope").rglob("*.py")))


def _p5_fragments() -> list[str]:
    md = (PROCEDURES / "P5-troubleshooting.md").read_text()
    rows = md.split("## Messages from cad2ascope", 1)[1].split("## Symptoms", 1)[0]
    frags = re.findall(r"^\| `([^`]+)` \|", rows, re.M)
    sheet = html.unescape((PROCEDURES / "lab-sheets.html").read_text()).split("P5. Troubleshooting", 1)[1]
    for cell in re.findall(r"<tr><td>(.*?)</td>", sheet):
        for part in cell.split(" / "):
            part = re.sub(r"<[^>]+>", "", part).strip().strip("…").strip()
            if part:
                frags.append(part)
    return frags


@pytest.mark.parametrize("fragment", _p5_fragments())
def test_quoted_messages_exist_in_the_code(fragment):
    assert fragment in SOURCE, f"P5 quotes {fragment!r}, but no message in src/cad2ascope contains it"


def _code_snippets(text: str) -> list[str]:
    """Inline code spans, fenced blocks, and HTML <code> elements: where documented commands live."""
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    rest = re.sub(r"```.*?```", "", text, flags=re.S)
    spans = re.findall(r"`([^`\n]+)`", rest) + re.findall(r"<code>(.*?)</code>", rest, re.S)
    lines = [line for block in fenced for line in block.splitlines()]
    return [html.unescape(re.sub(r"<[^>]+>", "", x)) for x in lines + spans]


def _commands() -> list[str]:
    cmds = []
    for doc in [*DOCS, PROCEDURES / "lab-sheets.html"]:
        for snippet in _code_snippets(doc.read_text()):
            m = re.search(r"cad2ascope ((?:inspect|init|build|codegen|render|ci|fetch|run)\b.*)$", snippet.strip())
            if m and " + " not in m.group(1):  # "build + codegen" is a label in PLAN's diagram, not a command
                cmds.append(m.group(1).replace("…", "").strip())
    return sorted(set(cmds))


@pytest.mark.parametrize("command", _commands())
def test_documented_commands_parse(command):
    args = shlex.split(command)
    if args[0] in ("inspect", "init", "build", "codegen") and len(args) == 1:
        args.append("export.zip")
    if args[0] == "render" and len(args) == 1:
        args.append("assets/advantagescope/Robot_x")
    build_parser().parse_args(args)


def _links() -> list[tuple[Path, str]]:
    out = []
    for doc in [*DOCS, PROCEDURES / "lab-sheets.html"]:
        for target in re.findall(r"\]\(([^)\s]+)\)", doc.read_text()):
            if not target.startswith(("http://", "https://", "#", "mailto:")):
                out.append((doc, target.split("#", 1)[0]))
    return out


@pytest.mark.parametrize(("doc", "target"), _links(), ids=lambda v: v.name if isinstance(v, Path) else v)
def test_relative_links_resolve(doc, target):
    assert (doc.parent / target).exists(), f"{doc.relative_to(ROOT)} links to {target}, which does not exist"


def test_config_keys_in_docs_exist():
    schema = json.loads((ROOT / "spec" / "advantagescope.schema.json").read_text())
    props = schema["properties"]
    text = "\n".join(p.read_text() for p in DOCS + [PROCEDURES / "lab-sheets.html"])
    used = set(re.findall(r"`(robot|signals|joints|mesh|cameras|frames|codegen)\.([a-z_]+)`", text))
    assert used, "expected the docs to mention some config keys"
    for section, key in used:
        if key in ("py", "md", "yaml", "json", "urdf", "glb", "zip", "java"):  # a file name like robot.urdf
            continue
        assert key in props[section].get("properties", {}), f"docs mention {section}.{key}, which is not in the schema"
    joint_keys = props["joints"]["additionalProperties"]["properties"]
    for key in ("ratio", "direction", "zero_offset_deg", "zero_offset_m"):
        assert key in joint_keys
