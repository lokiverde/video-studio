"""Pure logic for the talking-head wrapper. No I/O here, so it is cheap to test.

Every cue time in a job is written in SOURCE seconds (what Tony said, when). Cuts
remove ranges of the source, so anything placed on the output timeline goes through
to_output() first."""
import re
from pathlib import PurePath

import th_army

MAX_CAPTION_WORDS = 7
CAPTION_GAP = 0.6
CAPTION_TAIL = 0.15


def to_output(t, cuts):
    removed = 0.0
    for start, end in sorted(cuts):
        if t >= end:
            removed += end - start
        elif t > start:
            removed += t - start
    return t - removed


def in_cut(t, cuts):
    return any(start <= t < end for start, end in cuts)


def _cut_overlap(s, e, cuts):
    return sum(max(0.0, min(e, end) - max(s, start)) for start, end in cuts)


def _word_survives(s, e, cuts):
    """ASR word starts lead the sound by 0.2 to 0.3 s, so a start stamp a hair inside
    a cut does not mean the word was cut. Keep it while most of its span still plays."""
    return not in_cut(s, cuts) or 2 * _cut_overlap(s, e, cuts) < e - s


def _past_cuts(t, cuts):
    """A time inside a cut moves to that cut's end (and past any cut touching it)."""
    for start, end in sorted(cuts):
        if start <= t < end:
            t = end
    return t


def _norm(token):
    return re.sub(r"[^a-z0-9%-]", "", token.lower())


def _apply_fixes(tokens, fixes):
    """Replace misheard phrases. Returns a new token list, originals untouched."""
    out = [dict(t) for t in tokens]
    for wrong, right in fixes or []:
        want = [_norm(w) for w in wrong.split()]
        repl = right.split()
        i = 0
        while i <= len(out) - len(want):
            if [_norm(t["t"]) for t in out[i:i + len(want)]] == want:
                merged = {"s": out[i]["s"], "e": out[i + len(want) - 1]["e"], "t": " ".join(repl)}
                out = out[:i] + [merged] + out[i + len(want):]
            i += 1
    return out


def _is_split_tail(prev, tok):
    """"-8" and "%" always attach. ",500" and ".7" attach only to a number ("$4", "8")."""
    if re.match(r"^[-%]", tok):
        return True
    return bool(re.match(r"^[.,]\d", tok) and re.search(r"\d$", prev))


def _glue_split_tokens(tokens):
    """Whisper emits "1120", "-8", "70", "%", "$4", ",500" and "8", ".7" as separate
    words. Join them back so captions read right and caption fixes can match."""
    out = []
    for tok in tokens:
        if out and _is_split_tail(out[-1]["t"], tok["t"]):
            out[-1] = {"s": out[-1]["s"], "e": tok["e"], "t": out[-1]["t"] + tok["t"]}
        else:
            out.append(dict(tok))
    return out


def _tokens(words, cuts):
    return [
        {"s": _past_cuts(w["start"], cuts), "e": w["end"], "t": w["word"].strip().replace("—", ", ").replace("–", ", ")}
        for w in words
    ]


def _fix_restores(tokens, fixes, word):
    """Older jobs patch a word the cut ate with a caption fix ("I like about it" to
    "What I like about it"). True when a fix matches right where `word` would go and
    adds it back, so keeping the word as well would print it twice."""
    pos = sum(1 for t in tokens if t["s"] < word["start"])
    target = _norm(word["word"].strip())
    got = [_norm(t["t"]) for t in tokens]
    for wrong, right in fixes or []:
        want = [_norm(w) for w in wrong.split()]
        if [_norm(w) for w in right.split()].count(target) <= want.count(target):
            continue
        if any(got[i:i + len(want)] == want for i in range(max(0, pos - len(want)), pos + 1)):
            return True
    return False


def _caption_words(words, cuts, src_end, fixes):
    spoken = [w for w in words if w["word"].strip() and w["start"] <= src_end]
    base = _glue_split_tokens(_tokens([w for w in spoken if not in_cut(w["start"], cuts)], cuts))
    return [
        w for w in spoken
        if not in_cut(w["start"], cuts)
        or (_word_survives(w["start"], w["end"], cuts) and not _fix_restores(base, fixes, w))
    ]


def build_captions(words, cuts, src_end, fixes=None, max_words=MAX_CAPTION_WORDS):
    tokens = _tokens(_caption_words(words, cuts, src_end, fixes), cuts)
    tokens = _apply_fixes(_glue_split_tokens(tokens), fixes)
    chunks, cur, count = [], [], 0
    for tok in tokens:
        n = len(tok["t"].split())
        if cur and (tok["s"] - cur[-1]["e"] > CAPTION_GAP or count + n > max_words or re.search(r"[.?!]$", cur[-1]["t"])):
            chunks.append(cur)
            cur, count = [], 0
        cur.append(tok)
        count += n
    if cur:
        chunks.append(cur)
    return [
        {
            "s": round(to_output(c[0]["s"], cuts), 2),
            "e": round(to_output(c[-1]["e"], cuts) + CAPTION_TAIL, 2),
            "t": " ".join(t["t"] for t in c),
        }
        for c in chunks
    ]


