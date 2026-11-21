#!/usr/bin/env python3
"""Talking-head wrapper CLI. Tony films himself, this wraps the footage in the evidence
layout (portrait card + source panels + captions) and renders 16:9 and 9:16.

  th.py new <video> [--title T] [--word city]   job folder (ends in the word), footage prep, transcript
  th.py find <job> "phrase"         source timestamps where a phrase is spoken
  th.py check <job>                 validate job.json
  th.py sheet <job>                 contact sheets for both cuts + caption QC, shown to Tony
  th.py capqc <job>                 caption QC alone: over the mouth or chin, or hard to read
  th.py approve <job>               record Tony's go (only after he says so)
  th.py render <job> [--only 16x9|9x16]   blocked until approved, then writes the publish kit
  th.py kit <job>                   rewrite transcript.txt, transcript.srt, youtube.md (+ route.md and
                                    video_library_entry.txt once rendered)
  th.py music <job> <track> [--level -30] [--hook-track T] [--no-sfx]
                                    ducked bed (+ suspense under the hook, + SFX) into the finals, no re-render
  th.py takes plan <script.md> <main> [<other> ...] --out <dir> | takes splice <dir>
                                    several takes in, best attempt per script section, one master out
  th.py enhance <job> [--undo]      clean up the voice (denoise, EQ, compression, -14 LUFS)
  th.py enhance <job> --export      WAV for Adobe Podcast Enhance; --adobe <wav> swaps it back in
  th.py revoice <job> --export|--adobe <wav>   same, on already rendered finals (+ music)
  th.py level <job> [--switch S]    lift quiet off-mic speech in the finals (audio QC quiet
                                    stretches), re-mix the music, then re-cut the Shorts
  th.py words <job>                 re-transcribe the final, list words lost at a cut (runs after
                                    render and revoice too)

After render, every video: th_shorts.py (2 to 3 Shorts) and yt_thumb.py (thumbnail).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import time

import approval
import audio_qc
import capqc
import common
import platform_util
import kit_links
import lanes
import publish_kit
import room_voice
import takes
import th_army
import th_lib
import transcribe
import voice_level
import wordcheck

TEMPLATE = common.ROOT / "talking-head"
COMPS = {"16x9": "Landscape", "9x16": "Portrait"}
SHEET_COLS = {"16x9": 4, "9x16": 6}


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, **kw)
    if result.returncode != 0:
        common.die(f"command failed: {' '.join(map(str, cmd[:4]))}...\n{result.stderr[-1500:]}")
    return result


def load_job(job_id):
    path = common.job_dir(job_id) / "job.json"
    if not path.exists():
        common.die(f"job {job_id} has no job.json (is it a talking-head job?)")
    return json.loads(path.read_text())


def load_words(job_id):
    data = json.loads((common.job_dir(job_id) / "transcript.json").read_text())
    return [w for seg in data["segments"] for w in seg["words"]]


def detect_silences(audio):
    out = subprocess.run(
        ["ffmpeg", "-i", str(audio), "-af", "silencedetect=noise=-32dB:d=0.9", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))


def cmd_new(args):
    video = Path(args.video).expanduser()
    if not video.exists():
        common.die(f"no such file: {video}")
    job_id, jdir = common.new_job(word=args.word, title=args.title)
    public = jdir / "public"
    public.mkdir(parents=True, exist_ok=True)
    (jdir / "out").mkdir(exist_ok=True)
    (jdir / "work").mkdir(exist_ok=True)
    print(f"[th] job {job_id}")
    # dense keyframes so Remotion can seek anywhere without stutter
    # Camera files arrive as 4K 10-bit HEVC at 29.97 with data and thumbnail tracks. The
    # renderer needs 8-bit H.264 at the template's 30 fps, first video + first audio only.
    # 1440p keeps the 9:16 full-frame crop sharp without 4K decode cost.
    run(["ffmpeg", "-y", "-i", str(video), "-map", "0:v:0", "-map", "0:a:0",
         "-vf", "scale=-2:'min(1440,ih)'", "-r", "30", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-g", "30",
         "-c:a", "aac", "-b:a", "192k", str(public / "footage.mp4")])
    audio = jdir / "work" / "audio.wav"
    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    print("[th] transcribing...")
    print(f"[th] transcribed with {transcribe.transcribe(audio, jdir / 'transcript.json')}")
    data = json.loads((jdir / "transcript.json").read_text())
    lines = [f"{s['start']:7.2f} {s['end']:7.2f}  {s['text'].strip()}" for s in data["segments"]]
    (jdir / "transcript.txt").write_text("\n".join(lines) + "\n")
    words = [w for seg in data["segments"] for w in seg["words"]]
    shaky = [f"{w['start']:.2f} {w['word'].strip()} ({w.get('probability', 1):.2f})" for w in words if w.get("probability", 1) < 0.8]
    silences = detect_silences(audio)
    cuts = th_lib.suggest_cuts(silences)
    src_end = round(min(words[-1]["end"] + 1.2, float(data["segments"][-1]["end"]) + 1.2), 2) if words else 0
    skeleton = {
        "title": args.title or video.stem,
        "source": "footage.mp4",
        "srcEnd": src_end,
        "cuts": cuts,
        "captionFixes": [],
        "endCard": {"seconds": 2.5, "kicker": "", "headline": "", "sub": ""},
        "sections": [],
    }
    (jdir / "job.json").write_text(json.dumps(skeleton, indent=2) + "\n")
    common.set_state(job_id, status="transcribed", title=skeleton["title"], kind="talking-head")
    print("\n".join(lines))
    print(f"\n[th] suggested cuts (silences over 2.5s): {cuts}")
    print("[th] low-confidence words, CHECK BY EAR if they carry a fact:")
    print("  " + ("\n  ".join(shaky) if shaky else "none"))
    print(f"[th] next: author {jdir / 'job.json'}, then th.py sheet {job_id}")


def cmd_find(args):
    hits = th_lib.find_phrase(load_words(args.job), args.phrase)
    print("\n".join(f"{t:.2f}" for t in hits) if hits else "not found (try fewer words, Whisper may have misheard)")


def checked_job(job_id):
    job = load_job(job_id)
    problems = th_lib.validate(job)
    if problems:
        common.die("job.json problems:\n  " + "\n  ".join(problems))
    jdir = common.job_dir(job_id)
    for name in th_lib.job_files(job):
        if not (jdir / "public" / name).exists():
            common.die(f"missing file in {jdir / 'public'}: {name}")
    return job


def write_props(job_id, portrait):
    job = checked_job(job_id)
    captions = th_lib.build_captions(load_words(job_id), job.get("cuts", []), job["srcEnd"], job.get("captionFixes"))
    render_job = {k: v for k, v in job.items() if k != "captionFixes"}
    if th_army.is_army(job):
        public = common.job_dir(job_id) / "public"
        missing = [f for f in th_army.asset_files(job, "9x16" if portrait else "16x9") if not (public / f).exists()]
        if missing:
            common.die(f"army stills not drawn yet ({missing[0]}...). Run: th.py sheet {job_id}")
        render_job["army"] = th_army.render_props(job, portrait)
    path = common.job_dir(job_id) / "work" / f"props_{'9x16' if portrait else '16x9'}.json"
    path.write_text(json.dumps({"job": {**render_job, "captions": captions}, "portrait": portrait}))
    return job, path


def remotion(job_id, *cmd):
    jdir = common.job_dir(job_id)
    return run([platform_util.tool("npx"), "remotion", *cmd, f"--public-dir={jdir / 'public'}", "--log=error"], cwd=TEMPLATE)


MAX_STATIC_SECONDS = 7.0


def report_pacing(job):
    """Tony's rule: past about 7 seconds of the same picture, break it up with a still
    or a clip. Warnings, not errors: sometimes holding on his face is the right call."""
    gaps = th_lib.static_stretches(job, MAX_STATIC_SECONDS)
    for g in gaps:
        print(f"[th] PACING: {g['seconds']}s with nothing changing, {g['from']:.1f} to {g['to']:.1f} ({g['showing']})."
              f" Add a cutaway or another cue.")
    return gaps


CUT_EDGE_FATES = {
    "kept": "captions keep it from the cut end, but the cut may clip its first sound",
    "dropped": "it is dropped from the captions",
    "clipped": "the cut clips its last sound",
}


def report_cut_edges(job, words):
    """A cut edge a hair inside a word drops it from the captions or clips its audio.
    On 2026-10-21 that cost the HOA job a full re-render, so catch it before the sheet."""
    hits = th_lib.cut_edge_words(words, job.get("cuts", []), job["srcEnd"])
    for h in hits:
        where = (f"starts {h['cut'][1] - h['start']:.2f}s before cut end {h['cut'][1]}" if h["edge"] == "end"
                 else f"ends {h['end'] - h['cut'][0]:.2f}s after cut start {h['cut'][0]}")
        print(f"[th] CUT EDGE: \"{h['word']}\" ({h['start']:.2f} to {h['end']:.2f}) {where}, {CUT_EDGE_FATES[h['fate']]}."
              f" Check by ear; to keep the whole word set the cut {h['edge']} to {h['suggest']}.")
    return hits


def cmd_check(args):
    job = checked_job(args.job)
    print(f"[th] ok: {len(job['sections'])} sections, {len(th_lib.cue_times(job))} cues, cuts {job.get('cuts', [])}")
    if not report_pacing(job):
        print(f"[th] pacing ok: the picture changes at least every {MAX_STATIC_SECONDS:.0f} seconds")
    if not report_cut_edges(job, load_words(args.job)):
        print(f"[th] cut edges ok: no word within {th_lib.CUT_EDGE_WINDOW}s of a cut edge")


def tile_sheet(files, labels, cols, out_path, pad=6):
    """Timecoded thumbnails in reading order. Pillow, same as the faceless sheets
    (this ffmpeg build has no drawtext)."""
    from PIL import Image, ImageDraw
    thumbs = [Image.open(f).convert("RGB") for f in files]
    w, h = thumbs[0].size
    rows = -(-len(thumbs) // cols)
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + pad) + pad), "white")
    for i, (thumb, label) in enumerate(zip(thumbs, labels)):
        draw = ImageDraw.Draw(thumb, "RGBA")
        box = draw.textbbox((10, 8), label, font_size=22)
        draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill=(0, 0, 0, 170))
        draw.text((10, 8), label, fill="white", font_size=22)
        sheet.paste(thumb, (pad + (i % cols) * (w + pad), pad + (i // cols) * (h + pad)))
    sheet.save(out_path, quality=88)


def cmd_sheet(args):
    """One still per cue, a beat after it lands, tiled. Shown to Tony BEFORE the render."""
    _voice_reminder(args.job)
    jdir = common.job_dir(args.job)
    job = checked_job(args.job)
    if th_army.is_army(job):
        import th_army_build   # draws public/army/, FLUX only for pictures not cached yet
        th_army_build.build(args.job, job)
    for aspect, comp in COMPS.items():
        job, props = write_props(args.job, portrait=aspect == "9x16")
        cuts = job.get("cuts", [])
        moments = th_lib.sheet_moments(job) + [job["srcEnd"] + job.get("endCard", {}).get("seconds", 0) / 2]
        frames = sorted({round(th_lib.to_output(t, cuts) * 30) if t <= job["srcEnd"] else round(th_lib.to_output(job["srcEnd"], cuts) * 30 + (t - job["srcEnd"]) * 30) for t in moments})
        stills = jdir / "work" / f"stills_{aspect}"
        shutil.rmtree(stills, ignore_errors=True)
        stills.mkdir(parents=True)
        for i, frame in enumerate(frames):
            out = stills / f"{i:03d}.jpg"
            remotion(args.job, "still", "src/index.ts", comp, str(out), f"--props={props}", f"--frame={frame}", "--image-format=jpeg", "--scale=0.33")
        sheet = jdir / "work" / f"contact_sheet{'' if aspect == '16x9' else '_9x16'}.jpg"
        tile_sheet(sorted(stills.glob("*.jpg")), [f"{fr / 30:.1f}s" for fr in frames], SHEET_COLS[aspect], sheet)
        print(f"[th] {aspect}: {len(frames)} frames -> {sheet}")
    if any(caption_qc(args.job).values()):
        print("[th] tell Tony about the caption problems with the sheets (fix them first if it is a layout call)")
    common.set_state(args.job, status="sheet", sheet_fingerprint=approval.fingerprint(jdir, "talking-head"))
    print(f"[th] show Tony BOTH sheets and wait for his go, then: th.py approve {args.job}")


def caption_qc(job_id):
    """A caption over Tony's mouth or chin, or one hard to read (capqc.py). Runs with the
    sheets, so a bad spot is fixed before Tony approves and before the long render."""
    jdir = common.job_dir(job_id)
    found = {}
    for aspect, comp in COMPS.items():
        job, props = write_props(job_id, portrait=aspect == "9x16")
        cuts = job.get("cuts", [])
        moments = [th_lib.to_output(t, cuts) for t in th_lib.sheet_moments(job) if t <= job["srcEnd"]]
        problems = capqc.check(comp, props, jdir / "public", moments, jdir / "work" / f"capqc_{aspect}")
        print(f"[th] CAPTIONS {aspect}: " + ("ok" if not problems else "PROBLEMS\n  " + "\n  ".join(problems)))
        found[aspect] = problems
    common.set_state(job_id, caption_qc=found)
    return found


def cmd_capqc(args):
    checked_job(args.job)
    caption_qc(args.job)


def cmd_approve(args):
    """Record Tony's go. Run this ONLY after he has seen both sheets and approved in chat."""
    jdir = common.job_dir(args.job)
    problem = approval.can_approve(common.get_state(args.job), approval.fingerprint(jdir, "talking-head"))
    if problem:
        common.die(f"[th] cannot approve: {problem}")
    common.set_state(args.job, approved_fingerprint=approval.fingerprint(jdir, "talking-head"),
                     approved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"[th] approved {args.job}. Any edit to job.json or the b-roll voids this.")


