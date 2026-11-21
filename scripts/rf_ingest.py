"""rf ingest: bring a generated file back into a real-footage job.

Each file is checked with ffprobe, copied into rf/returns/ (the original is never edited
or moved), hashed, given a first-frame thumbnail for the contact sheet, and recorded as
one line of rf/ledger.jsonl. The video-engine skill runs this on every file it saves from
OpenArt and passes the model, creation id and quoted credits; a file Tony brings from
anywhere else is ledgered as provider "manual", with nothing guessed from the file.
Spec: docs/briefs/2026-10-24-realistic-footage.md, sections 5.2 and 5.3.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import common

ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
ARCHIVE_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c",
                 b"Rar!\x1a\x07", b"BZh", b"\xfd7zXZ\x00")
IMAGE_FORMATS = {"image2", "png_pipe", "jpeg_pipe", "webp_pipe"}
SHOT_KINDS = {"clip": "video", "still": "image"}
ASPECT_TOLERANCE = 0.02


class Media(NamedTuple):
    kind: str            # "video" or "image"
    width: int
    height: int
    duration_s: float | None
    fps: float | None
    has_audio: bool


def refuse(src, why):
    common.die(f"rf ingest: {src} {why}; nothing was ingested")


def is_archive(path):
    if path.suffix.lower() in ARCHIVE_SUFFIXES:
        return True
    with open(path, "rb") as fh:
        head = fh.read(512)
    return head.startswith(ARCHIVE_MAGIC) or head[257:262] == b"ustar"


def frame_rate(text):
    num, _, den = (text or "0/0").partition("/")
    if not den or float(den) == 0 or float(num) == 0:
        return None
    rate = float(num) / float(den)
    return int(rate) if rate.is_integer() else round(rate, 3)


def probe(path):
    """What the file holds, or None when ffprobe finds no picture in it."""
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_type,width,height,avg_frame_rate:format=format_name,duration",
                           "-of", "json", str(path)], capture_output=True, text=True)
    if proc.returncode:
        return None
    info = json.loads(proc.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video or not video.get("width"):
        return None
    fmt = info.get("format", {})
    if fmt.get("format_name") in IMAGE_FORMATS:
        return Media("image", int(video["width"]), int(video["height"]), None, None, False)
    duration = float(fmt["duration"]) if fmt.get("duration") else None
    return Media("video", int(video["width"]), int(video["height"]),
                 round(duration, 3) if duration else None, frame_rate(video.get("avg_frame_rate")),
                 any(s.get("codec_type") == "audio" for s in streams))


def target_aspect(shot, defaults):
    text = (shot.get("settings") or {}).get("aspect") or defaults.get("aspect")
    try:
        w, h = (float(n) for n in str(text).split(":"))
        return text, w / h
    except ValueError:
        return None, None


def check(src, shot, defaults):
    """Refuse anything that is not a picture this shot can use; warn on a shape mismatch.
    Paid output is never refused for its shape: the clip block crops it and says so."""
    if not src.is_file():
        refuse(src, "is not a file")
    if src.stat().st_size == 0:
        refuse(src, "is empty (0 bytes)")
    if is_archive(src):
        refuse(src, "is an archive; unpack it and ingest the video or image inside")
    media = probe(src)
    if media is None:
        refuse(src, "is not a video or image ffprobe can read")
    wanted = SHOT_KINDS.get(shot.get("kind"))
    if wanted and media.kind != wanted:
        refuse(src, f"is {'an' if media.kind == 'image' else 'a'} {media.kind}, but "
                    f"{shot['id']} is a {shot['kind']} shot")
    label, ratio = target_aspect(shot, defaults)
    if ratio and abs(media.width / media.height - ratio) > ASPECT_TOLERANCE * ratio:
        print(f"[rf] WARNING: {src.name} is {media.width}x{media.height}, not {label} like "
              f"{shot['id']}; it will be cropped hard in that cut")
    return media


def next_take(returns, shot_id, suffix):
    taken = [int(p.stem.rsplit("take", 1)[-1]) for p in returns.glob(f"{shot_id}_take*")
             if p.stem.rsplit("take", 1)[-1].isdigit()]
    return returns / f"{shot_id}_take{max(taken, default=0) + 1}{suffix}"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def thumb_path(take):
    return take.parent / "thumbs" / f"{take.stem}.jpg"


def thumbnail(take):
    thumb = thumb_path(take)
    thumb.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(take), "-frames:v", "1",
                    "-vf", "scale=480:-2", str(thumb)], check=True)
    return thumb


def stage(returns, shot_id, checked):
    """Copy and thumbnail every checked file. If any step fails, remove everything this
    run copied, so the batch lands whole or not at all."""
    staged = []
    try:
        for src, media in checked:
            take = next_take(returns, shot_id, src.suffix.lower())
            staged.append(take)
            shutil.copy2(src, take)
            thumbnail(take)
    except (OSError, subprocess.CalledProcessError) as err:
        unstage(staged)
        common.die(f"rf ingest: copying {src.name} into the job failed ({err}); nothing was ingested")
    return staged


def unstage(staged):
    for take in staged:
        take.unlink(missing_ok=True)
        thumb_path(take).unlink(missing_ok=True)


def load_record(path, creation):
    """The engine's saved evidence for one OpenArt call (the creation record, raw or under
    "creation", plus its quote and balances). It must name the creation it came from."""
    if not creation:
        common.die("rf ingest: --record is the evidence for one OpenArt call; pass its --creation id "
                   "with it; nothing was ingested")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", creation):
        common.die(f"rf ingest: creation id {creation!r} cannot name a record file; nothing was ingested")
    src = Path(path)
    try:
        record = json.loads(src.read_text(encoding="utf-8"))
    except FileNotFoundError:
        common.die(f"rf ingest: no such record {src}; nothing was ingested")
    except (OSError, ValueError) as err:
        common.die(f"rf ingest: {src} is not a JSON record ({err}); nothing was ingested")
    inner = record.get("creation") if isinstance(record, dict) else None
    named = (record.get("historyId") if isinstance(record, dict) else None) or \
        (inner.get("historyId") if isinstance(inner, dict) else None)
    if not named:
        common.die(f"rf ingest: {src} names no historyId, so it is not a creation record; "
                   "nothing was ingested")
    if named != creation:
        common.die(f"rf ingest: {src} is the record of creation {named}, not {creation}; "
                   "nothing was ingested")
    return src


def record_home(job_dir, creation, src):
    """Where a creation's record is kept. One creation keeps one record: the same record
    again is fine, a different one is refused so earlier ledger lines keep their evidence."""
    kept = job_dir / "rf" / "openart" / f"{creation}.json"
    if kept.is_file() and kept.read_bytes() != src.read_bytes():
        common.die(f"rf ingest: the job already keeps a different record for creation {creation} "
                   f"({kept.relative_to(job_dir).as_posix()}); nothing was ingested")
    return kept


def keep_record(job_dir, kept, src, staged):
    """Copy the record byte for byte; if that fails, take the staged files back out."""
    try:
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, kept)
    except OSError as err:
        unstage(staged)
        common.die(f"rf ingest: keeping the record {src.name} failed ({err}); nothing was ingested")
    return kept.relative_to(job_dir).as_posix()


def ingest(job_dir, data, shot, files, model=None, creation=None, credits=None, record=None):
    """Check every file, copy and thumbnail them all, and only then write the ledger, so
    one bad file in a batch ingests nothing. Returns the ledger lines written.

    Only the engine has an OpenArt creation id, so creation is what marks a file as
    OpenArt's; a model on its own is whatever Tony says it was (provider manual), and
    credits are OpenArt's quote for one call, never a figure for a manual file. record is
    the path of the engine's saved evidence for that call; it is kept in rf/openart/."""
    if credits is not None and not creation:
        common.die("rf ingest: --credits is OpenArt's quote for one call; pass the --creation id "
                   "with it, or leave both out for a file from anywhere else; nothing was ingested")
    record_src = load_record(record, creation) if record else None
    kept = record_home(job_dir, creation, record_src) if record_src else None
    defaults = data.get("defaults", {})
    checked = [(src, check(src, shot, defaults)) for src in files]
    returns = job_dir / "rf" / "returns"
    returns.mkdir(parents=True, exist_ok=True)
    takes = stage(returns, shot["id"], checked)
    record_file = keep_record(job_dir, kept, record_src, takes) if kept else None
    lines = []
    for (src, media), dest in zip(checked, takes):
        line = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "shot": shot["id"], "file": dest.relative_to(job_dir).as_posix(),
                "sha256": sha256(dest),
                "provider": defaults.get("provider", "openart") if creation else "manual",
                "model": model, "creation_id": creation,
                "resolution": f"{media.width}x{media.height}", "duration_s": media.duration_s,
                "fps": media.fps, "has_audio": media.has_audio,
                "prompt_sha256": hashlib.sha256((shot.get("prompt") or "").encode()).hexdigest(),
                "credits": int(credits) if credits is not None and float(credits).is_integer() else credits,
                "record": record_file, "approved": False}
        with open(job_dir / "rf" / "ledger.jsonl", "a") as fh:
            fh.write(json.dumps(line) + "\n")
        lines.append(line)
        print(f"[rf] {shot['id']}: {src.name} -> {line['file']} ({line['resolution']}, "
              f"{line['provider']})")
    return lines
