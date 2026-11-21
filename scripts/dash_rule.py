"""Tony's dash rule (2026-11-14), marked by hand in Finder:

- A folder whose name ends in "-" is done: everything in it is uploaded, so nothing updates
  or uploads from it again. ALLOW_DONE_FOLDER=1 opens one run, only when Tony names that
  folder and asks.
- A file whose name ends in "-" (clip-.mp4 or clip.mp4-) is never uploaded. No override:
  Tony takes the dash off if he changes his mind.

A dash in the middle of a name (final_9x16-preview.mp4) does not count.
"""
from __future__ import annotations   # the Mac mini runs /usr/bin/python3 3.9

import os
from pathlib import Path

OVERRIDE_ENV = "ALLOW_DONE_FOLDER"
READ_ONLY_COMMANDS = frozenset({"status", "save-theme"})


class DashRuleError(RuntimeError):
    """Raised instead of touching a dashed folder or uploading a dashed file."""


def skipped_file(path: Path) -> bool:
    name = Path(path).name
    return name.endswith("-") or Path(name).stem.endswith("-")


def done_folder(path: Path) -> Path | None:
    """The nearest folder at or above path whose name ends in "-", or None."""
    path = Path(path)
    folders = [path, *path.parents] if path.is_dir() else list(path.parents)
    return next((folder for folder in folders if folder.name.endswith("-")), None)


def override() -> bool:
    return os.environ.get(OVERRIDE_ENV) == "1"


def check_folder(path: Path) -> None:
    folder = done_folder(path)
    if folder is not None and not override():
        raise DashRuleError(
            f"{folder.name} ends in '-': Tony marked that folder done, so nothing in it gets "
            f"updated or uploaded. Only if he asked for this folder by name, rerun with "
            f"{OVERRIDE_ENV}=1.")


def check_upload(path: Path) -> None:
    if skipped_file(path):
        raise DashRuleError(f"{Path(path).name} ends in '-': Tony marked it skip, so it never "
                            f"gets uploaded. He takes the dash off to upload it.")
    check_folder(path)


def keep_uploads(paths: list[Path]) -> list[Path]:
    """The files that may go up, saying which dashed files were left out."""
    kept = []
    for path in paths:
        if skipped_file(path):
            print(f"[dash rule] skipped {Path(path).name}: name ends in '-', not uploaded")
        else:
            kept.append(path)
    return kept


def dashed_twin(path: Path) -> Path | None:
    """The dashed copy of an expected file (short_2-.mp4 or short_2.mp4-), if Tony made one."""
    path = Path(path)
    for twin in (path.with_name(f"{path.stem}-{path.suffix}"), path.with_name(f"{path.name}-")):
        if twin.exists():
            return twin
    return None


def guard_command(cmd: str, job: str | None, jobs_dir: Path) -> None:
    """Stop a command that would update a dashed job folder; reading one stays allowed."""
    if not job or cmd in READ_ONLY_COMMANDS:
        return
    folder = Path(job) if Path(job).is_absolute() else Path(jobs_dir) / job
    check_folder(folder)
