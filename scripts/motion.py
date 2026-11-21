"""Animate a scene's still into a short clip (the motion tier).

A scene opts in with a `motion` block:

    "motion": {"prompt": "the papers lift slightly in a draft, subtle camera drift"}

The still that was already rendered and approved at the preview gate becomes the
FIRST FRAME, so the clip inherits the composition, the drawn character, and the
style the human signed off on. Nothing about the look is re-rolled; only movement
is added. That is the same principle as the drawn character compositor: keep what
must stay identical out of the sampler.

Runs after TTS, because clip length is chosen to match the scene's narration, and
narration length is not known until the audio exists.

Costs, measured 2026-08-13 on Tim: LTX 2B at 1280x704 for 121 frames is 73.3s, so a
5-second motion scene costs about a minute of GPU. Hunyuan is ~8x that and reserved
for shots needing a real camera move.
"""
import argparse
import base64
import math

import common

FPS = 24.0            # LTX was trained at 24; assemble re-times to the project fps
MAX_SECONDS = 6.0     # clips longer than this cost more than they add
MIN_FRAMES = 25       # 8n+1, about a second: below this there is no motion to see
NEGATIVE = ("static, frozen, blurry, low quality, distorted, watermark, text, "
            "morphing, extra limbs, duplicated subject")


def snap_length(seconds):
    """LTX needs length = 8n+1. Round to the nearest legal count for `seconds`."""
    frames = min(seconds, MAX_SECONDS) * FPS
    n = max(3, round((frames - 1) / 8))     # 3 -> 25 frames minimum
    return max(MIN_FRAMES, int(n * 8 + 1))


def snap_dim(value):
    """LTX needs both dimensions to be multiples of 32. 720 is NOT (it is 22.5),
    which is why the working canvas becomes 1280x704 here rather than 1280x720."""
    return max(32, int(round(value / 32) * 32))


def clip_path(work, scene_id):
    return work / f"motion_{scene_id:02d}.webm"


def scene_seconds(work, scene_id):
    """Narration length for this scene, or 0 when the audio is not there yet."""
    import subprocess
    import json
    audio = None
    for ext in ("wav", "mp3"):
        candidate = work / f"scene_{scene_id:02d}.{ext}"
        if candidate.exists():
            audio = candidate
            break
    if audio is None:
        return 0.0
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "json", str(audio)], capture_output=True, text=True)
    if out.returncode:
        return 0.0
    return float(json.loads(out.stdout)["format"]["duration"])


def animate_one(cfg, scene, still, out_path, seconds, seed=None):
    """One still -> one clip. Returns {"model", "gen_s", "seed", "length"}."""
    motion = scene["motion"]
    payload = {
        "prompt": motion.get("prompt") or scene["image_prompt"],
        "negative": motion.get("negative", NEGATIVE),
        "model": motion.get("model", "ltx"),
        "width": snap_dim(int(cfg["IMG_W"])),
        "height": snap_dim(int(cfg["IMG_H"])),
        "length": snap_length(seconds or MAX_SECONDS),
        "fps": FPS,
        "image_b64": base64.b64encode(still.read_bytes()).decode(),
    }
    if motion.get("steps"):
        payload["steps"] = int(motion["steps"])
    if seed is not None:
        payload["seed"] = seed
    elif motion.get("seed"):
        payload["seed"] = int(motion["seed"])

    data, headers = common.http_json(f"{cfg['TIM_MEDIA_URL']}/video", payload,
                                     timeout=1800, with_headers=True)
    if len(data) < 5000:
        raise RuntimeError(f"suspiciously small clip ({len(data)} bytes) for "
                           f"scene {scene['id']}")
    out_path.write_bytes(data)
    return {"model": headers.get("x-model", payload["model"]),
            "gen_s": float(headers.get("x-gen-seconds", 0) or 0),
            "seed": int(headers.get("x-seed", 0) or 0),
            "length": payload["length"]}


def motion_scenes(data):
    return [s for s in data["scenes"] if isinstance(s.get("motion"), dict)]


def run(job_id, only_scene=None, seed=None):
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    work = common.job_dir(job_id) / "work"
    scenes = motion_scenes(data)
    if only_scene is not None:
        scenes = [s for s in scenes if s["id"] == only_scene]
    if not scenes:
        return {}

    state = common.get_state(job_id)
    timings = state.get("motion", {})
    for scene in scenes:
        still = work / f"scene_{scene['id']:02d}.png"
        if not still.exists():
            print(f"[motion] scene {scene['id']}: no still yet, skipping")
            continue
        seconds = scene_seconds(work, scene["id"]) or float(scene.get("duration", 0))
        out = clip_path(work, scene["id"])
        result = animate_one(cfg, scene, still, out, seconds, seed)
        timings[str(scene["id"])] = result
        print(f"[motion] scene {scene['id']}: {out.name} model={result['model']} "
              f"{result['length']}f gen={result['gen_s']:.0f}s "
              f"(narration {seconds:.1f}s)")
    common.set_state(job_id, motion=timings)
    return timings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--scene", type=int, help="only this scene")
    p.add_argument("--seed", type=int, help="force a seed (default: fresh each run)")
    a = p.parse_args()
    if not run(a.job, a.scene, a.seed):
        print("[motion] no scenes carry a motion block")


if __name__ == "__main__":
    main()
