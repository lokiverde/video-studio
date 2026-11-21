"""faceless-video orchestrator CLI. What other agents and the MCP server call.

  fv.py make --article-url URL [--theme sketch] [--voice stock] [--no-preview]
  fv.py make --outline-file outline.md ...
  fv.py make --scenes-file scenes.json ...      (LLM caller authored the script)
  fv.py regen-scene JOB N [--prompt "..."] [--seed 123]
  fv.py finish JOB [--voice tony] [--engine tim|kokoro|fish] [--music file.mp3]
  fv.py status JOB
  fv.py bloglink JOB URL                        companion article URL, first line of every description
  fv.py links JOB [--youtube ID] [--blog URL]   fill the LinkedIn first comment (links.json, no re-approval)
  fv.py publish JOB [--go] [--drop N] [--at N=WHEN]   Shorts + LinkedIn video into Blotato (Go table first)
  fv.py save-theme NAME --from-job JOB [--character "..."]
  fv.py themes
"""
import argparse
import json
import shutil

import common
import dash_rule
import approval
import time
import write_script
import gen_images
import qc_frames
import motion
import mograph
import tts
import voiceover
import assemble
import thumbnail
import publish_kit
import kit_links
import publish
import rf
import upload


def warn_unreferenced_character(job_id):
    """The character spec is only injected into prompts containing the theme's reference
    phrase. A hero shot that omits it renders a generic person instead, and nothing says
    so until you look at the stills. Say so here instead."""
    data = json.loads((common.job_dir(job_id) / "scenes.json").read_text())
    theme = common.load_theme(data.get("theme"))
    if not theme.get("character"):
        return
    character = common.load_character(theme["character"])
    phrase = character.get("reference_phrase", "the main character")
    misses = common.check_character_refs(data["scenes"], phrase)
    if misses:
        print(f"[fv] WARNING: {len(misses)} shot(s) look like they contain a person but "
              f'never say "{phrase}", so {character.get("display_name", theme["character"])} '
              f"will NOT be injected and FLUX will invent its own:")
        for scene_id, shot_i, prompt in misses:
            print(f"[fv]   scene {scene_id} shot {shot_i}: {prompt[:90]}")
        print(f'[fv] Fix: rewrite those shots to say "{phrase}", or add "no people" if the '
              f"shot is objects only.")
    # The inverse mistake on figure shots: the prompt is supposed to be background-only,
    # so mentioning the character there makes FLUX draw a second one under the paste.
    doubles = [(scene.get("id"), i, spec["prompt"])
               for scene in data["scenes"]
               for i, spec in enumerate(common.shot_specs(scene), start=1)
               if spec["figure"] is not None and phrase in spec["prompt"].lower()]
    if doubles:
        print(f"[fv] WARNING: {len(doubles)} figure shot(s) mention \"{phrase}\" in the "
              f"prompt. The character is drawn and pasted on figure shots; the prompt must "
              f"describe the background only or FLUX generates a second person:")
        for scene_id, shot_i, prompt in doubles:
            print(f"[fv]   scene {scene_id} shot {shot_i}: {prompt[:90]}")


def cmd_make(a):
    title = json.loads(open(a.scenes_file).read()).get("title") if a.scenes_file else None
    job_id, jdir = common.new_job(word=a.word, title=title)
    print(f"[fv] job {job_id}")
    if a.scenes_file:
        data = json.loads(open(a.scenes_file).read())
        common.validate_scenes(data)
        data.setdefault("theme", a.theme)
        data.setdefault("voice", a.voice)
        (jdir / "scenes.json").write_text(json.dumps(data, indent=2))
        common.set_state(job_id, status="scripted", title=data.get("title", ""))
    else:
        write_script.run(job_id, a.article_url, a.article_file, a.outline_file,
                         a.theme, a.voice)

    warn_unreferenced_character(job_id)
    gen_images.run(job_id)
    # Structural screen on the generated (dev-path) hero frames only; figure shots
    # are exempt because the drawn character cannot break. Wired in 2026-08-13;
    # before that this was a by-hand step that was easy to forget.
    qc_frames.run(job_id)
    # The 9:16 cut gets its own native renders by default (2026-09-16). A centre crop of
    # the landscape frame slices off any figure placed left or right of middle.
    if not a.no_portrait:
        gen_images.run_portrait(job_id)
        qc_frames.run(job_id, portrait=True)
    try:
        upload.run(job_id, previews=True)
    except (RuntimeError, SystemExit):
        print("[fv] preview upload skipped (Bunny not configured or unreachable)")

    if a.no_preview:
        cmd_finish_impl(job_id, a.voice, a.engine, a.music)
    else:
        common.set_state(job_id, status="previewed")
        state = common.get_state(job_id)
        print(f"[fv] PREVIEW READY for job {job_id}")
        print(f"[fv] contact sheet 16:9: {jdir / 'work' / 'contact_sheet.jpg'}")
        if (jdir / "work" / "contact_sheet_9x16.jpg").exists():
            print(f"[fv] contact sheet 9:16: {jdir / 'work' / 'contact_sheet_9x16.jpg'}")
        for url in state.get("preview_urls", []):
            print(f"[fv] {url}")
        print(f"[fv] next: fv.py finish {job_id}   (or regen-scene {job_id} N first)")


