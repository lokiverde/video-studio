"""Motion graphic scenes: an animated graphic as a scene's picture (docs/mograph.md).

A scene may carry a "mograph" block instead of an image_prompt:

    {"id": 4, "narration": "...", "caption": "",
     "mograph": {"kind": "compare", "title": "Median price",
                 "items": [{"label": "Redondo Beach", "value": 1.45},
                           {"label": "Torrance", "value": 1.02}],
                 "prefix": "$", "suffix": "M", "decimals": 2}}

Three kinds: compare (bars that grow while their numbers count up), punch (a kinetic punch
line, word by word) and list (items that slide in as the narration names them). The
Remotion template in talking-head/ draws them (src/mograph/). Nothing goes to FLUX.

Preview: the contact sheets show each graphic's settled last frame with a MOTION badge.
Finish: after tts, `run` renders both cuts at native size, timed to the scene's narration,
into work/mograph_NN.mp4 and work/mographv_NN.mp4. assemble plays them the way it plays a
clip scene, with no AI disclosure: a drawn graphic is not realistic footage.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import common
import platform_util

KINDS = ("compare", "punch", "list")
# Everything else that can be a scene's picture; a graphic replaces the whole picture.
STANDALONE = ("clip", "photo", "figure", "motion", "shots", "image_prompt", "card", "graphic",
              "hold", "tag", "note")

# Brokerage navy, the army theme's canvas. A theme's army_style or mograph_style overrides
# it, and a scene's "colors" overrides both, key by key.
DEFAULT_PALETTE = {"bg": "#1d3557", "bg_deep": "#00121f", "text": "#ffffff",
                   "accent": "#29a8d6", "accent_hi": "#9fe3fb", "dim": "#3d6380"}
PALETTE_KEYS = tuple(DEFAULT_PALETTE)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

COMPARE_ITEMS = (2, 5)
LIST_ITEMS = (2, 6)
PUNCH_WORDS = 14
PUNCH_CHARS = 90
LABEL_CHARS = 32
ITEM_CHARS = 52
TITLE_CHARS = 60
SHORT_CHARS = 80      # kicker, sub, source
MAX_DECIMALS = 3

# Reveal timing, seconds. An item lands a beat before the narration says it.
CUE_LEAD = 0.15
MIN_START = 0.3       # nothing lands before the title has settled in
FIRST_REVEAL = 0.5    # an even spread starts here...
SPREAD_END = 0.7      # ...and ends at this share of the narration
MIN_GAP = 0.35
SETTLE = 1.2          # the last item lands at least this long before the scene ends, so a
                      # compare bar (Compare.tsx GROW_S, 1s) reaches its value on screen
WORDS_PER_SECOND = 2.6   # sheet-time estimate of narration length, before tts exists

STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "your", "my", "our",
             "is", "are", "at", "by", "with", "it", "its"}

TEMPLATE = common.ROOT / "talking-head"
FONTS = common.ROOT / "assets" / "fonts"
COMPOSITION = "Mograph"
BADGE = "MOTION"


# ---- validation -----------------------------------------------------------------------

def _text(value, what, limit, required=True):
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be text")
    if len(value) > limit:
        raise ValueError(f"{what} runs {len(value)} characters, keep it to {limit}")


def _number(value):
    """A real, finite number (json.loads turns a bare NaN or Infinity into a float that
    the template's JSON.parse then rejects)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_compare(spec):
    items = spec.get("items")
    low, high = COMPARE_ITEMS
    if not isinstance(items, list) or not low <= len(items) <= high:
        raise ValueError(f"compare needs {low} to {high} items")
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("label"), str) \
                or not item["label"].strip():
            raise ValueError(f"item {n} needs a label")
        _text(item["label"], f"item {n} label", LABEL_CHARS)
        if not _number(item.get("value")) or item["value"] < 0:
            raise ValueError(f"item {n} value must be a number, zero or more")
        _text(item.get("text"), f"item {n} text", 12, required=False)
        _text(item.get("cue"), f"item {n} cue", LABEL_CHARS, required=False)
    if not any(item["value"] > 0 for item in items):
        raise ValueError("at least one value must be above zero")
    highlight = spec.get("highlight")
    if highlight is not None and (not isinstance(highlight, int) or isinstance(highlight, bool)
                                  or not 0 <= highlight < len(items)):
        raise ValueError(f"highlight must be an item number from 0 to {len(items) - 1}")
    decimals = spec.get("decimals", 0)
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= MAX_DECIMALS:
        raise ValueError(f"decimals must be 0 to {MAX_DECIMALS}")
    for key in ("prefix", "suffix"):
        _text(spec.get(key), key, 6, required=False)
    _text(spec.get("title"), "title", TITLE_CHARS, required=False)
    _text(spec.get("source"), "source", SHORT_CHARS, required=False)


