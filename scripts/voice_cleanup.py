"""Echo cleanup for the cloned voice (voice=tony). Tony heard an echo on the Sacramento
Final Tally (2026-10-09): the Chatterbox clone carries room sound from its reference
recording, and the pitch-shift step of the voice preset smears it a little more.

Resemble Enhance (the same local AI cleaner talking-head uses, ~/video-studio/.venv-enhance)
removes room echo and noise. Loading its model takes minutes, so every scene is packed
into ONE file with silent gaps, enhanced once, and split back by sample offset. The
untouched reads are kept in work/voice_raw/. Machines without the enhancer (the Mac mini, the Linux server)
skip the step and keep the preset voice."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import platform_util

ENHANCER_PY = platform_util.venv_python(platform_util.studio_venv("enhance"))
ENHANCER = Path.home() / "video-studio/enhance_voice.py"
SR = 48000
GAP = SR // 2  # half a second of silence between scenes, so one read never bleeds into the next


def available() -> bool:
    return ENHANCER_PY.exists() and ENHANCER.exists()


def pack(clips: list, gap: int = GAP):
    """One signal with `gap` zeros after each clip, plus (start, length) for each clip."""
    import numpy as np
    spans, parts, pos = [], [], 0
    for clip in clips:
        spans.append((pos, len(clip)))
        parts += [clip, np.zeros(gap, np.float32)]
        pos += len(clip) + gap
    return np.concatenate(parts), spans


def unpack(signal, spans: list) -> list:
    return [signal[start:start + length] for start, length in spans]


def _read(path: Path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _write(path: Path, samples) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                    "-i", "-", "-c:a", "pcm_s16le", str(path)],
                   input=samples.astype("float32").tobytes(), check=True)


def _enhance(src: Path, dst: Path) -> None:
    """Resemble Enhance on the CPU (MPS returns noise). 86s of narration took 7.5 minutes."""
    subprocess.run([str(ENHANCER_PY), str(ENHANCER), str(src), str(dst),
                    "--lambd", "0.9", "--device", "cpu"], check=True)


def clean_scenes(work: Path, ids: list) -> bool:
    """Replace work/scene_NN.wav for each id with the echo-cleaned read. False if skipped."""
    work = Path(work)
    if not available():
        print("[voice] echo cleanup skipped: Resemble Enhance is not installed on this machine")
        return False
    wavs = [work / f"scene_{n:02d}.wav" for n in ids if (work / f"scene_{n:02d}.wav").exists()]
    if not wavs:
        return False
    keep = work / "voice_raw"
    keep.mkdir(exist_ok=True)
    for wav in wavs:
        shutil.copy(wav, keep / wav.name)
    signal, spans = pack([_read(keep / wav.name) for wav in wavs])
    print(f"[voice] echo cleanup: {len(wavs)} scenes, {len(signal) / SR:.0f}s of audio "
          f"(about 5x real time on the CPU)", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "all.wav", Path(tmp) / "all_clean.wav"
        _write(src, signal)
        _enhance(src, dst)
        cleaned = _read(dst)
    if len(cleaned) < spans[-1][0] + spans[-1][1]:
        raise RuntimeError(f"echo cleanup returned {len(cleaned)} samples, expected {len(signal)}")
    for wav, clip in zip(wavs, unpack(cleaned, spans)):
        _write(wav, clip)
    return True