def cmd_regen(a):
    if getattr(a, "portrait", False):
        gen_images.run_portrait(a.job, only_scene=a.scene, only_shot=a.shot,
                                seed=a.seed, prompt_override=a.prompt)
        return
    gen_images.run(a.job, only_scene=a.scene, seed=a.seed, prompt_override=a.prompt,
                   only_shot=a.shot)
    # Keep the two cuts telling the same story: a landscape reroll (often with a new
    # prompt, already saved to scenes.json) re-renders its portrait twin as well.
    if common.get_state(a.job).get("portrait") and not getattr(a, "landscape_only", False):
        gen_images.run_portrait(a.job, only_scene=a.scene, only_shot=a.shot)
    try:
        upload.run(a.job, previews=True)
    except (RuntimeError, SystemExit):
        pass


def remembered_music(job_id, music):
    """The bed a job was finished with is remembered in state, so a later re-assembly
    (verticalize, a second finish) keeps the same sound without being told again."""
    if music:
        common.set_state(job_id, music=music)
        return music
    return common.get_state(job_id).get("music")


def require_approval(job_id, waived):
    """Nothing renders until Tony has seen the contact sheets and said go."""
    reason = approval.gate(common.get_state(job_id), approval.fingerprint(common.job_dir(job_id), "faceless"), waived)
    if reason:
        common.die(f"[fv] BLOCKED: {reason}.\n"
                   f"      sheets: jobs/{job_id}/work/contact_sheet.jpg and contact_sheet_9x16.jpg\n"
                   f"      after Tony says go: fv.py approve {job_id}   (his explicit waiver only: --no-preview)")


def cmd_approve(a):
    """Record Tony's go. Run this ONLY after he has seen both sheets and approved in chat."""
    jdir = common.job_dir(a.job)
    problem = approval.faceless_sheet_problem(jdir)
    if problem:
        common.die(f"[fv] cannot approve: {problem}")
    common.set_state(a.job, approved_fingerprint=approval.fingerprint(jdir, "faceless"),
                     approved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"[fv] approved {a.job}. Any edit to scenes.json or a rerolled still voids this.")


def cmd_finish(a):
    require_approval(a.job, a.no_preview)
    remember_music_volume(a.job, a.music_volume)
    cmd_finish_impl(a.job, a.voice, a.engine, a.music)


def cmd_voiceover(a):
    """Tony's own recorded take replaces TTS, then the rest of finish runs unchanged."""
    require_approval(a.job, a.no_preview)
    remember_music_volume(a.job, a.music_volume)
    cmd_finish_impl(a.job, music=a.music,
                    narrate=lambda job: voiceover.run(job, a.take, clean=a.clean,
                                                      max_pause=a.max_pause, eq=not a.no_eq))


def remember_music_volume(job_id, level):
    """--music-volume is kept in state like the music bed, so a re-assembly keeps it."""
    if level is not None:
        common.set_state(job_id, music_volume=level)


def cmd_verticalize(a):
    """New portrait stills are something Tony has not seen, so this stops at the sheet
    unless the preview is waived."""
    gen_images.run_portrait(a.job)
    qc_frames.run(a.job, portrait=True)
    if not a.no_preview:
        print(f"[fv] PORTRAIT PREVIEW READY: jobs/{a.job}/work/contact_sheet_9x16.jpg")
        print(f"[fv] show Tony, then: fv.py approve {a.job} && fv.py finish {a.job}")
        return
    mograph.run(a.job)
    assemble.run(a.job, remembered_music(a.job, a.music))
    publish_kit.run(a.job)
    upload.run(a.job, previews=True)
    upload.run(a.job)


