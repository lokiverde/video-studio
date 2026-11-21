#!/usr/bin/env python3
"""Cut standalone YouTube Shorts / TikTok / Reels from a finished talking-head video.

Each Short is one strong section of the 9:16 final, with a hook banner over the first
seconds. Segments are written as spoken phrases in job.json and resolved against the
burned-in captions, so cuts land on caption boundaries:

    "shorts": [
      {"start": "Under state law, a no-fault move-out", "end": "belongs in your offer",
       "hook": "OGDENVILLE MOVE-OUT: $10,500", "title": "...",
       "description": "One or two sentences in Tony's voice. Bill numbers go here."}
    ]

An optional "tail" (seconds, 0 to 4) keeps picture past the last word, e.g. a faceless
video's ending hold.

  th_shorts.py sheet <job>     resolve segments, write work/shorts_sheet.jpg for Tony
  th_shorts.py approve <job>   record Tony's go (only after he says so in chat)
  th_shorts.py cut <job>       blocked until approved; writes out/short_<n>.mp4 + shorts.md
  th_shorts.py kit <job>       rewrite out/shorts.md (title + description per Short)

shorts.md is paste-ready: the same description works on YouTube Shorts, TikTok and Reels
(no #Shorts tag; YouTube detects vertical video under 3 minutes on its own). Title and
description edits never void the cut approval; start, end and hook do. With an article URL
in links.json (fv.py bloglink) it is the first line of every description, and when the main
video routed long-form each Short carries the Studio related-video reminder.

Length: 15 to 180 seconds (YouTube's Shorts limit since 2024-10-15). the scheduler caps uploads at
50 MiB, which at the cutter's 4 to 6 Mbps holds about 70 to 95 seconds, so longer Shorts warn.

Frame 1 (2026-11-14): each Short can open on its own "opener" card (number, photo, receipt...)
and set its own "banner" look; `sheet` and `cut` print FIRST FRAME warnings (lead-in words,
long hooks, no opener, two neighbors opening the same way). `cut` also writes
out/short_<n>_cover.jpg, frame 1 as a still, for the custom Shorts thumbnail. See shorts_opener.py.

Editing the shorts block voids the approval. It never touches the main render approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common
import publish_kit
import shorts_opener

FONT_PATH = common.ROOT / "assets/fonts/DejaVuSans-Bold.ttf"
SOURCE = "final_9x16_music.mp4"
FALLBACK_SOURCE = "final_9x16.mp4"
W, H = 1080, 1920
HOOK_SECONDS = 3.0
HOOK_TOP = 290          # sits over the chapter tag the main video shows up top
ACCENT = "#FACC15"
# Hook banner looks. The split (quiz tips) layout uses Brokerage blue with a light blue
# outline, same as its numbers (Tony, 2026-10-14). Everything else keeps the yellow.
# Per-series looks (2026-11-14): one yellow on every Short made the channel grid read as one
# video. A job sets "shorts_banner", a Short sets "banner"; "none" when the opener card is the hook.
BANNERS = {
    "default": {"fill": ACCENT, "text": "#0F172A", "border": None},
    "brokerage": {"fill": "#1d3557", "text": "#FFFFFF", "border": "#29a8d6"},
    "red": {"fill": "#DC2626", "text": "#FFFFFF", "border": None},
    "orange": {"fill": "#F97316", "text": "#0B0B0F", "border": None},
    "green": {"fill": "#16A34A", "text": "#FFFFFF", "border": None},
    "none": None,
}
BANNER_BORDER = 8
BANNER_H = 190           # tall enough to hide the panel heading or chapter tag under it
BANNER_MIN_W = 900
MIN_S, MAX_S = 15, 180
POSTDECK_MAX_BYTES = 50 * 1024 * 1024   # the scheduler's upload cap, hard-coded in several places there
MAX_TAIL = 4.0
FADE_IN, FADE_OUT = 0.15, 0.4
TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _seconds(stamp: str) -> float:
    h, m, s, ms = TIME_RE.match(stamp.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = lines[1].split("-->")
        cues.append((_seconds(start), _seconds(end), " ".join(lines[2:])))
    return cues


def _norm(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("-", " ")).split()


def _find(words: list[tuple[str, int]], phrase: str, after: int = 0) -> tuple[int, int]:
    """Index of the first and last matched word of phrase, searching from word `after`."""
    target = _norm(phrase)
    tokens = [w for w, _ in words]
    for i in range(after, len(tokens) - len(target) + 1):
        if tokens[i:i + len(target)] == target:
            return i, i + len(target) - 1
    raise ValueError(f"phrase not found in captions: '{phrase}'")


def resolve(cues, start_phrase: str, end_phrase: str) -> tuple[float, float]:
    """Start of the cue holding the first word, end of the cue holding the last word."""
    words = [(w, idx) for idx, (_, _, text) in enumerate(cues) for w in _norm(text)]
    first, _ = _find(words, start_phrase)
    try:
        _, last = _find(words, end_phrase, after=first)
    except ValueError:
        _find(words, end_phrase)  # re-raises "not found" if it is missing entirely
        raise ValueError(f"end phrase '{end_phrase}' comes before the start phrase")
    return cues[words[first][1]][0], cues[words[last][1]][1]


def check_length(start: float, end: float) -> list[str]:
    length = end - start
    if length > MAX_S:
        return [f"{length:.0f}s is over {MAX_S}s; YouTube only treats vertical video up to 3 minutes as a Short"]
    if length < MIN_S:
        return [f"{length:.0f}s is under {MIN_S}s; too thin to stand alone"]
    return []


def size_problems(n_bytes: float) -> list[str]:
    if n_bytes > POSTDECK_MAX_BYTES:
        return [f"about {n_bytes / 1048576:.0f} MiB, over the scheduler's 50 MiB upload cap: post it by hand or re-encode"]
    return []


def bitrate(path: Path) -> float:
    """Overall bits per second of a video file, 0 when ffprobe cannot say."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out.replace(".", "", 1).isdigit() else 0.0