CUT_EDGE_WINDOW = 0.3
CUT_EDGE_PAD = 0.02


def cut_edge_words(words, cuts, src_end, window=CUT_EDGE_WINDOW):
    """Words a cut edge catches: the start stamp sits inside a cut within `window` of its
    end, or the end stamp sits inside a cut within `window` of its start. Each hit says
    what the captions do with the word ("kept", "dropped", "clipped" when its tail is
    cut) and the cut edge that would clear it."""
    hits = []
    for w in words:
        s, e, text = w["start"], w["end"], w["word"].strip()
        if not text or s > src_end:
            continue
        for start, end in sorted(cuts):
            hit = {"word": text, "start": s, "end": e, "cut": [start, end]}
            if start <= s < end and end - s <= window:
                fate = "kept" if _word_survives(s, e, cuts) else "dropped"
                hits.append({**hit, "edge": "end", "fate": fate, "suggest": round(s - CUT_EDGE_PAD, 2)})
            elif start < e <= min(start + window, end):
                fate = "clipped" if s < start else "dropped"
                hits.append({**hit, "edge": "start", "fate": fate, "suggest": round(e + CUT_EDGE_PAD, 2)})
    return hits


def find_phrase(words, phrase):
    want = [_norm(w) for w in phrase.split()]
    got = [_norm(w["word"]) for w in words]
    return [words[i]["start"] for i in range(len(got) - len(want) + 1) if got[i:i + len(want)] == want]


def suggest_cuts(silences, min_len=2.5, pad=0.35):
    """Long silences are probably dead air. Keep `pad` seconds on each side so the
    cut does not clip a breath."""
    return [[round(s + pad, 2), round(e - pad, 2)] for s, e in silences if e - s >= min_len]


def _block_times(block):
    times = []
    for key in ("at", "xAt", "noteAt", "dangerAt"):
        if isinstance(block.get(key), (int, float)):
            times.append(block[key])
    for part in block.get("parts", []):
        if isinstance(part, dict):
            times.append(part["at"])
    for item in block.get("items", []):
        times.append(item["at"])
    icons = block.get("icons")
    if isinstance(icons, dict) and isinstance(icons.get("at"), (int, float)):
        times.append(icons["at"])
    return times


STUDIO_THEMES = {"light", "blush", "lime", "periwinkle", "dark", "crimson", "midnight", "glow", "paper"}
STYLES = {"evidence", "studio", "news", "board", "army"}
PUNCH_STYLES = {"studio", "news", "board", "army"}
# board style: "full" (Peverelli, graphics take the whole frame) or "split" (quiz tips look,
# Simon Scrapes: Tony stays on the right third, graphics in a light card on the left)
BOARD_LAYOUTS = {"full", "split"}
# split layout: a big countdown number sweeps across before each item; the sheet shows it here
WIPE_SHEET_S = 0.25
# news style: typed lines over Tony, cutout stickers beside him, framed photo cutaways
TYPED_COLORS = {"green", "red", "amber"}
STICKER_POSITIONS = {"left", "right", "bottom-left", "bottom-right"}
CUTAWAY_FITS = {"cover", "blur"}
TYPED_SHEET_LEAD = 0.3   # the sheet shows a typed line just before it leaves, fully typed


def punch_boundaries(job):
    """Studio and news styles alternate a wide and a tight framing on Tony, switching at
    every cut (it hides the jump) and at any extra `punches` moments on a long take."""
    if job.get("style") not in PUNCH_STYLES or job.get("punch") is False:
        return []
    return sorted({end for _, end in job.get("cuts", [])} | set(job.get("punches", [])))


def cue_times(job):
    times = {t for s in job.get("sections", []) for b in s.get("blocks", []) for t in _block_times(b)}
    return sorted(times)


def sheet_moments(job):
    """Source-second moments the contact sheet should show: the hook, each question tag,
    a beat after every cue, and the middle of every cutaway."""
    hook = job.get("hook")
    moments = [hook["from"] + 2.0] if hook else []
    moments += [s["tag"]["from"] + 1.0 for s in job.get("sections", []) if s.get("tag")]
    moments += [t + 0.9 for t in cue_times(job)]
    moments += [(c["from"] + c["to"]) / 2 for c in job.get("cutaways", [])]
    moments += [p["from"] + 1.2 for p in job.get("phrases", [])]
    moments += [t["to"] - TYPED_SHEET_LEAD for t in job.get("typed", [])]
    moments += [s["from"] + 1.0 for s in job.get("stickers", [])]
    lower = job.get("lowerThird") or []
    moments += [item["from"] + 1.5 for item in (lower if isinstance(lower, list) else [lower])]
    if job.get("counter"):
        moments.append(job["counter"]["from"] + 1.2)
    moments += [min(show["from"] + 1.2, show["to"] - 0.1) for show in (job.get("board") or {}).get("shows", [])]
    moments += [show["from"] + WIPE_SHEET_S for show in wipe_shows(job)]
    moments += th_army.sheet_moments(job)
    return sorted(set(moments))


