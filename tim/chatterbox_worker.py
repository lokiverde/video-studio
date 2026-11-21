"""Persistent Chatterbox TTS worker on Tim. Loopback only; tim-media proxies to it.

Lives in ~/chatterbox-venv (torch 2.6 CPU), separate from media-venv so the
ComfyUI cu128 stack is never touched. Model loads once and stays resident.

Run: ~/chatterbox-venv/bin/uvicorn chatterbox_worker:app --host 127.0.0.1 --port 8791
"""
import io
import time
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

REFS = {
    "tony": Path.home() / "tim-media" / "refs" / "tony_ref.wav",
    "partner": Path.home() / "tim-media" / "refs" / "partner_ref.wav",
}

app = FastAPI()
_model = None


class TTSReq(BaseModel):
    text: str
    voice: str = "stock"  # stock | tony | partner
    exaggeration: float = 0.5
    cfg_weight: float = 0.5


def get_model():
    global _model
    if _model is None:
        import perth
        if perth.PerthImplicitWatermarker is None:
            # perth's torch watermarker fails to register on aarch64
            perth.PerthImplicitWatermarker = perth.DummyWatermarker
        from chatterbox.tts import ChatterboxTTS
        _model = ChatterboxTTS.from_pretrained(device="cpu")
    return _model


@app.get("/health")
def health():
    return {"ok": True, "loaded": _model is not None}


@app.post("/tts")
def tts(r: TTSReq):
    if not r.text.strip():
        raise HTTPException(400, "empty text")
    if r.voice != "stock" and r.voice not in REFS:
        raise HTTPException(400, f"unknown voice '{r.voice}' (stock|{'|'.join(REFS)})")
    model = get_model()
    kwargs = {"exaggeration": r.exaggeration, "cfg_weight": r.cfg_weight}
    if r.voice in REFS:
        ref = REFS[r.voice]
        if not ref.exists():
            raise HTTPException(500, f"reference wav missing: {ref}")
        kwargs["audio_prompt_path"] = str(ref)
    t0 = time.time()
    wav = model.generate(r.text, **kwargs)
    audio = wav.squeeze(0).numpy()
    buf = io.BytesIO()
    sf.write(buf, audio, model.sr, format="WAV")
    buf.seek(0)
    return Response(content=buf.read(), media_type="audio/wav",
                    headers={"X-Gen-Seconds": f"{time.time()-t0:.1f}",
                             "X-Audio-Seconds": f"{len(audio)/model.sr:.1f}"})
