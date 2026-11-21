"""Every final is brought to one loudness target (-16 LUFS) with a straight gain and a
peak limiter. Before 2026-10-09 the mix only ran dynaudnorm, which evens the level out but
never targets one, so finals landed at -19 to -21 LUFS and played quiet. Dynamic loudnorm
was tried the same day and dropped: it lifts the gaps between words, and with them the
room echo. Tony found -15 "a little too loud", hence -16."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import loudness  # noqa: E402

STDERR = """[Parsed_loudnorm_0 @ 0x600]
{
	"input_i" : "-19.13",
	"input_tp" : "-0.52",
	"input_lra" : "7.00",
	"input_thresh" : "-29.40",
	"output_i" : "-14.02",
	"output_tp" : "-1.50",
	"output_lra" : "5.10",
	"output_thresh" : "-24.20",
	"normalization_type" : "dynamic",
	"target_offset" : "0.02"
}
"""


def test_parse_reads_the_json_block_from_ffmpeg_stderr():
    m = loudness.parse(STDERR)
    assert m["input_i"] == "-19.13"
    assert m["target_offset"] == "0.02"


def test_parse_fails_loudly_without_a_measurement():
    with pytest.raises(ValueError):
        loudness.parse("ffmpeg said nothing useful")


def test_level_chain_is_a_straight_gain_then_a_limiter():
    chain = loudness.level_chain(-19.1)
    assert chain.startswith(f"volume={loudness.TARGET_I + 19.1:.1f}dB")
    assert "alimiter" in chain and "loudnorm" not in chain


def test_level_chain_tops_up():
    assert loudness.level_chain(-19.1, extra_db=0.6).startswith(
        f"volume={loudness.TARGET_I + 19.1 + 0.6:.1f}dB")


def _measure(path):
    out = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af",
                          loudness.first_pass_filter(), "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    m = loudness.parse(out)
    return float(m["input_i"]), float(m["input_tp"])


def test_normalize_brings_a_quiet_video_up_to_target(tmp_path):
    clip = tmp_path / "quiet.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-af", "volume=-24dB", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)],
                   check=True)
    assert _measure(clip)[0] < -25
    loudness.normalize(clip)
    level, peak = _measure(clip)
    assert level == pytest.approx(loudness.TARGET_I, abs=0.5)
    assert peak <= -1.0
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0", str(clip)], capture_output=True, text=True).stdout
    assert "video" in probe and "audio" in probe