def cmd_finish_impl(job_id, voice=None, engine="tim", music=None, narrate=None):
    music = remembered_music(job_id, music)
    if narrate:
        narrate(job_id)
    else:
        tts.run(job_id, voice, engine)
    # Motion and motion graphics run between narration and assembly: clip length is
    # chosen to match each scene's narration, which does not exist until tts has run.
    motion.run(job_id)
    mograph.run(job_id)
    assemble.run(job_id, music)
    thumbnail.run(job_id)
    publish_kit.run(job_id)
    try:
        urls = upload.run(job_id)
    except (RuntimeError, SystemExit):
        urls = []
        print("[fv] CDN upload failed; finals are local only")
    out = common.job_dir(job_id) / "out"
    print(f"[fv] DONE {job_id}")
    finals = [n for n in ("final_16x9.mp4", "final_9x16.mp4") if (out / n).exists()]
    print("[fv] local: " + " + ".join(str(out / n) for n in finals)
          + (" + thumbnail.jpg" if (out / "thumbnail.jpg").exists() else ""))
    if (out / "youtube.md").exists():
        print(f"[fv] publish kit: {out / 'youtube.md'} + transcript.txt + transcript.srt")
    for url in urls:
        print(f"[fv] {url}")


def cmd_save_theme(a):
    data = common.load_scenes(a.from_job)
    theme = dict(common.load_theme(data.get("theme", "sketch")))
    theme["name"] = a.name
    theme["voice"] = common.get_state(a.from_job).get("voice", theme.get("voice", "stock"))
    if a.character:
        theme["character_desc"] = a.character
    path = common.THEMES_DIR / f"{a.name}.json"
    path.write_text(json.dumps(theme, indent=2))
    print(f"[fv] theme saved: {path}")
    print("[fv] tip: character_desc is what keeps a recurring character consistent")


def cmd_status(a):
    state = common.get_state(a.job)
    print(json.dumps(state, indent=2))


def cmd_props(_a):
    import composite  # noqa: F401  (puts the character directory on the path)
    import props
    for name, (_fn, what) in props.LIBRARY.items():
        print(f"{name:12s} {what}")
    print('\nUse on a figure block: "prop": "phone"  or  "prop": {"name": "phone", "hand": "l"}')


def cmd_poses(_a):
    import composite
    print("poses:   " + ", ".join(composite.pose_names()))
    print("moods:   " + ", ".join(composite.MOODS))
    print("shots:   " + ", ".join(composite.SHOTS))
    print("who:     " + ", ".join(composite.figure.LOOKS))


def cmd_themes(_a):
    for path in sorted(common.THEMES_DIR.glob("*.json")):
        theme = json.loads(path.read_text())
        print(f"{path.stem:20s} {theme.get('description', '')}")


def cmd_characters(_a):
    for path in sorted(common.CHARACTERS_DIR.glob("*.json")):
        char = json.loads(path.read_text())
        lora = char.get("lora") or {}
        tag = f" [lora: {lora['trigger']}]" if lora.get("trigger") else ""
        print(f"{char.get('display_name', path.stem)} ({path.stem}){tag}")
        print(f"  {char.get('description', '')}")


def cmd_log_script(a):
    import time
    entry = {
        "date": time.strftime("%Y-%m-%d"),
        "job_id": a.job,
        "title": a.title or common.get_state(a.job).get("title", ""),
        "platform": a.platform,
        "hook_category": a.hook,
        "framework": a.framework,
        "tone": a.tone,
        "opening_phrase": a.opening,
        "cta": a.cta,
        "topic": a.topic,
        "angle": a.angle,
        "length_s": common.get_state(a.job).get("duration_s"),
    }
    # AI footage videos also record their camera technique and style, so results can be
    # compared within the format. Plain lines stay exactly as they were.
    entry.update({k: v for k, v in (("format", a.format), ("technique", a.technique),
                                    ("style", a.style)) if v})
    hist = common.ROOT / "history"
    hist.mkdir(exist_ok=True)
    with open(hist / "scripts.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[fv] logged script history for {a.job}")


def cmd_script_history(a):
    path = common.ROOT / "history" / "scripts.jsonl"
    if not path.exists():
        print("no history yet")
        return
    lines = path.read_text().strip().splitlines()[-a.last:]
    for line in lines:
        e = json.loads(line)
        print(f"{e['date']} {e.get('hook_category', '?'):16s} {e.get('framework', '?'):24s} "
              f"{e.get('tone', '?'):14s} {e.get('title', '')[:40]}")


