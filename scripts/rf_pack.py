"""fv.py rf pack: the prompt pack the video-engine skill generates from.

rf/pack.md lists every shot in generation order (stills, then clips), each with its
OpenArt model and mode, settings, style, reference checklist, the draft-then-final
instruction for clips and a copy block. rf/prompts/<id>.txt holds each prompt on its own.
No prices anywhere: a Python script cannot call the OpenArt MCP, so the engine quotes
them live. Spec: docs/briefs/2026-10-24-realistic-footage.md, sections 5.3 and 5.7.
"""
import json
import re

import common
import rf_library

KIND_ORDER = ("still", "clip")
PACKABLE = ("drafted", "linted", "packed")   # a returned or ingested shot keeps its status
SHOT_ID = re.compile(r"[A-Za-z0-9_-]+")      # it names rf/prompts/<id>.txt
PRICE_WORDS = ("credit", "price", "cost")
DRAFT_THEN_FINAL = ("Draft then final: generate the draft only. Run the final only after Tony "
                    "passes the draft's camera behavior and cast, under an AUTH line that covers it.")


def generation_order(shots):
    """Stills before clips, each kind in shot-list order."""
    for shot in shots:
        if shot.get("kind") not in KIND_ORDER:
            common.die(f"shot {shot.get('id')}: 'kind' must be still or clip, got {shot.get('kind')!r}")
    return sorted(shots, key=lambda s: KIND_ORDER.index(s["kind"]))


def check_job(data):
    """Stop on a shot list that cannot be packed as a whole: drafts turned off, or shot ids
    that are missing, repeated or unsafe as file names."""
    if data.get("defaults", {}).get("draft_first", True) is not True:
        common.die("rf/shots.json: 'draft_first' must stay true: every clip is drafted and "
                   "passed by Tony before any final (spec 5.7 guards)")
    ids = [s.get("id") for s in data["shots"]]
    for shot_id in ids:
        if not isinstance(shot_id, str) or not SHOT_ID.fullmatch(shot_id):
            common.die(f"shot id {shot_id!r} must be letters, digits, - or _ "
                       f"(it names rf/prompts/<id>.txt)")
        if ids.count(shot_id) > 1:
            common.die(f"shot id '{shot_id}' is used twice")


def priced(settings):
    return any(word in str(key).lower() for key in settings for word in PRICE_WORDS) \
        or any("$" in str(value) for value in settings.values())


def check(shot):
    """Stop on a shot that cannot be packed: no prompt yet, no model or mode, a price in its
    settings, or a style or technique the library does not have."""
    shot_id = shot["id"]
    if not (shot.get("prompt") or "").strip():
        common.die(f"shot {shot_id} has no prompt; write it in rf/shots.json first")
    for field in ("model", "mode"):
        if not shot.get(field):
            common.die(f"shot {shot_id} has no '{field}'")
    if priced(shot.get("settings", {})):
        common.die(f"shot {shot_id}: settings carry a price; the engine quotes prices live, "
                   f"never the pack")
    rf_library.require_names(shot.get("style"), shot.get("technique"), f"shot {shot_id}: ")


def record_lint(data, lint_results):
    """The shot list with each linted shot's result ({id: "pass" | "WARN" | "FAIL"}) and
    status: a FAIL keeps a shot from packed (it drops back to drafted), a pass or WARN moves
    a drafted shot to linted. Returned or ingested shots keep their status."""
    def updated(shot):
        result, status = lint_results[shot.get("id")], shot.get("status", "drafted")
        if status in PACKABLE:
            status = "drafted" if result == "FAIL" else "packed" if status == "packed" else "linted"
        return {**shot, "lint": result, "status": status}
    return {**data, "shots": [updated(s) if s.get("id") in lint_results else s for s in data["shots"]]}


def mark_packed(shots):
    """Shots not yet generated become packed; a returned or ingested shot keeps its status."""
    return [{**s, "status": "packed"} if s.get("status", "drafted") in PACKABLE else s
            for s in shots]