def write_kit(job_id):
    """Publish kit, same files and format as a faceless job: out/transcript.txt,
    out/transcript.srt, out/youtube.md (title, description with timeline, tags)."""
    job = load_job(job_id)
    out = common.job_dir(job_id) / "out"
    out.mkdir(exist_ok=True)
    captions = th_lib.build_captions(load_words(job_id), job.get("cuts", []), job["srcEnd"], job.get("captionFixes"))
    authored = job.get("youtube") or {}
    missing = [k for k in ("title", "description", "tags") if not authored.get(k)]
    if missing:
        print(f"[th] KIT: job.json has no youtube.{', youtube.'.join(missing)}. Author the youtube block, then: th.py kit {job_id}")
    tags = authored.get("tags") or []
    meta = {"title": publish_kit.clean(authored.get("title") or job["title"])[:publish_kit.TITLE_MAX],
            "description": publish_kit.clean(authored.get("description") or ""),
            "tags": publish_kit.fit_tags([publish_kit.clean(t).lower() for t in tags if publish_kit.clean(t)]),
            "hashtags": [publish_kit.clean(h).lstrip("#") for h in authored.get("hashtags", [])][:3],
            "source": "job.json"}
    time_map = th_lib.to_output(job["srcEnd"], job.get("cuts", [])) + job.get("endCard", {}).get("seconds", 0)
    intro = authored.get("intro_chapter") or (job.get("hook") or {}).get("title", "Intro").replace("\n", " ")
    chapter_list = th_lib.chapters(job, intro=publish_kit.clean(intro))
    jdir = common.job_dir(job_id)
    shown = {**meta, "description": kit_links.with_blog_line(meta["description"], kit_links.load(jdir).get("blog_url"))}
    files = {
        "transcript.txt": " ".join(c["t"] for c in captions) + "\n",
        "transcript.srt": th_lib.build_srt(captions),
        "youtube.md": publish_kit.youtube_markdown(shown, chapter_list, time_map,
                                                   lanes.footer_for(lanes.job_lane(jdir, job),
                                                                    common.load_config(), job,
                                                                    lanes.job_signer(jdir, job))),
    }
    for name, text in files.items():
        (out / name).write_text(text)
        print(f"[th] {out / name}")
    import yt_thumb                       # lazy: only the kit needs the thumbnail rules
    for problem in yt_thumb.kit_problems(jdir):
        print(f"[th] KIT: {problem}")
    import kit_extras
    import library_entry
    spoken = library_entry.paragraphs(files["transcript.txt"])
    kit_extras.run(jdir, "talking-head", meta, chapter_list, spoken, authored.get("takeaways"), spoken,
                   source="final-cut captions", tag="[th]")


