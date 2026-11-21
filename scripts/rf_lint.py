"""fv.py rf lint: the prompt rules in docs/briefs/2026-10-24-realistic-footage.md 5.5,
with the likeness rules from 5.6.

Stills get I1 to I5, clips C1 to C8 and C10, every shot C9 and C12, the job C11, C13 and
the likeness half of C9. A FAIL blocks rf pack; a WARN prints and the pack goes ahead.
Every word list, pattern and threshold comes from assets/real-footage/lint.json. Word
lists catch the obvious; they cannot prove a prompt is clean, so Tony still looks.
"""
import json
import re
from pathlib import Path
from typing import NamedTuple

import common
import rf_library

SETTINGS_PATH = rf_library.LIBRARY / "lint.json"
REQUIRED = ("negation_cues", "prompt_blocks", "device_words", "filler_words", "artifact_words", "text_cues",
            "brands", "real_people", "property_cues", "address_pattern", "client_cues", "currency_cues",
            "currency_allowed", "likeness_names", "advice_topic_words", "clean_frame_terms", "clean_frame_min",
            "c2_ignore", "camera_cues", "cast_count_pattern", "image_ref_prefix", "ref_role_phrase",
            "ref_tag_token", "ref_tag_house", "operator_cues", "unseen_cues", "sync_cues", "final_cues",
            "short_clip_seconds", "max_beats_short_clip", "montage_shot_pattern", "montage_min_shot_seconds",
            "flux_providers", "flux_max_negations", "guarded_lanes", "lane_override_pattern")
PATTERNS = ("address_pattern", "cast_count_pattern", "ref_tag_token", "ref_tag_house", "montage_shot_pattern",
            "lane_override_pattern")
CAMERA_PARTS = {"trigger": "trigger", "reaction": "reaction", "settle": "settle",
                "not_this": '"not this" clause'}


class Finding(NamedTuple):
    level: str     # FAIL blocks the pack, WARN prints and continues
    code: str
    shot: str      # a shot id, or "job" for a rule about the whole job
    message: str

    def __str__(self):
        return f"{self.level} {self.code} {self.shot}: {self.message}"


def load_settings(path=SETTINGS_PATH):
    """lint.json, checked: every key the rules read is there and every pattern compiles."""
    settings = json.loads(Path(path).read_text())
    missing = [key for key in REQUIRED if key not in settings]
    if missing:
        common.die(f"{path} is missing {', '.join(missing)}")
    for key in PATTERNS:
        try:
            re.compile(settings[key])
        except re.error as err:
            common.die(f"{path}: {key} is not a valid pattern ({err})")
    return settings


def flat(text):
    """One line, single spaces, straight quotes."""
    text = (text or "").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def has(text, phrase):
    """Case-insensitive match of a whole word or phrase, plural included (banknote matches
    banknotes); symbols such as $ match anywhere."""
    pattern = re.escape(phrase.lower())
    if phrase[:1].isalnum():
        pattern = r"(?<![a-z0-9])" + pattern
    if phrase[-1:].isalnum():
        pattern += r"(?:e?s)?(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def hits(text, phrases):
    return [p for p in phrases if has(text, p)]


def mentions(text, cues):
    """Plain substring cues, for the structural rules (a cue may end in a space)."""
    low = text.lower()
    return any(cue in low for cue in cues)


def negated_clause(settings):
    """From a negation word (no, not, never...) to the end of its sentence or clause."""
    cues = "|".join(re.escape(c) for c in settings["negation_cues"])
    return re.compile(r"\b(?:" + cues + r")\b[^.;:!?]*", re.I)


def affirmed(text, settings):
    """The text without its negated clauses."""
    return negated_clause(settings).sub(" ", flat(text))


def negated(text, settings):
    """Only the negated clauses of the text."""
    return " ".join(m.group(0) for m in negated_clause(settings).finditer(flat(text)))


def label_pattern(settings):
    names = "|".join(re.escape(b) for b in settings["prompt_blocks"])
    return re.compile(r"^\s*(" + names + r")\s*:\s?(.*)$", re.I)