def model_line(shot):
    model = shot.get("model")
    if isinstance(model, dict):
        return f"draft {model.get('draft')}, final {model.get('final')}, {shot.get('mode')}"
    return f"{model}, {shot.get('mode')}"


def settings_line(shot):
    parts = [f"{key} {value}" if key in ("draft", "final") else str(value)
             for key, value in shot.get("settings", {}).items()]
    if shot.get("duration_s"):
        parts.append(f"{shot['duration_s']}s")
    return ", ".join(parts)


def reference_lines(refs):
    if not refs:
        return ["- none"]
    return [f"- [ ] {r.get('label')}: {r.get('file')}. Role: {r.get('role')}" for r in refs]


def dialogue_line(d):
    voice = f" (voice: {d['voice']})" if d.get("voice") else ""
    return f"- {d.get('speaker')}: \"{d.get('line')}\"{voice}"


def status_line(shot):
    returns = shot.get("returns") or []
    return f"Status: {shot.get('status')}" + (f" (returns: {', '.join(returns)})" if returns else "")


def section(shot):
    """One shot's part of the pack."""
    if shot["kind"] == "clip":
        title = f"clip: {shot.get('technique') or 'no technique'}, {shot.get('duration_s')}s"
    else:
        title = f"still: {shot.get('purpose') or 'still'}"
    lines = [f"## {shot['id']} {title}",
             f"Model and mode: {model_line(shot)}",
             f"Settings: {settings_line(shot)}",
             f"Style: {shot.get('style') or 'none'}",
             status_line(shot),
             "References:", *reference_lines(shot.get("refs"))]
    if shot.get("dialogue"):
        lines += ["Dialogue:", *(dialogue_line(d) for d in shot["dialogue"])]
    if shot["kind"] == "clip":
        lines.append(DRAFT_THEN_FINAL)
    lines += [f"Prompt file: rf/prompts/{shot['id']}.txt", "Copy block:", "",
              "```text", shot["prompt"].strip(), "```"]
    return "\n".join(lines)


def pack_text(data, shots):
    likeness = json.dumps(data["likeness"]) if data.get("likeness") else "none"
    syntax = data.get("defaults", {}).get("ref_tag_syntax", "unverified")
    head = [f"# Prompt pack: {data.get('job')}", "",
            f"Idea: {data.get('idea')}. Lane: {data.get('lane')}. Disclosure: always on.",
            f"Likeness: {likeness}.",
            "Order: stills first, then clips. Draft first: every clip runs on its draft model "
            "and settings before any final.",
            f"Reference tags: written @IMG1, @VID1, @AUD1; the engine sends them in the model's own "
            f"syntax (ref_tag_syntax: {syntax}).", ""]
    return "\n".join(head) + "\n" + "\n\n".join(section(s) for s in shots) + "\n"


def check_all(data):
    """Stop on anything that keeps the shot list from being packed; return its shots in
    generation order."""
    check_job(data)
    shots = generation_order(data["shots"])
    for shot in shots:
        check(shot)
    return shots


def write(rf_dir, data):
    """Check the shot list, write pack.md and one prompts/<id>.txt per shot, and hand back
    the shot list with its packed shots marked. Nothing is written when a check fails; the
    prompt files of shots no longer in the list are removed last."""
    marked = mark_packed(data["shots"])
    shots = check_all({**data, "shots": marked})
    text = pack_text(data, shots)
    prompts = rf_dir / "prompts"
    prompts.mkdir(exist_ok=True)
    current = {f"{shot['id']}.txt" for shot in shots}
    for shot in shots:
        (prompts / f"{shot['id']}.txt").write_text(shot["prompt"].strip() + "\n")
    (rf_dir / "pack.md").write_text(text)
    for stale in prompts.glob("*.txt"):
        if stale.name not in current:
            stale.unlink()
    return {**data, "shots": marked}