def load(job_id: str):
    jdir = common.job_dir(job_id)
    job = json.loads((jdir / "job.json").read_text())
    shorts = job.get("shorts") or []
    if not shorts:
        common.die('job.json has no "shorts" block')
    cues = parse_srt((jdir / "out" / "transcript.srt").read_text())
    source = jdir / "out" / SOURCE
    if not source.exists():
        source = jdir / "out" / FALLBACK_SOURCE
    resolved = []
    for n, short in enumerate(shorts, 1):
        start, end = resolve(cues, short["start"], short["end"])
        tail = min(max(float(short.get("tail", 0)), 0.0), MAX_TAIL)
        name = shorts_opener.banner_name(short, job)
        if name not in BANNERS:
            raise ValueError(f"short #{n}: unknown banner '{name}' (use one of {', '.join(BANNERS)})")
        resolved.append({**short, "n": n, "from": start, "to": end + tail, "banner": BANNERS[name]})
    return jdir, source, shorts, resolved


def banner_for(job: dict) -> dict:
    return BANNERS[shorts_opener.banner_name({}, job)]


def opener_card(jdir: Path, s: dict) -> Path | None:
    """Full-frame card for the Short's first seconds, in the banner's color when it has one."""
    accent = (s["banner"] or BANNERS["default"])["fill"]
    (jdir / "work").mkdir(exist_ok=True)
    return shorts_opener.opener_png(s.get("opener"), jdir, jdir / "work" / f"_opener_{s['n']}.png", accent)


def report_lint(shorts: list) -> None:
    for n, warning in shorts_opener.lint(shorts):
        print(f"[shorts] #{n} FIRST FRAME: {warning}")


def hook_png(text: str, path: Path, top: int = HOOK_TOP, banner: dict | None = BANNERS["default"]) -> Path:
    """Transparent 1080x1920 overlay: one accent banner near the top. A short can set
    "hook_top" when its opening panel has content where the banner normally sits.
    No banner (or no text) gives a clear overlay."""
    image = Image.new("RGBA", (W, H))
    if banner is None or not text.strip():
        image.save(path)
        return path
    draw = ImageDraw.Draw(image)
    size = 76
    face = ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)
    while draw.textlength(text, font=face) > W - 140 and size > 40:
        size -= 4
        face = ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)
    width = draw.textlength(text, font=face)
    box_w = max(width + 60, BANNER_MIN_W)
    left = (W - box_w) / 2
    draw.rectangle([left, top, left + box_w, top + BANNER_H], fill=banner["fill"],
                   outline=banner["border"], width=BANNER_BORDER if banner["border"] else 0)
    draw.text(((W - width) / 2, top + (BANNER_H - size) / 2 - 6), text, font=face,
              fill=banner["text"])
    image.save(path)
    return path


