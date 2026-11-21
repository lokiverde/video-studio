"""The edits the blog publisher makes to a site repo, as text in, text out. Pure.

Add-only: a new post goes first in the posts array (techtony.co under this month's
comment). An existing post of the same slug is never rewritten: without a video it gets the
videoId (and loses the writer's placeholder comment), with one it is left
alone. The video library entry comes from the kit's out/video_library_entry.txt.
The my-sites PLAYBOOK, rule 1, lists exactly these edits; anything else is out of bounds.
Spec: docs/briefs/2026-10-29-auto-poster.md, decision 11."""
from __future__ import annotations

import json
import math
import re
from datetime import date

import blog_md
import kit_links

WORDS_PER_MINUTE = 200
PLACEHOLDER_COMMENT = "videoId added once"
FALLBACK_MARK = "FALLBACK takeaways"
ARRAY_OPEN = re.compile(r"^export const (?:POSTS|blogPosts): \w+\[\] = \[(\];)?\n", re.M)
LIBRARY_OPEN = "export const VIDEO_LIBRARY: VideoEntry[] = [\n"
CATEGORY = re.compile(r'^\s+category:\s*"([^"]+)"', re.M)
TEMPLATE_END = re.compile(r"(?<!\\)`,\n  },")


def _ts(text: str) -> str:
    """A TypeScript string literal, bullets kept as the escape the sites already use."""
    return json.dumps(text, ensure_ascii=False).replace(blog_md.BULLET, "\\u2022 ")


