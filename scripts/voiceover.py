"""Tony's own read replaces the TTS voice.

`fv.py voiceover <job> <take>` takes ONE recording of the whole script (a phone memo, a
mic recording, a video file: anything ffmpeg reads), transcribes it with word times
(transcribe.py: Parakeet, else Whisper), lines the heard words up against every scene's
narration, and writes work/scene_NN.wav per scene, cut in the pauses between scenes.
The rest of finish then runs as usual (motion, assemble, kit, upload) with no TTS.

Stumbles are handled in the cut, so Tony never has to edit:
- a line read twice keeps its LAST read (alignment ties go to the later words), and
- a run of EXTRA_RUN or more unscripted words inside a scene (a restart) is cut out.
So "flub it, pause, start the block over" is the whole recording instruction.

The take gets the mic EQ Tony picked by ear (MIC_EQ, --no-eq to skip) on top of the 70 Hz
cut. The transcription copy stays unfiltered.

Long pauses between sentences are shortened to MAX_PAUSE (Tony's first own-voice cut ran
13 seconds of dead air and felt slow), so he can read at a relaxed pace and the video
still moves.
"""
from __future__ import annotations

import array
import difflib
import functools
import json
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import common
import transcribe
import voice_cleanup
import wordcheck

EXTRA_RUN = 2     # unscripted words in a row that count as a restart and get cut ("who gets who got")
LEAD_S = 0.20     # breath kept before a span's first word (never more than half the pause)
TAIL_S = 0.35     # room kept after a span's last word (never more than half the pause)
FADE_S = 0.012    # fade at every cut so joins do not click
SIMILAR_COST = 0.25   # alignment cost of a near-miss word (cheaper than any insert or delete)
SIMILAR_RATIO = 0.75  # difflib ratio at which two words count as the same word misheard
MAX_PAUSE = 0.30  # longest pause kept inside a scene, seconds (0 keeps the read's own pauses)
FRAME_S = 0.010   # silence is judged in 10 ms frames
QUIET_DB = -38.0  # a frame quieter than this (dBFS peak) is a pause...
FLOOR_X = 2.5     # ...or quieter than 2.5x the room floor, for a hissy phone memo
RATE = 44100
# Tony's voice-over mic, shaped by ear on 2026-11-11 (mic-test/match_eq.py): his own mic with
# the tone of a second mic he tried, keeping his mic's far quieter background (46 vs 27 dB
# signal to noise). About 6 dB less from 80 to 640 Hz, a 4 dB lift at 1 to 1.3 kHz, flat from
# 2 kHz up. He picked it over both raw mics in a level-matched listen. --no-eq for any other mic.
MIC_EQ_POINTS = ((79, -6.7), (100, -6.7), (126, -6.6), (159, -5.0), (200, -4.1), (252, -4.3),
                 (317, -6.3), (400, -6.2), (504, -6.4), (635, -3.8), (800, -0.2), (1008, 3.5),
                 (1270, 3.9), (1600, 1.7), (2016, -0.2), (2540, 0.0), (3200, 0.0), (4032, 0.4),
                 (5080, -0.2), (6400, 0.0), (8063, 0.0))
# 50 ms of filter resolves the low-end shelf. zero_phase plus atrim keeps the audio on time:
# the filter's delay would otherwise land every word 50 ms after its transcribed time.
MIC_EQ = ("firequalizer=delay=0.05:zero_phase=on:gain_entry='"
          + ";".join(f"entry({f},{g})" for f, g in MIC_EQ_POINTS) + "',atrim=start=0")
ACRONYM = re.compile(r"\b((?:[A-Za-z]\.){2,})")  # "A.I." is heard as one word, "AI"


def _script_tokens(text: str) -> list[str]:
    return wordcheck.tokens(ACRONYM.sub(lambda m: m.group(1).replace(".", ""), text))


def _expected(scenes: list[dict]) -> tuple[list[str], list[int]]:
    """Every narrated word of the script, with the scene it belongs to."""
    toks, owners = [], []
    for scene in scenes:
        for tok in _script_tokens(scene.get("narration") or ""):
            toks.append(tok)
            owners.append(scene["id"])
    return toks, owners


