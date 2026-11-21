"""Assemble stills + narration into final videos.

Per scene: Ken Burns (zoompan) the still for exactly its narration length.
Then concat, burn ASS captions timed to the audio, optional ducked music bed,
and emit a 1920x1080 master plus a 9:16 cut (sharp center over blurred fill).

ffmpeg patterns ported from ~/video-studio/stitch.py (scale-to-cover, ducking,
blur-fill reframe). All subprocess calls run with cwd=<job work dir> so filter
filenames stay relative (the repo path contains spaces).
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

import audio_qc
import captions
import clips
import common
import loudness
import mograph

W, H = 1920, 1080
PAD = 0.35  # breathing room after each scene's narration, seconds
SILENT_SCENE_DUR = 3.5  # default hold for a narration-free scene, seconds


def run_ff(args, cwd):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True, cwd=cwd)


def resolve_audio(name, kind):
    """Accept an absolute/relative path or a bare filename in assets/<kind>/.
    Returns an absolute Path or None (with a warning if it was requested)."""
    if not name:
        return None
    from pathlib import Path
    bases = (Path(name).expanduser(), common.ROOT / "assets" / kind / name)
    for base in bases:
        for candidate in (base, base.with_suffix(".mp3"), base.with_suffix(".wav")):
            if candidate.is_file():
                return candidate.resolve()
    print(f"[assemble] {kind} '{name}' not found, skipping")
    return None


def probe_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def audio_file(work, scene_id):
    """Narration audio for a scene, or None for a narration-free scene."""
    for ext in ("wav", "mp3"):
        path = work / f"scene_{scene_id:02d}.{ext}"
        if path.exists():
            return path
    return None


def audio_input(audio, dur):
    """ffmpeg input args for the scene's audio slot: the narration file, or a
    silent bed of the scene's length so sfx and music still have a track to mix on."""
    if audio:
        return ["-i", audio.name]
    return ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100"]


def narration_chain(narr_idx, sfx_idx=None, whole_dur=None, out="a"):
    """Audio filter for a scene: padded narration, optionally mixed with a
    sound effect that plays at the start of the scene. whole_dur pads the narration
    out to the full scene instead, for a clip that keeps playing after it ends."""
    pad = f"whole_dur={whole_dur:.3f}" if whole_dur else f"pad_dur={PAD}"
    if sfx_idx is None:
        return f"[{narr_idx}:a]apad={pad}[{out}]"
    return (f"[{narr_idx}:a]apad={pad}[na];"
            f"[{sfx_idx}:a]volume=0.7[sf];"
            f"[na][sf]amix=inputs=2:duration=first:dropout_transition=0.5[{out}]")


DUCK_RAMP = 0.3  # seconds a ducked clip takes to come back up once the narration ends


def clip_sound_chain(sfx_idx, dur, clip_sound):
    """A clip scene's sound: its narration track (silence when it has none) with the
    clip's own audio laid under it (a clips.ClipSound), padded to the whole scene."""
    lvl = f"{clip_sound.level:.3f}"
    if clip_sound.until is None:
        volume = lvl
    else:
        until = f"{clip_sound.until:.3f}"
        volume = (f"'if(lt(t,{until}),{lvl},min(1,{lvl}+(1-{lvl})*(t-{until})/{DUCK_RAMP:g}))'"
                  ":eval=frame")
    return (narration_chain(1, sfx_idx, whole_dur=dur, out="nar")
            + f";[0:a]volume={volume},apad=whole_dur={dur:.3f}[ca];"
            "[nar][ca]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")


CAPTION_MODES = ("both", "portrait", "landscape", "none")
DRIFT_ZOOM = 0.05   # how far a drift shot pushes in (or eases out) over its length


def caption_text(scene, theme, vertical):
    """The caption this cut burns in. A theme's "captions" says which cuts get them:
    both (the default), portrait, landscape or none (docs/swordfish.md: none on 16:9)."""
    mode = theme.get("captions", "both")
    if mode not in CAPTION_MODES:
        raise ValueError(f"theme 'captions' must be one of {', '.join(CAPTION_MODES)}, got {mode!r}")
    shown = mode == "both" or mode == ("portrait" if vertical else "landscape")
    return scene["caption"] if shown else ""


