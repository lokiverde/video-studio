"""Did every word make it into the file? Re-transcribe what we made and compare it with
what should be there.

  talking head: the delivered final against Tony's source transcript, after cuts. A word
      clipped at a cut, or lost when the enhanced voice is swapped in, shows up as a
      missing or changed word next to a join (or as a run of lost words anywhere).
  faceless: each scene's TTS narration against its script line. Chatterbox now and then
      skips a phrase, repeats one, or swallows the last word.

From Nate Herk's edit kit (reviewed 2026-10-29): "a transcript alone is not proof". ASR
can guess a clipped word right while a listener hears it broken, so this catches LOST
words, not every rough join. th.py's cut-edge check and Tony's ear still own the rest.
Single-word disagreements away from a join are ASR noise and only counted.

  wordcheck.py final <job> [--file out/final_16x9.mp4]
  wordcheck.py narration <job> [--scenes 3,7]
"""
import argparse
import json
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

import common
import th_lib
import transcribe

JOIN_WINDOW = 0.3      # seconds either side of a cut where a lost or clipped word counts (plus the edge words)
LOST_RUN = 2           # this many expected words gone in a row is a problem anywhere
CHANGED_RUN = 3        # a swap this long (either side) is a problem anywhere
SAME_SOUNDS = 0.85     # letter similarity above which a swap is ASR regrouping, not a lost word
MISHEARD = 0.7         # ...or, when both sides have about as many words, a mishearing ("self brokerage
                       # hunter" as "stealth hardcourt center", 4187)
SHOW = 8               # past this many, the audio is not the same speech at all (a class recording, say)

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]
# "$2,500" spoken as "twenty five hundred dollars" is the same thing said another way. A
# swap counts as number spelling only when it holds a real number word, so a lost "a" or
# "and" on its own still shows up.
ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
           "twelve": "twelfth"}
NUMBERS = set(ONES + TENS[2:] + ["hundred", "thousand", "million", "billion"])
NUMBERS |= {ORDINAL.get(w, w[:-1] + "ieth" if w.endswith("y") else w + "th") for w in NUMBERS}
NUMBERISH = NUMBERS | {"point", "and", "a", "dollar", "dollars", "percent", "k", "by"}


