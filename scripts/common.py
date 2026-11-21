"""Shared helpers for the faceless-video pipeline: config, jobs, HTTP, themes."""
import json
import os
import re
import secrets
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
THEMES_DIR = ROOT / "themes"
CHARACTERS_DIR = ROOT / "characters"

# Non-interactive SSH shells (a cron job) miss the homebrew bin dir.
for _extra in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _extra not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _extra

DEFAULTS = {
    "TIM_MEDIA_URL": "http://127.0.0.1:8189",
    "TIM_LLM_URL": "http://127.0.0.1:8000",
    "FISH_MODEL": "s2.1-pro",
    # Working resolution since 2026-08-13: stills render at 1280x720 and are upscaled
    # by the delivery chain (which already scaled everything to 3840 for Ken Burns).
    # Tony A/B'd native 1920x1088 against this through the real pipeline and called the
    # upscale clean for flat vector art. schnell 15.6s -> 13s, dev 131s -> 44s, and dev
    # compositions are structurally BETTER inside FLUX's ~1MP training range (native
    # 1920 is past it, which is where wide-frame character duplication came from).
    # Captions and thumbnails were always rendered at delivery resolution; unaffected.
    # Portrait twin becomes 720x1280 (probed 2026-08-13: no hang, schnell 20.6s,
    # dev+reference 51.1s). Set IMG_W/IMG_H in config.env to override per machine.
    "IMG_W": "1280",
    "IMG_H": "720",
    "FPS": "30",
}


def load_config():
    """config.env (KEY=VALUE lines) merged over defaults; real env wins over both."""
    cfg = dict(DEFAULTS)
    env_file = ROOT / "config.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if value.strip():
                cfg[key.strip()] = value.strip()
    for key in list(cfg) + ["FISH_API_KEY", "BUNNY_STORAGE_KEY"]:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def http_json(url, payload=None, headers=None, timeout=300, retries=3, method=None,
              with_headers=False):
    """POST (or GET when payload is None) returning raw bytes. Retries on 5xx/network.
    with_headers=True returns (bytes, response_headers) so callers can read the
    X-Gen-Seconds / X-Model telemetry tim-media sends back."""
    body = json.dumps(payload).encode() if payload is not None else None
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if with_headers:
                    # uvicorn sends header names lowercase; normalize so callers can
                    # look up "x-gen-seconds" without caring how the server cased it.
                    return data, {k.lower(): v for k, v in resp.headers.items()}
                return data
        except urllib.error.HTTPError as err:
            detail = err.read()[:300].decode(errors="replace")
            last_err = f"HTTP {err.code} from {url}: {detail}"
            if err.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last_err = f"{url} unreachable: {err}"
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(last_err)


# Wikimedia and most news CDNs reject the default urllib agent outright, and a
# 403 there looks exactly like a missing file. Send a real one.
USER_AGENT = "faceless-video/1.0 (+https://brokerage.example)"