def blocks(prompt, settings):
    """A prompt's labeled blocks (GOAL:, CAST:, CAMERA:...), each on one line, keyed in
    capitals whatever case the prompt used."""
    label, found, current = label_pattern(settings), {}, None
    for line in (prompt or "").splitlines():
        start = label.match(line)
        if start:
            current = start.group(1).upper()
            found[current] = start.group(2)
        elif current:
            found[current] += " " + line
    return {name: flat(text) for name, text in found.items()}


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", flat(text)) if s]


def joined(parts):
    """Separate texts as separate sentences, so a negated clause in one cannot run on into
    the next."""
    return flat(". ".join(p for p in parts if p))


def shot_text(shot):
    """Everything a shot says: purpose, prompt, references, dialogue."""
    refs = [" ".join(str(r.get(k, "")) for k in ("label", "file", "role")) for r in shot.get("refs") or []]
    lines = [" ".join(str(d.get(k, "")) for k in ("speaker", "line", "voice")) for d in shot.get("dialogue") or []]
    return joined([shot.get("purpose") or "", shot.get("prompt") or "", *refs, *lines])


def style_entry(shot):
    name = shot.get("style")
    return rf_library.front_matter("style", name) if name in rf_library.names("style") else {}


def still_rules(data, shot, s):
    sid, prompt = shot["id"], flat(shot.get("prompt"))
    stated, style, out = affirmed(prompt, s), style_entry(shot), []
    first = sentences(label_pattern(s).sub(r"\2", prompt, count=1))[:1]
    if not first or not hits(first[0], s["device_words"]):
        out.append(Finding("WARN", "I1", sid, "the first sentence names no capture device or photo style"))
    filler = hits(stated, s["filler_words"] + style.get("avoid", []))
    if filler:
        out.append(Finding("WARN", "I2", sid, f"filler or avoided words: {', '.join(filler)}"))
    if style:
        allowed = " ".join(style.get("artifacts", [])).lower()
        stray = [w for w in hits(stated, s["artifact_words"]) if w not in allowed]
        if stray:
            out.append(Finding("WARN", "I3", sid, f"artifacts the {shot['style']} style does not make: "
                                                  f"{', '.join(stray)}"))
    if shot.get("text_ok") is not True:
        text_asks = hits(stated, s["text_cues"] + s["brands"])
        if text_asks:
            out.append(Finding("FAIL", "I4", sid, f"brands, logos or readable text ({', '.join(text_asks)}); "
                                                  f"only Tony approves text, with \"text_ok\": true"))
    engine = (str(shot.get("provider") or data.get("defaults", {}).get("provider", "")) + str(shot.get("model"))).lower()
    if any(name in engine for name in s["flux_providers"]):
        count = len(negated_clause(s).findall(prompt))
        if count > s["flux_max_negations"]:
            out.append(Finding("WARN", "I5", sid, f"{count} negations on FLUX, which ignores them; "
                                                  f"describe what is there instead"))
    return out


def camera_rules(shot, prompt, b, s):
    """C2, C3 and C5: one behavior, a complete camera paragraph, a placed, unseen operator."""
    sid, out = shot["id"], []
    stated = affirmed(prompt, s)
    named = [n for n in rf_library.names("technique") if n not in s["c2_ignore"]
             and (has(stated, n) or has(stated, n.replace("-", " ")))]
    if len(named) > 1:
        out.append(Finding("WARN", "C2", sid, f"more than one camera behavior: {', '.join(named)}"))
    camera = b.get("CAMERA", prompt)
    lacking = [label for key, label in CAMERA_PARTS.items() if not mentions(camera, s["camera_cues"][key])]
    if lacking:
        out.append(Finding("WARN", "C3", sid, f"the camera paragraph has no {', '.join(lacking)}"))
    if not (mentions(prompt, s["operator_cues"]) and mentions(prompt, s["unseen_cues"])):
        out.append(Finding("WARN", "C5", sid, "say where the operator is and that they are never seen"))
    return out


