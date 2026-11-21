"""Speech to word-timed text for Tony's footage.

Parakeet (NVIDIA, via parakeet-mlx) is the default since 2026-10-12: on the California
takes it caught two whole retakes and a restart that Whisper skipped, and it did not
invent a closing line. It must run in 30 s chunks: at the 120 s default it dropped 175
words across three takes, at 30 s it dropped none. Whisper stays as the fallback when the Parakeet venv is missing.
Parakeet and mlx-whisper are Apple Silicon only. On Windows, Linux or an Intel Mac the third
engine, faster-whisper, runs instead (CPU, or an NVIDIA GPU when CUDA is present).
All three write the same Whisper-shaped JSON: {"segments": [{start, end, text, words: [{start,
end, word, probability}]}]}, so th.py, countdown.py and th_lib never know which ran.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import platform_util

PARAKEET_BIN = platform_util.venv_bin(platform_util.studio_venv("parakeet"), "parakeet-mlx")
PARAKEET_CHUNK_S, PARAKEET_OVERLAP_S = 30, 5
WHISPER_PY = platform_util.venv_python(platform_util.studio_venv("whisper"))
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_PY = platform_util.venv_python(platform_util.studio_venv("faster-whisper"))
# large-v3-turbo is the accurate default; set FASTER_WHISPER_MODEL=small.en on a slow laptop.
FASTER_MODEL = os.environ.get("FASTER_WHISPER_MODEL", "large-v3-turbo")
# Audio is decoded by ffmpeg (already required) rather than PyAV, whose releases have
# broken faster-whisper's own decoder before.
FASTER_SCRIPT = (
    "import json, subprocess, sys\n"
    "import numpy as np\n"
    "from faster_whisper import WhisperModel\n"
    "m = WhisperModel(sys.argv[1], device='auto', compute_type='auto')\n"
    "out = []\n"
    "for audio in sys.argv[3:]:\n"
    "    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', audio, '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'],\n"
    "                         capture_output=True, check=True).stdout\n"
    "    segs, _ = m.transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True, language='en')\n"
    "    out.append({'segments': [{'start': s.start, 'end': s.end, 'text': s.text,\n"
    "        'words': [{'start': w.start, 'end': w.end, 'word': w.word, 'probability': w.probability}\n"
    "                  for w in (s.words or [])]} for s in segs]})\n"
    "json.dump(out, open(sys.argv[2], 'w'))\n"
)


def _merge_tokens(tokens):
    """Parakeet emits sub-word pieces. A piece that starts with a space starts a new word."""
    words = []
    for t in tokens:
        if words and not t["text"].startswith(" "):
            last = words[-1]
            words[-1] = {**last, "word": last["word"] + t["text"], "end": t["end"],
                         "probability": min(last["probability"], t.get("confidence", 1.0))}
        else:
            text = t["text"] if t["text"].startswith(" ") else " " + t["text"]
            words.append({"word": text, "start": t["start"], "end": t["end"], "probability": t.get("confidence", 1.0)})
    return words


def parakeet_to_whisper(data):
    """Parakeet sentences and tokens -> Whisper segments and words. Pure."""
    segments = []
    for s in data.get("sentences", []):
        words = _merge_tokens(s.get("tokens", []))
        if not words:
            continue
        segments.append({"start": s["start"], "end": s["end"], "text": " " + s["text"].strip(), "words": words})
    return {"text": data.get("text", ""), "segments": segments}


def _run_parakeet(audio):
    with tempfile.TemporaryDirectory() as tmp:
        # 30 s chunks: the 120 s default silently dropped whole sentences (113 words on one take)
        subprocess.run([str(PARAKEET_BIN), str(audio), "--output-format", "json", "--output-dir", tmp,
                        "--chunk-duration", str(PARAKEET_CHUNK_S), "--overlap-duration", str(PARAKEET_OVERLAP_S)],
                       check=True, capture_output=True, text=True)
        produced = next(Path(tmp).glob("*.json"))
        return parakeet_to_whisper(json.loads(produced.read_text()))


def _run_whisper(audio):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "w.json"
        script = (
            "import mlx_whisper, json, sys\n"
            f"r = mlx_whisper.transcribe(sys.argv[1], path_or_hf_repo='{WHISPER_MODEL}', word_timestamps=True, language='en')\n"
            "json.dump(r, open(sys.argv[2], 'w'))\n"
        )
        subprocess.run([str(WHISPER_PY), "-c", script, str(audio), str(out)], check=True)
        return json.loads(out.read_text())


def _faster_python():
    """The interpreter that has faster-whisper: its own venv, else this Python if it was pip installed here."""
    if FASTER_PY.exists():
        return FASTER_PY
    if importlib.util.find_spec("faster_whisper"):
        return Path(sys.executable)
    return None


def _run_faster(audios):
    """faster-whisper over several files with one model load. Returns Whisper-shaped dicts in order."""
    py = _faster_python()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "fw.json"
        subprocess.run([str(py), "-c", FASTER_SCRIPT, FASTER_MODEL, str(out), *map(str, audios)], check=True)
        return json.loads(out.read_text())


def default_engine():
    """parakeet, then mlx whisper (both Apple Silicon), then faster-whisper (any OS); None when nothing is installed."""
    if PARAKEET_BIN.exists():
        return "parakeet"
    if WHISPER_PY.exists():
        return "whisper"
    if _faster_python():
        return "faster-whisper"
    return None


def available():
    """True when any transcriber is installed (a fresh machine may have none)."""
    return default_engine() is not None


INSTALL_HINT = ("no transcriber installed. Mac (Apple Silicon): parakeet-mlx in ~/video-studio/.venv-parakeet. "
                "Windows, Linux or Intel Mac: pip install faster-whisper (or a venv at ~/video-studio/.venv-faster-whisper)")


def transcribe_many(audios):
    """Whisper-shaped dicts for several files in order. Parakeet and faster-whisper take them all
    in one call, so the model loads once (forty TTS scenes would otherwise pay forty model loads)."""
    engine = default_engine()
    if engine == "faster-whisper":
        return _run_faster(audios)
    if engine != "parakeet":
        return [_run_whisper(a) for a in audios]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([str(PARAKEET_BIN), *map(str, audios), "--output-format", "json", "--output-dir", tmp,
                        "--output-template", "{index}", "--chunk-duration", str(PARAKEET_CHUNK_S),
                        "--overlap-duration", str(PARAKEET_OVERLAP_S)], check=True, capture_output=True, text=True)
        return [parakeet_to_whisper(json.loads((Path(tmp) / f"{i}.json").read_text())) for i in range(1, len(audios) + 1)]


def transcribe(audio, out_json, engine=None):
    """Write Whisper-shaped JSON for a 16 kHz mono WAV. Returns the engine that ran."""
    engine = engine or default_engine()
    if engine is None or (engine == "whisper" and not WHISPER_PY.exists()) \
            or (engine == "faster-whisper" and not _faster_python()):
        sys.exit(INSTALL_HINT)
    if engine == "parakeet":
        data = _run_parakeet(audio)
    elif engine == "faster-whisper":
        data = _run_faster([audio])[0]
    else:
        data = _run_whisper(audio)
    Path(out_json).write_text(json.dumps(data))
    return engine
