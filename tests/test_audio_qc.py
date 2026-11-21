"""Audio QC gate: a final can hit its loudness target and still swing. The Nov 2026 class
video measured -14.0 LUFS with clean peaks, but four attendee stretches sat 12 LU under
Tony's voice (LRA 12.8). A podcast reference (Tom Bilyeu, -15.7 LUFS) stays within about
3 LU for 37 minutes, and Tony's other finals sit at 3.6 to 5.8 LU. The gate measures
level, true peak, loudness range and quiet stretches from ffmpeg's ebur128 log."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audio_qc  # noqa: E402

LOG = """[Parsed_ebur128_0 @ 0x1] t: 0.1  TARGET:-23 LUFS    M: -120.7 S: -120.7     I: -70.0 LUFS       LRA:   0.0 LU  FTPK: -inf dBFS  TPK: -inf dBFS
[Parsed_ebur128_0 @ 0x1] t: 3.1  TARGET:-23 LUFS    M: -15.2 S: -14.9     I: -15.0 LUFS       LRA:   1.0 LU  FTPK: -3.0 dBFS  TPK: -3.0 dBFS
[Parsed_ebur128_0 @ 0x1] t: 3.2  TARGET:-23 LUFS    M: -15.1 S: -15.3     I: -15.0 LUFS       LRA:   1.0 LU  FTPK: -3.0 dBFS  TPK: -3.0 dBFS
[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -14.0 LUFS
    Threshold: -24.4 LUFS

  Loudness range:
    LRA:        12.8 LU
    Threshold: -34.6 LUFS
    LRA low:   -26.9 LUFS
    LRA high:  -13.1 LUFS

  True peak:
    Peak:       -2.1 dBFS
"""


def frames(levels, step=0.1):
    """(t, S) frames: one short-term value per 0.1 s, from a list of (seconds, LUFS) runs."""
    out, t = [], 0.0
    for secs, lufs in levels:
        for _ in range(int(round(secs / step))):
            t = round(t + step, 1)
            out.append((t, lufs))
    return out


def test_parse_reads_the_summary_and_every_frame():
    m = audio_qc.parse(LOG)
    assert (m["I"], m["LRA"], m["TP"]) == (-14.0, 12.8, -2.1)
    assert m["frames"] == [(0.1, -120.7), (3.1, -14.9), (3.2, -15.3)]


def test_parse_fails_loudly_without_a_summary():
    with pytest.raises(ValueError):
        audio_qc.parse("ffmpeg said nothing useful")


def test_parse_reads_minus_inf_peak_as_silence():
    m = audio_qc.parse(LOG.replace("Peak:       -2.1 dBFS", "Peak:       -inf dBFS"))
    assert m["TP"] == float("-inf")


def test_steady_speech_has_no_quiet_stretches():
    assert audio_qc.quiet_stretches(frames([(120, -14.5)]), integrated=-14.0) == []


def test_a_quiet_stretch_is_found_with_its_times():
    f = frames([(60, -14.5), (30, -26.5), (60, -14.5)])
    found = audio_qc.quiet_stretches(f, integrated=-14.8)
    assert len(found) == 1
    start, end, low, under = found[0]
    assert (start, end) == (60, 90)
    assert low == pytest.approx(-26.5)
    assert under == pytest.approx(-12.0)


def test_neighbouring_quiet_blocks_merge_into_one_stretch():
    f = frames([(60, -14.5), (20, -24.0), (10, -22.5), (60, -14.5)])
    found = audio_qc.quiet_stretches(f, integrated=-14.8)
    assert [(a, b) for a, b, *_ in found] == [(60, 90)]


def test_pauses_and_end_card_silence_are_not_quiet_stretches():
    # Below the -20 LU gate: room tone between sentences, a silent end card.
    f = frames([(60, -14.5), (8, -60.0), (60, -14.5), (6, -120.0)])
    assert audio_qc.quiet_stretches(f, integrated=-14.5) == []


def test_the_last_block_is_ignored_as_the_outro():
    # End card, music tail, a pad under the last words: the final block is not judged.
    f = frames([(90, -14.5), (6, -27.0)])
    assert audio_qc.quiet_stretches(f, integrated=-14.6) == []


def test_a_quiet_open_is_flagged():
    # The AI20 pipeline clip opens on an attendee question 11 LU under Tony.
    f = frames([(10, -26.5), (90, -14.5)])
    found = audio_qc.quiet_stretches(f, integrated=-14.8)
    assert [(a, b) for a, b, *_ in found] == [(0, 10)]


def test_a_short_dip_inside_a_block_is_not_flagged():
    # One soft sentence (3 s at -6 LU) does not move a 10 s block's median.
    f = frames([(60, -14.5), (3, -20.5), (60, -14.5)])
    assert audio_qc.quiet_stretches(f, integrated=-14.5) == []


def test_problems_is_empty_for_a_good_final():
    m = {"I": -14.1, "LRA": 4.4, "TP": -1.7, "frames": frames([(90, -14.5)])}
    assert audio_qc.problems(m, target=-14.0) == []


def test_problems_names_every_failure():
    m = {"I": -12.0, "LRA": 12.8, "TP": -0.2,
         "frames": frames([(250, -14.5), (80, -26.5), (60, -14.5)])}
    found = audio_qc.problems(m, target=-14.0)
    text = "\n".join(found)
    assert "-12.0 LUFS" in text and "target -14" in text
    assert "true peak -0.2" in text
    assert "loudness range 12.8 LU" in text
    assert "4:10-5:30" in text


def test_target_is_optional():
    m = {"I": -19.0, "LRA": 4.0, "TP": -2.0, "frames": frames([(60, -19.5)])}
    assert audio_qc.problems(m) == []


def _tone(path, parts):
    """A mono test file: runs of (seconds, dB) pink noise, which ebur128 reads like speech."""
    inputs, labels = [], []
    for i, (secs, gain) in enumerate(parts):
        inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={secs}:sample_rate=48000:seed={i + 1}"]
        labels.append(f"[{i}:a]volume={gain}dB[a{i}]")
    joined = "".join(f"[a{i}]" for i in range(len(parts)))
    fc = ";".join(labels) + f";{joined}concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-ac", "1", str(path)], check=True)


def test_check_flags_a_real_file_with_a_quiet_stretch(tmp_path):
    wav = tmp_path / "class.wav"
    _tone(wav, [(40, -6), (30, -18), (40, -6)])
    m = audio_qc.measure(wav)
    found = audio_qc.problems(m)
    assert any("quiet stretch 0:40-1:10" in p for p in found), found


def test_check_passes_a_steady_real_file(tmp_path):
    wav = tmp_path / "steady.wav"
    _tone(wav, [(60, -8)])
    assert audio_qc.problems(audio_qc.measure(wav)) == []


def test_cli_exits_nonzero_on_problems(tmp_path):
    wav = tmp_path / "class.wav"
    _tone(wav, [(40, -6), (30, -18), (40, -6)])
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "audio_qc.py"), str(wav)],
                         capture_output=True, text=True)
    assert run.returncode == 1
    assert "quiet stretch" in run.stdout