def wipe_shows(job):
    """Split layout: the board shows that open with a number wipe (every lit item, not the
    teaser). `board.wipe: false` turns the wipe off."""
    board = job.get("board") or {}
    if job.get("layout") != "split" or board.get("wipe") is False:
        return []
    return [show for show in board.get("shows", []) if show.get("active", -1) >= 0]


def _visual_events(job):
    """Every source-second moment where the picture changes."""
    events = {0.0, float(job["srcEnd"])}
    hook = job.get("hook")
    if hook:
        n = max(1, len(hook.get("broll", [])))
        events.update(hook["from"] + i * (hook["to"] - hook["from"]) / n for i in range(n + 1))
    lower = job.get("lowerThird") or []
    for item in (lower if isinstance(lower, list) else [lower]):
        events.add(item["from"])
    if job.get("counter"):
        events.add(job["counter"]["from"])
    for section in job.get("sections", []):
        events.update(section["evidence"])
        if section.get("tag"):
            events.add(section["tag"]["from"])
    events.update(cue_times(job))
    for c in job.get("cutaways", []):
        events.update((c["from"], c["to"]))
    for key in ("phrases", "typed", "stickers"):
        for item in job.get(key, []):
            events.update((item["from"], item["to"]))
    for show in (job.get("board") or {}).get("shows", []):
        events.update((show["from"], show["to"]))
    events.update(punch_boundaries(job))
    events.update(th_army.visual_events(job))
    return sorted(e for e in events if 0 <= e <= job["srcEnd"])


def static_stretches(job, max_gap=7.0):
    """Stretches longer than max_gap OUTPUT seconds where nothing on screen changes.
    Tony's rule: past about 7 seconds of the same picture, cut to a still or a clip."""
    cuts = job.get("cuts", [])
    events = _visual_events(job)
    found = []
    for start, end in zip(events, events[1:]):
        if to_output(end, cuts) - to_output(start, cuts) <= max_gap:
            continue
        found.append({"from": start, "to": end, "seconds": round(to_output(end, cuts) - to_output(start, cuts), 1),
                      "showing": _showing(job, (start + end) / 2)})
    return found


def _showing(job, t):
    """What fills the screen at source second t, for the pacing warning."""
    if any(s["evidence"][0] <= t < s["evidence"][1] for s in job.get("sections", [])):
        return "evidence panel"
    beat = next((b for b in job.get("beats", []) if b["from"] <= t < b["to"]), None)
    if beat and beat["layout"] == "graphic":
        return f"{beat['graphic']['type']} graphic"
    if beat and beat["layout"] == "split":
        if th_army.is_media(beat):
            return "screen recording beside Tony" if th_army.is_clip(beat) else "article shot beside Tony"
        return f"{beat['graphic']['type']} graphic beside Tony"
    if th_army.is_army(job) and any(a <= t < b for a, b in th_army.inset_runs(job)):
        return "Tony in the inset"
    return "Tony full frame"


MIN_CHAPTER_GAP = 10.0   # YouTube ignores chapters closer together than this