def cmd_sfx(_a):
    lib_path = common.ROOT / "assets" / "sfx" / "library.json"
    lib = json.loads(lib_path.read_text()) if lib_path.exists() else {}
    for name, desc in lib.items():
        if name.startswith("_"):
            continue
        exists = (common.ROOT / "assets" / "sfx" / f"{name}.mp3").exists()
        print(f"{name:12s} {'' if exists else '[MISSING] '}{desc}")


def cmd_save_character(a):
    char = {
        "name": a.name,
        "display_name": a.display_name or a.name.replace("-", " ").title(),
        "description": a.desc,
        "prompt_desc": a.look,
        "reference_phrase": a.reference or "the main character",
        "lora": None,
    }
    path = common.CHARACTERS_DIR / f"{a.name}.json"
    path.write_text(json.dumps(char, indent=2))
    print(f"[fv] character saved: {path}")
    print(f"[fv] use in a theme with \"character\": \"{a.name}\"")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="script + images + preview gate (or full render with --no-preview)")
    m.add_argument("--article-url")
    m.add_argument("--article-file")
    m.add_argument("--outline-file")
    m.add_argument("--scenes-file", help="pre-authored scenes.json (skips Tim LLM)")
    m.add_argument("--word", help="one word for the job folder: the city or topic")
    m.add_argument("--theme", default="sketch")
    m.add_argument("--voice", default="stock", help="stock | tony | a Kokoro voice id (e.g. am_onyx)")
    m.add_argument("--engine", default="tim", choices=["tim", "chatterbox", "kokoro", "fish"])
    m.add_argument("--music")
    m.add_argument("--no-preview", action="store_true")
    m.add_argument("--no-portrait", action="store_true",
                   help="skip the native 9:16 render pass (the vertical cut falls back to a centre crop)")
    m.set_defaults(fn=cmd_make)

    r = sub.add_parser("regen-scene", help="reroll one scene's image")
    r.add_argument("job")
    r.add_argument("scene", type=int)
    r.add_argument("--shot", type=int, default=1, help="which shot of the scene (1-based)")
    r.add_argument("--prompt")
    r.add_argument("--seed", type=int)
    r.add_argument("--portrait", action="store_true",
                   help="reroll ONLY the p_ portrait render (9:16), leave landscape alone")
    r.add_argument("--landscape-only", action="store_true",
                   help="reroll ONLY the landscape render, leave the portrait twin alone")
    r.set_defaults(fn=cmd_regen)

    f = sub.add_parser("finish", help="tts + assemble + upload an approved job")
    f.add_argument("job")
    f.add_argument("--voice", help="stock | tony | a Kokoro voice id (e.g. am_onyx)")
    f.add_argument("--engine", default="tim", choices=["tim", "chatterbox", "kokoro", "fish"])
    f.add_argument("--music")
    f.add_argument("--music-volume", type=float,
                   help="music level under narration, 0 to 1 (default 0.18), remembered for the job")
    f.add_argument("--no-preview", action="store_true",
                   help="skip the approval gate. ONLY on Tony's explicit waiver or a fully unattended run")
    f.set_defaults(fn=cmd_finish)

    vo = sub.add_parser("voiceover", help="finish an approved job with Tony's own recorded take instead of TTS")
    vo.add_argument("job")
    vo.add_argument("take", help="one recording of the whole script (m4a, mp3, wav, mov...)")
    vo.add_argument("--music")
    vo.add_argument("--music-volume", type=float,
                    help="music level under narration, 0 to 1 (default 0.18), remembered for the job")
    vo.add_argument("--clean", action="store_true",
                    help="run the echo cleanup on the take too (only for a roomy recording)")
    vo.add_argument("--max-pause", type=float, default=voiceover.MAX_PAUSE,
                    help=f"longest pause kept inside a scene, seconds (default {voiceover.MAX_PAUSE:g}; "
                         "0 keeps the read's own pauses)")
    vo.add_argument("--no-eq", action="store_true",
                    help="skip the mic EQ Tony picked for his voice-over mic (use for a phone memo or other mic)")
    vo.add_argument("--no-preview", action="store_true",
                    help="skip the approval gate. ONLY on Tony's explicit waiver")
    vo.set_defaults(fn=cmd_voiceover)

    ap = sub.add_parser("approve", help="record Tony's go after he has seen both contact sheets")
    ap.add_argument("job")
    ap.set_defaults(fn=cmd_approve)

    v = sub.add_parser("verticalize", help="portrait-native renders for the 9:16 cut, then re-assemble")
    v.add_argument("job")
    v.add_argument("--music")
    # The portrait pass re-rolls the character lottery (measured 2026-08-11: 10/58
    # off-model), so it gets the same structural screen as the landscape set.
    v.add_argument("--no-preview", action="store_true")
    v.set_defaults(fn=cmd_verticalize)

    k = sub.add_parser("kit", help="(re)write transcript.txt, transcript.srt and youtube.md for a rendered job")
    k.add_argument("job")
    k.set_defaults(fn=lambda a: publish_kit.run(a.job))

    kit_links.add_parsers(sub)            # bloglink + links: post-publication links, approval stays valid
    rf.add_parsers(sub)                   # rf new | status | ingest: realistic footage jobs
    publish.add_parsers(sub)              # publish + blotato-accounts: the Blotato auto-poster

    mo = sub.add_parser("motion", help="animate the stills of scenes carrying a motion block")
    mo.add_argument("job")
    mo.add_argument("--scene", type=int, help="only this scene")
    mo.add_argument("--seed", type=int, help="force a seed (default: fresh each run)")
    mo.set_defaults(fn=lambda a: motion.run(a.job, a.scene, a.seed))

    mg = sub.add_parser("mograph", help="render the motion graphic scenes (docs/mograph.md), both cuts")
    mg.add_argument("job")
    mg.add_argument("--scene", type=int, help="only this scene")
    mg.set_defaults(fn=lambda a: mograph.run(a.job, a.scene))

    rs = sub.add_parser("restage", help="re-paste figures onto stored backgrounds after editing poses/moods/framing (no FLUX)")
    rs.add_argument("job")
    rs.set_defaults(fn=lambda a: gen_images.restage(a.job))

    s = sub.add_parser("status", help="print job state")
    s.add_argument("job")
    s.set_defaults(fn=cmd_status)

    t = sub.add_parser("save-theme", help="save a job's look as a reusable theme")
    t.add_argument("name")
    t.add_argument("--from-job", required=True)
    t.add_argument("--character", help="recurring character description to pin into every prompt")
    t.set_defaults(fn=cmd_save_theme)

    sub.add_parser("themes", help="list themes").set_defaults(fn=cmd_themes)

    sub.add_parser("characters", help="list the character library").set_defaults(fn=cmd_characters)

    sub.add_parser("sfx", help="list the sound effect library").set_defaults(fn=cmd_sfx)
    sub.add_parser("props", help="list the drawn prop library").set_defaults(fn=cmd_props)
    sub.add_parser("poses", help="list poses, moods, framings and cast for figure blocks").set_defaults(fn=cmd_poses)

    ls_ = sub.add_parser("log-script", help="append a script's attributes to history (variety control)")
    ls_.add_argument("job")
    ls_.add_argument("--hook", required=True, help="hook category used")
    ls_.add_argument("--framework", required=True)
    ls_.add_argument("--tone", required=True)
    ls_.add_argument("--opening", required=True, help="first ~8 words of the script")
    ls_.add_argument("--cta", default="")
    ls_.add_argument("--topic", default="")
    ls_.add_argument("--angle", default="")
    ls_.add_argument("--title")
    ls_.add_argument("--platform", default="multi")
    ls_.add_argument("--format", choices=["ai-footage"], help="ai-footage for realistic footage videos")
    ls_.add_argument("--technique", help="camera behavior of an AI footage video, e.g. whip-pan")
    ls_.add_argument("--style", help="camera style of an AI footage video, e.g. phone-snapshot")
    ls_.set_defaults(fn=cmd_log_script)

    sh = sub.add_parser("script-history", help="show recent script attributes")
    sh.add_argument("--last", type=int, default=20)
    sh.set_defaults(fn=cmd_script_history)

    c = sub.add_parser("save-character", help="save a reusable named character")
    c.add_argument("name", help="kebab-case id, e.g. stick-man")
    c.add_argument("--desc", required=True, help="plain-English description (what the bot explains)")
    c.add_argument("--look", required=True, help="visual prompt description injected into image prompts")
    c.add_argument("--display-name")
    c.add_argument("--reference", help="phrase scripts use to invoke them (default: the main character)")
    c.set_defaults(fn=cmd_save_character)

    args = p.parse_args()
    dash_rule.guard_command(args.cmd, getattr(args, "job", None), common.JOBS_DIR)
    args.fn(args)


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        common.die("ffmpeg not installed (brew install ffmpeg)")
    try:
        main()
    except RuntimeError as err:
        common.die(str(err))