def frame(source: Path, at: float, out: Path) -> Image.Image:
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-i", str(source),
                    "-frames:v", "1", str(out), "-y"], check=True)
    return Image.open(out).convert("RGBA")


def cmd_sheet(args) -> None:
    jdir, source, shorts, resolved = load(args.job)
    work = jdir / "work"
    work.mkdir(exist_ok=True)
    report_lint(shorts)
    tiles = []
    rate = bitrate(source)
    for s in resolved:
        warn = check_length(s["from"], s["to"]) + size_problems(rate * (s["to"] - s["from"]) / 8)
        print(f"[shorts] #{s['n']} {s['from']:.1f}-{s['to']:.1f} ({s['to'] - s['from']:.0f}s) "
              f"hook='{s['hook']}' {'  WARN ' + '; '.join(warn) if warn else ''}")
        overlay = Image.open(hook_png(s["hook"], work / f"_hook_{s['n']}.png", s.get("hook_top", HOOK_TOP), s["banner"]))
        card = opener_card(jdir, s)
        under = Image.open(card).convert("RGBA") if card else frame(source, s["from"] + 0.5, work / "_f.png")
        first = Image.alpha_composite(under, overlay)
        last = frame(source, max(s["from"], s["to"] - 1.0), work / "_f.png")
        tiles += [first.convert("RGB"), last.convert("RGB")]
    (work / "_f.png").unlink(missing_ok=True)
    thumb_w, thumb_h, pad = 270, 480, 8
    sheet = Image.new("RGB", (len(tiles) * (thumb_w + pad) + pad, thumb_h + 2 * pad), "white")
    for i, tile in enumerate(tiles):
        sheet.paste(tile.resize((thumb_w, thumb_h), Image.LANCZOS), (pad + i * (thumb_w + pad), pad))
    out = work / "shorts_sheet.jpg"
    sheet.save(out, quality=88)
    print(f"[shorts] sheet {out}  (pairs: first frame with opener and hook, last frame)")


VISUAL_KEYS = ("start", "end", "hook", "hook_top", "tail", "opener", "banner")


def fingerprint(shorts: list) -> str:
    """Only what changes the picture. Copy edits (title, description) never re-gate a cut."""
    visual = [{k: s[k] for k in VISUAL_KEYS if k in s} for s in shorts]
    return hashlib.sha256(json.dumps(visual, sort_keys=True).encode()).hexdigest()


def _hashtags(job: dict) -> str:
    tags = (job.get("youtube") or {}).get("hashtags") or []
    return " ".join(t if t.startswith("#") else f"#{t}" for t in tags)


def short_copy(short: dict, job: dict, footer: str) -> dict:
    """Paste-ready title and description for one Short (YouTube, TikTok, Reels).
    A `standalone` Short is the whole job, with no long episode to point back to."""
    yt = job.get("youtube") or {}
    episode = yt.get("title") or job.get("title", "")
    if short.get("standalone"):
        link = None
    elif yt.get("url"):
        link = f"Full episode: {yt['url']}"
    else:
        link = f"Full episode on the channel: {episode}"
    lead = short.get("description") or f"From the full episode: {episode}."
    parts = [publish_kit.clean(lead), link, _hashtags(job), publish_kit.clean(footer)]
    return {"title": short.get("title", "").strip(),
            "description": "\n\n".join(p for p in parts if p)}


def copy_problems(short: dict) -> list[str]:
    problems = []
    title = short.get("title", "")
    if not title.strip() or len(title) > 100:
        problems.append(f"title must be 1 to 100 characters (has {len(title)})")
    if any("\u2014" in short.get(k, "") for k in ("title", "description", "hook")):
        problems.append("em dash in title, description or hook")
    return problems


def _no_dashes(text: str) -> str:
    """House rule for every kit file: em and en dashes become a comma, line breaks stay."""
    return re.sub(r"[ \t]*[\u2014\u2013][ \t]*", ", ", text)


RELATED_NOTES = {
    "LONG": "Studio, by hand (no API): set this Short's related video to the full episode.",
    "JUDGMENT": "If the main video goes up long-form: set this Short's related video to it in Studio, by hand.",
}