def shot_durations(scene, dur):
    """How long each shot of a scene holds. When every shot carries the "line" of
    narration it shows, time is shared by word count so the cut lands near where that
    line does; otherwise the scene splits evenly."""
    shots = scene.get("shots") or [scene.get("image_prompt") or scene.get("photo")]
    lines = [shot.get("line") if isinstance(shot, dict) else None for shot in shots]
    if all(isinstance(line, str) and line.split() for line in lines):
        words = [len(line.split()) for line in lines]
        return [dur * count / sum(words) for count in words]
    return [dur / len(shots)] * len(shots)


def shot_frames(durations, fps):
    """Whole frames per shot, rounded on the running total so the shots add up to the
    scene exactly; a frame lost per scene would drift the picture off the narration."""
    frames, done, elapsed = [], 0, 0.0
    for k, shot_dur in enumerate(durations):
        elapsed += shot_dur
        end = math.ceil(elapsed * fps - 1e-6) if k == len(durations) - 1 else round(elapsed * fps)
        frames.append(max(1, end - done))
        done = end
    return frames


def still_inputs(files, durations, fps, pacing):
    """ffmpeg inputs for a run of stills. A cuts still loops for its shot length; a drift
    still is a single frame that zoompan stretches into the shot (drift_filter)."""
    cmd = []
    for name, shot_dur in zip(files, durations):
        if pacing == "drift":
            cmd += ["-framerate", str(fps), "-i", name]
        else:
            cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{shot_dur:.3f}", "-i", name]
    return cmd


def drift_filter(index, w, h, frames, fps):
    """One still slowly pushing in (even shots) or easing out (odd shots) over frames:
    the documentary drift between hard cuts. Upscaled first, as the Ken Burns pass is,
    or zoompan judders."""
    z = DRIFT_ZOOM
    zexpr = (f"min(1+{z}*on/{frames},{1 + z})" if index % 2 == 0
             else f"max({1 + z}-{z}*on/{frames},1.0)")
    return (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps},setsar=1")


def shot_chains(n, w, h, durations, fps, pacing):
    """The filter for every still input: a plain cover crop, or a drift."""
    if pacing == "drift":
        frames = shot_frames(durations, fps)
        return "".join(f"[{i}:v]{drift_filter(i, w, h, frames[i], fps)}[v{i}];" for i in range(n))
    cover = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    return "".join(f"[{i}:v]{cover}[v{i}];" for i in range(n))


def cuts_clip(work, scene, dur, fps, sfx=None, pacing="cuts"):
    """Quick-cut scene: hard cuts between the scene's shots, 2-3s per shot when scripted
    right, caption overlaid throughout. "cuts" holds each still; "drift" moves each one a
    little (drift_filter). Shot lengths follow shot_durations."""
    shots = scene.get("shots") or [scene.get("image_prompt") or scene.get("photo")]
    files = [f"scene_{scene['id']:02d}.png"] + [
        f"scene_{scene['id']:02d}_{k}.png" for k in range(2, len(shots) + 1)]
    durations = shot_durations(scene, dur)
    cmd = still_inputs(files, durations, fps, pacing)
    cmd += [*audio_input(audio_file(work, scene["id"]), dur),
            "-loop", "1", "-framerate", str(fps), "-i", f"caption_{scene['id']:02d}.png"]
    n = len(files)
    sfx_idx = None
    if sfx:
        cmd += ["-i", str(sfx)]
        sfx_idx = n + 2
    scaled = shot_chains(n, W, H, durations, fps, pacing)
    inputs = "".join(f"[v{i}]" for i in range(n))
    fc = (f"{scaled}{inputs}concat=n={n}:v=1:a=0[cat];"
          f"[cat][{n + 1}:v]overlay=0:0,format=yuv420p[v];"
          + narration_chain(n, sfx_idx))
    run_ff([*cmd, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            f"clip_{scene['id']:02d}.mp4"], cwd=work)