def _heard(words: list[dict]) -> tuple[list[str], list[int]]:
    """Heard tokens, with the heard word each came from ("280" is three tokens)."""
    toks, owners = [], []
    for i, word in enumerate(words):
        for tok in wordcheck.tokens(word["word"]):
            toks.append(tok)
            owners.append(i)
    return toks, owners


def align(expected: list[str], heard: list[str]) -> list[int | None]:
    """For each expected token, the index of the heard token it matched exactly, or None.

    Edit-distance alignment. The traceback runs from the end and takes a match whenever
    a match is optimal, so when a line was read twice the LATER read is the one kept."""
    return _trace(expected, heard)[0]


def _sub_cost(a: str, b: str) -> float:
    """0 for the same word, SIMILAR_COST for a near miss ("engineer"/"engineers",
    "learn"/"learned"), 1 for a different word. Near misses must beat an insert plus a
    delete, or a scene's misheard last word gets left outside the scene and cut off."""
    if a == b:
        return 0.0
    return SIMILAR_COST if _similar(a, b) else 1.0


@functools.lru_cache(maxsize=None)
def _similar(a: str, b: str) -> bool:
    return min(len(a), len(b)) >= 3 and difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR_RATIO


def _trace(expected: list[str], heard: list[str]) -> tuple[list, list]:
    """(exact, near): exact[i] is the heard index matched word for word, near[i] also
    counts a misheard word ("engineers" heard as "engineer", "Claude" as "plot")."""
    n, m = len(expected), len(heard)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        prev, row, exp = cost[i - 1], cost[i], expected[i - 1]
        row[0] = float(i)
        for j in range(1, m + 1):
            row[j] = min(prev[j - 1] + _sub_cost(exp, heard[j - 1]), prev[j] + 1, row[j - 1] + 1)
    exact: list[int | None] = [None] * n
    near: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        here, sub = cost[i][j], _sub_cost(expected[i - 1], heard[j - 1])
        if sub < 1 and here == cost[i - 1][j - 1] + sub:
            near[i - 1] = j - 1          # read (a near miss is still the word)
            if sub == 0:
                exact[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif here == cost[i][j - 1] + 1:
            j -= 1          # a heard word the script does not have (false start, filler)
        elif here == cost[i - 1][j] + 1:
            i -= 1          # a script word that was not heard
        else:
            near[i - 1] = j - 1  # misheard: the word is there but transcribed differently
            i, j = i - 1, j - 1
    return exact, near


def _matches(scenes: list[dict], words: list[dict]):
    exp, exp_scene = _expected(scenes)
    heard, heard_word = _heard(words)
    exact, near = _trace(exp, heard)
    return exp, exp_scene, exact, near, heard_word


def _pad(words: list[dict], first: int, last: int) -> tuple[float, float]:
    """Seconds for words[first..last], widened into the pauses on either side."""
    start, end = words[first]["start"], words[last]["end"]
    before = start - (words[first - 1]["end"] if first > 0 else 0.0)
    after = (words[last + 1]["start"] - end) if last + 1 < len(words) else 2 * TAIL_S
    return start - min(LEAD_S, max(before, 0.0) / 2), end + min(TAIL_S, max(after, 0.0) / 2)


def _keep_runs(first: int, last: int, used: set[int]) -> list[tuple[int, int]]:
    """Word-index runs to keep from first..last, dropping false starts (long unmatched runs)."""
    runs, run_start, pending = [], first, []
    for w in range(first + 1, last + 1):
        if w not in used:
            pending.append(w)
            continue
        if len(pending) >= EXTRA_RUN:
            runs.append((run_start, pending[0] - 1))
            run_start = w
        pending = []
    runs.append((run_start, last))
    return runs


def scene_spans(scenes: list[dict], words: list[dict]) -> dict[int, list[tuple[float, float]]]:
    """{scene_id: [(start_s, end_s), ...]} of the take to keep for each narrated scene."""
    # Misheard words count as read: a scene's edges and its kept runs go by `near`, so
    # a last word the transcriber got wrong is not cut off the end of the scene.
    _, exp_scene, _, match, heard_word = _matches(scenes, words)
    used = {heard_word[j] for j in match if j is not None}
    spans = {}
    for scene in scenes:
        if not (scene.get("narration") or "").strip():
            continue
        idx = sorted({heard_word[match[k]] for k, sid in enumerate(exp_scene)
                      if sid == scene["id"] and match[k] is not None})
        if not idx:
            raise ValueError(f"scene {scene['id']}: none of its words were heard in the take")
        spans[scene["id"]] = [_pad(words, a, b) for a, b in _keep_runs(idx[0], idx[-1], used)]
    return spans


def report(scenes: list[dict], words: list[dict]) -> dict[int, list[str]]:
    """{scene_id: ["missing: word word", ...]} for script words the take did not match.
    A mishearing by the transcriber shows up here too, so it is a list to LISTEN to."""
    exp, exp_scene, match, _, _ = _matches(scenes, words)
    out: dict[int, list[str]] = {}
    group: list[str] = []
    for k, tok in enumerate(exp):
        last_of_scene = k + 1 == len(exp) or exp_scene[k + 1] != exp_scene[k]
        if match[k] is None:
            group.append(tok)
        if group and (match[k] is not None or last_of_scene):
            out.setdefault(exp_scene[k], []).append("missing: " + " ".join(group))
            group = []
    return out


def _flatten(data: dict) -> list[dict]:
    return [w for seg in data.get("segments", []) for w in seg.get("words", [])
            if w.get("word", "").strip()]


def _ffmpeg(src: Path, dst: Path, rate: int, voice_filter: bool, eq: bool = False) -> None:
    """Mono PCM at rate. voice_filter: the 70 Hz cut, plus Tony's mic EQ when eq is set.
    Without voice_filter (the transcription copy) the audio is left as recorded."""
    chain = ["highpass=f=70", *([MIC_EQ] if eq else [])]
    filters = ["-af", ",".join(chain)] if voice_filter else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
                    "-ar", str(rate), *filters, "-c:a", "pcm_s16le", str(dst)], check=True)


