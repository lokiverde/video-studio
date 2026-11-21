"""blog.md, a job's companion article, read into a post for fv.py publish. Pure.

The frontmatter reader covers what the kit and the writer write (quoted and bare scalars, inline
[a, b] lists, block lists of "- item"); there is no PyYAML on the Mac. Two body shapes:
hm_body() for the my-sites sites (one string per line, the shapes their renderer
knows: "## " headings, **bold**, links, table rows, "• " bullets, the video slot) and
markdown_body() for techtony.co (its renderer reads the markdown line by line).
Spec: docs/briefs/2026-10-29-auto-poster.md, decisions 10 and 11."""
from __future__ import annotations

import json
import re

import publish_copy

VIDEO_SLOT = "{{YOUTUBE_EMBED}}"
BULLET = "• "
BANNED = ("delve", "realm", "unleash", "tapestry", "transcend", "synergy")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
VIDEO_MARKER = re.compile(r"^\s*(?:\*?\[VIDEO(?: EMBED)?\]\*?|\{\{YOUTUBE_EMBED\}\})\s*$", re.I)
KEY_LINE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
ITALIC = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+?)(?<!\*)\*(?![*\w])")
RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
IMAGE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")


# ---- frontmatter ---------------------------------------------------------------------------

def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        try:
            return json.loads(raw)
        except ValueError:
            return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_scalar(part) for part in re.split(r",\s*", inner)] if inner else []
    return raw


def frontmatter(text: str) -> tuple[dict, str]:
    """(fields, body). Top-level keys only; a key with nothing after the colon collects the
    "- item" lines under it as a list. No frontmatter: ({}, text)."""
    m = FRONTMATTER.match(text or "")
    if not m:
        return {}, text or ""
    fields: dict = {}
    current = None
    for line in m.group(1).split("\n"):
        key = KEY_LINE.match(line)
        if key and not line[0].isspace():
            current = key.group(1)
            fields[current] = _scalar(key.group(2)) if key.group(2).strip() else []
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current and isinstance(fields.get(current), list):
            fields[current] = [*fields[current], _scalar(item.group(1))]
    return fields, m.group(2)


# ---- body ---------------------------------------------------------------------------------------

def _lines(body: str) -> tuple[str | None, list[str]]:
    """(the H1, the remaining lines). The H1 counts only before any text."""
    lines = (body or "").split("\n")
    title = None
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if re.match(r"^#\s+\S", line):
            title = line.lstrip("#").strip()
            lines = lines[:i] + lines[i + 1:]
        break
    return title, lines


def _with_slot(entries: list[str], blank: str | None = None) -> list[str]:
    """The video slot after the first paragraph when the writer left no marker."""
    if VIDEO_SLOT in entries or not entries:
        return entries
    first = next((i for i, e in enumerate(entries) if e.strip() and e != blank), 0)
    extra = [blank, VIDEO_SLOT] if blank is not None else [VIDEO_SLOT]
    return [*entries[:first + 1], *extra, *entries[first + 1:]]


def _hm_line(line: str) -> str | None:
    text = publish_copy.no_dashes(line.strip())
    if not text or RULE.match(text) or IMAGE.match(text) or text.startswith("```"):
        return None
    if VIDEO_MARKER.match(text):
        return VIDEO_SLOT
    heading = re.match(r"^#{2,6}\s+(.*?)\s*#*$", text)
    if heading:
        return f"## {heading.group(1)}"
    if text.startswith("|"):
        return text
    text = ITALIC.sub(r"\1", text)
    bullet = re.match(r"^[-*+]\s+(.*)$", text)
    if bullet:
        return BULLET + bullet.group(1)
    quote = re.match(r"^>\s?(.*)$", text)
    if quote:
        inner = quote.group(1).strip()
        return inner if inner.startswith('"') else f'"{inner}"'
    return text


def hm_body(body: str) -> tuple[str | None, list[str]]:
    """(the H1, the body as the my-sites sites store it). blog.md keeps one paragraph
    per line, so every line is its own entry (a signature stays on two lines)."""
    title, lines = _lines(body)
    entries = [e for e in (_hm_line(line) for line in lines) if e is not None]
    return title, _with_slot(entries)


def markdown_body(body: str) -> tuple[str | None, str]:
    """(the H1, the markdown techtony.co renders): the markers become the slot on its own
    line, runs of blank lines collapse, nothing else changes."""
    title, lines = _lines(body)
    out = [VIDEO_SLOT if VIDEO_MARKER.match(line) else publish_copy.no_dashes(line.rstrip()) for line in lines]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")
    if VIDEO_SLOT not in text:
        paras = text.split("\n\n")
        text = "\n\n".join([*paras[:1], VIDEO_SLOT, *paras[1:]])
    return title, text


# ---- the post -----------------------------------------------------------------------------------

def _text(value) -> str:
    return publish_copy.no_dashes(str(value)).strip() if isinstance(value, (str, int, float)) else ""


def post(text: str) -> dict:
    """Everything the publisher needs from blog.md. Title falls back to the H1, excerpt to
    meta_description."""
    meta, body = frontmatter(text)
    h1, _ = _lines(body)
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    return {"site": _text(meta.get("site")), "slug": _text(meta.get("slug")),
            "title": _text(meta.get("title")) or _text(h1),
            "excerpt": _text(meta.get("excerpt")) or _text(meta.get("meta_description")),
            "category": _text(meta.get("category")), "tags": [str(t) for t in tags], "body": body}


def problems(p: dict) -> list[str]:
    """What stops the blog at Go."""
    found = []
    if not p["slug"]:
        found.append("blog.md has no slug in its frontmatter")
    elif not SLUG.match(p["slug"]):
        found.append(f"blog.md slug {p['slug']!r} is not lowercase-words-with-dashes")
    if not p["title"]:
        found.append("blog.md has no title (frontmatter title or an H1)")
    if not p["excerpt"]:
        found.append("blog.md has no excerpt or meta_description")
    words = " ".join([p["title"], p["excerpt"], p["body"]]).lower()
    found += [f"blog.md uses the banned word {w!r}" for w in BANNED if re.search(rf"\b{w}", words)]
    return found