def cast_rules(shot, prompt, b, s):
    """C4: a cast count when more than one character, and a role for every reference."""
    sid, out = shot["id"], []
    refs = shot.get("refs") or []
    images = [r for r in refs if str(r.get("label", "")).upper().startswith(s["image_ref_prefix"])]
    speakers = {d.get("speaker") for d in shot.get("dialogue") or [] if d.get("speaker")}
    counted = re.search(s["cast_count_pattern"], (b.get("CAST") or prompt).lower())
    if not counted and (len(images) > 1 or len(speakers) > 1):
        out.append(Finding("FAIL", "C4", sid, 'more than one character and no cast count ("Exactly two on screen")'))
    phrase = s["ref_role_phrase"]
    bare = [str(r.get("label")) for r in refs if phrase not in str(r.get("role", "")).lower()]
    bare += [t for line in sentences(b.get("REFERENCES", "")) if phrase not in line.lower()
             for t in re.findall(s["ref_tag_token"], line)]
    if bare:
        out.append(Finding("FAIL", "C4", sid, f'references with no "{phrase}" role: {", ".join(bare)}'))
    return out


def dialogue_rules(shot, prompt, s):
    """C6: every line has a speaker, its exact words in quotes, a voice, and lip sync."""
    dialogue, problems = shot.get("dialogue") or [], []
    for d in dialogue:
        problems += [f"a line with no {key}" for key in ("speaker", "line", "voice") if not d.get(key)]
        if d.get("line") and f'"{flat(d["line"])}"' not in prompt:
            problems.append(f'"{d["line"]}" is not quoted word for word in the prompt')
    if dialogue or re.search(r'"[^"]+"', prompt):
        if not dialogue:
            problems.append("the prompt quotes a line the shot's dialogue does not list")
        if not mentions(prompt, s["sync_cues"]):
            problems.append("no lip-sync instruction")
    return [Finding("WARN", "C6", shot["id"], "; ".join(problems))] if problems else []


def timing_rules(shot, b, montage, s):
    """C7: a few beats in a short clip, no montage shot under the minimum."""
    sid = shot["id"]
    if montage:
        short = [str(i + 1) for i, (start, end) in enumerate(montage) if end - start < s["montage_min_shot_seconds"]]
        return [Finding("WARN", "C7", sid, f"montage shots under {s['montage_min_shot_seconds']:g}s: "
                                           f"{', '.join(short)}")] if short else []
    if float(shot.get("duration_s") or 0) > s["short_clip_seconds"]:
        return []
    beats = [x for x in sentences(b.get("ACTION", ""))[1:]
             if not any(x.lower().startswith(cue) for cue in s["final_cues"])]
    if len(beats) > s["max_beats_short_clip"]:
        return [Finding("WARN", "C7", sid, f"{len(beats)} beats in {shot.get('duration_s')}s; keep it to "
                                           f"{s['max_beats_short_clip']}")]
    return []


def tag_rules(shot, prompt, s):
    """C10: tags written the house way (@IMG1, @VID1, @AUD1), each naming one of the shot's
    references. The engine swaps them for the model's real syntax."""
    labels = {str(r.get("label")) for r in shot.get("refs") or []}
    bad = [t for t in re.findall(s["ref_tag_token"], prompt)
           if not re.fullmatch(s["ref_tag_house"], t) or t[1:] not in labels]
    return [Finding("WARN", "C10", shot["id"], f"tags that are not @IMG1-style or name no reference in "
                                               f"refs: {', '.join(bad)}")] if bad else []


