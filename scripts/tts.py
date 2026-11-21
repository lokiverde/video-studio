"""Narrate each scene. Local-first: Chatterbox on Tim, Kokoro fallback, fish.audio opt-in."""
import argparse
import subprocess
import tempfile
from pathlib import Path

import common
import voice_cleanup
import wordcheck

TEMPO_RANGE = (0.8, 1.4)   # past 1.4 atempo starts eating consonants

# Tony's approved voice (2026-10-08): the Chatterbox clone made
# deeper and clearer. About one semitone down (asetrate, so the chest drops too), warmth at
# 120Hz, less mud at 320Hz, presence at 3.5kHz, de-ess, gentle compression. Applied to every
# voice=tony read; don't speed it up afterwards, that is what made it sound robotic.
TONY_VOICE = ["aresample=48000", "asetrate=45600", "aresample=48000", "atempo=1.0526",
              "highpass=f=70", "equalizer=f=120:t=o:w=1:g=3", "equalizer=f=320:t=o:w=1:g=-2.5",
              "equalizer=f=3500:t=o:w=1.2:g=2.5", "deesser=i=0.4",
              "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2"]


def tts_tim(cfg, text, voice, engine):
    payload = {"text": text}
    if engine == "chatterbox":
        payload["engine"] = "chatterbox"
        payload["voice"] = voice  # stock | tony
    elif voice and voice not in ("stock", "tony"):
        payload["voice"] = voice  # a Kokoro voice id, e.g. am_onyx, bm_george
    return common.http_json(f"{cfg['TIM_MEDIA_URL']}/tts", payload, timeout=900), "wav"


def tts_fish(cfg, text, voice):
    key = cfg.get("FISH_API_KEY")
    if not key:
        common.die("FISH_API_KEY not set in config.env")
    ref = cfg.get("FISH_VOICE_TONY" if voice == "tony" else "FISH_VOICE_STOCK")
    payload = {"text": text, "format": "mp3"}
    if ref:
        payload["reference_id"] = ref
    headers = {"Authorization": f"Bearer {key}", "model": cfg["FISH_MODEL"]}
    return common.http_json("https://api.fish.audio/v1/tts", payload, headers, timeout=300), "mp3"


def voice_preset(audio, ext, voice):
    """The saved per-voice treatment. Only "tony" has one; other voices pass through."""
    if voice != "tony":
        return audio, ext
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / f"in.{ext}", Path(tmp) / "out.wav"
        src.write_bytes(audio)
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                            "-af", ",".join(TONY_VOICE), "-ar", "48000", str(dst)], check=True)
        except (OSError, subprocess.CalledProcessError) as err:
            raise RuntimeError(f"tony voice preset failed: {err}")
        return dst.read_bytes(), "wav"


def narrate(cfg, text, voice, engine):
    """Returns (audio_bytes, ext, engine_used), with the voice's saved preset applied."""
    data, ext, used = _narrate(cfg, text, voice, engine)
    data, ext = voice_preset(data, ext, voice)
    return data, ext, used


def _narrate(cfg, text, voice, engine):
    """Returns (audio_bytes, ext, engine_used).

    Engine "tim" picks per voice: stock -> Kokoro (instant, decent), tony ->
    Chatterbox (local clone, ~6-11x realtime on CPU, batch-friendly).
    "chatterbox" forces the premium engine for stock too. Chatterbox falls
    back to Kokoro if the worker is down (but never silently for voice=tony:
    a stock-sounding "tony" video is worse than a failed run).
    """
    if engine == "fish":
        data, ext = tts_fish(cfg, text, voice)
        return data, ext, "fish"
    want_chatterbox = engine == "chatterbox" or (engine == "tim" and voice == "tony")
    if want_chatterbox:
        try:
            data, ext = tts_tim(cfg, text, voice, "chatterbox")
            return data, ext, "chatterbox"
        except RuntimeError as err:
            if voice == "tony":
                raise RuntimeError(f"chatterbox required for voice=tony but unavailable: {err}")
            print(f"[tts] chatterbox unavailable ({err}); falling back to kokoro")
    data, ext = tts_tim(cfg, text, voice, "kokoro")
    return data, ext, "kokoro"


