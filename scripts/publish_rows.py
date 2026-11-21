"""What a job posts and what each channel's caption says, for fv.py publish.

LONG route: every cut Short (out/short_N.mp4) plus the full 9:16 on Tony LI (row "L").
SHORT route: one row, the cut Short when there is one, else the 9:16 final itself; no
separate LinkedIn row, the Short is the whole video. Spec: docs/briefs/2026-10-29-auto-poster.md,
decisions 1, 14 and 18."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import dash_rule
import kit_links
import lanes
import publish_copy
import publish_kit
import th_shorts

FULL_9X16 = ("final_9x16_music.mp4", "final_9x16.mp4")
KEEP = ("dropped", "drop_channels", "add_channels", "pinned_at", "status", "posts", "media_url", "blotato_media", "at",
        "channels", "skipped", "times")


def load_job(jdir: Path) -> dict:
    for name in ("job.json", "scenes.json"):
        path = Path(jdir) / name
        if path.exists():
            return json.loads(path.read_text())
    return {}


def full_vertical(jdir: Path) -> Path | None:
    out = Path(jdir) / "out"
    return next((out / name for name in FULL_9X16 if (out / name).exists()), None)


def build(jdir: Path, job: dict, route: str, probe: Callable[[Path], float]) -> list[dict]:
    """Fresh rows for the job's files, in kit order. Missing cuts are reported, not invented."""
    out = Path(jdir) / "out"
    shorts = job.get("shorts") or []
    if route == "SHORT":
        source = out / "short_1.mp4" if (out / "short_1.mp4").exists() else full_vertical(jdir)
        if source is None:
            raise ValueError("SHORT route but no short_1.mp4 and no 9:16 final in out/")
        title = (shorts[0].get("title") if shorts else None) or (job.get("youtube") or {}).get("title") \
            or job.get("title", "")
        return [{"id": "1", "kind": "short", "file": source.name, "seconds": probe(source),
                 "title": title, "standalone": True}]
    rows = []
    for n, short in enumerate(shorts, 1):
        path = out / f"short_{n}.mp4"
        if not path.exists():
            twin = dash_rule.dashed_twin(path)
            if twin is not None:
                print(f"[publish] {twin.name} ends in '-': Tony marked it skip, left out")
            else:
                print(f"[publish] short_{n}.mp4 is not cut yet: left out (th_shorts.py cut first)")
            continue
        rows.append({"id": str(n), "kind": "short", "file": path.name, "seconds": probe(path),
                     "title": short.get("title", "")})
    full = full_vertical(jdir)
    if full is not None and (out / "linkedin.md").exists():
        rows.append({"id": "L", "kind": "linkedin_full", "file": full.name, "seconds": probe(full),
                     "title": "LinkedIn full video"})
    return rows


def merge(saved: list[dict], fresh: list[dict]) -> list[dict]:
    """Fresh rows in kit order carrying the saved edits and Blotato state by id. A saved row
    that already went out stays even when its file is gone, so --edit can still reach it."""
    by_id = {r["id"]: r for r in saved or []}
    merged = [{**row, **{k: by_id[row["id"]][k] for k in KEEP if k in by_id.get(row["id"], {})}}
              for row in fresh]
    fresh_ids = {r["id"] for r in fresh}
    return merged + [r for r in saved or [] if r["id"] not in fresh_ids and r.get("status")]


def job_view(job: dict, youtube_id: str | None) -> dict:
    """The job with the long video's URL filled in for the 'Full episode' line, without
    touching job.json (that would void a talking-head approval)."""
    yt = job.get("youtube") or {}
    if not youtube_id or yt.get("url"):
        return job
    return {**job, "youtube": {**yt, "url": kit_links.youtube_url(youtube_id)}}


def _hashtags(job: dict) -> str:
    tags = (job.get("youtube") or {}).get("hashtags") or []
    return " ".join(t if t.startswith("#") else f"#{t}" for t in tags)


def short_description(row: dict, job: dict, footer: str, youtube_id: str | None,
                      blog_url: str | None) -> str:
    """The same description the Shorts kit writes into shorts.md, with the blog line first."""
    if row.get("standalone"):
        yt = job.get("youtube") or {}
        shorts = job.get("shorts") or [{}]
        lead = shorts[0].get("description") or yt.get("description") or ""
        parts = [publish_kit.clean(lead), _hashtags(job), publish_kit.clean(footer)]
        description = "\n\n".join(p for p in parts if p)
    else:
        short = (job.get("shorts") or [])[int(row["id"]) - 1]
        description = th_shorts.short_copy(short, job_view(job, youtube_id), footer)["description"]
    return kit_links.with_blog_line(publish_copy.no_dashes(description), blog_url)


def copy_for(row: dict, channel: dict, jdir: Path, job: dict, lane: str, cfg: dict,
             youtube_id: str | None, blog_url: str | None, ai: bool, signer: str | None = None) -> dict:
    """{"text": ...} (plus "title" for YouTube) for one row on one channel. signer: the
    record's, whose license line the footer carries."""
    footer = lanes.footer_for(lane, cfg, job, signer)
    if row["kind"] == "linkedin_full":
        md = (Path(jdir) / "out" / "linkedin.md").read_text()
        return {"text": publish_copy.linkedin_full(md, footer, ai)}
    description = short_description(row, job, footer, youtube_id, blog_url)
    return publish_copy.for_platform(channel["platform"], row.get("title", ""), description, footer, ai,
                                     keep_footer=lanes.carries_dre(lane))
