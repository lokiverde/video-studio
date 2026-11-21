"""Format routing: one publishing decision per video, from the real rendered length.

  under 120 s    SHORT     9:16 as a public Short. With a companion article, the 16:9 also
                           goes up Unlisted, only for the blog embed. Never a public 16:9.
  120 to 180 s   JUDGMENT  Tony's call before upload. Recommends long-form when the
                           kit has chapters, a Short when the video answers one question.
  over 180 s     LONG      public 16:9 + the Test & compare thumbnail set + Shorts.

Evidence (2026-10-22): same title, same clip, the vertical far outdrew the
16:9 in an Incognito test. YouTube Shorts run to 180 seconds since 2024-10-15 and must be square or vertical.

The kit writers call write() after a render (fv.py finish and kit, th.py render and kit,
which covers the countdown and army flows). It prints one ROUTE: line, writes out/route.md
and keeps the inputs in state.json so a new article link can re-decide it. Shorts-only
formats (archive-reel, surf-reel, storyboard-reel, tribute-reel) never call it.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import common

SHORT_UNDER_S = 120
SHORT_MAX_S = 180          # still a legal Short at exactly 180
SHORTS_ONLY = frozenset({"archive-reel", "surf-reel", "storyboard-reel", "tribute-reel"})
FINALS = ("final_16x9.mp4", "final_16x9_music.mp4", "final_9x16.mp4", "final_9x16_music.mp4")
RELATED_VIDEO = ("After each Short is up: YouTube Studio > the Short > Related video > this video. "
                 "By hand, there is no API for it.")


@dataclass(frozen=True)
class Route:
    kind: str                      # SHORT, JUDGMENT or LONG
    seconds: float
    has_article: bool
    chapters: int
    fmt: str
    recommend: str | None = None   # JUDGMENT only: SHORT or LONG
    reason: str = ""
    steps: tuple[str, ...] = ()


def _short_steps(has_article: bool) -> tuple[str, ...]:
    steps = ["Upload final_9x16.mp4 to YouTube as a public Short."]
    if has_article:
        steps.append("Upload final_16x9.mp4 as Unlisted, only for the companion article's embed.")
    steps += ["Never publish the 16:9 as a public video: under 120 seconds it is dead weight on the channel.",
              "No Test & compare thumbnail set (there is no public 16:9). Ignore the KIT thumbnail line."]
    return tuple(steps)


def _long_steps() -> tuple[str, ...]:
    return ("Upload final_16x9.mp4 to YouTube as a public video.",
            "Thumbnail Test & compare set: yt_thumb.py --job <job>, then A, B and C in Studio.",
            "Cut 2 to 3 Shorts with th_shorts.py (sheet, approve, cut).",
            RELATED_VIDEO)


def decide(seconds: float, has_article: bool, fmt: str = "faceless", chapters: int = 1) -> Route:
    """The route for a video of this real length. Pure."""
    base = {"seconds": round(float(seconds), 1), "has_article": bool(has_article),
            "chapters": int(chapters), "fmt": fmt}
    if fmt in SHORTS_ONLY:
        note = "9:16-only format: a Short, no thumbnail set."
        if seconds > SHORT_MAX_S:
            note += f" Over {SHORT_MAX_S} s, YouTube will not treat it as a Short."
        return Route("SHORT", reason=note, steps=(note,), **base)
    if seconds < SHORT_UNDER_S:
        return Route("SHORT", reason=f"under {SHORT_UNDER_S} s", steps=_short_steps(has_article), **base)
    if seconds <= SHORT_MAX_S:
        recommend = "LONG" if chapters > 1 else "SHORT"
        reason = (f"it has {chapters} chapters, so it reads as long-form" if recommend == "LONG"
                  else "it answers one question (one chapter), so it works as a Short")
        steps = ("Tony decides before upload.",
                 "If SHORT: " + " ".join(_short_steps(has_article)),
                 "If LONG: " + " ".join(_long_steps()))
        return Route("JUDGMENT", recommend=recommend, reason=reason, steps=steps, **base)
    return Route("LONG", reason=f"over {SHORT_MAX_S} s", steps=_long_steps(), **base)


def route_line(route: Route) -> str:
    head = f"ROUTE: {route.kind} ({route.seconds:.0f}s)"
    if route.kind == "JUDGMENT":
        return f"{head}. Recommend {route.recommend}: {route.reason}. Tony decides before upload."
    if route.kind == "LONG":
        return f"{head}. Public 16:9 + Test & compare thumbnail set + Shorts."
    if route.fmt in SHORTS_ONLY:
        return f"{head}. {route.reason}"
    extra = " + 16:9 Unlisted for the article embed" if route.has_article else ", no 16:9 upload"
    return f"{head}. 9:16 public Short{extra}."


def route_markdown(route: Route, source: str, job: str = "<job>") -> str:
    article = "yes" if route.has_article else "no (no links.json blog_url, no out/blog.md)"
    steps = "\n".join(f"- {s}" for s in route.steps).replace("<job>", job)
    return (f"{route_line(route)}\n\n"
            f"# Format route\n\n"
            f"Measured length: {route.seconds:.1f} s ({source}, ffprobe). Chapters in the kit: "
            f"{route.chapters}. Companion article: {article}.\n\n"
            f"{steps}\n\n"
            f"Rules: under {SHORT_UNDER_S} s a Short, {SHORT_UNDER_S} to {SHORT_MAX_S} s Tony's call, "
            f"over {SHORT_MAX_S} s long-form. See SKILL.md \"Format routing\".\n")


# ---------- the wrapper the kit writers call ----------

def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def final_video(jdir: Path) -> Path | None:
    out = Path(jdir) / "out"
    return next((out / name for name in FINALS if (out / name).exists()), None)


def has_article(jdir: Path) -> bool:
    import kit_links
    return bool(kit_links.load(jdir).get("blog_url")) or (Path(jdir) / "out" / "blog.md").exists()


def _publish(jdir: Path, route: Route, source: str) -> Route:
    print(f"[route] {route_line(route)}")
    (Path(jdir) / "out" / "route.md").write_text(route_markdown(route, source, Path(jdir).name))
    common.set_state(str(jdir), route={"kind": route.kind, "seconds": route.seconds, "chapters": route.chapters,
                                       "fmt": route.fmt, "source": source})
    return route


def write(jdir: Path, chapters: int, fmt: str, seconds: float | None = None) -> Route | None:
    """Decide from the real final, print the ROUTE: line, write out/route.md. None (and a
    note) when nothing has been rendered yet."""
    final = final_video(jdir)
    if seconds is None:
        if not final:
            print("[route] no final render yet: the route is decided after render")
            return None
        seconds = probe_seconds(final)
    source = final.name if final else "given length"
    return _publish(jdir, decide(seconds, has_article(jdir), fmt, chapters), source)


def redecide(jdir: Path) -> Route | None:
    """Same inputs as the last write(), fresh companion-article check. None when the kit
    never routed this job."""
    saved = common.get_state(str(jdir)).get("route")
    if not saved:
        return None
    route = decide(saved["seconds"], has_article(jdir), saved.get("fmt", "faceless"), saved.get("chapters", 1))
    return _publish(jdir, route, saved.get("source", "final"))


def recorded_kind(jdir: Path) -> str | None:
    """The route kind the kit last decided for this job, if any."""
    try:
        state = json.loads((Path(jdir) / "state.json").read_text())
    except (OSError, ValueError):
        return None
    return (state.get("route") or {}).get("kind")