def resolve_tempo(data, theme):
    """Playback speed for the narration. scenes.json wins over the theme; 1.0 is untouched."""
    for source in (data, theme):
        if "narration_tempo" not in source:
            continue
        tempo = source["narration_tempo"]
        lo, hi = TEMPO_RANGE
        if isinstance(tempo, bool) or not isinstance(tempo, (int, float)) or not lo <= tempo <= hi:
            raise ValueError(f"narration_tempo must be a number from {lo} to {hi}, got {tempo!r}")
        return float(tempo)
    return 1.0


def retime(audio, ext, tempo):
    """Speed the read up (or down) with ffmpeg atempo, which keeps the pitch. The TTS
    engines on Tim have no speed knob, so a fast deadpan delivery is made here."""
    if tempo == 1.0:
        return audio
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / f"in.{ext}", Path(tmp) / f"out.{ext}"
        src.write_bytes(audio)
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                            "-filter:a", f"atempo={tempo}", str(dst)], check=True)
        except (OSError, subprocess.CalledProcessError) as err:
            raise RuntimeError(f"ffmpeg atempo={tempo} failed: {err}")
        return dst.read_bytes()


def run(job_id, voice=None, engine="tim"):
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    voice = voice or data.get("voice", "stock")
    work = common.job_dir(job_id) / "work"
    try:
        tempo = resolve_tempo(data, common.load_theme(data.get("theme", "sketch")))
    except ValueError as err:
        common.die(str(err))
    if tempo != 1.0:
        print(f"[tts] narration tempo x{tempo}")

    used, narrated = None, []
    for scene in data["scenes"]:
        text = (scene.get("narration") or "").strip()
        if not text:
            print(f"[tts] scene {scene['id']}: no narration, skipped (silent scene)")
            continue
        used = _narrate_scene(cfg, scene, text, voice, engine, tempo, work)
        narrated.append(scene["id"])

    if voice == "tony" and narrated:
        voice_cleanup.clean_scenes(work, narrated)  # takes the clone's room echo out

    left = _check_words(job_id, data, cfg, voice, engine, tempo, work) if narrated else {}
    common.set_state(job_id, status="narrated", voice=voice, tts_engine=used, narration_check=left)


def _narrate_scene(cfg, scene, text, voice, engine, tempo, work):
    audio, ext, used = narrate(cfg, text, voice, engine)
    if len(audio) < 500:
        common.die(f"scene {scene['id']}: TTS returned {len(audio)} bytes")
    audio = retime(audio, ext, tempo)
    out = work / f"scene_{scene['id']:02d}.{ext}"
    for old in work.glob(f"scene_{scene['id']:02d}.wav"):
        old.unlink()
    for old in work.glob(f"scene_{scene['id']:02d}.mp3"):
        old.unlink()
    out.write_bytes(audio)
    print(f"[tts] scene {scene['id']}: {out.name} ({used}, {len(audio)//1024}KB)")
    return used


def _check_words(job_id, data, cfg, voice, engine, tempo, work):
    """Transcribe every narrated scene and compare it with its script line (wordcheck.py).
    Chatterbox now and then skips a phrase, repeats one or swallows the last word, and
    nothing downstream listens before the CDN upload. A flagged scene gets ONE fresh take
    (each read is different), then whatever is still wrong is reported, not fatal: ASR can
    mishear a clean read too. Returns {scene_id: problems} still open."""
    result = wordcheck.check_narration(job_id)
    if result is None:
        print("[tts] word check skipped: no transcriber installed (parakeet-mlx, mlx-whisper or faster-whisper)")
        return {}
    report, _ = result
    if report:
        scenes = {s["id"]: s for s in data["scenes"]}
        for sid, problems in sorted(report.items()):
            print(f"[tts] scene {sid} retake: {'; '.join(problems)}")
            _narrate_scene(cfg, scenes[sid], scenes[sid]["narration"].strip(), voice, engine, tempo, work)
        if voice == "tony":
            voice_cleanup.clean_scenes(work, sorted(report))
        report, _ = wordcheck.check_narration(job_id, set(report))
    for sid, problems in sorted(report.items()):
        print(f"[tts] NARRATION scene {sid} still off after a retake, LISTEN: {'; '.join(problems)}")
    if not report:
        print("[tts] word check: every scene says its script")
    return {str(k): v for k, v in report.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--voice", help="stock | tony | a Kokoro voice id (e.g. am_onyx)")
    p.add_argument("--engine", default="tim", choices=["tim", "chatterbox", "kokoro", "fish"])
    a = p.parse_args()
    run(a.job, a.voice, a.engine)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        common.die(str(err))
