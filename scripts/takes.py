"""Several takes in, one master out: line every take up against the read-aloud script,
pick the cleanest attempt at each section, splice them into one file for th.py new.

  takes.py plan  <script.md> <main.mp4> [<other.mp4> ...] --out <dir>
      transcribes each take (cached), writes <dir>/edit.json and prints the per-section table
  takes.py splice <dir>
      builds <dir>/master.mp4 from edit.json and prints the join times for job.json punches

Read the table before splicing. The plan is a proposal: edit edit.json by hand when a
section needs a line from another take (2026-10-12: the clean "are the ones whose
paycheck" line came from take 0394 while the rest of #3 came from 0397).
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import transcribe

SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
         "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
OPEN_WORDS = 3          # a section attempt starts where its first words are said
PAD_IN, PAD_OUT = 0.25, 0.3
TIE = 0.02              # scores this close count as equal: main take, then the later attempt
MAX_WORD_S = 0.9        # Parakeet stretches a word's end through the pause after it
RESTART_PAD = 0.08      # keep this much before the word Tony restarts on
JOIN_GAP = 0.5          # pieces of one take this close are one continuous piece
LOOKAHEAD, LOOKBACK = 8, 30   # script positions searched when following a take word by word
FADE = 0.02             # audio fade at each join, stops clicks


TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _say(n):
    """0 to 99 as the words Tony's script spells out ("twenty two")."""
    if n <= 20:
        return [SMALL[n]]
    return [TENS[n // 10]] + ([SMALL[n % 10]] if n % 10 else [])


def norm_words(text):
    """Lowercase words without punctuation, numbers read the way the script spells them: 0 to 99
    as words, 2000 to 2099 as "twenty twenty six". Other numbers lose their commas ("1757")."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower().replace("’", "").replace("'", ""))
    out = []
    for w in re.findall(r"[a-z0-9]+", text):
        if w.isdigit() and int(w) <= 99:
            out += _say(int(w))
        elif w.isdigit() and 2000 <= int(w) <= 2099:
            out += ["twenty"] + (_say(int(w) % 100) if int(w) % 100 else ["hundred"])
        else:
            out.append(w)
    return out


def script_sections(md):
    """Read-aloud sections of a script file: every '## ' heading between the '# ' title and
    the '---' that starts the on-screen notes."""
    lines = md.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    if start is None:
        sys.exit("script has no '# ' title line")
    sections, cur = [], None
    for line in lines[start + 1:]:
        if line.strip() == "---":
            break
        if line.startswith("## "):
            cur = {"name": line[3:].strip(), "text": ""}
            sections.append(cur)
        elif cur is not None:
            cur["text"] += " " + line
    return [{**s, "words": norm_words(s["text"])} for s in sections if norm_words(s["text"])]


def _tokens(words):
    out = []
    for i, w in enumerate(words):
        for t in norm_words(w["word"]):
            out.append((t, i))
    return out


def _openings(toks, section):
    want = section["words"][:OPEN_WORDS]
    names = [t for t, _ in toks]
    return [k for k in range(len(names) - len(want) + 1) if names[k:k + len(want)] == want]


def _word_end(w):
    return min(w["end"], w["start"] + MAX_WORD_S)


def restarts(names, script):
    """Take-token spans [i, j) to drop because Tony went back and said a line again. Follows
    the take through the script; a token that matches nothing ahead but starts a 3-word run
    the script already passed is a restart, and everything since that run was first said goes."""
    first_at, p, drops = {}, 0, []
    for i, t in enumerate(names):
        nxt = names[i:i + 2]
        tail = len(nxt) < 2 or p == len(script) - 1
        ahead = [p] if p < len(script) and script[p] == t and (tail or script[p:p + 2] == nxt) else [
            q for q in range(p + 1, min(p + LOOKAHEAD, len(script))) if script[q:q + 2] == nxt and len(nxt) == 2]
        if ahead:
            first_at.setdefault(ahead[0], i)
            p = ahead[0] + 1
            continue
        back = [q for q in range(max(p - LOOKBACK, 0), p) if script[q:q + 3] == names[i:i + 3] and q in first_at]
        if back:
            q = back[-1]
            drops.append((first_at[q], i))
            first_at = {pos: idx for pos, idx in first_at.items() if pos < q}
            first_at[q] = i
            p = q + 1
    merged = []
    for a, b in sorted(drops):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def find_attempts(words, section, bounds=None):
    """Every place the take starts this section, scored by how much of the section it says
    before the next start (of this or any section in `bounds`). Score 1.0 = every word.
    `drop` lists restarted lines inside the attempt, `to` never reaches the next start."""
    toks = _tokens(words)
    starts = _openings(toks, section)
    stops = sorted(set(starts) | set(bounds or [])) + [len(toks)]
    sec = section["words"]
    found = []
    for k in starts:
        stop = min(st for st in stops if st > k)
        limit = words[toks[stop][1]]["start"] - 0.05 if stop < len(toks) else float("inf")
        stop = min(stop, k + int(len(sec) * 1.6) + 6)
        window = [t for t, _ in toks[k:stop]]
        sm = difflib.SequenceMatcher(None, sec, window, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        matched = sum(b.size for b in blocks)
        last = blocks[-1].b + blocks[-1].size - 1 if blocks else 0
        w0, w1 = toks[k][1], toks[k + last][1]
        drop = [(words[toks[k + a][1]]["start"] - 0.02, words[toks[k + b][1]]["start"] - RESTART_PAD)
                for a, b in restarts(window[:last + 1], sec)]
        found.append({"start": words[w0]["start"], "end": min(_word_end(words[w1]), limit), "limit": limit,
                      "score": round(matched / len(sec), 3), "k": k, "drop": [[round(a, 2), round(b, 2)] for a, b in drop]})
    return found


def propose(sections, take_words, main):
    """Best attempt per section across all takes. Ties go to the main take, then to the
    later attempt (a retake usually comes after the flub)."""
    plan = []
    for sec in sections:
        best = None
        for name, words in take_words.items():
            toks = _tokens(words)
            bounds = [k for other in sections if other is not sec for k in _openings(toks, other)]
            for a in find_attempts(words, sec, bounds):
                cand = {"section": sec["name"], "take": name, "from": round(max(a["start"] - PAD_IN, 0), 2),
                        "to": round(min(a["end"] + PAD_OUT, a["limit"]), 2), "score": a["score"], "drop": a["drop"]}
                if best is None or cand["score"] > best["score"] + TIE:
                    best = cand
                elif abs(cand["score"] - best["score"]) <= TIE:
                    prefer_main = name == main and best["take"] != main
                    later_same = name == best["take"] and cand["from"] > best["from"]
                    if prefer_main or later_same:
                        best = cand
        plan.append(best or {"section": sec["name"], "take": None, "score": 0.0})
    return plan


def segments_for(entry):
    """One proposed section -> splice segments, split around any dropped restarts."""
    cuts = [d for d in entry.get("drop", []) if entry["from"] < d[0] < d[1] <= entry["to"]]
    edges = [entry["from"]] + [x for d in cuts for x in d] + [entry["to"]]
    return [{"take": entry["take"], "from": round(a, 2), "to": round(b, 2), "section": entry["section"]}
            for a, b in zip(edges[::2], edges[1::2]) if b - a > 0.2]


def merge_segments(segments):
    """Neighbouring pieces of the same take that touch or overlap become one piece (no join,
    no doubled half second)."""
    out = []
    for seg in segments:
        prev = out[-1] if out else None
        if prev and prev["take"] == seg["take"] and seg["from"] <= prev["to"] + JOIN_GAP and seg["to"] > prev["from"]:
            out[-1] = {**prev, "to": max(prev["to"], seg["to"])}
        else:
            out.append(dict(seg))
    return out


def splice_points(segments):
    """Join times on the master timeline: running sums of the segment lengths."""
    out, t = [], 0.0
    for seg in segments[:-1]:
        t = round(t + seg["to"] - seg["from"], 2)
        out.append(t)
    return out


def _filter(segments, index_of):
    parts, labels = [], []
    for i, seg in enumerate(segments):
        src, dur = index_of[seg["take"]], seg["to"] - seg["from"]
        parts.append(f"[{src}:v:0]trim={seg['from']}:{seg['to']},setpts=PTS-STARTPTS,scale=-2:1440,fps=30,format=yuv420p[v{i}]")
        parts.append(f"[{src}:a:0]atrim={seg['from']}:{seg['to']},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={FADE},afade=t=out:st={max(dur - FADE, 0):.3f}:d={FADE}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]")
    return ";".join(parts)


def _audio(video, wav):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)


def cmd_plan(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sections = script_sections(Path(args.script).read_text())
    videos = {Path(v).stem: str(Path(v).expanduser()) for v in args.videos}
    take_words = {}
    for name, path in videos.items():
        tj = out / f"{name}.json"
        if not tj.exists():
            wav = out / f"{name}.wav"
            _audio(path, wav)
            print(f"[takes] transcribing {name} ({transcribe.transcribe(wav, tj)})")
        take_words[name] = [w for s in json.loads(tj.read_text())["segments"] for w in s["words"]]
    main = next(iter(videos))
    plan = propose(sections, take_words, main)
    print(f"{'section':28} {'take':34} {'from':>8} {'to':>8} score")
    for p in plan:
        print(f"{p['section'][:28]:28} {str(p['take'])[:34]:34} {p.get('from', 0):8.2f} {p.get('to', 0):8.2f} {p['score']:.2f}")
    missing = [p["section"] for p in plan if not p["take"]]
    if missing:
        print(f"[takes] no attempt found for: {', '.join(missing)}. Add those segments to edit.json by hand.")
    for p in plan:
        for a, b in p.get("drop", []):
            print(f"[takes]   {p['section']}: dropped a restarted line {a:.2f}s to {b:.2f}s")
    edit = {"takes": videos, "segments": merge_segments([seg for p in plan if p["take"] for seg in segments_for(p)])}
    (out / "edit.json").write_text(json.dumps(edit, indent=2) + "\n")
    print(f"[takes] wrote {out / 'edit.json'}. Read it, fix by hand if needed, then: takes.py splice {out}")


def cmd_splice(args):
    out = Path(args.dir)
    edit = json.loads((out / "edit.json").read_text())
    names = list(edit["takes"])
    index_of = {n: i for i, n in enumerate(names)}
    segs = edit["segments"]
    bad = [s for s in segs if s["take"] not in index_of or s["to"] <= s["from"]]
    if bad:
        sys.exit(f"bad segments: {bad}")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    for n in names:
        cmd += ["-i", edit["takes"][n]]
    master = out / "master.mp4"
    cmd += ["-filter_complex", _filter(segs, index_of), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-g", "30", "-c:a", "aac", "-b:a", "256k", str(master)]
    subprocess.run(cmd, check=True)
    print(f"[takes] {master}")
    print(f"[takes] joins (put these in job.json punches): {splice_points(segs)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan"); a.add_argument("script"); a.add_argument("videos", nargs="+"); a.add_argument("--out", required=True)
    a.set_defaults(fn=cmd_plan)
    a = sub.add_parser("splice"); a.add_argument("dir"); a.set_defaults(fn=cmd_splice)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
