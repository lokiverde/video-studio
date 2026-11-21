"""The few things that differ between macOS, Windows and Linux, in one place.

Everything else in the pipeline is Python, ffmpeg and Node, which behave the same on all
three. Callers ask this module instead of hard-coding a Mac path or command.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ~/video-studio holds the local model venvs (transcription, voice cleanup) and the relay files.
STUDIO_HOME = Path.home() / "video-studio"


def venv_bin(venv: Path, name: str) -> Path:
    """A program inside a virtualenv: venv/bin/name on macOS and Linux, venv\\Scripts\\name.exe on Windows."""
    if IS_WINDOWS:
        return Path(venv) / "Scripts" / (name if name.lower().endswith(".exe") else name + ".exe")
    return Path(venv) / "bin" / name


def venv_python(venv: Path) -> Path:
    """The Python interpreter of a virtualenv on this OS."""
    return venv_bin(venv, "python")


def studio_venv(name: str) -> Path:
    """One of the studio's local model venvs, e.g. studio_venv("parakeet") -> ~/video-studio/.venv-parakeet."""
    return STUDIO_HOME / f".venv-{name}"


# Where Windows keeps its fonts (C:\\Windows\\Fonts on a normal install).
WIN_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
BUNDLED_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def pick_font(*candidates: str | Path, fallback: str | Path) -> str:
    """The first font file that exists, else the fallback (a font that ships in assets/fonts)."""
    for c in candidates:
        if c and Path(c).expanduser().exists():
            return str(Path(c).expanduser())
    return str(fallback)


def pick_font_face(*candidates: tuple[str | Path, int], fallback: tuple[str | Path, int]) -> tuple[str, int]:
    """Like pick_font for (path, face index) pairs, since a .ttc holds several faces."""
    for path, index in candidates:
        if path and Path(path).expanduser().exists():
            return str(Path(path).expanduser()), index
    return str(fallback[0]), fallback[1]


def heavy_font(mac: str) -> str:
    """A heavy display face: the named macOS font, Arial Black or Impact on Windows, the bundled Anton elsewhere."""
    return pick_font(mac, WIN_FONTS / "ariblk.ttf", WIN_FONTS / "impact.ttf",
                     "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", fallback=BUNDLED_FONTS / "Anton-Regular.ttf")


def tool(name: str, folder: str | Path | None = None) -> str:
    """The full path of a command-line tool such as npx. On Windows npx and npm are .cmd shims
    that subprocess cannot find by bare name, so look for name, name.cmd and name.exe. With a
    folder, look only there; without one, on PATH. Falls back to the plain name or path."""
    if folder is not None:
        for candidate in (name, name + ".cmd", name + ".exe"):
            if (Path(folder) / candidate).exists():
                return str(Path(folder) / candidate)
        return str(Path(folder) / name)
    return shutil.which(name) or name


def clipboard_cmd() -> list[str] | None:
    """The command that puts stdin on the clipboard (pbcopy, clip, wl-copy or xclip), or None."""
    if IS_MAC:
        return ["pbcopy"]
    if IS_WINDOWS:
        return ["clip"]
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    return None


def open_cmd(url: str) -> list[str]:
    """The command that opens a link in the default browser."""
    if IS_MAC:
        return ["open", url]
    if IS_WINDOWS:
        return ["cmd", "/c", "start", "", url]
    return ["xdg-open", url]


def detached_low_priority(nice: int) -> dict:
    """subprocess.Popen keyword arguments that start a job detached from this terminal at
    low priority: a new session plus `nice` on macOS and Linux, a detached process group
    at below-normal priority on Windows."""
    if IS_WINDOWS:
        flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                 | getattr(subprocess, "DETACHED_PROCESS", 0x8)
                 | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000))
        return {"creationflags": flags}
    return {"start_new_session": True, "preexec_fn": lambda: os.nice(nice)}
