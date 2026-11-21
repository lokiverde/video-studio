"""Countdown video (Adam in Austin format): tally research, write the read-aloud script,
draft studio sections and link the quiz. Format and research rules: docs/countdown.md.

  countdown.py tally <job>                  research.json -> countdown.json (validated, ranked)
  countdown.py script <job> [--out PATH]    countdown.json -> read-aloud script (your notes folder)
  countdown.py sections <job> [--apply]     transcript + countdown -> studio sections, endCard, quiz bar
  countdown.py quizlink <job> [--quiz SLUG] quiz and call links in youtube, shorts and the pinned comment
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import th_lib  # noqa: E402

QUIZZES = {
    "neighborhood": {"brand": "siteone", "host": "quiz.siteone.com", "title": "Which neighborhood fits your life?"},
    "investor-type": {"brand": "examplerealty", "host": "quiz.example.com", "title": "What kind of real estate investor are you?"},
    "home-check": {"brand": "sitethree", "host": "quiz.sitethree.com", "title": "Is your home ready to sell?"},
    "buyer-check": {"brand": "sitethree", "host": "quiz.sitethree.com", "title": "Is this the right home for you?"},
    "ai-readiness": {"brand": "techtony", "host": "quiz.techtony.co", "title": "Is your real estate business ready for AI?"},
}
CALL_URL_DEFAULT = "https://calendly.com/your-booking-link"
CALL_KEY = "COUNTDOWN_CALL_URL"
CALL_PREFIX = "Book a free call with Tony:"
QUIZ_MARK = "Take the free quiz:"
SCRIPT_DIR = Path.home() / "Documents" / "video-scripts"
REASONS = (3, 7)
QUOTES = (1, 3)
QUOTE_MAX = 200
NUMBER_WORDS = ["one", "two", "three", "four", "five", "six", "seven"]
MID_ROLL_RANK = 4
THEMES = ["light", "blush", "periwinkle", "dark", "lime", "midnight", "crimson"]
MIN_BEAT_S = 4.0
CTA_LOWER_S = 7.0
CUE_LEAD = 0.35
CUE_MARGIN = 0.2
PINNED = re.compile(r"\n*## Pinned comment\n.*?(?=\n## |\Z)", re.S)
USERNAME = re.compile(r"(^|[^A-Za-z0-9])/?u/[A-Za-z0-9_-]+", re.IGNORECASE)


# ---- small helpers -------------------------------------------------------------------

def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _whole(value, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _join(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, dict) else list(value)


def _load_json(path):
    if not path.exists():
        common.die(f"missing {path.name} in {path.parent}")
    return json.loads(path.read_text())


def _dump(path, data, ascii_only=True):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=ascii_only) + "\n")


def resolve_job(name):
    """A job id under jobs/, or a path to a job folder."""
    path = Path(name).expanduser()
    return path if path.is_dir() else common.job_dir(name)


def load_words(jdir):
    data = _load_json(jdir / "transcript.json")
    return [w for seg in data["segments"] for w in seg.get("words", [])]


# ---- quiz and call registry -----------------------------------------------------------

def quiz_for(slug):
    """Registry entry for a quiz slug: host, public URL base and title."""
    entry = QUIZZES[slug]
    host = entry["host"]
    return {"slug": slug, "brand": entry["brand"], "host": host, "title": entry["title"],
            "url_base": f"https://{host}/{slug}"}


def quiz_host_path(quiz):
    return f"{quiz['host']}/{quiz['slug']}"


def call_url():
    """Booking link. Order: environment, config.env, then Tony's standard Calendly link."""
    return os.environ.get(CALL_KEY) or common.load_config().get(CALL_KEY) or CALL_URL_DEFAULT


# ---- research.json validation ----------------------------------------------------------