def http_get(url, timeout=60):
    """Fetch a binary asset (a photograph, usually). Separate from http_json so
    the JSON content type and retry-on-5xx semantics stay where they belong."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"HTTP {err.code} fetching {url}") from err
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise RuntimeError(f"{url} unreachable: {err}") from err


# Words that never describe a video on their own. The job word should be the subject:
# the city, the topic, the product.
_FILLER = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "if",
           "your", "you", "my", "what", "why", "how", "when", "who", "this", "that", "these",
           "self", "managed", "california", "ca", "rent", "control", "new", "must", "know",
           "every", "answer", "questions", "first", "can", "still", "really", "no", "not"}
_BILLS = {"AB", "SB", "ACA", "SCA"}


def job_word(word=None, title=None):
    """One lowercase word for the end of the job folder (Tony, 2026-09-27)."""
    if word:
        clean = re.sub(r"[^a-z0-9]", "", word.lower())[:20]
        if clean:
            return clean
    if title:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9']*", title)
        acronyms = [t for t in tokens if t.isupper() and len(t) >= 2 and t not in _BILLS]
        if acronyms:
            return acronyms[0].lower()[:20]
        for t in tokens:
            if t.lower() not in _FILLER and len(t) > 2:
                return re.sub(r"[^a-z0-9]", "", t.lower())[:20]
    return secrets.token_hex(2)


def check_jobs_drive():
    """On the Mac mini jobs/ links onto the external SSD; fail plainly when that drive is not mounted."""
    if JOBS_DIR.is_symlink() and not JOBS_DIR.exists():
        die(f"jobs/ links to {os.readlink(JOBS_DIR)}, which is not there. "
            "Is the SSD plugged in and mounted?")


def new_job(word=None, title=None):
    check_jobs_drive()
    base = time.strftime("%Y%m%d-%H%M%S") + "-" + job_word(word, title)
    job_id, n = base, 2
    while (JOBS_DIR / job_id).exists():
        job_id, n = f"{base}-{n}", n + 1
    job_dir = JOBS_DIR / job_id
    (job_dir / "work").mkdir(parents=True)
    (job_dir / "out").mkdir()
    return job_id, job_dir


def job_dir(job_id):
    path = JOBS_DIR / job_id
    if not path.is_dir():
        check_jobs_drive()
        die(f"no such job: {job_id}")
    return path


def load_scenes(job_id):
    path = job_dir(job_id) / "scenes.json"
    if not path.exists():
        die(f"job {job_id} has no scenes.json")
    data = json.loads(path.read_text())
    validate_scenes(data)
    return data


def validate_scenes(data):
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not 3 <= len(scenes) <= 14:
        die("scenes.json needs 3-14 scenes")
    first_shot = True
    for scene in scenes:
        specs = shot_specs(scene)
        # A clip scene may be silent: it is timed from the clip itself. A motion graphic
        # may be silent too (it runs for its "duration"), and its caption may be empty.
        if scene.get("mograph") is not None:
            required = ("id",)
        elif scene.get("clip") is not None:
            required = ("id", "caption")
        else:
            required = ("id", "narration", "caption")
        for field in required:
            if not scene.get(field) and scene.get(field) != 0:
                die(f"scene missing '{field}': {json.dumps(scene)[:120]}")
        # A motion graphic (docs/mograph.md) is drawn by the Remotion template from its
        # own block: nothing is generated for it, so none of the shot checks apply.
        if scene.get("mograph") is not None:
            import mograph
            try:
                mograph.validate_scene(scene)
            except ValueError as err:
                die(f"scene {scene.get('id')}: {err}")
            continue
        # A clip scene's picture is a finished video file (realistic footage): nothing
        # is generated for it, so none of the shot checks below apply.
        if scene.get("clip") is not None:
            validate_clip(scene)
            first_shot = False
            continue
        # A shot needs SOMETHING to put on screen: a prompt to generate from or a
        # photograph to ingest. image_prompt is no longer unconditionally required,
        # because a photo scene has no prompt to write.
        for i, spec in enumerate(specs, start=1):
            # A held shot reuses the background of the shot before it (a reaction beat,
            # a punch-in), so it has nothing to generate and needs no prompt.
            # A number card is drawn, not generated: no prompt, and nothing pasted on it.
            if spec.get("card") is not None:
                if spec.get("figure") or spec.get("photo") or spec.get("hold"):
                    die(f"scene {scene.get('id')} shot {i}: a 'card' shot stands alone, it "
                        f"cannot also have a figure, photo or hold")
                first_shot = False
                continue
            if spec.get("tag") is not None or spec.get("note") is not None:
                import doodle
                try:
                    doodle.validate_overlays(spec)
                except ValueError as err:
                    die(f"scene {scene.get('id')} shot {i}: {err}")
            # A graphic (docs/army.md, docs/swordfish.md) is drawn around its own FLUX
            # pictures; the theme decides which module draws it and which need a prompt.
            if spec.get("graphic") is not None:
                if spec.get("figure") or spec.get("photo") or spec.get("hold") \
                        or spec.get("card") is not None:
                    die(f"scene {scene.get('id')} shot {i}: a 'graphic' shot stands alone, "
                        f"it cannot also have a figure, photo, card or hold")
                graphics = graphics_module(data.get("theme", "sketch"))
                try:
                    graphics.validate(spec["graphic"], spec.get("prompt", ""))
                except ValueError as err:
                    die(f"scene {scene.get('id')} shot {i}: {err}")
                if graphics.has_backdrop(spec["graphic"], spec.get("prompt", "")):
                    first_shot = False
                continue
            if spec.get("hold"):
                if first_shot:
                    die(f"scene {scene.get('id')} shot {i}: the first shot of a video "
                        f"cannot 'hold', there is no earlier background to hold on")
                if spec.get("photo"):
                    die(f"scene {scene.get('id')} shot {i}: 'hold' and 'photo' cannot combine")
                first_shot = False
                continue
            first_shot = False
            if not spec.get("prompt") and not spec.get("photo"):
                die(f"scene {scene.get('id')} shot {i}: needs an 'image_prompt'/'prompt' "
                    f"or a 'photo': {json.dumps(scene)[:120]}")
        for spec in specs:
            if spec.get("photo") and spec.get("figure"):
                die(f"scene {scene.get('id')}: a shot cannot have both 'photo' and "
                    f"'figure' (the photo replaces the generated frame the figure "
                    f"would be pasted onto)")
            figure = spec.get("figure")
            members = figure if isinstance(figure, list) else [figure]
            for member in members if figure is not None else []:
                if not (isinstance(member, dict) and member.get("pose")):
                    die(f"scene {scene.get('id')}: figure block needs at least a 'pose': "
                        f"{json.dumps(member)[:120]}")
        motion = scene.get("motion")
        if motion is not None:
            if not isinstance(motion, dict):
                die(f"scene {scene.get('id')}: motion must be an object, got "
                    f"{json.dumps(motion)[:120]}")
            model = motion.get("model", "ltx")
            if model not in MOTION_MODELS:
                die(f"scene {scene.get('id')}: motion model '{model}' unknown "
                    f"(have: {', '.join(MOTION_MODELS)})")
            # A cuts scene shows several stills in sequence; a motion clip replaces
            # the picture wholesale, so the extra shots would silently never appear.
            if scene.get("shots") and len(scene["shots"]) > 1:
                die(f"scene {scene.get('id')}: a motion block cannot be combined with "
                    f"multiple shots (the clip replaces the whole scene's picture)")


CLIP_AUDIO = ("keep", "duck", "mute")   # what a clip scene does with its own sound


def validate_clip(scene):
    """A clip replaces the scene's whole picture, so it stands alone: a photo, figure,
    animation, extra shot, prompt or drawn overlay beside it would never reach the final
    (and a tag or note would still show on the contact sheet, which would mislead)."""
    clip = scene["clip"]
    if not isinstance(clip, str) or not clip.strip():
        die(f"scene {scene.get('id')}: 'clip' must name a video file, got {json.dumps(clip)[:80]}")
    for other in ("photo", "figure", "motion", "shots", "image_prompt", "card", "graphic",
                  "hold", "tag", "note", "mograph"):
        if scene.get(other) is not None:
            die(f"scene {scene.get('id')}: a 'clip' scene cannot also have '{other}' "
                f"(the clip replaces the whole scene's picture)")
    if "audio" in scene and scene["audio"] not in CLIP_AUDIO:
        die(f"scene {scene.get('id')}: 'audio' must be keep, duck or mute, got "
            f"{json.dumps(scene['audio'])[:40]}")
    trim = scene.get("trim")
    if trim is None:
        return
    numbers = isinstance(trim, list) and len(trim) == 2 and all(
        isinstance(t, (int, float)) and not isinstance(t, bool) for t in trim)
    if not numbers or not 0 <= trim[0] < trim[1]:
        die(f"scene {scene.get('id')}: 'trim' must be [start, end] in seconds with start "
            f"before end, got {json.dumps(trim)[:80]}")


def shot_specs(scene):
    """Every shot of a scene as {"prompt": str, "figure": dict|None,
    "photo": str|None, "focus": str, ...}.

    A shots entry may be a plain prompt string or {"prompt": ..., "figure": {...}}.
    A single-image scene carries the figure block at scene level. A figure block
    means the drawn character gets composited onto the frame after generation, so
    the prompt should describe the background only.

    A "photo" is a real photograph used INSTEAD of generating the frame. It wins
    over prompt and figure: nothing is sent to FLUX for that shot. "focus" says
    where to anchor the crop (auto|top|upper|center|lower|bottom).

    "tag" and "note" are drawn over the finished still (doodle.overlay); "line" is
    the part of the narration the shot shows, which times the cut (assemble)."""
    raw = scene.get("shots")
    if not raw:
        return [_spec(scene, scene.get("image_prompt", ""))]
    return [_spec(shot, shot.get("prompt", "")) if isinstance(shot, dict) else _spec({}, shot)
            for shot in raw]


def _spec(source, prompt):
    return {"prompt": prompt,
            "figure": source.get("figure"),
            "photo": source.get("photo"),
            "focus": source.get("focus", "auto"),
            "card": source.get("card"),
            "graphic": source.get("graphic"),
            "hold": bool(source.get("hold")),
            "punch": source.get("punch", 1.0),
            "punch_x": source.get("punch_x", 0.5),
            "tag": source.get("tag"),
            "note": source.get("note"),
            "line": source.get("line")}


def graphics_module(theme):
    """The module that draws a theme's graphic shots: army.py, or doodle.py for a theme
    with "graphics": "doodle" (docs/swordfish.md). theme is a loaded theme or a name.
    Imported on first use so themes without graphic shots never load either."""
    if isinstance(theme, str):
        theme = load_theme(theme)
    if (theme or {}).get("graphics") == "doodle":
        import doodle
        return doodle
    import army
    return army


# Words that mean a person is in the shot. If one of these appears but the theme's
# reference phrase does not, the character description silently never gets injected
# and FLUX invents its own person. That failure is invisible until you look at the
# stills, so catch it before spending render time.
# Motion tier, measured on Tim 2026-08-13 (121 frames, 5s): ltx 46.1s at 480x832 and
# 73.3s at the 1280x704 working canvas, hunyuan ~8x that but performs bigger camera
# moves, wan 571.1s and largely ignores motion direction (kept for reproducibility).
MOTION_MODELS = ("ltx", "hunyuan", "wan")

PERSON_WORDS = (
    "character", "person", "man", "woman", "figure", "he ", "she ", "his ", "her ",
    "someone", "people", "tenant", "owner", "board member", "neighbor", "hero",
)


def check_character_refs(scenes, reference_phrase):
    """Return [(scene_id, shot_index, prompt)] for shots that look like they contain a
    person but never say the reference phrase, so the character spec will not be injected.
    Shots with a figure block are exempt: the character is drawn onto them after
    generation, so their prompts are supposed to be background-only. Graphic and card
    shots are exempt too: they never take the hero path."""
    phrase = reference_phrase.lower()
    misses = []
    for scene in scenes:
        for i, spec in enumerate(shot_specs(scene), start=1):
            if spec["figure"] is not None or spec.get("photo") or spec.get("graphic") is not None \
                    or spec.get("card") is not None:
                continue
            text = spec["prompt"].lower()
            if phrase in text:
                continue
            if "no people" in text or "no person" in text:
                continue
            # Supporting cast is described inline with the same design language rather
            # than injected. A shot that already spells out the head is self-describing,
            # so flagging it would make this warning noise on every video with a crowd.
            if "white head" in text:
                continue
            if any(word in text for word in PERSON_WORDS):
                misses.append((scene.get("id"), i, spec["prompt"]))
    return misses


def load_character(name):
    path = CHARACTERS_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in CHARACTERS_DIR.glob("*.json")))
        die(f"unknown character '{name}' (available: {available})")
    return json.loads(path.read_text())


def load_theme(name_or_obj):
    if isinstance(name_or_obj, dict):
        theme = name_or_obj
    else:
        path = THEMES_DIR / f"{name_or_obj}.json"
        if not path.exists():
            available = ", ".join(sorted(p.stem for p in THEMES_DIR.glob("*.json")))
            die(f"unknown theme '{name_or_obj}' (available: {available})")
        theme = json.loads(path.read_text())
    # A theme may reference a library character by name instead of (or in
    # addition to) an inline character_desc; the library wins.
    if theme.get("character"):
        character = load_character(theme["character"])
        theme = {**theme, "character_desc": character["prompt_desc"]}
        # A reference image beats any amount of description: the character comes from
        # pixels instead of forty words that FLUX is free to reinterpret.
        reference = character.get("reference") or {}
        if reference.get("file"):
            theme = {**theme,
                     "reference_file": reference["file"],
                     "reference_strength": float(reference.get("strength", 0.2)),
                     "reference_mode": reference.get("mode", "attn_bias")}

        # A character LoRA is only used once it has beaten prompt-pinning on a
        # side-by-side and been marked deployable. Trained-but-unproven weights stay
        # off, so a bad run can never quietly degrade every render.
        lora = character.get("lora") or {}
        if lora.get("deployable") and lora.get("file"):
            theme = {**theme,
                     "lora_file": lora["file"],
                     "lora_strength": float(lora.get("strength", 1.0)),
                     "lora_trigger": lora.get("trigger", "")}
    return theme


def get_state(job_id):
    path = job_dir(job_id) / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def set_state(job_id, **updates):
    path = job_dir(job_id) / "state.json"
    state = {**get_state(job_id), **updates, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)          # replace, not rename: Windows refuses to rename over a file
    return state