def write_kit(job_id: str) -> Path:
    import format_route                   # lazy: only the kit needs the route, links and title rules
    import kit_links
    import lanes
    import title_lint
    jdir = common.job_dir(job_id)
    job = json.loads((jdir / "job.json").read_text())
    blog = kit_links.load(jdir).get("blog_url")
    related = RELATED_NOTES.get(format_route.recorded_kind(jdir))
    footer = lanes.footer_for(lanes.job_lane(jdir, job), common.load_config(), job, lanes.job_signer(jdir, job))
    lines = [f"# Shorts: {job.get('title', job_id)}\n",
             "Same description for YouTube Shorts, TikTok and Reels.\n"]
    for n, short in enumerate(job.get("shorts") or [], 1):
        for problem in copy_problems(short):
            print(f"[shorts] #{n} WARN {problem}")
        for warning in title_lint.lint(short.get("title", ""), short=True):
            print(f"[shorts] #{n} TITLE: {warning}")
        copy = short_copy(short, job, footer)
        description = kit_links.with_blog_line(_no_dashes(copy["description"]), blog)
        cover_file = shorts_opener.cover_name(n)
        cover = (f"\nCustom thumbnail: {cover_file} (desktop Studio, same image as frame 1)\n"
                 if (jdir / "out" / cover_file).exists() else "")
        lines.append(f"\n## short_{n}.mp4\n\nTitle:\n```\n{_no_dashes(copy['title'])}\n```\n\n"
                     f"Description:\n```\n{description}\n```\n{cover}" + (f"\n{related}\n" if related else ""))
    out = jdir / "out" / "shorts.md"
    out.write_text("".join(lines))
    print(f"[shorts] {out}")
    return out


def cmd_kit(args) -> None:
    write_kit(args.job)


def cmd_approve(args) -> None:
    _, _, shorts, _ = load(args.job)
    common.set_state(args.job, shorts_approved=fingerprint(shorts),
                     shorts_approved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"[shorts] approved {args.job}. Editing the shorts block voids this.")


def cmd_cut(args) -> None:
    jdir, source, shorts, resolved = load(args.job)
    if common.get_state(args.job).get("shorts_approved") != fingerprint(shorts):
        common.die("[shorts] not approved (or edited since). Show Tony the sheet first.")
    report_lint(shorts)
    for s in resolved:
        length = s["to"] - s["from"]
        overlay = hook_png(s["hook"], jdir / "work" / f"_hook_{s['n']}.png", s.get("hook_top", HOOK_TOP), s["banner"])
        out = jdir / "out" / f"short_{s['n']}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{s['from']:.3f}", "-t", f"{length:.3f}",
                        "-i", str(source), "-i", str(overlay), *opener_args(jdir, s, length),
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                        str(out), "-y"], check=True)
        cover = jdir / "out" / shorts_opener.cover_name(s["n"])
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.05", "-i", str(out), "-frames:v", "1",
                        "-q:v", "2", str(cover), "-y"], check=True)
        print(f"[shorts] {out.name}  {length:.0f}s  {out.stat().st_size // 1024 // 1024}MB  cover {cover.name}")
        for problem in size_problems(out.stat().st_size):
            print(f"[shorts] {out.name} WARN {problem}")
    write_kit(args.job)


def opener_args(jdir: Path, s: dict, length: float) -> list[str]:
    """Extra input and the filter graph: opener card (if any) first, then the hook banner."""
    card = opener_card(jdir, s)
    fade = f"fade=t=out:st={length - FADE_OUT:.3f}:d={FADE_OUT}[v];"
    audio = f"[0:a]afade=t=in:d={FADE_IN},afade=t=out:st={length - FADE_OUT:.3f}:d={FADE_OUT}[a]"
    if not card:
        return ["-filter_complex", f"[0:v][1:v]overlay=0:0:enable='lt(t,{HOOK_SECONDS})',{fade}{audio}"]
    hold = shorts_opener.opener_seconds(s.get("opener"))
    return ["-loop", "1", "-t", f"{hold:.3f}", "-i", str(card), "-filter_complex",
            f"[2:v]scale={W}:{H},setsar=1,format=yuv420p[card];"
            f"[0:v][card]overlay=0:0:eof_action=pass:enable='lt(t,{hold:.3f})'[o];"
            f"[o][1:v]overlay=0:0:enable='lt(t,{HOOK_SECONDS})',{fade}{audio}"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("sheet", cmd_sheet), ("approve", cmd_approve), ("cut", cmd_cut),
                     ("kit", cmd_kit)):
        p = sub.add_parser(name)
        p.add_argument("job")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as err:
        print(f"[shorts] {err}", file=sys.stderr)
        sys.exit(1)