def validate_research(data):
    """Every problem with a research.json, as plain sentences. Empty list means valid."""
    if not isinstance(data, dict):
        return ["research.json must be a JSON object"]
    problems = [f"missing {key}" for key in ("question", "topic", "place") if not _text(data.get(key))]
    if data.get("quiz") not in QUIZZES:
        problems.append(f"unknown quiz {data.get('quiz')!r}, use one of {sorted(QUIZZES)}")
    problems += _source_problems(data.get("sources"))
    reasons = data.get("reasons")
    if not isinstance(reasons, list) or not REASONS[0] <= len(reasons) <= REASONS[1]:
        count = len(reasons) if isinstance(reasons, list) else 0
        return problems + [f"need {REASONS[0]} to {REASONS[1]} reasons, got {count}"]
    return problems + _reason_problems(reasons)


def _comments(src):
    value = src.get("comments_read") if isinstance(src, dict) else None
    return value if _whole(value, 0) else 0


def _source_problems(sources):
    if not isinstance(sources, list) or not sources:
        return ["sources: list every thread you read (url, community, comments_read)"]
    problems = []
    for i, src in enumerate(sources, 1):
        if not isinstance(src, dict):
            problems.append(f"source {i}: not an object")
            continue
        if not _url(src.get("url")):
            problems.append(f"source {i}: needs an http(s) url")
        if not _text(src.get("community")):
            problems.append(f"source {i}: needs a community, e.g. r/LosAngeles")
        if not _whole(src.get("comments_read"), 0):
            problems.append(f"source {i}: comments_read must be a whole number")
    if sum(_comments(src) for src in sources) <= 0:
        problems.append("comments_read totals 0: count the comments you actually read")
    return problems


def _duplicate_problems(reasons):
    problems = []
    for key in ("id", "label"):
        values = [str(r.get(key, "")).strip().lower() for r in reasons if isinstance(r, dict)]
        for value in sorted({v for v in values if v and values.count(v) > 1}):
            problems.append(f"duplicate {key} {value!r}")
    return problems


def _reason_problems(reasons):
    problems = _duplicate_problems(reasons)
    for i, reason in enumerate(reasons, 1):
        if not isinstance(reason, dict):
            problems.append(f"reason {i}: not an object")
            continue
        tag = f"reason {i} ({reason.get('id') or reason.get('label') or '?'})"
        problems += [f"{tag}: missing {key}" for key in ("id", "label") if not _text(reason.get(key))]
        if not _whole(reason.get("count"), 1):
            problems.append(f"{tag}: count must be a whole number above 0")
        problems += _quote_problems(tag, reason.get("quotes"))
        problems += _rebuttal_problems(tag, reason.get("rebuttal"))
    return problems


def _quote_problems(tag, quotes):
    if not isinstance(quotes, list) or not QUOTES[0] <= len(quotes) <= QUOTES[1]:
        return [f"{tag}: needs 1 to 3 quotes"]
    problems = []
    for j, quote in enumerate(quotes, 1):
        text = quote.get("text") if isinstance(quote, dict) else None
        if not _text(text):
            problems.append(f"{tag}: quote {j} has no text")
            continue
        if len(text) > QUOTE_MAX:
            problems.append(f"{tag}: quote {j} is {len(text)} characters, the limit is {QUOTE_MAX}")
        if USERNAME.search(text):
            problems.append(f"{tag}: quote {j} contains a u/username, cut it out")
        if not _url(quote.get("url")):
            problems.append(f"{tag}: quote {j} needs an http(s) url")
    return problems


def _rebuttal_problems(tag, rebuttal):
    if not isinstance(rebuttal, dict):
        return [f"{tag}: missing rebuttal (stat, value, source, url)"]
    missing = [key for key in ("stat", "value", "source") if not _text(rebuttal.get(key))]
    if not _url(rebuttal.get("url")):
        missing.append("url")
    return [f"{tag}: rebuttal is missing {', '.join(missing)}"] if missing else []