def _noise_floor(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", "astats=metadata=0", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    found = re.findall(r"Noise floor dB: (-?[0-9.]+|-inf)", out)
    return float(found[-1]) if found and found[-1] != "-inf" else -60.0


def _loudnorm_measure(path, chain):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", f"{chain},{th_lib.loudnorm_pass1()}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    block = out[out.rfind("{"):out.rfind("}") + 1]
    if not block:
        common.die(f"loudnorm measurement failed:\n{out[-1200:]}")
    return json.loads(block)


ENHANCER_PY = platform_util.venv_python(platform_util.studio_venv("enhance"))
ENHANCER = Path.home() / "video-studio/enhance_voice.py"


def _ai_enhance(src_wav, out_wav):
    """Resemble Enhance on the CPU, about 2.3x real time (a 6 minute take: ~14 minutes)."""
    if not (ENHANCER_PY.exists() and ENHANCER.exists()):
        return False
    print(f"[th] local AI voice: {src_wav.name} (about 2.3x real time on the CPU)", flush=True)
    run([str(ENHANCER_PY), str(ENHANCER), str(src_wav), str(out_wav), "--lambd", "0.9", "--device", "cpu"])
    return True


def _room_voice_wav(jdir, media):
    """Room voice on the source timeline (room_voice.py): the enhancer in denoise-only mode on
    the camera track, the raw track (mains hum notched out) back under it. Every voice in the
    room is kept."""
    if not (ENHANCER_PY.exists() and ENHANCER.exists()):
        common.die(f"[th] the room voice needs the local enhancer: {ENHANCER_PY}")
    work = jdir / "work"
    src_wav, dn_wav, out = work / "voice_raw.wav", work / "voice_dn.wav", work / "voice_room.wav"
    run(["ffmpeg", "-y", "-i", str(media), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", str(src_wav)])
    print(f"[th] room voice: denoise-only pass (about 1 minute per 25 minutes of audio)", flush=True)
    run(room_voice.denoise_cmd(ENHANCER_PY, ENHANCER, src_wav, dn_wav))
    sr = voice_level.SR
    room_voice.save(room_voice.room_mix(room_voice.load(dn_wav, sr), room_voice.load(src_wav, sr), sr), sr, out)
    return out


def _enhance_room(args, raw, live):
    voice = _room_voice_wav(common.job_dir(args.job), raw)
    chain, before, got = _level_chain(voice, room_voice.room_chain(room_voice.speech_level(
        room_voice.load(voice, voice_level.SR), voice_level.SR)))
    _mux_voice(raw, voice, chain, live)
    common.set_state(args.job, voice="room")
    print(f"[th] room voice in, {before:.1f} -> {got:.1f} LUFS -> {live}\n"
          f"     after the render, if audio QC flags quiet attendees: th.py level {args.job}")


def _mux_voice(video_src, voice_wav, chain, out):
    run(["ffmpeg", "-y", "-i", str(video_src), "-i", str(voice_wav), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", f"{chain},aresample=48000", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest",
         "-movflags", "+faststart", str(out)])


def _level_chain(src, chain):
    """Tone chain plus a gain + limiter that lands at -14 LUFS. Linear loudnorm backs off
    when peaks are wide (it stopped 2 dB short), so measure, top up, measure again."""
    target = th_lib.LOUDNESS_TARGET["I"]
    # Cameras record the voice as dual mono. Fold to one channel, process, then write it
    # back as identical L/R, so what we measure is what YouTube plays. Measuring stereo
    # and encoding mono put the file 3 dB off and pushed true peak over 0 dBTP.
    chain = f"aformat=channel_layouts=mono,{chain},pan=stereo|c0=c0|c1=c0"
    base = _loudnorm_measure(src, chain)["input_i"]
    extra, got = 0.0, None
    for _ in range(3):
        full = f"{chain},{th_lib.external_level_chain(base, extra_db=extra)}"
        got = float(_loudnorm_measure(src, full)["input_i"])
        if abs(got - target) <= 0.3:
            break
        extra += target - got
    return full, float(base), got


def _enhance_from(args, jdir, raw, live):
    """Swap in an externally enhanced voice (Adobe Podcast Enhance): check it lines up,
    bring it to -14 LUFS without touching its tone, and mux it under the original video."""
    ext = Path(args.adobe).expanduser()
    if not ext.exists():
        common.die(f"no such file: {ext}")
    problem = th_lib.external_audio_problem(_duration(raw), _duration(ext))
    if problem:
        common.die(f"[th] {problem}. Export again with --export and enhance the whole file.")
    kept = jdir / "work" / "voice_adobe.wav"
    shutil.copy(ext, kept)
    chain, before, got = _level_chain(kept, "anull")
    print(f"[th] Adobe voice, loudness {before:.1f} -> {got:.1f} LUFS (target {th_lib.LOUDNESS_TARGET['I']})")
    run(["ffmpeg", "-y", "-i", str(raw), "-i", str(kept), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", f"{chain},aresample=48000", "-c:a", "aac", "-b:a", "192k",
         "-ac", "2", "-shortest", "-movflags", "+faststart", str(live)])
    common.set_state(args.job, voice="adobe")
    print(f"[th] Adobe voice in place -> {live}")


def cmd_enhance(args):
    """Voice cleanup, applied to the working copy so every render and sheet hears it.
    The untouched copy is kept in work/footage_raw.mp4; --undo puts it back."""
    jdir = common.job_dir(args.job)
    live, raw = jdir / "public" / "footage.mp4", jdir / "work" / "footage_raw.mp4"
    if args.undo:
        if not raw.exists():
            common.die("nothing to undo, no work/footage_raw.mp4")
        shutil.move(str(raw), str(live))
        print(f"[th] original audio restored")
        return
    if not raw.exists():
        shutil.move(str(live), str(raw))
    if args.export:
        wav = jdir / "work" / "voice_for_adobe.wav"
        run(["ffmpeg", "-y", "-i", str(raw), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", str(wav)])
        shutil.copy(raw, live)  # untouched until the Adobe file comes back
        print(f"[th] upload {wav} to https://podcast.adobe.com/enhance, download the WAV,\n"
              f"     then: th.py enhance {args.job} --adobe <downloaded.wav>")
        return
    if args.adobe:
        _enhance_from(args, jdir, raw, live)
        return
    if args.room:
        _enhance_room(args, raw, live)
        return
    if not args.voice:
        src_wav, ai_wav = jdir / "work" / "voice_raw.wav", jdir / "work" / "voice_ai.wav"
        run(["ffmpeg", "-y", "-i", str(raw), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", str(src_wav)])
        if _ai_enhance(src_wav, ai_wav):
            chain, before, got = _level_chain(ai_wav, th_lib.local_ai_eq_chain())
            _mux_voice(raw, ai_wav, chain, live)
            common.set_state(args.job, voice="ai")
            print(f"[th] local AI voice in, {before:.1f} -> {got:.1f} LUFS -> {live}")
            return
        print(f"[th] local AI enhancer missing ({ENHANCER_PY}), falling back to preset {th_lib.DEFAULT_VOICE}")
        args.voice = th_lib.DEFAULT_VOICE
    floor = _noise_floor(raw)
    chain, before, got = _level_chain(raw, th_lib.voice_chain(floor, args.voice))
    print(f"[th] voice preset {args.voice}, noise floor {floor:.1f} dB, loudness {before:.1f} -> {got:.1f} LUFS")
    af = f"{chain},aresample=48000"
    run(["ffmpeg", "-y", "-i", str(raw), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", af,
         "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", str(live)])
    # 20 second A/B pair for Tony's ears
    for name, src in (("voice_before.m4a", raw), ("voice_after.m4a", live)):
        run(["ffmpeg", "-y", "-ss", str(args.sample_at), "-t", "20", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "192k", str(jdir / "work" / name)])
    print(f"[th] enhanced -> {live}; compare work/voice_before.m4a and work/voice_after.m4a")


MUSIC_DIR = common.ROOT / "assets" / "music"


def _track_path(name):
    for cand in (Path(name), MUSIC_DIR / name, MUSIC_DIR / f"{name}.mp3"):
        if cand.is_file():
            return cand
    common.die(f"no music track {name!r}. In {MUSIC_DIR}: {', '.join(sorted(f.stem for f in MUSIC_DIR.glob('*.mp3')))}")


def _integrated_lufs(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    found = re.findall(r"I:\s+(-?[0-9.]+) LUFS", out)
    if not found:
        common.die(f"could not measure loudness of {path}")
    return float(found[-1])


def _duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout
    return float(out.strip())


SFX_KIT = common.ROOT / "assets" / "sfx" / "kit"
SFX_GAIN_DB = {"pop": -12.0, "tick": -14.0, "click": -12.0, "whoosh": -14.0, "riser": -16.0, "impact": -10.0}


def _first_beat_out(job):
    """Output second where the hook ends: the first board show, else the first chaptered section."""
    shows = (job.get("board") or {}).get("shows", [])
    marks = [sh["from"] for sh in shows] + [s["evidence"][0] for s in job.get("sections", []) if s.get("chapter")]
    first = min(marks) if marks else (job["sections"][0]["evidence"][0] if job.get("sections") else 0.0)
    return th_lib.to_output(first, job.get("cuts", []))


def _build_sfx(cues, total, out_wav):
    """One WAV the length of the final with every effect placed: kit/<kind>.mp3 at each cue."""
    kinds = sorted({c["kind"] for c in cues})
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    for k in kinds:
        cmd += ["-i", str(SFX_KIT / f"{k}.mp3")]
    parts, labels = [], []
    for i, k in enumerate(kinds):
        ts = [c["t"] for c in cues if c["kind"] == k]
        outs = "".join(f"[{k}{j}]" for j in range(len(ts)))
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={SFX_GAIN_DB.get(k, -12.0)}dB,asplit={len(ts)}{outs}")
        for j, t in enumerate(ts):
            ms = max(int(t * 1000), 0)
            parts.append(f"[{k}{j}]adelay={ms}|{ms}[{k}d{j}]")
            labels.append(f"[{k}d{j}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad=whole_dur={total:.3f}[o]")
    run(cmd + ["-filter_complex", ";".join(parts), "-map", "[o]", "-t", f"{total:.3f}", "-ar", "48000", str(out_wav)])


def cmd_music(args):
    """Ducked bed under the rendered finals, plus suspense under the hook (--hook-track) and the
    SFX layer from assets/sfx/kit (skip with --no-sfx). Writes out/final_<aspect>_music.mp4 next
    to the voice-only files, video stream copied, so it takes seconds, not a render."""
    jdir = common.job_dir(args.job)
    job = load_job(args.job)
    track = _track_path(args.track)
    gain = th_lib.music_gain(_integrated_lufs(track), args.level)
    hook = _track_path(args.hook_track) if args.hook_track else None
    hook_gain = th_lib.music_gain(_integrated_lufs(hook), args.hook_level) if hook else None
    switch = args.switch if args.switch is not None else _first_beat_out(job)
    cues = [] if args.no_sfx else [c for c in th_lib.sfx_cues(job) if (SFX_KIT / f"{c['kind']}.mp3").exists()]
    finals = sorted((jdir / "out").glob("final_*x*.mp4"))
    finals = [f for f in finals if not f.stem.endswith("_music")]
    if not finals:
        common.die("render first, no out/final_*.mp4")
    for final in finals:
        total = _duration(final)
        out = final.with_name(f"{final.stem}_music.mp4")
        inputs = ["-i", str(final), "-stream_loop", "-1", "-i", str(track)]
        if hook:
            inputs += ["-stream_loop", "-1", "-i", str(hook)]
        if cues:
            sfx_wav = jdir / "work" / f"sfx_{final.stem}.wav"
            _build_sfx(cues, total, sfx_wav)
            inputs += ["-i", str(sfx_wav)]
        fc = th_lib.mix_filter(gain, total, hook_gain=hook_gain, switch=switch, sfx=bool(cues))
        run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "0:v", "-map", "[out]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)])
        extra = (f", {hook.stem} under the hook to {switch:.1f}s" if hook else "") + (f", {len(cues)} SFX" if cues else "")
        print(f"[th] {out.name}: {track.stem} at {args.level} LUFS bed ({gain:+.1f} dB){extra}")
        audio_qc.check(out, label="th audio QC")   # the music cut is the one that gets uploaded
    common.set_state(args.job, music={"track": track.name, "level": args.level, "hook": hook.name if hook else None,
                                       "hook_level": args.hook_level, "switch": args.switch,
                                       "sfx": len(cues), "no_sfx": args.no_sfx})


def _rerun_music(job_id, switch=None):
    """Re-mix the bed after a voice swap, the way the job's last `th.py music` run did it."""
    music = common.get_state(job_id).get("music")
    if not music:
        return
    if music.get("hook") and "switch" not in music and switch is None:
        print("[th] MUSIC: this job's music run predates recording --switch, so the hook hands over "
              "at the first beat. Army jobs need theirs: pass --switch <seconds>.")
    cmd_music(argparse.Namespace(job=job_id, **th_lib.music_rerun_args(music, switch)))


QC_SILENCE_FILTER = "silencedetect=noise=-45dB:d=1.5"


def _silences(stderr, length):
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", stderr)]
    return list(zip(starts, ends)) + ([(starts[-1], length)] if len(starts) > len(ends) else [])


def _source_pauses(job_id):
    """Pauses Tony left in the footage, moved onto the output timeline (cuts removed)."""
    job = load_job(job_id)
    src = common.job_dir(job_id) / "public" / job["source"]
    out = subprocess.run(["ffmpeg", "-nostdin", "-i", str(src), "-vn", "-af", QC_SILENCE_FILTER, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    cuts = job.get("cuts", [])
    return [(th_lib.to_output(a, cuts), th_lib.to_output(b, cuts)) for a, b in _silences(out, job["srcEnd"])]


def _qc(final, tail_ok, expected=()):
    """Black frames, long silences and stream drift in a rendered file (th_lib.qc_problems)."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-i", str(final), "-vf", "blackdetect=d=0.1:pix_th=0.03",
                          "-af", QC_SILENCE_FILTER, "-f", "null", "-"], capture_output=True, text=True).stderr
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", out)]
    probe = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", str(final)]).stdout
    durs = {kind: float(d) for kind, d in (line.split(",")[:2] for line in probe.split() if "," in line and line.split(",")[1] not in ("N/A", ""))}
    video_s, audio_s = durs.get("video", 0.0), durs.get("audio", 0.0)
    return th_lib.qc_problems(black, _silences(out, video_s), video_s, audio_s, tail_ok, expected)


def _audio_qc(job_id, finals):
    """Level, true peak, loudness range and quiet stretches on each voice final (audio_qc.py).
    Recorded in state; a final with problems is not shown to Tony or uploaded until the quiet
    spans are levelled or he waives it."""
    found = {}
    for final in finals:
        problems = audio_qc.check(final, th_lib.LOUDNESS_TARGET["I"], label="th audio QC")
        if problems:
            found[final.stem] = problems
    common.set_state(job_id, audio_qc=found)
    if found:
        print(f"[th] AUDIO QC: fix before showing Tony. Quiet stretches are usually off-mic speech: "
              f"th.py level {job_id} lifts them (docs: talking-head SKILL, Audio QC).")
    return found


def _swap_final_voice(args, jdir, finals, voice_wav, chain, label):
    for final in finals:
        problem = th_lib.external_audio_problem(_duration(final), _duration(voice_wav))
        if problem:
            common.die(f"[th] {final.name}: {problem}")
    for final in finals:
        backup = jdir / "work" / f"{final.stem}_prevoice.mp4"
        if not backup.exists():
            shutil.copy(final, backup)
        _mux_voice(backup, voice_wav, chain, final)
        print(f"[th] {final.name}: {label} voice in")
    common.set_state(args.job, voice=label)
    _audio_qc(args.job, finals)
    _rerun_music(args.job)


def _revoice_ai(args, jdir, finals):
    ai_wav = jdir / "work" / "final_voice_ai.wav"
    if args.ai_wav:
        shutil.copy(Path(args.ai_wav).expanduser(), ai_wav)
    else:
        src = jdir / "work" / "final_voice_for_adobe.wav"
        backup = jdir / "work" / f"{finals[0].stem}_prevoice.mp4"
        run(["ffmpeg", "-y", "-i", str(backup if backup.exists() else finals[0]), "-map", "0:a:0", "-vn",
             "-ac", "1", "-ar", "48000", str(src)])
        if not _ai_enhance(src, ai_wav):
            common.die(f"[th] local AI enhancer missing: {ENHANCER_PY}")
    chain, before, got = _level_chain(ai_wav, th_lib.local_ai_eq_chain())
    print(f"[th] local AI voice, {before:.1f} -> {got:.1f} LUFS")
    _swap_final_voice(args, jdir, finals, ai_wav, chain, "ai")


def _revoice_room(args, jdir, finals):
    """Room voice into rendered finals. Remotion snaps each kept segment to a frame (20 to 65 ms
    on the class video), so each segment of the new voice goes exactly where the render put the
    same samples of the audio it played, which keeps the picture in sync."""
    job = load_job(args.job)
    live, raw = jdir / "public" / job["source"], jdir / "work" / "footage_raw.mp4"
    voice = _room_voice_wav(jdir, raw if raw.exists() else live)
    sr = voice_level.SR
    backup = jdir / "work" / f"{finals[0].stem}_prevoice.mp4"
    cuts = job.get("cuts", [])
    keep = room_voice.kept_segments(cuts, job["srcEnd"])
    offsets = room_voice.segment_offsets(room_voice.load(backup if backup.exists() else finals[0], sr),
                                         room_voice.load(live, sr), keep, cuts, sr)
    placed = room_voice.place({"v": room_voice.load(voice, sr)}, keep, offsets, cuts, _duration(finals[0]), sr)["v"]
    out = jdir / "work" / "final_voice_room.wav"
    room_voice.save(placed, sr, out)
    print(f"[th] room voice placed segment by segment ({min(offsets) * 1000:.0f} to {max(offsets) * 1000:.0f} ms)")
    chain, before, got = _level_chain(out, room_voice.room_chain(room_voice.speech_level(placed, sr)))
    print(f"[th] room voice, {before:.1f} -> {got:.1f} LUFS")
    _swap_final_voice(args, jdir, finals, out, chain, "room")
    print(f"[th] if audio QC flags quiet attendees: th.py level {args.job}, then th_shorts.py cut {args.job}")


def cmd_revoice(args):
    """Adobe Enhance on an already rendered job: --export writes the finals' voice track,
    --adobe swaps the enhanced WAV into both finals (old ones kept in work/), re-mixes the
    music bed if the job had one. Re-cut Shorts afterwards with th_shorts.py cut."""
    jdir = common.job_dir(args.job)
    finals = [jdir / "out" / f"final_{a}.mp4" for a in COMPS]
    finals = [f for f in finals if f.exists()]
    if not finals:
        common.die("render first, no out/final_*.mp4")
    if args.export:
        wav = jdir / "work" / "final_voice_for_adobe.wav"
        run(["ffmpeg", "-y", "-i", str(finals[0]), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", str(wav)])
        print(f"[th] {wav}")
        return
    if args.ai or args.ai_wav:
        _revoice_ai(args, jdir, finals)
        _word_check(args.job, finals[0])
        return
    if args.room:
        _revoice_room(args, jdir, finals)
        _word_check(args.job, finals[0])
        return
    ext = Path(args.adobe).expanduser()
    for final in finals:
        problem = th_lib.external_audio_problem(_duration(final), _duration(ext))
        if problem:
            common.die(f"[th] {final.name}: {problem}")
    kept = jdir / "work" / "final_voice_adobe.wav"
    shutil.copy(ext, kept)
    chain, before, got = _level_chain(kept, "anull")
    print(f"[th] Adobe voice, loudness {before:.1f} -> {got:.1f} LUFS")
    for final in finals:
        backup = jdir / "work" / f"{final.stem}_prevoice.mp4"
        if not backup.exists():
            shutil.copy(final, backup)
        run(["ffmpeg", "-y", "-i", str(backup), "-i", str(kept), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             "-af", f"{chain},aresample=48000", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest",
             "-movflags", "+faststart", str(final)])
        print(f"[th] {final.name}: Adobe voice in")
    common.set_state(args.job, voice="adobe")
    _audio_qc(args.job, finals)
    _rerun_music(args.job)
    _word_check(args.job, finals[0])


def _level_final(jdir, final):
    """Lift one final's quiet speech; None (file untouched) when nothing sits under the voice.
    The float WAV (about 250 MB for a 22 minute class) goes after: _prevoice is the way back."""
    lifted = jdir / "work" / f"level_{final.stem}.wav"
    try:
        stats = voice_level.level_file(final, lifted)
        if stats["max_db"] < 1.0:
            print(f"[th] {final.name}: nothing to lift (voice {stats['voice_db']} dB)")
            return None
        backup = jdir / "work" / f"{final.stem}_prevoice.mp4"
        if not backup.exists():
            shutil.copy(final, backup)
        chain, before, got = _level_chain(lifted, "anull")
        tmp = jdir / "work" / f"{final.stem}_levelled.mp4"   # not in out/, where music globs final_*
        _mux_voice(final, lifted, chain, tmp)
        tmp.replace(final)
    finally:
        lifted.unlink(missing_ok=True)
    print(f"[th] {final.name}: lifted {stats['lifted_pct']}% of speech (median {stats['median_db']:+.1f} dB, "
          f"max {stats['max_db']:+.1f} dB), {before:.1f} -> {got:.1f} LUFS")
    return stats


def cmd_level(args):
    """Quiet speech in the rendered finals (off-mic attendee questions, Tony away from the mic)
    lifted to the voice: voice_level.py, the -14 LUFS chain again, video copied, old finals kept
    as work/final_*_prevoice.mp4. Then audio QC and the music bed as last mixed (--switch
    overrides the recorded one). Shorts are cut from the finals, so they need cutting again."""
    jdir = common.job_dir(args.job)
    finals = [f for f in (jdir / "out" / f"final_{a}.mp4" for a in COMPS) if f.exists()]
    if not finals:
        common.die("render first, no out/final_*.mp4")
    stats = {f.stem: s for f in finals if (s := _level_final(jdir, f))}
    _audio_qc(args.job, finals)
    if not stats:
        return
    common.set_state(args.job, level=stats)
    _rerun_music(args.job, args.switch)
    print(f"[th] re-cut the Shorts, they still carry the old audio: th_shorts.py cut {args.job}")


def cmd_kit(args):
    write_kit(args.job)


def _word_check(job_id, final):
    """Re-transcribe the final and compare it with the source after cuts (wordcheck.py). Not
    a gate: ASR noise is real, so it names times to LISTEN to before Tony sees the video.
    On the first back-catalog run (2026-10-29) it found two uncut stutters in published
    videos that the Whisper-era source transcripts had smoothed over."""
    problems = wordcheck.print_final(final.name, wordcheck.check_final(job_id, final))
    common.set_state(job_id, words=problems)
    return problems


def cmd_words(args):
    out = common.job_dir(args.job) / "out"
    final = next((out / f"final_{a}.mp4" for a in COMPS if (out / f"final_{a}.mp4").exists()), None)
    if not final:
        common.die("render first, no out/final_*.mp4")
    _word_check(args.job, final)


def _voice_reminder(job_id):
    """Local AI voice (or Adobe) is the default (Tony, 2026-09-27). Not a hard gate: unattended
    runs fall back to the fitted studio preset. Just never skip it silently."""
    if not th_lib.voice_is_final(common.get_state(job_id)):
        print(f"[th] VOICE: not AI-enhanced yet (the default). Run: th.py enhance {job_id}")


def cmd_render(args):
    jdir = common.job_dir(args.job)
    reason = approval.gate(common.get_state(args.job), approval.fingerprint(jdir, "talking-head"), args.no_preview)
    if reason:
        common.die(f"[th] BLOCKED: {reason}.\n"
                   f"      sheets: {jdir / 'work' / 'contact_sheet.jpg'} and contact_sheet_9x16.jpg\n"
                   f"      after Tony says go: th.py approve {args.job}   (his explicit waiver only: --no-preview)")
    _voice_reminder(args.job)
    pauses = _source_pauses(args.job)
    rendered = []
    for aspect, comp in COMPS.items():
        if args.only and args.only != aspect:
            continue
        _, props = write_props(args.job, portrait=aspect == "9x16")
        out = jdir / "out" / f"final_{aspect}.mp4"
        print(f"[th] rendering {aspect}...")
        remotion(args.job, "render", "src/index.ts", comp, str(out), f"--props={props}", "--codec=h264", "--crf=18", "--concurrency=6")
        print(f"[th] {out}")
        problems = _qc(out, load_job(args.job).get("endCard", {}).get("seconds", 0) + 0.5, pauses)
        print(f"[th] QC {aspect}: " + ("ok" if not problems else "PROBLEMS\n  " + "\n  ".join(problems)))
        if problems:
            common.set_state(args.job, qc={aspect: problems})
            common.die(f"[th] QC failed on {out.name}. Fix before showing Tony.")
        rendered.append(out)
    _audio_qc(args.job, rendered)
    _word_check(args.job, rendered[0])
    write_kit(args.job)
    common.set_state(args.job, status="rendered")
    if not load_job(args.job).get("shorts"):
        print(f"[th] next (every video): add a \"shorts\" block to job.json, then "
              f"th_shorts.py sheet {args.job}")


def main():
    if sys.argv[1:2] == ["takes"]:
        return takes.main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("video"); p.add_argument("--title")
    p.add_argument("--word", help="one word for the job folder: the city or topic (else taken from --title)")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("find"); p.add_argument("job"); p.add_argument("phrase"); p.set_defaults(fn=cmd_find)
    p = sub.add_parser("check"); p.add_argument("job"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("sheet"); p.add_argument("job"); p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("capqc"); p.add_argument("job"); p.set_defaults(fn=cmd_capqc)
    p = sub.add_parser("render"); p.add_argument("job"); p.add_argument("--only", choices=list(COMPS))
    p.add_argument("--no-preview", action="store_true", help="skip the approval gate. ONLY on Tony's explicit waiver")
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("approve"); p.add_argument("job"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("kit"); p.add_argument("job"); p.set_defaults(fn=cmd_kit)
    p = sub.add_parser("words"); p.add_argument("job"); p.set_defaults(fn=cmd_words)
    p = sub.add_parser("music"); p.add_argument("job"); p.add_argument("track")
    p.add_argument("--level", type=float, default=th_lib.MUSIC_BED_LUFS)
    p.add_argument("--hook-track", help="suspense track under the hook, crossfades into the bed at --switch")
    p.add_argument("--hook-level", type=float, default=th_lib.MUSIC_BED_LUFS + 2)
    p.add_argument("--switch", type=float, help="output seconds where the hook track hands over (default: first beat)")
    p.add_argument("--no-sfx", action="store_true", help="leave the SFX layer out")
    p.set_defaults(fn=cmd_music)
    sub.add_parser("takes", help="takes plan|splice, see takes.py")  # handled before parsing
    p = sub.add_parser("revoice"); p.add_argument("job"); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true"); g.add_argument("--adobe")
    g.add_argument("--ai", action="store_true", help="run the local AI voice on the finals")
    g.add_argument("--ai-wav", help="already enhanced local AI output to swap in")
    g.add_argument("--room", action="store_true", help="class or room recording: denoise-only voice that keeps "
                                                        "every speaker (room_voice.py)")
    p.set_defaults(fn=cmd_revoice)
    p = sub.add_parser("level", help="lift quiet off-mic speech in the finals, then re-mix the music")
    p.add_argument("job"); p.add_argument("--switch", type=float, help="hook hand-over for the music re-mix "
                                          "(default: the one the last music run used)")
    p.set_defaults(fn=cmd_level)
    p = sub.add_parser("enhance"); p.add_argument("job"); p.add_argument("--undo", action="store_true")
    p.add_argument("--sample-at", type=float, default=20.0)
    p.add_argument("--voice", choices=sorted(th_lib.VOICE_PRESETS), help="EQ preset instead of the local AI (default)")
    p.add_argument("--export", action="store_true", help="write work/voice_for_adobe.wav for Adobe Podcast Enhance")
    p.add_argument("--adobe", help="Adobe-enhanced WAV to swap in (same length as the footage)")
    p.add_argument("--room", action="store_true", help="class or room recording (attendees, Tony away from the "
                                                       "mic): denoise-only voice, the AI voice garbles them")
    p.set_defaults(fn=cmd_enhance)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