def _validate_punch(spec):
    text = spec.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("punch needs a 'text' line")
    words = text.split()
    if len(words) > PUNCH_WORDS:
        raise ValueError(f"punch text runs {len(words)} words, keep it to {PUNCH_WORDS} words")
    _text(text, "punch text", PUNCH_CHARS)
    em = spec.get("em", [])
    if not isinstance(em, list) or not all(isinstance(w, str) for w in em):
        raise ValueError("em must be a list of words from the text")
    plain = {_word(w) for w in words}
    for word in em:
        if _word(word) not in plain:
            raise ValueError(f"em word '{word}' is not in the text")
    _text(spec.get("kicker"), "kicker", SHORT_CHARS, required=False)
    _text(spec.get("sub"), "sub", SHORT_CHARS, required=False)


def _validate_list(spec):
    items = spec.get("items")
    low, high = LIST_ITEMS
    if not isinstance(items, list) or not low <= len(items) <= high:
        raise ValueError(f"list needs {low} to {high} items")
    for n, item in enumerate(items, 1):
        text = item if isinstance(item, str) else item.get("text") if isinstance(item, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"item {n} needs text")
        _text(text, f"item {n}", ITEM_CHARS)
        if isinstance(item, dict):
            _text(item.get("sub"), f"item {n} sub", SHORT_CHARS, required=False)
            _text(item.get("cue"), f"item {n} cue", ITEM_CHARS, required=False)
    if not isinstance(spec.get("numbered", True), bool):
        raise ValueError("numbered must be true or false")
    _text(spec.get("title"), "title", TITLE_CHARS, required=False)


def _validate_colors(colors):
    if colors is None:
        return
    if not isinstance(colors, dict):
        raise ValueError("colors must be an object")
    for key, value in colors.items():
        if key not in PALETTE_KEYS:
            raise ValueError(f"colors has no '{key}' (use {', '.join(PALETTE_KEYS)})")
        if not isinstance(value, str) or not HEX.match(value):
            raise ValueError(f"colors.{key} must be a hex color like #29a8d6, got {value!r}")


VALIDATORS = {"compare": _validate_compare, "punch": _validate_punch, "list": _validate_list}


def validate(spec):
    """Raise ValueError naming the first problem with a mograph block."""
    if not isinstance(spec, dict):
        raise ValueError("'mograph' must be an object")
    kind = spec.get("kind")
    if kind not in KINDS:
        raise ValueError(f"mograph kind must be compare, punch or list, got {kind!r}")
    VALIDATORS[kind](spec)
    _validate_colors(spec.get("colors"))


def validate_scene(scene):
    """The scene-level rules: the graphic stands alone, and the caption may be empty
    (the graphic usually carries the words) but must be there."""
    for other in STANDALONE:
        if scene.get(other) is not None:
            raise ValueError(f"a 'mograph' scene cannot also have '{other}' "
                             f"(the graphic replaces the whole scene's picture)")
    if not isinstance(scene.get("caption"), str):
        raise ValueError("needs a 'caption' (it may be empty)")
    duration = scene.get("duration")
    if duration is not None and (not _number(duration) or duration <= 0):
        raise ValueError("duration must be a number of seconds above zero")
    validate(scene["mograph"])


# ---- colors and timing ----------------------------------------------------------------

def palette(theme, spec):
    """DEFAULT_PALETTE, then the theme's army_style, its mograph_style, the scene's colors."""
    merged = dict(DEFAULT_PALETTE)
    for source in ((theme or {}).get("army_style"), (theme or {}).get("mograph_style"),
                   spec.get("colors")):
        merged.update({k: v for k, v in (source or {}).items() if k in PALETTE_KEYS})
    return merged


def _word(text):
    return re.sub(r"[^a-z0-9&']", "", text.lower())


def _tokens(text):
    return [w for w in (_word(t) for t in text.split()) if w]


def _find(words, cue):
    """Word index where the narration first names a cue: its significant words in a row,
    else its first significant word alone. None when the narration never says it."""
    wanted = [w for w in _tokens(cue) if w not in STOPWORDS] or _tokens(cue)
    if not wanted:
        return None
    for i in range(len(words) - len(wanted) + 1):
        if words[i:i + len(wanted)] == wanted:
            return i
    return words.index(wanted[0]) if wanted[0] in words else None