def title_warnings(question):
    """The title formula is the viewer's question, one CAPS word, the year. Warnings only."""
    warnings = []
    if not re.search(r"\b[A-Z]{3,}\b", question):
        warnings.append("title has no CAPS word (formula: question, one CAPS word, the year)")
    if not re.search(r"\b20\d{2}\b", question):
        warnings.append("title has no year")
    return warnings


# ---- tally -----------------------------------------------------------------------------

def rank_reasons(reasons):
    """Most counted reason is #1. Equal counts keep their input order (stable sort)."""
    ordered = sorted(reasons, key=lambda r: -r["count"])
    return [{**reason, "rank": rank} for rank, reason in enumerate(ordered, 1)]


def _item(reason, total):
    return {"rank": reason["rank"], "id": reason["id"], "label": reason["label"],
            "count": reason["count"], "share": round(reason["count"] / total, 3),
            "quotes": [dict(q) for q in reason["quotes"]], "rebuttal": dict(reason["rebuttal"]),
            "surprise": reason.get("surprise")}


def build_countdown(data):
    """countdown.json content. Items run countdown order: the highest rank first, #1 last."""
    ranked = rank_reasons(data["reasons"])
    total = sum(r["count"] for r in ranked)
    return {
        "question": data["question"],
        "place": data["place"],
        "proper_nouns": [p for p in (data.get("proper_nouns") or []) if _text(p)],
        "quiz": quiz_for(data["quiz"]),
        "comments_read": sum(s["comments_read"] for s in data["sources"]),
        "threads": len(data["sources"]),
        "communities": list(dict.fromkeys(s["community"] for s in data["sources"])),
        "items": [_item(r, total) for r in sorted(ranked, key=lambda r: r["rank"], reverse=True)],
    }


def countdown_table(cd):
    lines = [cd["question"],
             f"{cd['comments_read']} comments, {_plural(cd['threads'], 'thread')}, {_join(cd['communities'])}",
             ""]
    for item in cd["items"]:
        rebuttal = item["rebuttal"]
        lines.append(f"#{item['rank']:<2} {item['label']:<30} {item['count']:>4} {item['share'] * 100:6.1f}%  "
                     f"{_plural(len(item['quotes']), 'quote')}  rebuttal {rebuttal['value']} ({rebuttal['source']})")
    return "\n".join(lines)


# ---- script ----------------------------------------------------------------------------

def counted_total(cd):
    return sum(item["count"] for item in cd["items"])


def mid_roll_rank(items):
    """The quiz CTA goes right after the rank 4 reason. Under four reasons, after the second item."""
    if any(item["rank"] == MID_ROLL_RANK for item in items):
        return MID_ROLL_RANK
    return items[1]["rank"] if len(items) > 1 else items[0]["rank"]


def headline_text(label, keep_names):
    """Lowercase headline. Common words go lowercase; place names, listed proper nouns and acronyms keep their capitals."""
    keep = {w.lower() for name in keep_names for w in name.split()}
    out = []
    for word in label.split():
        bare = re.sub(r"[^A-Za-z]", "", word)
        acronym = bare.isupper() and len(bare) >= 2
        out.append(word if acronym or bare.lower() in keep else word.lower())
    return " ".join(out)


def _keep_names(cd):
    return [cd["place"], *cd.get("proper_nouns", [])]


def _front_matter(cd, job_path):
    return "\n".join([
        "---",
        f"title: {json.dumps(cd['question'], ensure_ascii=False)}",
        f"quiz: {cd['quiz']['url_base']}",
        f"job: {job_path}",
        f"comments_read: {cd['comments_read']}",
        f"threads: {cd['threads']}",
        "---",
    ])


def _filming_notes(cd):
    return "\n".join([
        "## Filming notes",
        "Plain paragraphs, one idea each. Brackets are placeholders: write them in your voice, then delete the brackets.",
        f"Pause a beat before each Number N. Say the quiz URL slowly, twice (mid-roll and end): {cd['quiz']['url_base']}",
        "Quotes on screen are verbatim. Your paraphrase is yours.",
    ])


