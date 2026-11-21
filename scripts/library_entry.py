"""A ready-to-paste VIDEO_LIBRARY entry: out/video_library_entry.txt.

A TypeScript object literal matching VideoEntry in my-sites
packages/ui/src/video-types.ts exactly, following the header rules of video-library.ts:
transcript = what was actually said, lightly cleaned, never rewritten; keyTakeaways = 3 to 5
lines stated in the video; ownerUrl = the one page that carries the full transcript (the
companion article). The studio never edits my-sites: a Money Maker session pastes it.

id and uploadDate are placeholders until upload (fv.py links --youtube --uploaded), ownerUrl until
the article URL is set (fv.py bloglink). Takeaways come from youtube.takeaways, written with
the script; without them the first sentence of the first five scenes stands in, flagged.
"""
from __future__ import annotations

import json
import re

import kit_links
import publish_kit

DATE_PENDING = "TODO_UPLOAD_DATE"
TAKEAWAYS = (3, 5)
FALLBACK_NOTE = ("  // FALLBACK takeaways: the first sentence of the first five scenes. "
                 "Replace with 3 to 5 lines stated in the video.")
PARAGRAPH_WORDS = 55       # a one-line caption transcript is split into paragraphs about this long
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def iso_duration(seconds: float) -> str:
    """ISO 8601 duration from seconds, rounded to the second: 181 -> PT3M1S."""
    total = max(int(round(seconds)), 0)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{hours}H" if hours else "", f"{minutes}M" if minutes else "",
             f"{secs}S" if secs or not (hours or minutes) else ""]
    return "PT" + "".join(parts)


def first_sentence(text: str) -> str:
    text = publish_kit.clean(text)
    return SENTENCE_END.split(text, maxsplit=1)[0] if text else ""


def paragraphs(transcript: str, title: str | None = None) -> list[str]:
    """Transcript paragraphs as spoken. A faceless transcript.txt opens with the title (not
    spoken), so it is dropped. A single long line (talking-head captions) is grouped into
    paragraphs at sentence ends; no word is changed."""
    paras = [publish_kit.clean(p) for p in re.split(r"\n\s*\n", transcript or "") if p.strip()]
    if title and paras and paras[0] == publish_kit.clean(title):
        paras = paras[1:]
    out = []
    for para in paras:
        if len(para.split()) <= PARAGRAPH_WORDS * 2:
            out.append(para)
            continue
        chunk = []
        for sentence in SENTENCE_END.split(para):
            chunk.append(sentence)
            if len(" ".join(chunk).split()) >= PARAGRAPH_WORDS:
                out.append(" ".join(chunk))
                chunk = []
        if chunk:
            out.append(" ".join(chunk))
    return out


def takeaways(authored, fallback_texts: list[str]) -> tuple[list[str], bool]:
    """(takeaways, is_fallback). Authored ones win, as written (problems() flags a bad count)."""
    written = [publish_kit.clean(t) for t in (authored or []) if publish_kit.clean(t)]
    if written:
        return written, False
    picked = [first_sentence(t) for t in fallback_texts]
    return [s for s in picked if s][:TAKEAWAYS[1]], True


def _description(text: str) -> str:
    """The article page shows this under the player, so link lines (quiz, call, sources) are
    left out, and so is a heading like "Sources:" that has nothing left under it."""
    lines = [ln for ln in publish_kit.clean(text).split("\n") if "://" not in ln]
    while lines and (not lines[-1].strip() or lines[-1].rstrip().endswith(":")):
        lines.pop()
    return "\n".join(lines).strip()


def build(meta: dict, seconds: float, chapters, transcript: list[str], points: list[str],
          source: str, links: dict) -> dict:
    """The VideoEntry, field for field, in the type's own order."""
    return {
        "id": links.get("youtube_id") or kit_links.ID_PENDING,
        "title": publish_kit.clean(meta["title"]),
        "description": _description(meta.get("description", "")),
        "uploadDate": links.get("upload_date") or DATE_PENDING,
        "duration": iso_duration(seconds),
        "ownerUrl": links.get("blog_url") or kit_links.OWNER_PENDING,
        "keyTakeaways": points,
        "chapters": [{"start": int(round(start)), "label": publish_kit.clean(label)} for start, label in chapters],
        "transcript": transcript,
        "transcriptSource": source,
    }


def render(entry: dict, job: str, fallback: bool) -> str:
    body = json.dumps(entry, indent=2, ensure_ascii=False)
    if fallback:
        body = body.replace('\n  "keyTakeaways": [', f'\n{FALLBACK_NOTE}\n  "keyTakeaways": [', 1)
    return (f"// VIDEO_LIBRARY entry for job {job}. Paste at the top of VIDEO_LIBRARY in my-sites\n"
            f"// packages/ui/src/video-library.ts (newest first), in a Money Maker session.\n"
            f"// Until upload: id ({kit_links.ID_PENDING}) and uploadDate ({DATE_PENDING}), fv.py links --youtube --uploaded.\n"
            f"// Until the article is live: ownerUrl ({kit_links.OWNER_PENDING}, fv.py bloglink fills it).\n"
            f"{body},\n")


def problems(entry: dict, fallback: bool) -> list[str]:
    found = []
    if fallback:
        found.append("no youtube.takeaways: the library entry uses the flagged first-sentence fallback")
    elif not TAKEAWAYS[0] <= len(entry["keyTakeaways"]) <= TAKEAWAYS[1]:
        found.append(f"youtube.takeaways has {len(entry['keyTakeaways'])}, the library wants 3 to 5")
    return found
