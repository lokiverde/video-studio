"""Tony's own read: one take lined up against the script and cut into scenes."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assemble  # noqa: E402
import voiceover  # noqa: E402


def _words(text, start=0.0, step=0.4, gap_after=None):
    """Heard words at a steady pace. gap_after={index: extra seconds} adds pauses."""
    out, t = [], start
    for i, w in enumerate(text.split()):
        out.append({"word": " " + w, "start": round(t, 3), "end": round(t + 0.3, 3)})
        t += step + (gap_after or {}).get(i, 0.0)
    return out


def test_align_matches_a_clean_read():
    assert voiceover.align(["a", "b", "c"], ["a", "b", "c"]) == [0, 1, 2]


def test_align_keeps_the_last_read_of_a_repeated_line():
    # "a b c" was read twice before "d": the second read wins.
    assert voiceover.align(["a", "b", "c", "d"], ["a", "b", "c", "a", "b", "c", "d"]) == [3, 4, 5, 6]


def test_align_keeps_the_full_retake_after_a_false_start():
    expected = "x so i built my own".split()
    heard = "x so i built so i built my own".split()
    assert voiceover.align(expected, heard) == [0, 4, 5, 6, 7, 8]


def test_align_marks_a_skipped_word():
    assert voiceover.align(["a", "b", "c"], ["a", "c"]) == [0, None, 1]


def test_scene_spans_cut_at_the_pause_between_scenes():
    scenes = [{"id": 1, "narration": "one two three"}, {"id": 2, "narration": "four five"}]
    heard = _words("one two three four five", start=0.5, gap_after={2: 1.0})
    spans = voiceover.scene_spans(scenes, heard)
    first, second = spans[1], spans[2]
    assert first[0][0] < heard[0]["start"]
    assert first[-1][1] > heard[2]["end"]
    assert first[-1][1] <= second[0][0]
    assert second[0][0] < heard[3]["start"]


def test_scene_spans_drop_a_stumble_inside_a_scene():
    scenes = [{"id": 1, "narration": "so i made a little app that does it"}]
    heard = _words("so i made a littel so i made a little app that does it")
    spans = voiceover.scene_spans(scenes, heard)[1]
    assert len(spans) == 1
    assert spans[0][0] > heard[4]["end"] - 0.01  # the false start is gone
    assert spans[0][0] < heard[5]["start"]


def test_scene_spans_number_words_line_up():
    scenes = [{"id": 1, "narration": "about two hundred eighty sessions"}]
    heard = _words("about 280 sessions")
    assert voiceover.scene_spans(scenes, heard)[1]


def test_report_lists_missing_words():
    scenes = [{"id": 1, "narration": "my inbox gets sorted before I wake up"}]
    heard = _words("my inbox gets sorted I wake up")
    report = voiceover.report(scenes, heard)
    assert report == {1: ["missing: before"]}


def test_report_is_empty_on_a_clean_read():
    scenes = [{"id": 1, "narration": "Built that too."}]
    assert voiceover.report(scenes, _words("built that too")) == {}


def test_scene_with_nothing_heard_fails_loudly():
    scenes = [{"id": 1, "narration": "hello there"}, {"id": 2, "narration": "never read"}]
    with pytest.raises(ValueError, match="scene 2"):
        voiceover.scene_spans(scenes, _words("hello there"))


@pytest.mark.parametrize("value", [0.0, 0.12, 1])
def test_music_volume_accepts_zero_to_one(value):
    assert assemble.music_volume({"music_volume": value}, {}, None) == float(value)


@pytest.mark.parametrize("value", [-0.1, 1.5, "loud", True])
def test_music_volume_rejects_out_of_range(value):
    with pytest.raises(ValueError):
        assemble.music_volume({"music_volume": value}, {}, None)


def test_music_volume_order_state_then_scenes_then_theme_then_default():
    assert assemble.music_volume({}, {}, None) == 0.18
    assert assemble.music_volume({}, {"music_volume": 0.2}, None) == 0.2
    assert assemble.music_volume({"music_volume": 0.1}, {"music_volume": 0.2}, None) == 0.1
    assert assemble.music_volume({"music_volume": 0.1}, {}, 0.05) == 0.05


def test_scene_spans_keep_a_misheard_last_word():
    # "engineers" heard as "engineer": the span still runs to the end of that word.
    scenes = [{"id": 1, "narration": "AI for operators, not engineers."}]
    heard = _words("AI operator not an engineer", start=0.5)
    spans = voiceover.scene_spans(scenes, heard)[1]
    assert spans[-1][1] > heard[-1]["end"]


def test_scene_spans_keep_a_misheard_first_word():
    scenes = [{"id": 1, "narration": "one two"}, {"id": 2, "narration": "Claude is the best tool"}]
    heard = _words("one two plot is the best tool", start=0.5, gap_after={1: 1.0})
    second = voiceover.scene_spans(scenes, heard)[2]
    assert second[0][0] < heard[2]["start"]


def test_scene_spans_drop_a_two_word_restart():
    scenes = [{"id": 1, "narration": "a business owner who got tired of hunting"}]
    heard = _words("a business owner who gets who got tired of hunting")
    spans = voiceover.scene_spans(scenes, heard)[1]
    assert len(spans) == 2
    assert spans[0][1] <= heard[4]["start"]   # "who gets" is gone
    assert spans[1][0] >= heard[4]["end"] - 0.01


def _tone_and_gaps(rate, parts):
    """Audio made of ("tone"|"quiet", seconds) parts: a loud square wave or near silence."""
    import array
    out = array.array("h")
    for kind, secs in parts:
        n = int(secs * rate)
        if kind == "tone":
            out.extend(8000 if (k // 4) % 2 else -8000 for k in range(n))
        else:
            out.extend((k % 3) - 1 for k in range(n))   # a faint room floor, not digital zero
    return out


def test_tighten_shortens_a_long_pause_to_the_cap():
    rate = 8000
    audio = _tone_and_gaps(rate, [("tone", 1.0), ("quiet", 1.2), ("tone", 1.0)])
    out = voiceover.tighten(audio, max_pause=0.3, rate=rate)
    assert abs(len(out) / rate - 2.3) < 0.05


def test_tighten_leaves_short_pauses_alone():
    rate = 8000
    audio = _tone_and_gaps(rate, [("tone", 1.0), ("quiet", 0.25), ("tone", 1.0)])
    assert len(voiceover.tighten(audio, max_pause=0.3, rate=rate)) == len(audio)


def test_tighten_off_keeps_the_read_as_is():
    rate = 8000
    audio = _tone_and_gaps(rate, [("tone", 0.5), ("quiet", 1.5), ("tone", 0.5)])
    assert len(voiceover.tighten(audio, max_pause=0, rate=rate)) == len(audio)


def test_tighten_never_eats_into_the_words():
    rate = 8000
    audio = _tone_and_gaps(rate, [("tone", 1.0), ("quiet", 2.0), ("tone", 1.0)])
    out = voiceover.tighten(audio, max_pause=0.3, rate=rate)
    loud = sum(1 for s in out if abs(s) > 1000)
    assert loud == sum(1 for s in audio if abs(s) > 1000)


def test_tighten_handles_a_noisy_room():
    # A hissy phone memo: the floor sits well above digital silence but far under the voice.
    import array
    rate = 8000
    audio = _tone_and_gaps(rate, [("tone", 1.0), ("quiet", 1.2), ("tone", 1.0)])
    hiss = array.array("h", (s if abs(s) > 100 else s * 1000 for s in audio))
    out = voiceover.tighten(hiss, max_pause=0.3, rate=rate)
    assert abs(len(out) / rate - 2.3) < 0.05


# --- the mic EQ Tony picked by ear on 2026-11-11 (mic-test/match_eq.py) ---

def _pcm(path):
    import wave
    import numpy as np
    with wave.open(str(path), "rb") as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float)


def _welch(x, rate, nperseg=16384):
    # Averaged Hann-windowed power spectrum, 50% overlap (scipy.signal.welch without scipy:
    # CI installs numpy only). Scale is left off because callers compare two takes.
    import numpy as np
    win = np.hanning(nperseg)
    starts = range(0, len(x) - nperseg + 1, nperseg // 2)
    power = np.mean([np.abs(np.fft.rfft((x[i:i + nperseg] - x[i:i + nperseg].mean()) * win)) ** 2
                     for i in starts], axis=0)
    return np.fft.rfftfreq(nperseg, 1 / rate), power


def _band_gain_db(flat, shaped, fc, rate=voiceover.RATE):
    import numpy as np
    f, pf = _welch(flat, rate)
    _, ps = _welch(shaped, rate)
    band = (f >= fc * 2 ** (-1 / 6)) & (f < fc * 2 ** (1 / 6))
    return 10 * np.log10(ps[band].sum() / pf[band].sum())


@pytest.fixture(scope="module")
def white_take(tmp_path_factory):
    import subprocess
    path = tmp_path_factory.mktemp("eq") / "white.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anoisesrc=color=white:amplitude=0.3:duration=8:sample_rate=44100:seed=5", str(path)], check=True)
    return path


def test_mic_eq_gives_the_take_the_tone_tony_picked(white_take, tmp_path):
    # His own mic with the second mic's tone: less low end, a lift around 1 kHz, top end untouched.
    flat, shaped = tmp_path / "flat.wav", tmp_path / "eq.wav"
    voiceover._ffmpeg(white_take, flat, voiceover.RATE, voice_filter=True, eq=False)
    voiceover._ffmpeg(white_take, shaped, voiceover.RATE, voice_filter=True, eq=True)
    a, b = _pcm(flat), _pcm(shaped)[:len(_pcm(flat))]
    assert -7.5 < _band_gain_db(a, b, 315) < -4.5
    assert 2.5 < _band_gain_db(a, b, 1100) < 4.5
    assert abs(_band_gain_db(a, b, 4000)) < 1.0
    assert abs(_band_gain_db(a, b, 12000)) < 1.0


def test_mic_eq_keeps_every_word_where_it_was(tmp_path):
    # Scenes are cut on word times heard in the unfiltered take: the EQ must not delay the audio.
    import subprocess
    import numpy as np
    click, out = tmp_path / "click.wav", tmp_path / "out.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "aevalsrc='if(between(n,44100,44101),0.8,0)':s=44100:d=2", str(click)], check=True)
    voiceover._ffmpeg(click, out, voiceover.RATE, voice_filter=True, eq=True)
    assert abs(int(np.argmax(np.abs(_pcm(out)))) - 44100) <= 44      # within 1 ms


def test_the_transcription_copy_stays_unfiltered(white_take, tmp_path):
    plain, again = tmp_path / "plain.wav", tmp_path / "again.wav"
    voiceover._ffmpeg(white_take, plain, 16000, voice_filter=False)
    voiceover._ffmpeg(white_take, again, 16000, voice_filter=False, eq=True)   # eq means nothing without the voice filter
    assert plain.read_bytes() == again.read_bytes()


def _record_ffmpeg(monkeypatch):
    import array
    calls = []

    def fake(src, dst, rate, voice_filter, eq=False):
        calls.append(eq)
        voiceover._write(dst, array.array("h", [0] * rate), rate)
    monkeypatch.setattr(voiceover, "_ffmpeg", fake)
    return calls


def test_scenes_get_the_mic_eq_by_default(tmp_path, monkeypatch):
    calls = _record_ffmpeg(monkeypatch)
    voiceover._write_scenes(tmp_path, tmp_path / "take.aiff", tmp_path, {1: [(0.0, 0.5)]})
    assert calls == [True]
    assert (tmp_path / "scene_01.wav").exists()


def test_no_eq_leaves_the_take_as_recorded(tmp_path, monkeypatch):
    calls = _record_ffmpeg(monkeypatch)
    voiceover._write_scenes(tmp_path, tmp_path / "take.aiff", tmp_path, {1: [(0.0, 0.5)]}, eq=False)
    assert calls == [False]


@pytest.mark.parametrize("flag, expected", [([], True), (["--no-eq"], False)])
def test_fv_voiceover_no_eq_flag(monkeypatch, flag, expected):
    import fv
    seen = {}
    monkeypatch.setattr(fv, "require_approval", lambda job, waived: None)
    monkeypatch.setattr(fv, "cmd_finish_impl", lambda job, music=None, narrate=None: narrate(job))
    monkeypatch.setattr(voiceover, "run", lambda job, take, **kw: seen.update(kw))
    monkeypatch.setattr(sys, "argv", ["fv.py", "voiceover", "20261111-000000-test", "take.aiff", *flag])
    fv.main()
    assert seen["eq"] is expected