def _template(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


# ---- reading the posts file -------------------------------------------------------------------

def categories(text: str) -> list[str]:
    return sorted(set(CATEGORY.findall(text)))


def find_post(text: str, slug: str) -> tuple[int, int] | None:
    """(start, end) of the "  {" ... "  }," entry whose slug is slug. A techtony entry ends
    after its content template literal, which may itself hold a "  }," line (code samples)."""
    m = re.search(rf'^\s+slug:\s*"{re.escape(slug)}",?\s*$', text, re.M)
    if not m:
        return None
    start = text.rfind("\n  {\n", 0, m.start()) + 1
    plain = text.find("\n  },", m.end())
    content = text.find("content: `", m.end())
    if content >= 0 and (plain < 0 or content < plain):
        close = TEMPLATE_END.search(text, content + len("content: `"))
        return start, (close.end() if close else len(text))
    return start, (len(text) if plain < 0 else plain + len("\n  },"))


def video_of(entry: str) -> str | None:
    """The entry's videoId as an 11 character id (it may be stored as a URL)."""
    m = re.search(r'^\s+videoId:\s*"([^"]*)"', entry, re.M)
    if not m:
        return None
    try:
        return kit_links.video_id(m.group(1))
    except ValueError:
        return m.group(1)


def pick_category(wanted: str, known: list[str], default: str) -> tuple[str, str]:
    """(category, note). The site's own spelling of the post's category when the site has
    it, else the site default. A site with no posts yet takes the post's category as is."""
    if not known:
        return (wanted or default), ""
    match = next((k for k in known if k.lower() == (wanted or "").lower()), None)
    if match:
        return match, ""
    note = f"category {wanted!r} is not on this site yet, so {default!r}" if wanted else ""
    return default, note


# ---- entries ---------------------------------------------------------------------------------------

def hm_entry(p: dict, *, category: str, day: date, video_id: str, author: str | None = None) -> str:
    _, body = blog_md.hm_body(p["body"])
    lines = ["  {", f"    slug: {_ts(p['slug'])},", f"    title: {_ts(p['title'])},",
             f"    category: {_ts(category)},", f"    date: {_ts(day.isoformat())},"]
    if author:
        lines.append(f"    author: {_ts(author)},")
    lines += [f"    videoId: {_ts(video_id)},", f"    excerpt: {_ts(p['excerpt'])},", "    body: [",
              *[f"      {_ts(line)}," for line in body], "    ],", "  },"]
    return "\n".join(lines) + "\n"


def reading_time(content: str) -> str:
    minutes = max(1, math.ceil(len(re.findall(r"\w+", content)) / WORDS_PER_MINUTE))
    return f"{minutes} min read"


def techtony_entry(p: dict, *, category: str, day: date, video_id: str, image: str | None) -> str:
    _, content = blog_md.markdown_body(p["body"])
    lines = ["  {", f"    slug: {_ts(p['slug'])},", f"    title: {_ts(p['title'])},",
             f"    date: {_ts(long_date(day))},", f"    excerpt: {_ts(p['excerpt'])},",
             f"    readingTime: {_ts(reading_time(content))},", f"    category: {_ts(category)},"]
    if image:
        lines.append(f"    featuredImage: {_ts(image)},")
    lines += [f"    videoId: {_ts(video_id)},", f"    content: `\n{_template(content)}\n`,", "  },"]
    return "\n".join(lines) + "\n"


# ---- edits -------------------------------------------------------------------------------------------

def add_entry(text: str, entry: str, fmt: str, day: date) -> str:
    """The entry first in the array. techtony.co groups posts under month comments."""
    m = ARRAY_OPEN.search(text)
    if not m:
        raise ValueError("no posts array (export const POSTS / blogPosts) in the posts file")
    if m.group(1):                                     # "= [];": the first post on the site
        return f"{text[:m.start()]}{m.group(0)[:-3]}\n{entry}];\n{text[m.end():]}"
    at = m.end()
    if fmt == "techtony":
        month = f"  // {day:%B} {day.year}\n"
        if text.startswith(month, at):
            at += len(month)
        else:
            entry = month + entry
    return text[:at] + entry + text[at:]


def fill_video(text: str, span: tuple[int, int], video_id: str, before: str) -> str:
    """videoId into the entry at span, before its `before:` field, placeholder comment out."""
    start, end = span
    lines = [ln for ln in text[start:end].split("\n") if PLACEHOLDER_COMMENT not in ln]
    at = next((i for i, ln in enumerate(lines) if re.match(rf"^\s+{before}:", ln)), None)
    if at is None:
        at = next(i for i, ln in enumerate(lines) if re.match(r"^\s+slug:", ln)) + 1
    indent = re.match(r"^(\s*)", lines[at] if at < len(lines) else "    ").group(1) or "    "
    entry = "\n".join([*lines[:at], f"{indent}videoId: {_ts(video_id)},", *lines[at:]])
    return text[:start] + entry + text[end:]


def change(text: str, p: dict, site: dict, video_id: str, day: date) -> dict:
    """{"action": "add" | "fill" | "live", "text", "entry", "category", "note", "video"} for one
    post. entry is the new or changed entry alone (what Tony approves), text the whole new
    file, video the id a live post already embeds."""
    span = find_post(text, p["slug"])
    if span:
        existing = CATEGORY.search(text[span[0]:span[1]])
        category = existing.group(1) if existing else ""
        live = video_of(text[span[0]:span[1]])
        if live:
            return {"action": "live", "text": text, "entry": "", "category": category, "note": "", "video": live}
        new = fill_video(text, span, video_id, site["video_before"])
        filled = find_post(new, p["slug"])
        return {"action": "fill", "text": new, "entry": new[filled[0]:filled[1]] + "\n", "category": category,
                "note": "", "video": None}
    category, note = pick_category(p["category"], categories(text), site["default_category"])
    if site["format"] == "techtony":
        image = site["image_url"].format(slug=p["slug"]) if site.get("image_url") else None
        entry = techtony_entry(p, category=category, day=day, video_id=video_id, image=image)
    else:
        entry = hm_entry(p, category=category, day=day, video_id=video_id, author=site.get("author"))
    return {"action": "add", "text": add_entry(text, entry, site["format"], day), "entry": entry,
            "category": category, "note": note, "video": None}


# ---- the video library ---------------------------------------------------------------------------------

def library_entry(entry_txt: str, links: dict) -> tuple[str | None, str | None]:
    """(the object text for VIDEO_LIBRARY, None) or (None, why it is skipped)."""
    if FALLBACK_MARK in entry_txt:
        return None, "the kit has fallback takeaways: write youtube.takeaways, re-run the kit, then add it"
    filled = kit_links.entry_with_links(entry_txt, links)
    body = "\n".join(ln for ln in filled.split("\n") if not ln.lstrip().startswith("//")).strip().rstrip(",")
    try:
        data = json.loads(body)
    except ValueError as err:
        return None, f"out/video_library_entry.txt is not a plain object: {err}"
    if not isinstance(data, dict):
        return None, "out/video_library_entry.txt is not a plain object"
    pending = [k for k in ("id", "uploadDate", "ownerUrl") if str(data.get(k, "")).startswith("TODO_")]
    if pending:
        return None, f"{', '.join(pending)} still pending (fv.py publish JOB --uploaded YYYY-MM-DD)"
    return "\n".join(f"  {ln}" for ln in body.split("\n")) + ",\n", None


def add_library(text: str, obj: str, video_id: str) -> tuple[str, str | None]:
    """(new library text, None) or (the text unchanged, why)."""
    if re.search(rf'"id":\s*"{re.escape(video_id)}"', text):
        return text, f"{video_id} is already in the video library"
    if LIBRARY_OPEN not in text:
        raise ValueError("no VIDEO_LIBRARY array in the video library file")
    at = text.index(LIBRARY_OPEN) + len(LIBRARY_OPEN)
    return text[:at] + obj + text[at:], None