def reveal_times(cues, narration, speech_s, scene_s):
    """Seconds into the scene at which each item lands: when the narration names it (a
    word-count estimate of where that word falls), else on an even spread through the
    first SPREAD_END of the narration. Always in order, MIN_GAP apart where the scene has
    room, and the last one at least SETTLE before the scene ends."""
    count = len(cues)
    span = speech_s if speech_s > 0 else scene_s
    end = max(FIRST_REVEAL, span * SPREAD_END)
    even = [FIRST_REVEAL + (end - FIRST_REVEAL) * i / max(1, count - 1) for i in range(count)]
    words = _tokens(narration or "") if speech_s > 0 else []
    times = []
    for i, cue in enumerate(cues):
        at = _find(words, cue) if words else None
        times.append(even[i] if at is None else max(MIN_START, speech_s * at / len(words) - CUE_LEAD))
    latest = max(MIN_START, scene_s - SETTLE)
    gap = min(MIN_GAP, (latest - MIN_START) / max(1, count - 1))
    for i in range(1, count):
        times[i] = max(times[i], times[i - 1] + gap)
    times[-1] = min(times[-1], latest)
    for i in range(count - 2, -1, -1):
        times[i] = min(times[i], times[i + 1] - gap)
    return [round(max(0.0, t), 3) for t in times]


def scene_seconds(work, scene):
    """(narration seconds, scene seconds), timed the way assemble times a scene."""
    import assemble   # lazy: assemble imports this module
    audio = assemble.audio_file(work, scene["id"])
    if audio:
        speech = assemble.probe_dur(audio)
        return speech, speech + assemble.PAD
    return 0.0, float(scene.get("duration", assemble.SILENT_SCENE_DUR))


def estimated_seconds(scene):
    """Before tts exists (the contact sheet), a word-count guess at scene_seconds."""
    import assemble
    words = len((scene.get("narration") or "").split())
    if words:
        speech = words / WORDS_PER_SECOND
        return speech, speech + assemble.PAD
    return 0.0, float(scene.get("duration", assemble.SILENT_SCENE_DUR))


# ---- props ----------------------------------------------------------------------------

def _str(block, key):
    """An optional text field as the template wants it: absent or null is ""."""
    return block.get(key) or ""


def _compare_props(spec, cue_at):
    items = spec["items"]
    times = cue_at([item.get("cue") or item["label"] for item in items])
    values = [item["value"] for item in items]
    highlight = spec.get("highlight")
    return {"title": _str(spec, "title"), "source": _str(spec, "source"),
            "prefix": _str(spec, "prefix"), "suffix": _str(spec, "suffix"),
            "decimals": spec.get("decimals", 0),
            "highlight": values.index(max(values)) if highlight is None else highlight,
            "items": [{"label": item["label"], "value": float(item["value"]),
                       "text": _str(item, "text"), "at": at} for item, at in zip(items, times)]}


def _punch_props(spec, _cue_at):
    return {"text": spec["text"], "em": [_word(w) for w in spec.get("em", [])],
            "kicker": _str(spec, "kicker"), "sub": _str(spec, "sub")}


def _list_props(spec, cue_at):
    items = [{"text": item, "sub": ""} if isinstance(item, str)
             else {"text": item["text"], "sub": _str(item, "sub"), "cue": item.get("cue")}
             for item in spec["items"]]
    times = cue_at([item.get("cue") or item["text"] for item in items])
    return {"title": _str(spec, "title"), "numbered": spec.get("numbered", True),
            "items": [{"text": item["text"], "sub": item["sub"], "at": at}
                      for item, at in zip(items, times)]}


KIND_PROPS = {"compare": _compare_props, "punch": _punch_props, "list": _list_props}


def props(scene, theme, speech_s, scene_s, fps, portrait):
    """Everything the template needs for one cut of one scene."""
    spec = scene["mograph"]

    def cue_at(cues):
        return reveal_times(cues, scene.get("narration", ""), speech_s, scene_s)
    return {"kind": spec["kind"], "portrait": bool(portrait), "fps": int(fps),
            "frames": max(1, math.ceil(round(scene_s * fps, 6))),
            "palette": palette(theme, spec), **KIND_PROPS[spec["kind"]](spec, cue_at)}


def chapter_label(scene):
    """Words for a YouTube chapter when a graphic scene has no caption: its title, its
    kicker, its punch line, else its first list item or bar label."""
    spec = scene.get("mograph") or {}
    first = (spec.get("items") or [None])[0]
    item = first if isinstance(first, str) else (first or {}).get("text") or (first or {}).get("label")
    return spec.get("title") or spec.get("kicker") or spec.get("text") or item or ""


# ---- rendering ------------------------------------------------------------------------