def _hook(cd):
    n = len(cd["items"])
    word = NUMBER_WORDS[n - 1]
    return "\n".join([
        "## HOOK",
        "Read the title aloud, no greeting.",
        "",
        "[I kept hearing ... (the claim, in your words). I didn't believe it, so I investigated.]",
        "",
        f"I read {cd['comments_read']} comments across {_plural(cd['threads'], 'thread')} in {_join(cd['communities'])}.",
        "",
        f"Patterns emerged, the same {word} reasons over and over. Counting down from {word} to the number one reason.",
    ])


def _teaser(index, items):
    if index + 1 < len(items):
        return f"[Teaser: this one surprised me even more. Next up: {items[index + 1]['label'].lower()}.]"
    return "[Lead into the end: the call and the quiz.]"


def _item_block(cd, item, index, items):
    rank = item["rank"]
    spoken = NUMBER_WORDS[rank - 1]
    lines = [
        f"## #{rank} {item['label']}",
        f"Pause a beat before \"Number {spoken}\".",
        "",
        f"Number {spoken}, {headline_text(item['label'], _keep_names(cd))}.",
        "",
        f"Surprise: {item['surprise'] or '[the line where you say you thought this would rank higher]'}",
        "",
        f"Counted: {item['count']} of {counted_total(cd)} comments ({item['share'] * 100:.0f}%). "
        "Paraphrase two or three of these, funny or brutal, then the quotes as they appear on screen.",
    ]
    lines += [f"Quote {j}: \"{q['text']}\"" + (f" ({q['community']})" if q.get("community") else "")
              for j, q in enumerate(item["quotes"], 1)]
    rb = item["rebuttal"]
    lines += ["",
              f"Local expert pushback: {rb['stat']} ({rb['value']}, {rb['source']}). Name the source. {rb['url']}",
              "",
              "[Balanced reframe: one or two sentences on what the data says for this market.]",
              "",
              _teaser(index, items)]
    return "\n".join(lines)


def _mid_roll_block(cd):
    quiz = cd["quiz"]
    return "\n".join([
        "## MID-ROLL QUIZ CTA (after the reason above, the data peak)",
        "Pause a beat, then:",
        f"Take my quiz: {quiz['title']} The link is on screen and below.",
        "[Say it in your words. Keep the quiz title, and say the link is on screen and below.]",
        "Don't want to be quizzed? Reach out directly.",
        "Then back to the next reason.",
    ])


def _end_block(cd):
    quiz = cd["quiz"]
    return "\n".join([
        "## END CTA",
        "[One line on what to do this week, then:]",
        "Book a free call with Tony, the link is in the description. Or take the quiz: "
        f"{quiz['title']} Find it at {quiz_host_path(quiz)}.",
    ])


def script_markdown(cd, job_path):
    """The read-aloud skeleton. Claude fills the brackets in Tony's voice."""
    items = cd["items"]
    mid = mid_roll_rank(items)
    parts = [_front_matter(cd, job_path), "", _filming_notes(cd), "", f"# {cd['question']}", "", _hook(cd)]
    for index, item in enumerate(items):
        parts += ["", _item_block(cd, item, index, items)]
        if item["rank"] == mid:
            parts += ["", _mid_roll_block(cd)]
    parts += ["", _end_block(cd)]
    return "\n".join(parts) + "\n"