def _srt_clock(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_srt(captions):
    """Captions are already on the output timeline. A cue is trimmed if it would run
    into the next one, players show overlapping cues stacked."""
    out = []
    for i, cap in enumerate(captions):
        end = min(cap["e"], captions[i + 1]["s"]) if i + 1 < len(captions) else cap["e"]
        out.append(f"{i + 1}\n{_srt_clock(cap['s'])} --> {_srt_clock(end)}\n{cap['t']}\n\n")
    return "".join(out)


def chapters(job, intro="Intro"):
    """YouTube timeline from the question tags, on the OUTPUT timeline. First chapter is
    always 0:00. A section with no tag can name itself with a "chapter" key, and a job
    can list `chapters` [{at, label}] for moments that have no section (news style).
    Board style: every show that lights an item is a chapter ("#5 Cost"); the teaser is not."""
    cuts = job.get("cuts", [])
    found = [(0.0, intro)]
    marks = [(c["at"], c["label"]) for c in job.get("chapters", [])] + th_army.chapter_marks(job)
    board = job.get("board") or {}
    for show in board.get("shows", []):
        if show.get("active", -1) >= 0:
            item = board["items"][show["active"]]
            marks.append((show["from"], " ".join(filter(None, [item.get("tag"), item["label"]]))))
    for section in job.get("sections", []):
        tag = section.get("tag")
        if tag:
            marks.append((tag["from"], f"{tag['n']}. {tag['topic']}"))
        elif section.get("chapter"):
            marks.append((section["evidence"][0], section["chapter"]))
    for start, label in sorted(marks):
        at = round(to_output(start, cuts), 1)
        if at - found[-1][0] >= MIN_CHAPTER_GAP:
            found.append((at, label))
    return found


def job_files(job):
    """Every file the render reads from public/, in a stable order, no duplicates."""
    names = [job["source"], *job.get("hook", {}).get("broll", []), *[c["file"] for c in job.get("cutaways", [])]]
    blocks = [b for s in job.get("sections", []) for b in s.get("blocks", [])]
    names += [b["file"] for b in blocks if b.get("type") in ("screen", "receipt")]
    names += [b["logo"] for b in blocks if b.get("type") == "pullquote" and b.get("logo")]
    names += [s["file"] for s in job.get("stickers", [])]
    names += th_army.media_files(job)
    return list(dict.fromkeys(names))


def _validate_cutaways(job):
    problems = []
    cuts = job.get("cuts", [])
    spans = sorted((c["from"], c["to"], c["file"]) for c in job.get("cutaways", []))
    for start, end, name in spans:
        if not 0 <= start < end <= job["srcEnd"]:
            problems.append(f"cutaway {name}: bad range [{start}, {end}] (video ends at {job['srcEnd']})")
        if any(start < cut_end and end > cut_start for cut_start, cut_end in cuts):
            problems.append(f"cutaway {name}: [{start}, {end}] runs into a cut")
    for (_, end_a, name_a), (start_b, _, name_b) in zip(spans, spans[1:]):
        if start_b < end_a:
            problems.append(f"cutaways {name_a} and {name_b} overlap")
    for c in job.get("cutaways", []):
        if c.get("fit", "cover") not in CUTAWAY_FITS:
            problems.append(f"cutaway {c['file']}: unknown fit {c['fit']!r}, use one of {sorted(CUTAWAY_FITS)}")
    return problems


def _span_problem(job, start, end):
    """Why an on-screen item cannot sit at [start, end], or None."""
    cuts = job.get("cuts", [])
    if not 0 <= start < end <= job["srcEnd"]:
        return f"bad range [{start}, {end}]"
    if in_cut(start, cuts) or any(start < cut_start < end for cut_start, _ in cuts):
        return f"[{start}, {end}] runs into a cut"
    return None


def _validate_typed(job):
    problems = []
    lines = sorted(job.get("typed", []), key=lambda t: t["from"])
    for line in lines:
        text = line.get("text", "")
        problem = _span_problem(job, line["from"], line["to"])
        if problem:
            problems.append(f"typed {text!r}: {problem}")
        for hl in line.get("hl", []):
            if hl["text"] not in text:
                problems.append(f"typed {text!r}: highlight {hl['text']!r} is not in the line")
            if hl.get("color", "green") not in TYPED_COLORS:
                problems.append(f"typed {text!r}: unknown color {hl['color']!r}, use one of {sorted(TYPED_COLORS)}")
    for a, b in zip(lines, lines[1:]):
        if b["from"] < a["to"]:
            problems.append(f"typed {a.get('text', '')!r} and {b.get('text', '')!r} overlap")
    return problems


def _validate_stickers(job):
    problems = []
    for s in job.get("stickers", []):
        problem = _span_problem(job, s["from"], s["to"])
        if problem:
            problems.append(f"sticker {s['file']}: {problem}")
        if s.get("pos", "left") not in STICKER_POSITIONS:
            problems.append(f"sticker {s['file']}: unknown pos {s['pos']!r}, use one of {sorted(STICKER_POSITIONS)}")
    return problems


def validate(job):
    problems = []
    for key in ("title", "source", "srcEnd", "sections"):
        if key not in job:
            problems.append(f"missing required field: {key}")
    if problems:
        return problems
    if job.get("style", "evidence") not in STYLES:
        problems.append(f"unknown style {job['style']!r}, use one of {sorted(STYLES)}")
    layout = job.get("layout")
    if layout is not None and layout not in BOARD_LAYOUTS:
        problems.append(f"unknown layout {layout!r}, use one of {sorted(BOARD_LAYOUTS)}")
    elif layout == "split" and job.get("style") != "board":
        problems.append("layout 'split' is a board style layout, set style to 'board'")
    cuts = job.get("cuts", [])
    for start, end in cuts:
        if not 0 <= start < end <= job["srcEnd"]:
            problems.append(f"bad cut [{start}, {end}]")
    for i, section in enumerate(job["sections"], 1):
        lo, hi = section["evidence"]
        if lo >= hi:
            problems.append(f"section {i}: evidence window [{lo}, {hi}] is empty")
        for block in section.get("blocks", []):
            for t in _block_times(block):
                if not lo <= t <= hi:
                    problems.append(f"section {i}: {block['type']} cue at {t} is outside its evidence window [{lo}, {hi}]")
                if in_cut(t, cuts):
                    problems.append(f"section {i}: {block['type']} cue at {t} lands inside a cut")
        theme = section.get("theme")
        if theme is not None and theme not in STUDIO_THEMES:
            problems.append(f"section {i}: unknown theme {theme!r}, use one of {sorted(STUDIO_THEMES)}")
    return (problems + _validate_cutaways(job) + _validate_phrases(job) + _validate_typed(job)
            + _validate_stickers(job) + _validate_board(job) + _validate_receipts(job) + th_army.validate(job))


def _validate_board(job):
    """Board shows: inside the video, clear of cuts, pointing at real items, never on top of
    a section (the board is full screen, it would hide the panel)."""
    board = job.get("board")
    if not board:
        return []
    items, problems = board.get("items", []), []
    if "wipe" in board and not isinstance(board["wipe"], bool):
        problems.append(f"board wipe {board['wipe']!r}: use true or false")
    for i, show in enumerate(board.get("shows", []), 1):
        start, end = show["from"], show["to"]
        if not 0 <= start < end <= job["srcEnd"]:
            problems.append(f"board show {i}: bad range [{start}, {end}], past the end or backwards")
            continue
        if any(start < b < end for b, _ in job.get("cuts", [])) or in_cut(start, job.get("cuts", [])):
            problems.append(f"board show {i}: [{start}, {end}] runs into a cut")
        # active -1: a teaser show with no card lit (the board before #5)
        if not -1 <= show.get("active", -1) < len(items):
            problems.append(f"board show {i}: active {show.get('active')} is not one of the {len(items)} items")
        if not 0 <= show.get("revealed", 0) <= len(items):
            problems.append(f"board show {i}: revealed {show.get('revealed')} is more than the {len(items)} items")
        for k, s in enumerate(job.get("sections", []), 1):
            lo, hi = s["evidence"]
            if start < hi and lo < end:
                problems.append(f"board show {i}: [{start}, {end}] overlaps section {k} [{lo}, {hi}]")
    return problems


def _bad_box(box):
    return len(box) != 4 or not all(0 <= v <= 1 for v in box) or box[0] + box[2] > 1.001 or box[1] + box[3] > 1.001


def _validate_receipts(job):
    """Receipt boxes are [x, y, w, h] fractions of the image: `highlight` is the whole quote
    (the push aims at it), `lines` one box per line (what gets drawn, from tools/receipts)."""
    problems = []
    for i, s in enumerate(job.get("sections", []), 1):
        for b in s.get("blocks", []):
            if b.get("type") != "receipt":
                continue
            for box in ([b["highlight"]] if b.get("highlight") is not None else []) + list(b.get("lines", [])):
                if _bad_box(box):
                    problems.append(f"section {i}: receipt highlight {box} must be [x, y, w, h] fractions of the image")
    return problems


def _validate_phrases(job):
    problems = []
    for p in job.get("phrases", []):
        start, end, text = p["from"], p["to"], p.get("text", "")
        if not 0 <= start < end <= job["srcEnd"]:
            problems.append(f"phrase {text!r}: bad range [{start}, {end}]")
        elif in_cut(start, job.get("cuts", [])) or any(start < b < end for b, _ in job.get("cuts", [])):
            problems.append(f"phrase {text!r}: [{start}, {end}] runs into a cut")
    return problems


# ---- voice enhancement ------------------------------------------------------------
# Webcam and room audio: rumble, hiss, boxy low mids, uneven level, a few clipped peaks.
# Order matters: clean first, then tone, then dynamics, then a hard ceiling.
LOUDNESS_TARGET = {"I": -14, "TP": -1.5, "LRA": 7}   # YouTube and Instagram normalize near -14 LUFS


# Voice presets. Each: highpass, EQ bands [(Hz, type, width, gain dB)], compressor
# (threshold dB, ratio), and whether to gate the pauses.
# "studio" (default since 2026-09-27) is fitted to Tony's Adobe Podcast Enhance render:
# measured against the raw take, Adobe cut 4 kHz about 4 dB and 8 kHz about 3 dB, added
# about 1 dB at 125 to 250 Hz, kept dynamics natural (crest factor ~11) and left the
# pauses dead silent. It cannot copy Adobe's AI de-reverb; `th.py enhance --adobe` swaps
# in the real Adobe audio for that. "broadcast" is the chest-boost try from the same day,
# "clean" the original brighter chain. No pitch shift: no rubberband in this ffmpeg, and a
# plain pitch drop moves the formants and sounds robotic.
VOICE_PRESETS = {
    "clean": {"hp": 80, "comp": (-21, 3.0), "gate": False, "eq": [
        (280, "q", 1.1, -3.0), (3200, "q", 1.4, 3.0), (11000, "h", 0.7, 2.0)]},
    "broadcast": {"hp": 70, "comp": (-23, 3.5), "gate": False, "eq": [
        (120, "q", 1.0, 3.5), (280, "q", 1.1, -3.5), (3200, "q", 1.4, 2.5), (11000, "h", 0.7, 1.0)]},
    # Fitted by measurement to Tony's Adobe Enhance render of the Riverside take
    # (5 passes, 0.4 dB mean band error, crest 9.5 vs Adobe 11). Re-fit if the mic changes.
    "studio": {"hp": 70, "nr": 12, "deess": False, "comp": (-20, 1.6, 10, 150, 1), "gate": True, "eq": [
        (63, "q", 1.0, -4.6), (125, "q", 1.0, 1.0), (250, "q", 1.0, -1.0), (500, "q", 1.0, -2.2),
        (1000, "q", 1.0, -0.1), (2000, "q", 1.0, -1.8), (4000, "q", 1.0, -5.3), (8000, "q", 1.0, -4.5),
        (12000, "q", 1.0, 0.7)]},
}
DEFAULT_VOICE = "studio"
EXTERNAL_TOLERANCE_S = 0.25   # an enhanced track must line up with the footage


def voice_chain(noise_floor, preset=DEFAULT_VOICE):
    if preset not in VOICE_PRESETS:
        raise ValueError(f"unknown voice preset '{preset}', pick one of {sorted(VOICE_PRESETS)}")
    v = VOICE_PRESETS[preset]
    nf = round(min(-20.0, max(-80.0, noise_floor)))
    thresh, ratio, attack, release, makeup = (*v["comp"], 6, 120, 2)[:5] if len(v["comp"]) == 2 else v["comp"]
    return ",".join([
        f"highpass=f={v['hp']}",                           # rumble and desk thumps
        f"afftdn=nr={v.get('nr', 14)}:nf={nf}:tn=1",       # steady room hiss, tracks the floor
        *[f"equalizer=f={hz}:t={t}:w={w}:g={g}" for hz, t, w, g in v["eq"]],
        *(["deesser=i=0.35"] if v.get("deess", True) else []),   # S's
        f"acompressor=threshold={thresh}dB:ratio={ratio}:attack={attack}:release={release}:makeup={makeup}dB",
        # after compression, so makeup gain never lifts the room back up in the pauses
        *(["agate=threshold=0.012:ratio=6:attack=4:release=250:range=0.03"] if v["gate"] else []),
        "alimiter=limit=0.89:attack=3:release=60",
    ])


# Local AI voice (DEFAULT since 2026-09-27, Tony: "6 sounds great"). Resemble Enhance
# (~/video-studio/.venv-enhance, enhance_voice.py, CPU only: MPS returns noise) removes
# echo and noise and rebuilds the treble like Adobe Podcast Enhance; this EQ, fitted to
# Tony's Adobe render, closes the rest. Delivered at -14 LUFS it measured 0.3 dB from Adobe.
LOCAL_AI_EQ = [(63, -2.9), (125, -1.8), (250, 0.2), (500, -2.5), (1000, -0.9),
               (2000, -0.2), (4000, -6.7), (8000, -2.1), (12000, -2.9)]
FINAL_VOICES = ("ai", "adobe", "room")   # room: denoise-only for class and room recordings (room_voice.py)


def local_ai_eq_chain():
    return ",".join(f"equalizer=f={hz}:t=q:w=1.0:g={g}" for hz, g in LOCAL_AI_EQ)


def voice_is_final(state):
    return state.get("voice") in FINAL_VOICES


def external_level_chain(input_lufs, target=None, extra_db=0.0):
    """Adobe keeps a wide crest factor, so linear loudnorm refuses to lift it all the way
    (it stopped at -15.7). A straight gain to -14 LUFS plus a fast limiter at -1.5 dBTP only
    touches the few loudest syllables and leaves the tone alone."""
    target = LOUDNESS_TARGET["I"] if target is None else target
    gain = round(target - float(input_lufs) + extra_db, 1)
    # 4x oversampling around the limiter approximates true-peak limiting; without it the
    # preset path measured +1.1 dBTP after AAC encoding.
    return (f"volume={gain}dB,aresample=192000,"
            f"alimiter=limit=0.79:attack=2:release=50:level=disabled,aresample=48000")


def external_audio_problem(footage_s, audio_s, tolerance=EXTERNAL_TOLERANCE_S):
    """None when an externally enhanced track (Adobe) lines up with the footage."""
    gap = audio_s - footage_s
    if gap > tolerance:
        return f"enhanced audio is {gap:.2f}s longer than the footage"
    if gap < -tolerance:
        return f"enhanced audio is {-gap:.2f}s shorter than the footage"
    return None


def loudnorm_pass1():
    t = LOUDNESS_TARGET
    return f"loudnorm=I={t['I']}:TP={t['TP']}:LRA={t['LRA']}:print_format=json"


def loudnorm_pass2(measured):
    t = LOUDNESS_TARGET
    return (f"loudnorm=I={t['I']}:TP={t['TP']}:LRA={t['LRA']}"
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")


# ---- background music ---------------------------------------------------------------
# A quiet bed that ducks under Tony's voice and comes up in the pauses and the end card.
# Mixed after the render, so swapping or removing a track never needs a re-render.
MUSIC_BED_LUFS = -30.0   # about 16 LU under the -14 LUFS voice, felt more than heard


def music_gain(track_lufs, bed_lufs=MUSIC_BED_LUFS):
    return round(bed_lufs - track_lufs, 1)


def music_rerun_args(music, switch=None):
    """`th.py music` arguments that repeat the job's last run from state.json["music"], for a
    re-mix after a voice swap. Runs before 2026-11-10 did not record --switch, --hook-level or
    --no-sfx: those fall back to the defaults, and a run that mixed no SFX mixes none again."""
    hook = music.get("hook")
    return {"track": PurePath(music["track"]).stem, "level": music["level"],
            "hook_track": PurePath(hook).stem if hook else None,
            "hook_level": music.get("hook_level", MUSIC_BED_LUFS + 2),
            "switch": switch if switch is not None else music.get("switch"),
            "no_sfx": music.get("no_sfx", not music.get("sfx"))}


def music_filter(gain_db, total, fade_in=1.5, fade_out=3.0):
    """Input 0 is the rendered video (voice), input 1 the looped music track."""
    return (
        "[0:a]asplit=2[voice][key];"
        f"[1:a]volume={gain_db:.1f}dB,afade=t=in:d={fade_in:.3f}[bed];"
        "[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600:makeup=1[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:normalize=0,"
        f"afade=t=out:st={total - fade_out:.3f}:d={fade_out:.3f},"
        "alimiter=limit=0.89[out]"
    )


# True-peak limiter at the end of the music mix: 4x oversampled, -3 dBFS (SFX transients overshoot about
# 1.3 dB in the AAC encode, so -2 was not enough), auto level OFF.
# ffmpeg's alimiter defaults to level=true, which multiplies the output by 1/limit, so a mix
# that reached the limiter landed at 0 dBFS (bizplan music cuts measured -0.1 dBTP, 2026-11-10).
MIX_LIMITER = "aresample=192000,alimiter=limit=0.71:attack=2:release=50:level=disabled,aresample=48000"


def mix_filter(bed_gain, total, hook_gain=None, switch=None, sfx=False, xfade=2.0, fade_out=3.0):
    """Final audio: Tony's voice, a ducked music bed, an optional suspense track under the
    hook, and an optional SFX track. Inputs: 0 the rendered video, 1 the bed, 2 the hook
    track when hook_gain is set, then the SFX wav. The hook fades out over `xfade` seconds
    ending at `switch` (output seconds, the first "Number N") while the bed fades in."""
    hook = hook_gain is not None
    start = max((switch or 0.0) - xfade, 0.0)
    keys = "[k1][k2]" if hook else "[k1]"
    parts = [f"[0:a]asplit={2 + hook}[voice]{keys}"]
    bed_in = f"afade=t=in:st={start:.3f}:d={xfade:.3f}" if hook else "afade=t=in:d=1.5"
    parts.append(f"[1:a]volume={bed_gain:.1f}dB,{bed_in}[bed]")
    parts.append("[bed][k1]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600:makeup=1[db]")
    mix = "[voice][db]"
    if hook:
        parts.append(f"[2:a]volume={hook_gain:.1f}dB,afade=t=in:d=1.0,afade=t=out:st={start:.3f}:d={xfade:.3f}[hook]")
        parts.append("[hook][k2]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600:makeup=1[dh]")
        mix += "[dh]"
    if sfx:
        parts.append(f"[{2 + hook}:a]anull[fx]")
        mix += "[fx]"
    n = 2 + hook + sfx
    parts.append(f"{mix}amix=inputs={n}:duration=first:normalize=0,"
                 f"afade=t=out:st={total - fade_out:.3f}:d={fade_out:.3f},{MIX_LIMITER}[out]")
    return ";".join(parts)


# ---- sound effects ----------------------------------------------------------------
# Peverelli's rule, adopted 2026-10-12: a sound only where the picture does something.
SFX_MIN_GAP = 0.3          # output seconds between two effects, closer ones stack into mush
RISER_S = 1.6              # the riser is cut to this length and ends as the board lands
SFX_PRIORITY = {"impact": 5, "riser": 4, "whoosh": 3, "pop": 2, "click": 2, "tick": 1}
POP_BLOCKS = {"headline", "bigstat", "pullquote", "receipt", "screen", "quote", "stat", "cta", "note"}


# must match SPAN_GAP_S in talking-head/src/boardSpans.ts (graphics this close read as one run)
BOARD_SPAN_GAP_S = 0.8


def _raw_sfx(job):
    """(source seconds, kind) for everything that moves on screen."""
    raw = []
    board = job.get("board") or {}
    last = len(board.get("items", [])) - 1
    for show in board.get("shows", []):
        final = show.get("active") == last and show.get("revealed") == last + 1
        raw += [(show["from"] - RISER_S, "riser"), (show["from"], "impact" if final else "whoosh")]
    board_style = job.get("style") == "board"
    # board: the whoosh means "full screen comes in", so only the first graphic of a run gets
    # one; a swap inside a run (gap <= BOARD_SPAN_GAP_S) only pops its card
    ends = [s["evidence"][1] for s in job.get("sections", [])] + [sh["to"] for sh in board.get("shows", [])]
    for sec in job.get("sections", []):
        start = sec["evidence"][0]
        mid_run = board_style and any(0 <= start - e <= BOARD_SPAN_GAP_S for e in ends)
        if (board_style and not mid_run) or (not board_style and sec.get("full")):
            raw.append((start, "whoosh"))
        for b in sec.get("blocks", []):
            if b.get("type") in POP_BLOCKS and "at" in b:
                raw.append((b["at"], "pop"))
            items = b.get("items", [])
            if b.get("type") in ("steps", "list") and items:
                raw += [(items[0]["at"], "pop")] + [(it["at"], "tick") for it in items[1:]]
            elif b.get("type") == "bars" and items:
                raw.append((items[0]["at"], "pop"))
    for key in ("typed", "stickers"):
        raw += [(item["from"], "pop") for item in job.get(key, [])]
    lower = job.get("lowerThird") or []
    raw += [(item["from"], "pop") for item in (lower if isinstance(lower, list) else [lower])]
    raw += th_army.sfx(job)
    if job.get("endCard"):
        raw.append((job["srcEnd"], "whoosh"))
    return raw


def sfx_cues(job):
    """Effects on the OUTPUT timeline: [{t, kind}]. job["sfx"] = False turns them off, or
    {"mute": [source seconds], "add": [{at, kind}]} adjusts them. When two land closer than
    SFX_MIN_GAP the stronger one wins (impact > riser > whoosh > pop > tick)."""
    cfg = job.get("sfx", {})
    if cfg is False:
        return []
    cfg = cfg or {}
    cuts = job.get("cuts", [])
    raw = _raw_sfx(job) + [(a["at"], a["kind"]) for a in cfg.get("add", [])]
    muted = cfg.get("mute", [])
    raw = [(t, k) for t, k in raw if t >= 0 and not in_cut(t, cuts) and not any(abs(t - m) < 0.05 for m in muted)]
    kept = []
    for t, kind in sorted(raw, key=lambda c: (-SFX_PRIORITY.get(c[1], 0), c[0])):
        out = round(to_output(t, cuts), 3)
        if all(abs(out - k["t"]) >= SFX_MIN_GAP for k in kept):
            kept.append({"t": out, "kind": kind})
    return sorted(kept, key=lambda c: c["t"])


# ---- post-render QC ---------------------------------------------------------------
QC_BLACK_MIN_S = 0.25      # shorter black flashes are fades between sections
QC_SILENCE_MIN_S = 2.0     # Tony never pauses this long once dead air is cut
QC_DRIFT_MAX_S = 0.2       # audio and video streams must end together


QC_PAUSE_SLACK_S = 0.3


def qc_problems(black, silences, video_s, audio_s, tail_ok, expected=()):
    """What ffmpeg found in a rendered file, as problems to fix before Tony sees it.
    `tail_ok` is the end card length: silence there is expected. `expected` are the pauses
    Tony left in the source audio, on the output timeline: the render keeping one is fine,
    silence the render made (a dropout, a cut that runs pauses together) is not."""
    problems = [f"black frames {a:.1f}s to {b:.1f}s" for a, b in black if b - a >= QC_BLACK_MIN_S]
    quiet_from = video_s - tail_ok - 0.5

    def tonys(a, b):
        # His own pause, or his last pause (ending where speech ends) running into the silent end card.
        speech_end = video_s - tail_ok - QC_PAUSE_SLACK_S
        return any(ea - QC_PAUSE_SLACK_S <= a and (b <= eb + QC_PAUSE_SLACK_S or (eb >= speech_end and a <= eb))
                   for ea, eb in expected)

    card_from = video_s - tail_ok + 0.5   # only the part before the silent end card is dead air
    problems += [f"silence {a:.1f}s to {b:.1f}s" for a, b in silences
                 if min(b, card_from) - a >= QC_SILENCE_MIN_S and a < quiet_from and not tonys(a, b)]
    if abs(video_s - audio_s) > QC_DRIFT_MAX_S:
        problems.append(f"audio/video drift: video {video_s:.2f}s, audio {audio_s:.2f}s")
    return problems