def motion_clip(work, scene_id, dur, fps, sfx=None, vertical=False):
    """A scene whose still was animated (motion.py): use the generated clip as the
    picture instead of a Ken Burns pan.

    The clip is rendered at the working canvas (LTX needs multiples of 32, so
    1280x704 rather than 1280x720) and is usually SHORTER than the narration,
    because clip length is capped to keep GPU cost sane. `tpad` clones the final
    frame to fill the rest, so the motion plays out and then settles into a still,
    which reads as deliberate rather than as a loop or a freeze glitch.
    """
    video_clip(work, scene_id, f"motion_{scene_id:02d}.webm", dur, fps, sfx, vertical)


def video_clip(work, scene_id, src, dur, fps, sfx=None, vertical=False, span=None, anchor=None,
               clip_sound=None):
    """Any video file as a scene's picture in one cut: cover-cropped to the cut, the
    last frame held when the scene runs longer than the clip, the clip's own sound
    dropped in favour of the scene's narration track. span=(start, length) plays only
    that stretch of the file (a clip scene's "trim"); anchor (0 top, 1 bottom) moves
    the crop off centre (its "focus"); clip_sound plays the clip's own sound under the
    narration (clips.clip_volume)."""
    out_w, out_h = (VW, VH) if vertical else (W, H)
    cap = f"caption_v_{scene_id:02d}.png" if vertical else f"caption_{scene_id:02d}.png"
    out = f"clipv_{scene_id:02d}.mp4" if vertical else f"clip_{scene_id:02d}.mp4"
    seek = ["-ss", f"{span[0]:.3f}", "-t", f"{span[1]:.3f}"] if span else []
    cmd = [*seek, "-i", str(src), *audio_input(audio_file(work, scene_id), dur),
           "-loop", "1", "-framerate", str(fps), "-i", cap]
    sfx_idx = None
    if sfx:
        cmd += ["-i", str(sfx)]
        sfx_idx = 3
    crop = f"crop={out_w}:{out_h}" if anchor is None else \
        f"crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})*{anchor:.3f}"
    vf = (f"tpad=stop_mode=clone:stop_duration={dur:.3f},fps={fps},"
          f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
          f"{crop},setsar=1")
    # A clip scene can outlast its narration (the clip plays out), so its sound is padded
    # to the whole scene; otherwise the next scene's audio would start early.
    sound = (clip_sound_chain(sfx_idx, dur, clip_sound) if clip_sound is not None
             else narration_chain(1, sfx_idx, whole_dur=dur if span else None))
    fc = f"[0:v]{vf}[m];[m][2:v]overlay=0:0,format=yuv420p[v];" + sound
    run_ff([*cmd, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", out], cwd=work)


def mograph_render(work, scene, vertical, job_id):
    """The rendered graphic for one cut. finish renders it after tts; a bare assemble run
    (verticalize) stops here rather than play a scene with no picture."""
    path = mograph.render_path(work, scene["id"], vertical)
    if not path.exists():
        common.die(f"scene {scene['id']}: no motion graphic render at {path.name}, "
                   f"run: fv.py mograph {job_id}")
    return path


def ken_burns_clip(work, scene_id, dur, fps, zoom_in, sfx=None):
    """One scene: still + narration + caption overlay -> clip_NN.mp4.

    Caption is a pre-rendered transparent PNG (captions.py), composited with
    `overlay` so no libass/drawtext is needed. Upscale before zoompan kills jitter.
    """
    frames = math.ceil(dur * fps)
    if zoom_in:
        zexpr = f"min(1+0.08*on/{frames},1.08)"
    else:
        zexpr = f"max(1.08-0.08*on/{frames},1.0)"
    vf = (f"scale={W * 2}:-2,"
          f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={fps}")
    cmd = ["-loop", "1", "-framerate", str(fps), "-i", f"scene_{scene_id:02d}.png",
           *audio_input(audio_file(work, scene_id), dur),
           "-loop", "1", "-framerate", str(fps), "-i", f"caption_{scene_id:02d}.png"]
    sfx_idx = None
    if sfx:
        cmd += ["-i", str(sfx)]
        sfx_idx = 3
    fc = (f"[0:v]{vf}[kb];[kb][2:v]overlay=0:0,format=yuv420p[v];"
          + narration_chain(1, sfx_idx))
    run_ff([*cmd, "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
            "-ar", "44100", f"clip_{scene_id:02d}.mp4"], cwd=work)


END_HOLD_DEFAULT = 2.5     # seconds the last frame lingers; 0 turns it off
END_HOLD_MAX = 8.0
END_FADE = 0.5             # the music starts fading this long into the hold


MUSIC_VOLUME_DEFAULT = 0.18  # music level under narration, 0 to 1


def music_volume(data, theme, override=None):
    """Music level under narration. `fv.py finish --music-volume` (kept in state) wins,
    then scenes.json "music_volume", then the theme's, then the 0.18 default."""
    for value in (override, data.get("music_volume"), theme.get("music_volume")):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"music_volume must be a number from 0 to 1, got {value!r}")
        return float(value)
    return MUSIC_VOLUME_DEFAULT


def end_hold_seconds(data, theme):
    """How long to hold the final frame. scenes.json "end_hold" wins over the theme's."""
    for source in (data, theme):
        if "end_hold" not in source:
            continue
        hold = source["end_hold"]
        if isinstance(hold, bool) or not isinstance(hold, (int, float)) \
                or not 0 <= hold <= END_HOLD_MAX:
            raise ValueError(f"end_hold must be a number from 0 to {END_HOLD_MAX:g} seconds, "
                             f"got {hold!r}")
        return float(hold)
    return END_HOLD_DEFAULT


def concat_filter(count, has_music, mvol, total, hold):
    """The filter graph that joins the scene clips. With a hold, the last frame is cloned
    for `hold` seconds, the narration track is padded with silence to match, and the music
    (which keeps playing under the hold) fades out so the video lands instead of stopping.
    Returns (filter_complex, audio map label). The music is input number `count`."""
    pairs = "".join(f"[{i}:v][{i}:a]" for i in range(count))
    if not hold:
        fc = f"{pairs}concat=n={count}:v=1:a=1[vf][na]"
    else:
        fc = (f"{pairs}concat=n={count}:v=1:a=1[vc][nc];"
              f"[vc]tpad=stop_mode=clone:stop_duration={hold:.3f}[vf];"
              f"[nc]apad=pad_dur={hold:.3f}[na]")
    if not has_music:
        return fc, "[na]"
    fc += (f";[{count}:a]volume={mvol}[bg];"
           # b=1: by default dynaudnorm assumes unity gain past both ends, which fades the
           # first and last ~8 s in and out (the hook came out 7 LU quiet, 2026-11-17).
           "[na][bg]amix=inputs=2:duration=first:dropout_transition=2,dynaudnorm=b=1")
    if hold:
        # After dynaudnorm on purpose: the normaliser would pump a fade back up.
        fade = max(hold - END_FADE, 0.1)
        fc += f",afade=t=out:st={total + END_FADE:.3f}:d={fade:.3f}"
    return fc + "[af]", "[af]"


def _concat(work, pattern, out_name, count, music, mvol, total, hold):
    cmd = []
    for i in range(1, count + 1):
        cmd += ["-i", pattern.format(i)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
    fc, amap = concat_filter(count, bool(music), mvol, total, hold)
    run_ff([*cmd, "-filter_complex", fc, "-map", "[vf]", "-map", amap,
            "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", f"../out/{out_name}"], cwd=work)
    final = Path(work).parent / "out" / out_name
    loudness.normalize(final)
    audio_qc.check(final, loudness.TARGET_I)   # prints PROBLEMS with timestamps; fix before Tony sees it


def concat_clips(work, count, music=None, mvol=0.18, total=0.0, hold=0.0):
    """Captioned clips -> master 16:9 (+ optional ducked music bed, + end hold)."""
    _concat(work, "clip_{:02d}.mp4", "final_16x9.mp4", count, music, mvol, total, hold)


VW, VH = 1080, 1920  # native vertical (TikTok/Reels/Shorts)
V_CAPTION_MARGIN = 330  # keeps captions above the TikTok UI overlay zone


def vertical_clip(work, scene, dur, fps, pacing, zoom_in, sfx=None):
    """Native 9:16 companion clip from the same stills: center cover-crop
    (compositions are centered by prompt design), vertical caption placement."""
    cover = (f"scale={VW}:{VH}:force_original_aspect_ratio=increase,"
             f"crop={VW}:{VH},setsar=1")
    audio_in = audio_input(audio_file(work, scene["id"]), dur)
    cap = f"caption_v_{scene['id']:02d}.png"

    def best(name):
        """Prefer a portrait-native render (p_ prefix) over cropped landscape."""
        return f"p_{name}" if (work / f"p_{name}").exists() else name

    if pacing in ("cuts", "drift"):
        shots = scene.get("shots") or [scene.get("image_prompt") or scene.get("photo")]
        files = [best(f"scene_{scene['id']:02d}.png")] + [
            best(f"scene_{scene['id']:02d}_{k}.png") for k in range(2, len(shots) + 1)]
        durations = shot_durations(scene, dur)
        cmd = still_inputs(files, durations, fps, pacing)
        n = len(files)
        cmd += [*audio_in, "-loop", "1", "-framerate", str(fps), "-i", cap]
        sfx_idx = None
        if sfx:
            cmd += ["-i", str(sfx)]
            sfx_idx = n + 2
        scaled = shot_chains(n, VW, VH, durations, fps, pacing)
        inputs = "".join(f"[v{i}]" for i in range(n))
        fc = (f"{scaled}{inputs}concat=n={n}:v=1:a=0[cat];"
              f"[cat][{n + 1}:v]overlay=0:0,format=yuv420p[v];"
              + narration_chain(n, sfx_idx))
    else:
        frames = math.ceil(dur * fps)
        zexpr = (f"min(1+0.08*on/{frames},1.08)" if zoom_in
                 else f"max(1.08-0.08*on/{frames},1.0)")
        vf = (f"{cover},scale={VW * 2}:{VH * 2},"
              f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={VW}x{VH}:fps={fps}")
        cmd = ["-loop", "1", "-framerate", str(fps), "-i", best(f"scene_{scene['id']:02d}.png"),
               *audio_in, "-loop", "1", "-framerate", str(fps), "-i", cap]
        sfx_idx = None
        if sfx:
            cmd += ["-i", str(sfx)]
            sfx_idx = 3
        fc = (f"[0:v]{vf}[kb];[kb][2:v]overlay=0:0,format=yuv420p[v];"
              + narration_chain(1, sfx_idx))
    run_ff([*cmd, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            f"clipv_{scene['id']:02d}.mp4"], cwd=work)


def concat_vertical(work, count, music=None, mvol=0.18, total=0.0, hold=0.0):
    _concat(work, "clipv_{:02d}.mp4", "final_9x16.mp4", count, music, mvol, total, hold)


def run(job_id, music=None):
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    cfg = common.load_config()
    fps = int(cfg["FPS"])
    work = common.job_dir(job_id) / "work"
    scenes = data["scenes"]

    style = theme.get("caption_style", {})
    pacing = theme.get("pacing", "kenburns")
    portrait_only = bool(theme.get("portrait_only"))
    durations = []
    kept = []   # per scene: does a clip play its own sound as recorded
    for i, scene in enumerate(scenes):
        clip = clips.resolve(work.parent, scene["clip"]) if scene.get("clip") else None
        info = clips.probe(clip) if clip else None
        span = clips.span(scene, info.seconds) if clip else None
        audio = audio_file(work, scene["id"])
        narration_s = probe_dur(audio) if audio else 0.0
        if audio:
            dur = narration_s + PAD
            if clip and dur > span[1] + 0.05:
                print(f"[assemble] WARNING: scene {scene['id']}: narration runs {dur:.1f}s, "
                      f"the clip {span[1]:.1f}s; its last frame holds for the rest")
            elif clip:
                dur = span[1]  # the clip plays out after the narration ends
        elif (scene.get("narration") or "").strip():
            common.die(f"no narration audio for scene {scene['id']} (run tts first)")
        elif clip:
            dur = span[1]
        else:
            dur = float(scene.get("duration", SILENT_SCENE_DUR))
        durations.append(dur)
        clip_sound = clips.clip_volume(scene, info, narration_s, theme) if clip else None
        kept.append(bool(clip) and clips.keeps_sound(scene, info))
        sfx = resolve_audio(scene.get("sfx"), "sfx")
        captions.caption_png(caption_text(scene, theme, vertical=True),
                             work / f"caption_v_{scene['id']:02d}.png",
                             VW, VH, style, bottom_margin=V_CAPTION_MARGIN)
        # A generated motion clip wins over any still-based treatment: it is the
        # picture for this scene, in both cuts.
        has_motion = (work / f"motion_{scene['id']:02d}.webm").exists()
        # A motion graphic is rendered at each cut's own size (mograph.run): no crop.
        graphic = scene.get("mograph") is not None
        if not portrait_only:
            captions.caption_png(caption_text(scene, theme, vertical=False),
                                 work / f"caption_{scene['id']:02d}.png", W, H, style)
            if clip:
                clips.warn_aspect(scene, info, W, H)
                video_clip(work, scene["id"], clip, dur, fps, sfx, span=span,
                           anchor=clips.anchor(scene, info, W, H), clip_sound=clip_sound)
            elif graphic:
                video_clip(work, scene["id"], mograph_render(work, scene, False, job_id), dur, fps, sfx)
            elif has_motion:
                motion_clip(work, scene["id"], dur, fps, sfx)
            elif pacing in ("cuts", "drift"):
                cuts_clip(work, scene, dur, fps, sfx, pacing=pacing)
            else:
                ken_burns_clip(work, scene["id"], dur, fps, zoom_in=(i % 2 == 0), sfx=sfx)
        if clip:
            clips.warn_aspect(scene, info, VW, VH)
            video_clip(work, scene["id"], clip, dur, fps, sfx, vertical=True, span=span,
                       anchor=clips.anchor(scene, info, VW, VH), clip_sound=clip_sound)
        elif graphic:
            video_clip(work, scene["id"], mograph_render(work, scene, True, job_id), dur, fps, sfx,
                       vertical=True)
        elif has_motion:
            motion_clip(work, scene["id"], dur, fps, sfx, vertical=True)
        else:
            vertical_clip(work, scene, dur, fps, pacing, zoom_in=(i % 2 == 0), sfx=sfx)
        kind = "clip" if clip else "mograph" if graphic else "motion" if has_motion else pacing
        print(f"[assemble] scene {scene['id']}: {dur:.1f}s clip ({kind})"
              + (f" +sfx:{sfx.name}" if sfx else ""))

    music = resolve_audio(music or theme.get("music") or None, "music")
    # With no narration anywhere the music IS the soundtrack: run it near full
    # level instead of ducked under speech that does not exist. A clip that keeps its
    # own sound counts as speech: its voices and room tone must not drown.
    silent = not any(kept) and not any((s.get("narration") or "").strip() for s in scenes)
    total = sum(durations)
    try:
        hold = end_hold_seconds(data, theme)
        mvol = 0.85 if silent else music_volume(data, theme, common.get_state(job_id).get("music_volume"))
    except ValueError as err:
        common.die(str(err))
    track = str(music) if music else None
    if track and not silent and mvol != MUSIC_VOLUME_DEFAULT:
        print(f"[assemble] music at {mvol:g} under narration")
    if not portrait_only:
        concat_clips(work, len(scenes), track, mvol, total, hold)
    concat_vertical(work, len(scenes), track, mvol, total, hold)
    if hold:
        print(f"[assemble] last frame held {hold:g}s" + (", music fades out" if track else ""))

    out = common.job_dir(job_id) / "out"
    total += hold
    common.set_state(job_id, status="rendered", duration_s=round(total, 1), end_hold_s=hold,
                     scene_durations=[round(d, 3) for d in durations])
    finals = ["final_9x16.mp4"] if portrait_only else ["final_16x9.mp4", "final_9x16.mp4"]
    print(f"[assemble] {total:.0f}s video -> " + " + ".join(str(out / f) for f in finals))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--music", help="filename in assets/music/")
    a = p.parse_args()
    run(a.job, a.music)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        common.die(f"ffmpeg failed: {err}")
    except RuntimeError as err:
        common.die(str(err))
