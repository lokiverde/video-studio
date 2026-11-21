#!/usr/bin/env python3
"""Speech from text through the ElevenLabs API, on macOS, Windows or Linux.

Usage: python3 tts.py "<text>" <voice_id> <out.mp3> [model_id]
  default model: eleven_v3. A cloned voice can sound different on a newer model: A/B first.
Reads ELEVENLABS_API_KEY from the environment, else from config.env beside this file or in
the repo it was copied from. Never prints the key.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    for env in (Path(__file__).resolve().parent / "config.env", Path.cwd() / "config.env"):
        if env.exists():
            for line in env.read_text().splitlines():
                name, _, value = line.partition("=")
                if name.strip() == "ELEVENLABS_API_KEY" and value.strip():
                    return value.strip().strip('"').strip("'")
    sys.exit("tts.py: set ELEVENLABS_API_KEY in your environment or in config.env")


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    text, voice, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    model = sys.argv[4] if len(sys.argv) > 4 else "eleven_v3"
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        data=json.dumps({"text": text, "model_id": model}).encode(),
        headers={"xi-api-key": api_key(), "Content-Type": "application/json"}, method="POST")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            out.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"tts.py: ElevenLabs said {exc.code}: {exc.read().decode(errors='replace')[:300]}")
    print("wrote", out)


if __name__ == "__main__":
    main()