def _read(path: Path) -> array.array:
    with wave.open(str(path), "rb") as wav:
        samples = array.array("h")
        samples.frombytes(wav.readframes(wav.getnframes()))
    return samples


def _faded(segment: array.array, n: int) -> array.array:
    out = array.array("h", segment)
    n = min(n, len(out) // 2)
    for k in range(n):
        gain = k / n
        out[k] = int(out[k] * gain)
        out[-1 - k] = int(out[-1 - k] * gain)
    return out


def cut(samples: array.array, spans: list[tuple[float, float]], rate: int = RATE) -> array.array:
    """The spans of a take joined end to end, each faded at both edges."""
    out = array.array("h")
    for start, end in spans:
        lo, hi = max(0, int(start * rate)), min(len(samples), int(end * rate))
        out.extend(_faded(samples[lo:hi], int(FADE_S * rate)))
    return out


def _frame_peaks(samples: array.array, frame: int) -> list[int]:
    peaks = []
    for lo in range(0, len(samples), frame):
        chunk = samples[lo:lo + frame]
        peaks.append(max(max(chunk), -min(chunk)))
    return peaks


def _quiet_level(peaks: list[int]) -> float:
    """The peak under which a frame counts as a pause: -38 dBFS, or a little over the
    room floor (the 10th percentile frame) when the room is noisier than that."""
    floor = sorted(peaks)[len(peaks) // 10]
    return max(32767 * 10 ** (QUIET_DB / 20), floor * FLOOR_X)


def _quiet_runs(peaks: list[int], level: float) -> list[tuple[int, int]]:
    """(first, last) frame index of every run of quiet frames."""
    runs, start = [], None
    for k, peak in enumerate(peaks):
        if peak < level and start is None:
            start = k
        elif peak >= level and start is not None:
            runs.append((start, k - 1))
            start = None
    if start is not None:
        runs.append((start, len(peaks) - 1))
    return runs


def tighten(samples: array.array, max_pause: float = MAX_PAUSE, rate: int = RATE) -> array.array:
    """The audio with every pause longer than max_pause cut down to max_pause. Half the
    pause is kept on each side, so a breath or a soft last consonant is never clipped."""
    frame = max(1, int(FRAME_S * rate))
    if not max_pause or len(samples) < frame:
        return samples
    peaks = _frame_peaks(samples, frame)
    keep_half = int(max_pause * rate / 2)
    spans, pos = [], 0
    for first, last in _quiet_runs(peaks, _quiet_level(peaks)):
        lo, hi = first * frame, min(len(samples), (last + 1) * frame)
        if hi - lo <= 2 * keep_half:
            continue
        spans.append((pos, lo + keep_half))
        pos = hi - keep_half
    if not spans:
        return samples
    spans.append((pos, len(samples)))
    return _join(samples, spans, int(FADE_S * rate))


def _join(samples: array.array, spans: list[tuple[int, int]], fade: int) -> array.array:
    """Sample spans joined end to end, faded only where two spans meet (inside a pause),
    so the first and last word of the scene keep their full attack and ring."""
    out = array.array("h")
    for k, (lo, hi) in enumerate(spans):
        seg = array.array("h", samples[lo:hi])
        n = min(fade, len(seg) // 2)
        for i in range(n):
            gain = i / n
            if k > 0:
                seg[i] = int(seg[i] * gain)
            if k < len(spans) - 1:
                seg[-1 - i] = int(seg[-1 - i] * gain)
        out.extend(seg)
    return out


def _write(path: Path, samples: array.array, rate: int = RATE) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())


def _keep_take(jdir: Path, src: Path) -> Path:
    """A copy of the take inside the job, so a later re-assembly does not need the original."""
    folder = jdir / "voiceover"
    folder.mkdir(exist_ok=True)
    kept = folder / f"take{src.suffix.lower() or '.wav'}"
    if src.resolve() != kept.resolve():
        shutil.copy2(src, kept)
    return kept


def _transcribe(take: Path, tmp: Path) -> list[dict]:
    small, out_json = tmp / "take16k.wav", tmp / "take.json"
    _ffmpeg(take, small, 16000, voice_filter=False)
    engine = transcribe.transcribe(small, out_json)
    words = _flatten(json.loads(out_json.read_text()))
    print(f"[voiceover] heard {len(words)} words ({engine})")
    return words


def _write_scenes(work: Path, take: Path, tmp: Path, spans: dict,
                  max_pause: float = MAX_PAUSE, eq: bool = True) -> None:
    full = tmp / "take.wav"
    _ffmpeg(take, full, RATE, voice_filter=True, eq=eq)
    print(f"[voiceover] mic EQ {'on (--no-eq for a take from another mic)' if eq else 'off'}")
    samples = _read(full)
    for sid, parts in spans.items():
        for old in work.glob(f"scene_{sid:02d}.*"):
            if old.suffix in (".wav", ".mp3"):
                old.unlink()
        read = cut(samples, parts)
        audio = tighten(read, max_pause)
        _write(work / f"scene_{sid:02d}.wav", audio)
        dropped = f", {len(parts) - 1} false start(s) cut" if len(parts) > 1 else ""
        saved = (len(read) - len(audio)) / RATE
        trimmed = f", {saved:.1f}s of pauses trimmed" if saved >= 0.05 else ""
        print(f"[voiceover] scene {sid}: {len(audio) / RATE:.1f}s{dropped}{trimmed}")


def run(job_id: str, take: str, clean: bool = False, max_pause: float = MAX_PAUSE, eq: bool = True) -> None:
    jdir = common.job_dir(job_id)
    work = jdir / "work"
    data = common.load_scenes(job_id)
    src = Path(take).expanduser()
    if not src.is_file():
        common.die(f"[voiceover] no such file: {src}")
    if not transcribe.available():
        common.die("[voiceover] no transcriber installed (parakeet-mlx, mlx-whisper or faster-whisper)")
    kept = _keep_take(jdir, src)
    with tempfile.TemporaryDirectory() as tmp:
        words = _transcribe(kept, Path(tmp))
        (kept.parent / "take_words.json").write_text(json.dumps(words, indent=1))
        try:
            spans = scene_spans(data["scenes"], words)
        except ValueError as err:
            common.die(f"[voiceover] {err}. Is this the right take for {job_id}?")
        _write_scenes(work, kept, Path(tmp), spans, max_pause, eq)
    problems = report(data["scenes"], words)
    for sid, items in sorted(problems.items()):
        print(f"[voiceover] scene {sid} LISTEN: {'; '.join(items)}")
    if not problems:
        print("[voiceover] every scene's script was heard in the take")
    if clean:
        voice_cleanup.clean_scenes(work, sorted(spans))
    common.set_state(job_id, status="narrated", voice="own", tts_engine="own-take",
                     own_take=str(kept), max_pause=max_pause, mic_eq=eq, narration_check={str(k): v for k, v in problems.items()})