def clip_rules(data, shot, s):
    sid, raw = shot["id"], shot.get("prompt") or ""
    prompt, b = flat(raw), blocks(raw, s)
    montage = [(float(a), float(e)) for a, e in re.findall(s["montage_shot_pattern"], raw, flags=re.I)]
    out = []
    guard = negated(prompt, s)
    present = [t for t in s["clean_frame_terms"] if has(guard, t)]
    if len(present) < s["clean_frame_min"]:
        missing = [t for t in s["clean_frame_terms"] if t not in present]
        out.append(Finding("FAIL", "C1", sid, f'clean-frame guard missing ("Clean full frame: no ..."): '
                                              f'{", ".join(missing)}'))
    if not montage:
        out += camera_rules(shot, prompt, b, s)
    out += cast_rules(shot, prompt, b, s) + dialogue_rules(shot, prompt, s) + timing_rules(shot, b, montage, s)
    if not mentions(prompt, s["final_cues"]):
        out.append(Finding("WARN", "C8", sid, "no stated final image or result"))
    return out + tag_rules(shot, prompt, s)


def people_rules(data, shot, s):
    """C9: no real person, brand, property, client, student or money. C12: Tony or
    Partner only with an approved likeness."""
    sid, text, out = shot["id"], shot_text(shot), []
    cleared = text
    for allowed in s["currency_allowed"]:
        cleared = re.sub(re.escape(allowed), " ", cleared, flags=re.I)
    stated = affirmed(cleared, s)
    real = hits(stated, s["brands"] + s["real_people"] + s["property_cues"] + s["client_cues"]
                + s["currency_cues"])
    if re.search(s["address_pattern"], stated.lower()):
        real.append("a street address")
    if real:
        out.append(Finding("FAIL", "C9", sid, f"real people, brands, property, clients or money: "
                                              f"{', '.join(real)}"))
    likeness = data.get("likeness") or {}
    for person, names in s["likeness_names"].items():
        if hits(text, names) and likeness.get(person) != "approved":
            out.append(Finding("FAIL", "C12", sid, f"{person.title()} appears but the job's likeness block "
                                                   f'does not say "{person}": "approved"'))
    return out


def lane_key(lane):
    return re.sub(r"[^a-z]", "", str(lane).lower())


def job_rules(data, brief, s):
    """C9 for the likeness block, C11 for the lane, C13 for advice topics."""
    out, likeness = [], data.get("likeness") or {}
    others = [name for name in likeness if name not in s["likeness_names"]]
    if others:
        out.append(Finding("FAIL", "C9", "job", f"only Tony or Partner can be approved; not {', '.join(others)}"))
    guarded = {lane_key(lane) for lane in s["guarded_lanes"]}
    if lane_key(data.get("lane", "")) in guarded and not re.search(s["lane_override_pattern"], brief or "",
                                                                   flags=re.M):
        out.append(Finding("FAIL", "C11", "job", f'{data.get("lane")} lane without Tony\'s lane_override: '
                                                 f'"tony-approved" in rf/brief.md'))
    approved = [p for p in s["likeness_names"] if likeness.get(p) == "approved"]
    if approved:
        about = affirmed(joined([data.get("idea") or "", brief or "", *(shot_text(x) for x in data["shots"])]), s)
        topics = hits(about, s["advice_topic_words"])
        if topics:
            out.append(Finding("FAIL", "C13", "job", f"an approved likeness ({', '.join(approved)}) on "
                                                     f"real estate, HOA, legal or money advice: {', '.join(topics)}"))
    return out


def findings(data, brief, settings, shot_id=None):
    """Every finding for the job, or for one shot plus the job-wide rules."""
    shots = [x for x in data["shots"] if shot_id in (None, x.get("id"))]
    if shot_id and not shots:
        common.die(f"no shot {shot_id} (have: {', '.join(str(x.get('id')) for x in data['shots'])})")
    out = job_rules(data, brief, settings)
    for shot in shots:
        out += people_rules(data, shot, settings)
        out += clip_rules(data, shot, settings) if shot.get("kind") == "clip" else still_rules(data, shot, settings)
    return out


def results(data, found, shot_id=None):
    """Each linted shot's result: "FAIL", "WARN" or "pass" (job-wide findings count for
    every shot)."""
    def result(shot):
        mine = [f for f in found if f.shot in (shot.get("id"), "job")]
        return "FAIL" if any(f.level == "FAIL" for f in mine) else "WARN" if mine else "pass"
    return {s.get("id"): result(s) for s in data["shots"] if shot_id in (None, s.get("id"))}