def _say(n):
    """A non-negative int as words: 2500 -> two thousand five hundred."""
    if n < 20:
        return [ONES[n]]
    if n < 100:
        return [TENS[n // 10]] + ([ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [ONES[n // 100], "hundred"] + (_say(n % 100) if n % 100 else [])
    for size, name in SCALES:
        if n >= size:
            return _say(n // size) + [name] + (_say(n % size) if n % size else [])
    return [str(n)]


def _ordinal(n):
    """21 -> twenty first: the last word takes the ordinal form."""
    words = _say(n)
    last = words[-1]
    return words[:-1] + [ORDINAL.get(last, last[:-1] + "ieth" if last.endswith("y") else last + "th")]


def _number(raw):
    whole, _, frac = raw.partition(".")
    words = _say(int(whole)) if whole else ["zero"]
    return words + (["point"] + [ONES[int(d)] for d in frac] if frac else [])


def tokens(text):
    """Comparable words: lowercase, no punctuation, numbers and money spelled out."""
    text = text.lower().replace("&", " and ").replace("%", " percent ")
    text = re.sub(r"(?<=[a-z])\.(?=[a-z])", " ", text)    # quiz.siteone.com = quiz siteone com
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    text = re.sub(r"(?<=\d)x(?=\d)", " by ", text)          # 9x16 = nine by sixteen
    text = re.sub(r"\$(\d+(?:\.\d+)?)", r"\1 dollars", text)
    out = []
    for raw in re.split("[\\s\\-\u2013\u2014/]+", text):
        raw = raw.replace("'", "").replace("’", "")
        raw = re.sub(r"[^a-z0-9.]", "", raw).strip(".")
        ordinal = re.fullmatch(r"(\d+)(st|nd|rd|th)", raw)
        if ordinal:
            out.extend(_ordinal(int(ordinal.group(1))))
            continue
        raw = re.sub(r"(?<=\d)s$", "", raw)                  # 1990s
        if raw:
            out.extend(_number(raw) if re.fullmatch(r"\d+(\.\d+)?", raw) else [raw])
    return out


def _quote(items):
    return " ".join(i["w"] for i in items)


def _same_sounds(exp, got):
    """"guest stays" heard as "guests stay": the same letters regrouped, nothing lost. With
    about as many words on both sides, a looser match is a mishearing of the same phrase."""
    if not exp or not got or max(len(exp), len(got)) < 2:   # one word for one ("cant" -> "can") is a real change
        return False
    a, b = "".join(x["w"] for x in exp), "".join(x["w"] for x in got)
    floor = MISHEARD if abs(len(exp) - len(got)) <= 1 else SAME_SOUNDS
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= floor


def differences(expected, heard):
    """Opcodes (kind, exp_slice, heard_slice) where the two disagree, minus number
    spellings and regrouped letters. Both sides are lists of {"w": token, ...}."""
    sm = SequenceMatcher(None, [e["w"] for e in expected], [h["w"] for h in heard], autojunk=False)
    out = []
    for kind, i1, i2, j1, j2 in sm.get_opcodes():
        if kind == "equal":
            continue
        exp, got = expected[i1:i2], heard[j1:j2]
        both = exp + got
        if (all(x["w"] in NUMBERISH or x["w"].isdigit() for x in both) and any(x["w"] in NUMBERS for x in both)) \
                or _same_sounds(exp, got):
            continue
        out.append((kind, exp, got))
    return out


# --- talking head: the final against the source ------------------------------------

def expected_final(words, cuts, src_end):
    """Source transcript words that survive the cuts, as tokens on the output timeline,
    each with its index "i". A word plays when its middle and most of its span are outside
    every cut, whichever end the cut touches (HOA, 2026-10-21: "Assembly" started 0.02 s
    before a cut and was gone; 0651: a zero-length "even" sat inside a cut)."""
    out = []
    for w in words:
        text, s, e = w["word"].strip(), w["start"], w["end"]
        if not text or s > src_end or th_lib.in_cut((s + e) / 2, cuts) or 2 * th_lib._cut_overlap(s, e, cuts) >= e - s > 0:
            continue
        for tok in tokens(text):
            out.append({"w": tok, "s": round(th_lib.to_output(s, cuts), 3), "e": round(th_lib.to_output(e, cuts), 3),
                        "i": len(out)})
    return out


def joins(cuts):
    """Where each cut lands on the output timeline."""
    return sorted({round(th_lib.to_output(start, cuts), 3) for start, _ in cuts})


def _letters(items):
    return "".join(x["w"] for x in items)


def _lost_sound(exp, got):
    """A swap where the heard side has fewer letters ("cant" -> "can") lost some of the
    word; one with as many or more ("notices" -> "notice it") is ASR regrouping."""
    a, b = _letters(exp), _letters(got)
    return len(b) < len(a) or SequenceMatcher(None, a, b, autojunk=False).ratio() < 0.6


def _join_edges(expected, joins):
    """{token index: join time} for the last word before and the first word after each join."""
    edges = {}
    for j in joins:
        before = [x["i"] for x in expected if x["s"] < j]
        after = [x["i"] for x in expected if x["s"] >= j]
        for i in before[-1:] + after[:1]:
            edges[i] = j
    return edges


def final_problems(expected, heard, joins, window=JOIN_WINDOW):
    """(problems, minor): a word lost or cut short at a join (the word either side of it,
    or within `window`), a run of lost or changed words anywhere, or a stretch of extra
    speech (an uncut restart). Springfield, 2026-10-29: a "don't" four words past a join was
    ASR noise, so "next to a cut" means the edge words, not everything nearby."""
    edges = _join_edges(expected, joins)
    problems, minor = [], 0
    for kind, exp, got in differences(expected, heard):
        span = exp or got
        t0, t1 = span[0]["s"], span[-1]["e"]
        near = [edges[x["i"]] for x in exp if x.get("i") in edges] + [j for j in joins if t0 - window <= j <= t1 + window]
        what = f"expected \"{_quote(exp)}\", heard \"{_quote(got)}\"" if exp else f"extra \"{_quote(got)}\""
        if near and (kind == "delete" or kind == "replace" and _lost_sound(exp, got)):
            problems.append(f"{t0:.1f}s next to the cut at {near[0]:.1f}s: {what}")
        elif kind == "delete" and len(exp) >= LOST_RUN:
            problems.append(f"{t0:.1f}s lost words: {what}")
        elif max(len(exp), len(got)) >= CHANGED_RUN:
            problems.append(f"{t0:.1f}s {'extra speech' if kind == 'insert' else 'words differ'}: {what}")
        else:
            minor += 1
    return problems, minor


# --- faceless: each scene's narration against its script --------------------------

def narration_problems(script, heard):
    """(problems, minor) for one scene: skipped or added phrases, a long swap, a
    swallowed last word, or nothing heard at all."""
    expected = [{"w": w} for w in tokens(script)]
    if expected and not heard:
        return ["nothing heard"], 0
    problems, minor = [], 0
    for kind, exp, got in differences(expected, heard):
        if kind == "delete" and exp[-1] is expected[-1]:
            problems.append(f"lost the last word(s) \"{_quote(exp)}\"")
        elif kind == "delete" and len(exp) >= LOST_RUN:
            problems.append(f"skipped \"{_quote(exp)}\"")
        elif kind == "insert" and len(got) >= LOST_RUN:
            problems.append(f"added \"{_quote(got)}\"")
        elif kind == "replace" and max(len(exp), len(got)) >= CHANGED_RUN:
            problems.append(f"said \"{_quote(got)}\" for \"{_quote(exp)}\"")
        else:
            minor += 1
    return problems, minor


# --- I/O ---------------------------------------------------------------------------

def heard_tokens(data):
    """Whisper-shaped transcript -> tokens with times (one word can be several tokens)."""
    return [{"w": tok, "s": w["start"], "e": w["end"]}
            for seg in data.get("segments", []) for w in seg.get("words", []) for tok in tokens(w["word"])]


def _audio_16k(media, wav):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(media), "-vn", "-ac", "1",
                    "-ar", "16000", str(wav)], check=True)


def check_final(job_id, final):
    """Re-transcribe a rendered talking-head final. None when no transcriber is installed."""
    if not transcribe.available():
        return None
    jdir = common.job_dir(job_id)
    job = json.loads((jdir / "job.json").read_text())
    words = [w for seg in json.loads((jdir / "transcript.json").read_text())["segments"] for w in seg["words"]]
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "final.wav"
        _audio_16k(final, wav)
        transcribe.transcribe(wav, Path(tmp) / "final.json")
        data = json.loads((Path(tmp) / "final.json").read_text())
    cuts = job.get("cuts", [])
    return final_problems(expected_final(words, cuts, job["srcEnd"]), heard_tokens(data), joins(cuts))


def scene_audio(work, scene_id):
    for ext in ("wav", "mp3"):
        path = work / f"scene_{scene_id:02d}.{ext}"
        if path.exists():
            return path
    return None


def check_narration(job_id, scene_ids=None):
    """{scene_id: problems} for every narrated scene (or just scene_ids), plus the minor
    count. None when no transcriber is installed."""
    if not transcribe.available():
        return None
    work = common.job_dir(job_id) / "work"
    scenes = [s for s in common.load_scenes(job_id)["scenes"]
              if (s.get("narration") or "").strip() and (scene_ids is None or s["id"] in scene_ids)]
    files = {s["id"]: scene_audio(work, s["id"]) for s in scenes}
    found = {sid: f for sid, f in files.items() if f}
    results = dict(zip(found, transcribe.transcribe_many(list(found.values())))) if found else {}
    report, minor = {}, 0
    for scene in scenes:
        sid = scene["id"]
        if sid not in results:
            report[sid] = ["no narration audio"]
            continue
        problems, m = narration_problems(scene["narration"], heard_tokens(results[sid]))
        minor += m
        if problems:
            report[sid] = problems
    return report, minor


def print_final(label, result):
    if result is None:
        print(f"[words] {label}: skipped, no transcriber installed (parakeet-mlx, mlx-whisper or faster-whisper)")
        return []
    problems, minor = result
    shown = problems[:SHOW] + ([f"... and {len(problems) - SHOW} more: this much disagreement means other voices, "
                                "heavy noise or the wrong audio track, listen to it. A class or room recording on the "
                                "AI voice? th.py revoice <job> --room keeps every speaker"] if len(problems) > SHOW else [])
    print(f"[words] {label}: " + ("every word made it" if not problems else
                                  "LISTEN at these times before Tony sees it\n  " + "\n  ".join(shown))
          + (f" ({minor} single-word ASR differences, ignored)" if minor else ""))
    return problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("final"); f.add_argument("job"); f.add_argument("--file")
    n = sub.add_parser("narration"); n.add_argument("job"); n.add_argument("--scenes")
    a = p.parse_args()
    if a.cmd == "final":
        out = common.job_dir(a.job) / "out"
        final = Path(a.file) if a.file else next((out / n for n in ("final_16x9.mp4", "final_9x16.mp4")
                                                  if (out / n).exists()), None)
        if not final:
            common.die(f"[words] no final in {out}")
        return 1 if print_final(final.name, check_final(a.job, final)) else 0
    ids = {int(x) for x in a.scenes.split(",")} if a.scenes else None
    result = check_narration(a.job, ids)
    if result is None:
        print("[words] narration: skipped, no transcriber installed")
        return 0
    report, minor = result
    for sid, problems in sorted(report.items()):
        print(f"[words] scene {sid}: " + "; ".join(problems))
    print(f"[words] narration: {'clean' if not report else f'{len(report)} scene(s) to redo'}"
          + (f" ({minor} single-word ASR differences, ignored)" if minor else ""))
    return 1 if report else 0


if __name__ == "__main__":
    raise SystemExit(main())
