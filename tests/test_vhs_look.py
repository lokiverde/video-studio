"""Shop VHS (scripts/vhs_look.py): the tape look over a finished Shop video,
gone by the time the shirt comes back."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vhs_look  # noqa: E402


def test_mix_full_before_fade_and_clean_after():
    assert vhs_look.mix(1.0, 19.3, 0.7) == 1.0
    assert vhs_look.mix(18.6, 19.3, 0.7) == 1.0
    assert vhs_look.mix(19.3, 19.3, 0.7) == 0.0
    assert vhs_look.mix(25.0, 19.3, 0.7) == 0.0


def test_mix_eases_down_through_the_fade():
    mid = vhs_look.mix(18.95, 19.3, 0.7)
    assert 0.4 < mid < 0.6
    a, b = vhs_look.mix(18.8, 19.3, 0.7), vhs_look.mix(19.1, 19.3, 0.7)
    assert a > mid > b


def test_mix_without_clean_point_is_always_on():
    assert vhs_look.mix(100.0, None, 0.7) == 1.0


def test_mix_zero_fade_is_a_hard_switch():
    assert vhs_look.mix(19.29, 19.3, 0.0) == 1.0
    assert vhs_look.mix(19.3, 19.3, 0.0) == 0.0


def _frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3).astype(np.float32)


def test_apply_keeps_audio_and_leaves_the_clean_part_clean(tmp_path):
    src, dst = tmp_path / "src.mp4", tmp_path / "dst.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x3020a0:s=1080x1920:r=30:d=1.2",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=1.2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    vhs_look.apply(str(src), str(dst), strength=0.5, clean_from=0.6, fade=0.2)
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                                      "-of", "json", str(dst)], capture_output=True, text=True).stdout)
    assert sorted(s["codec_type"] for s in info["streams"]) == ["audio", "video"]
    taped = np.abs(_frame(dst, 0.1) - _frame(src, 0.1)).mean()
    clean = np.abs(_frame(dst, 1.0) - _frame(src, 1.0)).mean()
    assert taped > 3 * max(clean, 0.5)
    assert clean < 2.0


def test_play_readout_falls_back_to_the_bundled_font_off_a_mac(monkeypatch):
    import sr_vhs
    monkeypatch.setattr(sr_vhs, "OSD_FONTS", [(Path("/nonexistent/Menlo.ttc"), 1)] + sr_vhs.OSD_FONTS[1:])
    tape = sr_vhs.VHSPass({"strength": 0.5, "osd": "PLAY", "osd_end": 1.0})
    assert tape.osd is not None and tape.osd[..., 3].max() > 0.5
