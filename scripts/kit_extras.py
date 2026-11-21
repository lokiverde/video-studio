"""What every kit run adds after the classic three files (transcript.txt, transcript.srt,
youtube.md): title warnings, the format route (out/route.md) and the ready-to-paste
VIDEO_LIBRARY entry (out/video_library_entry.txt). Shared by publish_kit (faceless) and
th.py write_kit (talking-head, countdown, army). All of it is advice for Tony: nothing here
blocks a kit, uploads or edits a title.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import format_route
import kit_links
import library_entry
import title_lint


def run(jdir: Path, fmt: str, meta: dict, chapters, transcript: list[str], authored_takeaways,
        fallback_texts: list[str], source: str, tag: str = "[kit]") -> format_route.Route | None:
    jdir = Path(jdir)
    for warning in title_lint.lint(meta["title"]):
        print(f"{tag} TITLE: {warning}")
    final = format_route.final_video(jdir)
    if not final:
        print(f"{tag} no final render yet: route.md and video_library_entry.txt are written after render")
        return None
    try:
        seconds = format_route.probe_seconds(final)
    except (subprocess.CalledProcessError, ValueError, OSError) as err:
        print(f"{tag} could not measure {final.name} ({type(err).__name__}): no route.md or library entry this run")
        return None
    route = format_route.write(jdir, len(chapters), fmt, seconds)
    points, fallback = library_entry.takeaways(authored_takeaways, fallback_texts)
    entry = library_entry.build(meta, seconds, chapters, transcript, points, source, kit_links.load(jdir))
    path = jdir / "out" / "video_library_entry.txt"
    path.write_text(library_entry.render(entry, jdir.name, fallback))
    for problem in library_entry.problems(entry, fallback):
        print(f"{tag} LIBRARY: {problem}")
    print(f"{tag} {path}")
    return route
