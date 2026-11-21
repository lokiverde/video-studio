"""Caption text per platform for fv.py publish. Pure: the description comes in already
built by the Shorts kit (th_shorts.short_copy plus the blog line), and this only shapes it
for each platform's rules. Spec: docs/briefs/2026-10-29-auto-poster.md, decisions 9, 14,
23 and 24."""
from __future__ import annotations

import re

import kit_links
import publish_kit

AI_LINE = publish_kit.AI_DISCLOSURE_DEFAULT
X_URL_WEIGHT = 23                 # X counts every link as 23 characters, whatever its length
URL = re.compile(r"https?://\S+")
KIT_START = re.compile(r"^# LINKEDIN[ \t]*$", re.M)    # anything above it is notes for Tony
KIT_TITLE = re.compile(r"^#[ \t]+[^\n]*\n?", re.M)    # linkedin.md's own headings, never a #hashtag
KIT_NOTE = re.compile(r"^Before posting:[^\n]*\n?", re.M)
RULE = re.compile(r"^[ \t]*-{3,}[ \t]*$\n?", re.M)
LIMITS = {"youtube": 5000, "tiktok": 2200, "instagram": 2200, "facebook": 8000,
          "linkedin": 3000, "twitter": 280}
YOUTUBE_TITLE_MAX = 100
LINK_LINE_MARKS = (kit_links.BLOG_MARK, kit_links.VIDEO_MARK, "Full episode", "Written version")
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def no_dashes(text: str) -> str:
    """House rule: em and en dashes become a comma, line breaks stay."""
    return re.sub(r"[ \t]*[\u2014\u2013][ \t]*", ", ", text or "")


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _cut(text: str, limit: int, keep: str = "") -> str:
    """Text inside limit. A tail it ends with (the footer) survives: the body is cut instead."""
    if len(text) <= limit:
        return text
    if keep and text.endswith(keep) and len(keep) + 3 < limit:
        body = text[:-len(keep)].rstrip()
        return body[:limit - len(keep) - 3].rstrip() + "…\n\n" + keep
    return text[:limit - 1].rstrip() + "…"


def x_length(text: str) -> int:
    """Length as X counts it: every URL weighs 23."""
    return len(URL.sub("x" * X_URL_WEIGHT, text))


def strip_links(text: str) -> str:
    """No URL lines: LinkedIn ranks posts with links lower, and Blotato cannot add the first
    comment where Tony keeps them."""
    kept = [ln for ln in text.split("\n")
            if not URL.search(ln) and not ln.strip().startswith(LINK_LINE_MARKS)]
    return _tidy("\n".join(kept))


def _with_ai(text: str, ai: bool, footer: str = "") -> str:
    """The disclosure line goes just before the footer, so the footer stays last."""
    if not ai or AI_LINE in text:
        return text
    if footer and text.endswith(footer):
        return f"{text[:-len(footer)].rstrip()}\n\n{AI_LINE}\n\n{footer}"
    return f"{text}\n\n{AI_LINE}"


def x_text(title: str, description: str, footer: str, ai: bool = False,
           keep_footer: bool = False) -> str:
    """Title, the first link in the description, then the footer, inside 280 as X counts it.
    When something must give the footer goes first, then the title is cut; with keep_footer
    (the DRE line on real estate) only the title is ever cut."""
    url = next(iter(URL.findall(description)), None)
    tail = ([url] if url else []) + ([AI_LINE] if ai else [])
    footers = [footer] if footer else []
    for parts in ([title] + tail + footers, [title] + tail) if not keep_footer else ([title] + tail + footers,):
        text = "\n\n".join(parts)
        if x_length(text) <= LIMITS["twitter"]:
            return text
    rest = tail + (footers if keep_footer else [])
    room = LIMITS["twitter"] - x_length("\n\n".join([""] + rest))
    return "\n\n".join([_cut(title, max(room, 1))] + rest)


def for_platform(platform: str, title: str, description: str, footer: str,
                 ai: bool = False, keep_footer: bool = False) -> dict:
    """{"text": ...} for every platform, plus {"title": ...} for YouTube. The footer stays
    last on every platform; keep_footer also forbids X from dropping it."""
    title = no_dashes(title).strip()
    description = no_dashes(description)
    footer = no_dashes(footer)
    if platform == "twitter":
        return {"text": x_text(title, description, footer, ai, keep_footer)}
    if platform == "linkedin":
        body = strip_links(description)
        if footer and footer not in body:
            body = f"{body}\n\n{footer}"
        return {"text": _cut(_with_ai(body, ai, footer), LIMITS["linkedin"], footer)}
    text = _cut(_with_ai(description, ai, footer), LIMITS.get(platform, 2200), footer)
    if platform == "youtube":
        clean_title = re.sub(r"[<>\n]", "", title)[:YOUTUBE_TITLE_MAX] or "Video"
        return {"title": clean_title, "text": text}
    return {"text": text}


def linkedin_full(md: str, footer: str, ai: bool = False) -> str:
    """The full 9:16 post on Tony LI from linkedin.md: no frontmatter, no First comment
    section (Tony pastes that from the clipboard), none of the kit's title, "Before posting"
    note or dividers, the footer once at the end."""
    body = FRONTMATTER.sub("", md or "", count=1)
    body = kit_links.FIRST_COMMENT_SECTION.sub("", body)
    body = KIT_START.split(body)[-1]
    body = RULE.sub("", KIT_NOTE.sub("", KIT_TITLE.sub("", body)))
    body = _tidy(no_dashes(body))
    footer = no_dashes(footer)
    if footer and footer not in body:
        body = f"{body}\n\n{footer}"
    return _cut(_with_ai(body, ai, footer), LIMITS["linkedin"], footer)