def template_files():
    """Everything a render depends on besides its props: the mograph components, the
    composition list and the font."""
    return [*sorted((TEMPLATE / "src" / "mograph").glob("*.ts*")),
            TEMPLATE / "src" / "Root.tsx", FONTS / "Anton-Regular.ttf"]


def template_hash():
    digest = hashlib.sha256()
    for path in template_files():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_path(work, scene_id, vertical):
    return Path(work) / f"mograph{'v' if vertical else ''}_{scene_id:02d}.mp4"


def node_dir(cfg=None):
    """The folder holding the node and npx the template runs on: NODE_DIR in config.env
    for a machine whose Node is not on PATH (the Linux server: ~/.local/opt/node-v26.7.0-linux-x64/bin),
    else wherever npx is on PATH."""
    cfg = common.load_config() if cfg is None else cfg
    configured = (cfg.get("NODE_DIR") or "").strip()
    if configured:
        folder = Path(configured).expanduser()
        if not Path(platform_util.tool("npx", folder)).exists():
            common.die(f"NODE_DIR={configured} in config.env has no npx in it")
        return folder
    found = shutil.which("npx")
    if not found:
        common.die("npx not found: install Node, or set NODE_DIR in config.env to the folder "
                   "that holds node and npx")
    return Path(found).parent


def remotion(cmd, props_, out, frame=None):
    """One Remotion CLI call: cmd "still" (one frame to a png) or "render" (a silent mp4)."""
    if not (TEMPLATE / "node_modules" / "remotion").exists():
        common.die("talking-head/node_modules is missing; it is not in git: run "
                   "`npm ci` in talking-head/ (docs/mograph.md, New machine)")
    node = node_dir()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(props_, handle)
    args = [platform_util.tool("npx", node), "remotion", cmd, "src/index.ts", COMPOSITION, str(out),
            f"--props={handle.name}", f"--public-dir={FONTS}", "--log=error"]
    if cmd == "still":
        args += [f"--frame={frame if frame is not None else props_['frames'] - 1}", "--image-format=png"]
    else:
        args += ["--codec=h264", "--crf=18", "--muted", "--concurrency=50%"]
    try:
        # npx starts node through `env`, so that node has to come first on PATH too
        path = f"{node}{os.pathsep}{os.environ.get('PATH', '')}"
        result = subprocess.run(args, cwd=TEMPLATE, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, env={**os.environ, "PATH": path})
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if result.returncode != 0:
        common.die(f"remotion {cmd} failed for {out.name}:\n{result.stderr[-1500:]}")


def still(scene, theme, out_path, w, h, portrait, fps=30):
    """The contact-sheet picture: the graphic's settled last frame, every item landed,
    scaled to the sheet's still size, with a MOTION badge. assemble never reads it."""
    from PIL import Image
    import clips
    speech_s, scene_s = estimated_seconds(scene)
    props_ = props(scene, theme, speech_s, scene_s, fps, portrait)
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "frame.png"
        remotion("still", props_, frame, frame=props_["frames"] - 1)
        picture = Image.open(frame).convert("RGB").resize((w, h), Image.LANCZOS)
    clips.draw_badge(picture, BADGE)
    picture.save(out_path)
    print(f"[mograph] {Path(out_path).name}: {props_['kind']}, settled frame")


def run(job_id, only_scene=None):
    """Render every mograph scene in both cuts (9:16 only for a portrait_only theme), timed
    to the narration tts recorded. A render is kept when neither its props nor the template
    (template_hash) have changed since it was made."""
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    fps = int(common.load_config()["FPS"])
    work = common.job_dir(job_id) / "work"
    cuts = (True,) if theme.get("portrait_only") else (False, True)
    template = template_hash()
    rendered = []
    for scene in data["scenes"]:
        if scene.get("mograph") is None or only_scene not in (None, scene["id"]):
            continue
        speech_s, scene_s = scene_seconds(work, scene)
        for vertical in cuts:
            props_ = props(scene, theme, speech_s, scene_s, fps, vertical)
            made_from = {"props": props_, "template": template}
            out = render_path(work, scene["id"], vertical)
            stamp = out.with_suffix(".json")
            if out.exists() and stamp.exists() and json.loads(stamp.read_text()) == made_from:
                print(f"[mograph] {out.name}: unchanged, kept")
                continue
            print(f"[mograph] {out.name}: rendering {props_['kind']}, {scene_s:.1f}s...", flush=True)
            remotion("render", props_, out)
            stamp.write_text(json.dumps(made_from))
            rendered.append(out)
    return rendered


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--scene", type=int)
    a = p.parse_args()
    run(a.job, a.scene)


if __name__ == "__main__":
    main()
