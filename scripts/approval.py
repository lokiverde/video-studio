"""The preview gate, shared by fv.py (faceless) and th.py (talking head).

Tony reviews the contact sheet and says go BEFORE anything renders. An approval is tied
to a fingerprint of exactly what the sheet showed, so editing the job file or rerolling
a still voids it until he has seen a fresh sheet. Only `--no-preview` (his explicit
waiver, or a fully unattended run) gets past the gate without an approval."""
import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple

# Only the inputs a contact sheet is built from. Files that finish/render produce later
# (captions, clips, narration, the sheets themselves) must not void an approval.
FACELESS_STILL = re.compile(r"^(p_)?scene_\d+(_\d+)?\.png$")
SOURCE_FOOTAGE = "footage.mp4"


# Publishing text is not something the contact sheet shows, so rewording a title or a
# description must not send Tony back through the preview gate.
NOT_VISUAL = ("youtube", "audio", "post", "thumbnail", "shorts")  # not on the main sheet; shorts carry their own gate


def _sha(path):
    path = Path(path)
    if path.name == "job.json":
        try:
            job = json.loads(path.read_text())
            visual = {k: v for k, v in job.items() if k not in NOT_VISUAL}
            return hashlib.sha256(json.dumps(visual, sort_keys=True).encode()).hexdigest()
        except (ValueError, AttributeError):
            pass  # not valid JSON yet: fall through and hash the raw bytes
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inputs(job_dir, kind):
    job_dir = Path(job_dir)
    if kind == "listing":
        # The sheets are drawn from the picks (photos, labels, music) and the listing facts.
        # The photos themselves live in Tony's Drive folder and are named in picks.json.
        return [job_dir / "picks.json", job_dir / "listing.json"]
    if kind == "archive-reel":
        # The sheet shows job.json's picture plus everything in public/ (composites, clips) and product/.
        files = [p for sub in ("public", "product") if (job_dir / sub).is_dir()
                 for p in sorted((job_dir / sub).glob("*")) if p.is_file()]
        return [job_dir / "job.json", *files]
    if kind == "storyboard-reel":
        # The sheet is drawn from job.json's picture, every file it names (plate, renders,
        # clips, logo, shirt, mockup) and the cutouts made from the renders.
        cuts = sorted((job_dir / "work" / "cut").glob("*.png")) if (job_dir / "work" / "cut").is_dir() else []
        return [job_dir / "job.json", *_named_files(job_dir), *cuts]
    if kind == "talking-head":
        # Everything the sheet can show: the job file plus every b-roll still and clip.
        # The source footage is left out, it is large and never changes after `new`.
        # Subfolders count too: board style keeps its comment screenshots in public/receipts/.
        public = job_dir / "public"
        assets = sorted(p for p in public.rglob("*") if p.is_file() and p.relative_to(public).as_posix() != SOURCE_FOOTAGE) if public.is_dir() else []
        return [job_dir / "job.json", *assets]
    work = job_dir / "work"
    stills = sorted(p for p in work.glob("*.png") if FACELESS_STILL.match(p.name)) if work.is_dir() else []
    return [job_dir / "scenes.json", *stills, *_clip_files(job_dir)]


def _clip_files(job_dir):
    """The video files a faceless job's clip scenes name, absolute or inside the job folder.
    The sheet shows only a clip's first frame, so a new take with the same opening would
    otherwise slip past an approval. A job with no clips adds nothing, so its fingerprint
    is the same as before clip scenes existed."""
    try:
        scenes = json.loads((Path(job_dir) / "scenes.json").read_text()).get("scenes") or []
    except (OSError, ValueError, AttributeError):
        # Same stance as _named_files: scenes.json is hashed byte for byte anyway, and a
        # file that cannot be parsed cannot render, so there is no clip to approve.
        return []
    found = []
    for scene in scenes:
        ref = scene.get("clip") if isinstance(scene, dict) else None
        if not isinstance(ref, str) or not ref.strip():
            continue
        path = Path(ref).expanduser()
        path = path if path.is_absolute() else Path(job_dir) / path
        if path.is_file() and path not in found:
            found.append(path)
    return found