def cmd_script(args):
    jdir = resolve_job(args.job)
    cd = _load_json(jdir / "countdown.json")
    date = args.date or time.strftime("%m%d%Y")
    if not re.fullmatch(r"\d{8}", date):
        common.die("--date must be MMDDYYYY")
    out = Path(args.out).expanduser() if args.out else SCRIPT_DIR / f"{date} - {cd['place']} Countdown - Video Script.md"
    if out.exists() and not args.force:
        common.die(f"{out} exists. Pass --force to overwrite it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(script_markdown(cd, jdir))
    print(out)


# ---- sections --------------------------------------------------------------------------

def _token(word):
    return re.sub(r"[^a-z0-9#]", "", word.lower())


def phrase_times(words, phrase):
    """Start times (source seconds) where the phrase's words appear in order."""
    want = [_token(p) for p in phrase]
    toks = [_token(w["word"]) for w in words]
    return [words[i]["start"] for i in range(len(toks) - len(want) + 1) if toks[i:i + len(want)] == want]


def number_times(words, rank):
    """Every place Tony says 'number N' (word or digit) or '#N', in transcript order."""
    forms = {NUMBER_WORDS[rank - 1], str(rank)}
    hits = [t for form in sorted(forms) for t in phrase_times(words, ["number", form])]
    return sorted(hits + phrase_times(words, [f"#{rank}"]))


def locate_numbers(items, words):
    """Walk the countdown top down. Each 'number N' must come after the one before it, so a
    hook line like 'to the number one reason' cannot pull #1 up to the top."""
    found, missing, after = {}, [], -1.0
    for item in items:
        later = [t for t in number_times(words, item["rank"]) if t > after]
        if later:
            found = {**found, item["rank"]: later[0]}
            after = later[0]
        else:
            missing.append(item["rank"])
    return found, missing


def item_windows(items, found, src_end):
    """(item, start, end) per located reason, countdown order. Each runs to the next 'number'."""
    located = [item for item in items if item["rank"] in found]
    starts = [found[item["rank"]] for item in located]
    ends = starts[1:] + [src_end - CUE_MARGIN]
    return list(zip(located, starts, ends))


def _cta_time(words, lo, hi):
    takes = [t for t in phrase_times(words, ["take", "my", "quiz"]) if lo < t < hi]
    if takes:
        return takes[0]
    quizzes = [w["start"] for w in words if lo < w["start"] < hi and _token(w["word"]) == "quiz"]
    return quizzes[-1] if quizzes else None


def find_cta(windows, words, mid_rank):
    """Start of the mid-roll quiz line inside the mid-roll reason's window, or None plus a warning."""
    for item, lo, hi in windows:
        if item["rank"] != mid_rank:
            continue
        at = _cta_time(words, lo, hi)
        if at is None:
            return None, [f"mid-roll: no 'quiz' after #{mid_rank}, so no CTA. Add the line or skip it on purpose"]
        if at - 0.5 - lo < MIN_BEAT_S:
            return None, [f"mid-roll: the quiz line comes too soon after #{mid_rank} for a reason beat, CTA skipped"]
        return at, []
    return None, [f"mid-roll: #{mid_rank} is not in the transcript, CTA skipped"]


def _clear_of_cuts(t, cuts):
    """Push a cue out of any cut it lands in. Cuts are sorted by start, so one pass is enough."""
    moved = t
    for start, end in sorted(cuts):
        if start <= moved < end:
            moved = end + 0.05
    return moved


def _cue(start, end, cuts, lead=CUE_LEAD):
    return round(min(_clear_of_cuts(start + lead, cuts), end - CUE_MARGIN), 2)


def _chapter(item):
    label = item["label"]
    return f"#{item['rank']} {label[:1].upper()}{label[1:]}"


def _headline(item, at, ctx):
    block = {"type": "headline", "text": f"#{item['rank']} {headline_text(item['label'], ctx['keep'])}", "at": at}
    return {**block, "sub": item["surprise"]} if item.get("surprise") else block


def _quote_card(quote, at):
    card = {"type": "pullquote", "text": quote["text"], "at": at}
    return {**card, "source": quote["community"]} if quote.get("community") else card


def _rebuttal_stat(rebuttal, at):
    return {"type": "bigstat", "value": rebuttal["value"], "label": rebuttal["stat"],
            "source": rebuttal["source"], "at": at}


def _tally(item, a, b, ctx):
    """Running tally: the current reason first (solid bar), then the ones already revealed."""
    revealed = [item, *ctx["prior"]]
    bars = [{"label": headline_text(r["label"], ctx["keep"]),
             "value": round(r["count"] / ctx["max_count"], 3),
             "at": _cue(a, b, ctx["cuts"], CUE_LEAD + 0.25 * i)} for i, r in enumerate(revealed)]
    return {"type": "bars", "source": f"Share of {ctx['total']} counted comments", "items": bars}


def _beat_block(kind, payload, item, a, b, ctx):
    at = _cue(a, b, ctx["cuts"])
    if kind == "headline":
        return _headline(item, at, ctx)
    if kind == "quote":
        return _quote_card(payload, at)
    if kind == "bigstat":
        return _rebuttal_stat(item["rebuttal"], at)
    return _tally(item, a, b, ctx)


def item_sections(item, index, window, ctx):
    """One reason becomes a run of beat sections: headline, each quote, rebuttal, tally.
    Stacking them in one panel would overflow the 900px studio panel, so each gets its own beat."""
    lo, hi = window
    beats = [("headline", None)] + [("quote", q) for q in item["quotes"]] + [("bigstat", None), ("bars", None)]
    step = (hi - lo) / len(beats)
    sections, notes = [], []
    if step < MIN_BEAT_S:
        notes.append(f"#{item['rank']}: beats are {step:.1f}s, under {MIN_BEAT_S:.0f}s, tight")
    for k, (kind, payload) in enumerate(beats):
        a, b = lo + k * step, lo + (k + 1) * step
        section = {"evidence": [round(a, 2), round(b, 2)], "theme": THEMES[index % len(THEMES)],
                   "side": "right" if index % 2 == 0 else "left",
                   "blocks": [_beat_block(kind, payload, item, a, b, ctx)]}
        sections.append({**section, "chapter": _chapter(item)} if k == 0 else section)
    return sections, notes


def cta_section(quiz, start, end, index):
    """The mid-roll CTA window: the quiz title on screen with its link, while Tony asks for the quiz."""
    a, b = round(start - 0.5, 2), round(end - CUE_MARGIN, 2)
    headline = {"type": "headline", "text": quiz["title"], "sub": quiz_host_path(quiz), "at": round(a + CUE_LEAD, 2)}
    return {"evidence": [a, b], "theme": "midnight", "side": "right" if index % 2 == 0 else "left", "blocks": [headline]}


def build_sections(cd, windows, cta_at, mid_rank, cuts):
    items = cd["items"]
    total, max_count = counted_total(cd), max(item["count"] for item in items)
    sections, notes = [], []
    for index, (item, lo, hi) in enumerate(windows):
        is_mid = item["rank"] == mid_rank
        shown_hi = min(hi, cta_at - 0.5) if cta_at is not None and is_mid else hi
        ctx = {"cuts": cuts, "keep": _keep_names(cd), "total": total, "max_count": max_count,
               "prior": [i for i in items if i["rank"] > item["rank"]]}
        beat_sections, beat_notes = item_sections(item, index, (lo, shown_hi), ctx)
        sections += beat_sections
        notes += beat_notes
        if cta_at is not None and is_mid:
            sections.append(cta_section(cd["quiz"], cta_at, hi, index))
    return sections, notes


def quiz_bar(quiz, windows, cta_at, mid_rank):
    if cta_at is None:
        return None
    mid_hi = next(hi for item, _, hi in windows if item["rank"] == mid_rank)
    end = min(cta_at + CTA_LOWER_S, mid_hi - CUE_MARGIN)
    return {"from": round(cta_at, 2), "to": round(end, 2), "name": quiz["title"], "line": quiz_host_path(quiz)}


def end_card_for(quiz, job):
    current = job.get("endCard") or {}
    return {"seconds": current.get("seconds", 2.5), "kicker": "Take the free quiz",
            "headline": quiz["title"], "sub": quiz_host_path(quiz)}


def build_plan(cd, words, job):
    """Sections, end card and quiz bar for a located countdown. Pure: no file I/O."""
    items, quiz, mid_rank = cd["items"], cd["quiz"], mid_roll_rank(cd["items"])
    cuts, src_end = job.get("cuts", []), float(job["srcEnd"])
    found, missing = locate_numbers(items, words)
    windows = item_windows(items, found, src_end)
    cta_at, cta_notes = find_cta(windows, words, mid_rank)
    sections, beat_notes = build_sections(cd, windows, cta_at, mid_rank, cuts)
    return {
        "quiz": quiz,
        "found": found,
        "missing": missing,
        "sections": sections,
        "endCard": end_card_for(quiz, job),
        "lowerThird": quiz_bar(quiz, windows, cta_at, mid_rank),
        "warnings": [f"no 'number {r}' in the transcript" for r in missing] + cta_notes + beat_notes,
    }


def _bars_with_quiz(job, plan):
    """Existing name bars, minus an earlier quiz bar (so a re-run does not duplicate it), plus the new one."""
    title, line = plan["quiz"]["title"], quiz_host_path(plan["quiz"])
    kept = [bar for bar in _as_list(job.get("lowerThird")) if not (bar.get("name") == title and bar.get("line") == line)]
    return [*kept, plan["lowerThird"]]


def merge_job(job, plan):
    """New job dict. Replaces sections and endCard, drops the counter, adds the quiz bar. Everything
    else stays. The counter column sits on the right edge, on top of studio panel text."""
    merged = {key: value for key, value in job.items() if key != "counter"}
    merged = {**merged, "sections": plan["sections"]}
    merged["endCard"] = plan["endCard"]
    if plan["lowerThird"]:
        merged["lowerThird"] = _bars_with_quiz(job, plan)
    return merged


def _print_sections_summary(plan, problems):
    for rank, at in sorted(plan["found"].items(), key=lambda kv: -kv[0]):
        print(f"  #{rank} at {at:.2f}s")
    if plan["lowerThird"]:
        bar = plan["lowerThird"]
        print(f"  quiz bar {bar['from']:.2f}s to {bar['to']:.2f}s, mid-roll CTA")
    print(f"  {len(plan['sections'])} sections")
    for note in plan["warnings"]:
        print(f"[countdown] warning: {note}")
    for problem in problems:
        print(f"[countdown] check: {problem}")


def cmd_sections(args):
    jdir = resolve_job(args.job)
    cd = _load_json(jdir / "countdown.json")
    job = _load_json(jdir / "job.json")
    plan = build_plan(cd, load_words(jdir), job)
    candidate = merge_job(job, plan)
    problems = th_lib.validate(candidate)
    _dump(jdir / "work" / "countdown_sections.json", plan, ascii_only=False)
    _print_sections_summary(plan, problems)
    if not args.apply:
        print(f"[countdown] plan written to {jdir / 'work' / 'countdown_sections.json'}. Not applied, re-run with --apply.")
        return
    if plan["missing"] or problems:
        common.die("not applied: fix the warnings and checks above, then run again")
    _dump(jdir / "job.json", candidate)
    print(f"[countdown] applied to {jdir / 'job.json'}. Next: th.py check {jdir.name}")


# ---- quizlink --------------------------------------------------------------------------

STYLE_COPY_SUFFIXES = {"evidence", "studio", "news", "board", "split"}


def folder_word(jdir):
    """The job folder's topic word. Skipped from the end: the -2, -3 that new_job adds on a
    clash, and a style name on a style copy of a job (20261012-210030-california-board)."""
    parts = jdir.name.split("-")
    while len(parts) > 3 and (parts[-1].isdigit() or parts[-1].lower() in STYLE_COPY_SUFFIXES):
        parts = parts[:-1]
    return re.sub(r"[^a-z0-9]", "", parts[-1].lower()) or "video"


def quiz_url(quiz, word):
    return f"{quiz['url_base']}?v={word}&utm_source=youtube&utm_medium=video&utm_campaign={word}"


def link_lines(quiz, url, call):
    return [f"{CALL_PREFIX} {call}", f"{quiz['title']} {QUIZ_MARK} {url}"]


def _is_link_line(line):
    return line.startswith(CALL_PREFIX) or QUIZ_MARK in line


def _with_link_head(description, head):
    """Replace the two link lines at the top of a description, then a blank line, then the body."""
    lines = (description or "").split("\n")
    remaining = [ln for ln in lines[:2] if not _is_link_line(ln)] + lines[2:]
    body = "\n".join(remaining).lstrip("\n")
    return "\n".join([*head, "", body]) if body else "\n".join(head)


def _with_shorts_line(description, url):
    kept = [ln for ln in (description or "").split("\n") if QUIZ_MARK not in ln]
    text = "\n".join(kept).rstrip()
    line = f"{QUIZ_MARK} {url}"
    return f"{text}\n\n{line}" if text else line


def apply_links(job, quiz, url, call):
    """New job dict: youtube.description gets the links on top, every shorts description gets the quiz line."""
    yt = dict(job.get("youtube") or {})
    yt["description"] = _with_link_head(yt.get("description", ""), link_lines(quiz, url, call))
    out = {**job, "youtube": yt}
    if "shorts" in job:
        out["shorts"] = [{**s, "description": _with_shorts_line(s.get("description", ""), url)} for s in job["shorts"]]
    return out


def with_pinned_comment(md, lines):
    """youtube.md with one '## Pinned comment' section at the end, replacing any earlier one."""
    base = PINNED.sub("", md).rstrip("\n")
    return f"{base}\n\n## Pinned comment\n\n" + "\n".join(lines) + "\n"


def cmd_quizlink(args):
    jdir = resolve_job(args.job)
    slug = args.quiz or _load_json(jdir / "countdown.json")["quiz"]["slug"]
    quiz = quiz_for(slug)
    url = quiz_url(quiz, folder_word(jdir))
    call = call_url()
    job = _load_json(jdir / "job.json")
    _dump(jdir / "job.json", apply_links(job, quiz, url, call))
    md = jdir / "out" / "youtube.md"
    if md.exists():
        md.write_text(with_pinned_comment(md.read_text(), link_lines(quiz, url, call)))
        print(f"[countdown] pinned comment written to {md}")
    else:
        print("[countdown] no out/youtube.md yet, the pinned comment is written by th.py kit after render")
    print(url)


# ---- entry point -----------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tally", help="research.json -> countdown.json")
    p.add_argument("job")
    p.set_defaults(fn=cmd_tally)
    p = sub.add_parser("script", help="countdown.json -> read-aloud script")
    p.add_argument("job")
    p.add_argument("--out", help="output path (default: ~/Documents/video-scripts, dated)")
    p.add_argument("--date", help="MMDDYYYY, default today")
    p.add_argument("--force", action="store_true", help="overwrite an existing script")
    p.set_defaults(fn=cmd_script)
    p = sub.add_parser("sections", help="draft studio sections from the transcript")
    p.add_argument("job")
    p.add_argument("--apply", action="store_true", help="merge into job.json")
    p.set_defaults(fn=cmd_sections)
    p = sub.add_parser("quizlink", help="quiz and call links in youtube, shorts, pinned comment")
    p.add_argument("job")
    p.add_argument("--quiz", choices=sorted(QUIZZES), help="override the quiz in countdown.json")
    p.set_defaults(fn=cmd_quizlink)
    args = parser.parse_args(argv)
    args.fn(args)


def cmd_tally(args):
    jdir = resolve_job(args.job)
    data = _load_json(jdir / "research.json")
    problems = validate_research(data)
    if problems:
        common.die("research.json problems:\n  " + "\n  ".join(problems))
    cd = build_countdown(data)
    _dump(jdir / "countdown.json", cd, ascii_only=False)
    print(countdown_table(cd))
    for note in title_warnings(cd["question"]):
        print(f"[countdown] warning: {note}")
    print(f"[countdown] wrote {jdir / 'countdown.json'}")


if __name__ == "__main__":
    main()