def _named_files(job_dir):
    """Existing files named anywhere in the visual part of job.json, resolved against the
    job folder first and the pipeline root second (shared music, fonts, shirt photos)."""
    try:
        job = json.loads((Path(job_dir) / "job.json").read_text())
    except (OSError, ValueError):
        return []
    root = Path(__file__).resolve().parent.parent
    found = []

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str) and "/" in value and "://" not in value and len(value) < 300:
            for base in (Path(job_dir), root):
                path = base / value
                if path.is_file():
                    if path not in found:
                        found.append(path)
                    break

    walk({k: v for k, v in job.items() if k not in NOT_VISUAL})
    return found


def _label(job_dir, path):
    """A file's name in the fingerprint: its bare name, or its path under public/ when it sits
    in a subfolder. Top-level names are unchanged, so older approvals still match."""
    public = Path(job_dir) / "public"
    if path.parent != public and public in path.parents:
        return path.relative_to(public).as_posix()
    return path.name


def fingerprint(job_dir, kind):
    digest = hashlib.sha256()
    for path in _inputs(job_dir, kind):
        if path.exists():
            digest.update(f"{_label(job_dir, path)}:{_sha(path)}\n".encode())
    return digest.hexdigest()


def can_approve(state, current):
    """None when the job can be approved, otherwise the reason it cannot."""
    shown = state.get("sheet_fingerprint")
    if not shown:
        return "no contact sheet has been made for this job, make one and show Tony first"
    if shown != current:
        return "the contact sheet is stale (the job changed after it was made), make a fresh one and show Tony"
    return None


def gate(state, current, waived=False):
    """None when rendering may start, otherwise the reason it may not."""
    if waived:
        return None
    approved = state.get("approved_fingerprint")
    if not approved:
        return "this job has not been approved. Show Tony both contact sheets, wait for his go, then run `approve`"
    if approved != current:
        return "the job changed since Tony approved it. Make fresh contact sheets, show him, and approve again"
    return None


def sheet_is_stale(sheet_mtime, input_mtimes):
    return sheet_mtime is None or any(m > sheet_mtime for m in input_mtimes)


def _changed_at(path, clips):
    """When an input last changed. A take copied in with its dates kept (cp -p,
    shutil.copy2) carries an old mtime, but its ctime still moves when the file is
    replaced, so a swapped clip always counts as newer than the sheet."""
    stat = path.stat()
    return max(stat.st_mtime, stat.st_ctime) if path in clips else stat.st_mtime


class Sheet(NamedTuple):
    """A faceless contact sheet: its file, the prefix of the stills it is tiled from, its
    name in messages, and whether every job must have one."""
    file: str
    prefix: str
    label: str
    always: bool


# make writes the portrait stills after the 16:9 sheet, so each sheet is judged only
# against its own stills (plus scenes.json and the clips, which both sheets show).
FACELESS_SHEETS = (Sheet("contact_sheet.jpg", "scene_", "contact sheet", always=True),
                   Sheet("contact_sheet_9x16.jpg", "p_scene_", "9:16 contact sheet", always=False))


def _shown_on(job_dir, sheet):
    """The existing inputs one faceless sheet shows: scenes.json, the clips, its stills."""
    work = Path(job_dir) / "work"

    def belongs(path):
        is_still = path.parent == work and FACELESS_STILL.match(path.name)
        return not is_still or path.name.startswith(sheet.prefix)

    return [p for p in _inputs(job_dir, "faceless") if p.exists() and belongs(p)]


def faceless_sheet_problem(job_dir):
    """Faceless sheets are rebuilt from several code paths, so freshness is read from the
    files: each sheet must be newer than scenes.json, the clips and every still it was
    tiled from. The 16:9 sheet must exist; the 9:16 one must once portrait stills do."""
    job_dir = Path(job_dir)
    clips = set(_clip_files(job_dir))
    for sheet in FACELESS_SHEETS:
        path = job_dir / "work" / sheet.file
        shown = _shown_on(job_dir, sheet)
        if not path.exists():
            if sheet.always or any(p.name.startswith(sheet.prefix) for p in shown):
                return f"no {sheet.label} has been made for this job, make one and show Tony first"
            continue
        if sheet_is_stale(path.stat().st_mtime, [_changed_at(p, clips) for p in shown]):
            return f"the {sheet.label} is stale (scenes.json or a still changed after it was made), rebuild it and show Tony"
    return None
