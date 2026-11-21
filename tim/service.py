"""tim-media: one HTTP API on Tim wrapping ComfyUI (image/video) + Kokoro (tts).
Runs with CUDA hidden (no GPU in-process): image/video are HTTP passthrough to
ComfyUI :8188 which owns the GPU; Kokoro TTS runs on CPU. Bind tailnet only.
"""
import json, time, uuid, io, os, urllib.request
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

COMFY = "http://127.0.0.1:8188"
app = FastAPI(title="tim-media")

# ---------- ComfyUI helpers ----------
def _post(path, body):
    r = urllib.request.Request(COMFY+path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=60).read())

def _get(path):
    return json.loads(urllib.request.urlopen(COMFY+path, timeout=60).read())

def _run(wf, timeout_s=600):
    pid = _post("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    t0 = time.time()
    while time.time()-t0 < timeout_s:
        h = _get(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                for _, o in h[pid]["outputs"].items():
                    for key in ("images", "gifs", "videos"):
                        if o.get(key):
                            return o[key][0], time.time()-t0
            if st.get("status_str") == "error":
                raise HTTPException(500, f"comfy error: {json.dumps(st)[:300]}")
        time.sleep(1)
    raise HTTPException(504, "comfy timeout")

def _fetch(out):
    q = f"/view?filename={out['filename']}&subfolder={out.get('subfolder','')}&type={out.get('type','output')}"
    return urllib.request.urlopen(COMFY+q, timeout=120).read()

# ---------- image ----------
# schnell is a 4-step distilled model: fast enough for drafts, but it returns a
# structurally broken figure (detached head, extra hand, missing limb) in roughly
# 3 shots out of 10 no matter how good the prompt or the reference is. dev is the
# undistilled model and needs real steps plus a guidance value, so it is the one to
# use for anything a person will actually watch.
FLUX_CKPT = {
    "flux": "flux1-schnell-fp8.safetensors",
    "flux-dev": "flux1-dev-fp8.safetensors",
}
FLUX_STEPS = {"flux": 4, "flux-dev": 22}
# dev must not inherit schnell's "simple" scheduler. With simple, over half of all seeds
# come back washed out: soft edges, no black outlines, the whole frame out of focus, at
# any guidance from 3.5 up and at any step count. Measured 2026-08-12 on the seeds that
# failed: simple 0.3, beta 5.7 to 8.8 on the same high-frequency metric. beta fixed every
# one of them. normal and sgm_uniform did not.
FLUX_SCHEDULER = {"flux": "simple", "flux-dev": "beta"}
FLUX_GUIDANCE_NODE = "11"        # only present in the dev graph


class ImageReq(BaseModel):
    prompt: str
    model: str = "flux"          # flux (schnell) | flux-dev | juggernaut
    negative: str = ""
    width: int = 1024
    height: int = 1024
    seed: int = 0
    lora: str = ""            # filename in ComfyUI/models/loras, "" = no LoRA
    lora_strength: float = 1.0
    reference: str = ""       # filename in ComfyUI/input, "" = pure text to image
    reference_strength: float = 0.6
    reference_mode: str = "multiply"   # multiply | attn_bias
    reference_scale: float = 1.0       # shrink the reference to loosen its grip
    steps: int = 0            # 0 = the model's own default
    guidance: float = 3.5     # flux-dev only; schnell and juggernaut ignore it
    sampler: str = ""         # "" = the model's own default
    scheduler: str = ""       # "" = the model's own default

def _seed(s): return s if s else int.from_bytes(os.urandom(4), "big")

@app.post("/image")
def image(r: ImageReq):
    seed = _seed(r.seed)
    if r.model in FLUX_CKPT:
        steps = r.steps or FLUX_STEPS[r.model]
        wf = {
          "4":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":FLUX_CKPT[r.model]}},
          "6":{"class_type":"CLIPTextEncode","inputs":{"text":r.prompt,"clip":["4",1]}},
          "7":{"class_type":"CLIPTextEncode","inputs":{"text":"","clip":["4",1]}},
          "5":{"class_type":"EmptySD3LatentImage","inputs":{"width":r.width,"height":r.height,"batch_size":1}},
          "3":{"class_type":"KSampler","inputs":{"seed":seed,"steps":steps,"cfg":1.0,"sampler_name":"euler",
               "scheduler":FLUX_SCHEDULER[r.model],"denoise":1.0,"model":["4",0],"positive":["6",0],
               "negative":["7",0],"latent_image":["5",0]}},
          "8":{"class_type":"VAEDecode","inputs":{"samples":["3",0],"vae":["4",2]}},
          "9":{"class_type":"SaveImage","inputs":{"filename_prefix":"timmedia","images":["8",0]}}}
        if r.model == "flux-dev":
            # dev is guidance-distilled: without a FluxGuidance value it renders soft,
            # washed-out mush. schnell has the value baked in and must not get this node.
            wf[FLUX_GUIDANCE_NODE] = {"class_type":"FluxGuidance",
                                      "inputs":{"conditioning":["6",0],"guidance":r.guidance}}
            wf["3"]["inputs"]["positive"] = [FLUX_GUIDANCE_NODE, 0]
    else:  # juggernaut SDXL
        wf = {
          "4":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"}},
          "6":{"class_type":"CLIPTextEncode","inputs":{"text":r.prompt,"clip":["4",1]}},
          "7":{"class_type":"CLIPTextEncode","inputs":{"text":r.negative or "blurry, low quality, distorted","clip":["4",1]}},
          "5":{"class_type":"EmptyLatentImage","inputs":{"width":r.width,"height":r.height,"batch_size":1}},
          "3":{"class_type":"KSampler","inputs":{"seed":seed,"steps":25,"cfg":7.0,"sampler_name":"dpmpp_2m",
               "scheduler":"karras","denoise":1.0,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0]}},
          "8":{"class_type":"VAEDecode","inputs":{"samples":["3",0],"vae":["4",2]}},
          "9":{"class_type":"SaveImage","inputs":{"filename_prefix":"timmedia","images":["8",0]}}}
    if r.reference and r.model in FLUX_CKPT:
        # FLUX Redux: CLIP-Vision encodes the reference, the style model projects it
        # onto the positive conditioning. The prompt still drives pose and scene;
        # the reference supplies the character. Only the positive branch is touched.
        wf["20"] = {"class_type": "LoadImage", "inputs": {"image": r.reference}}
        image_src = ["20", 0]
        if r.reference_scale and r.reference_scale != 1.0:
            # Redux strength scales with how many image tokens it gets, so a smaller
            # reference loosens its grip on composition without weakening identity.
            wf["25"] = {"class_type": "ImageScaleBy",
                        "inputs": {"image": ["20", 0], "upscale_method": "area",
                                   "scale_by": r.reference_scale}}
            image_src = ["25", 0]
        wf["21"] = {"class_type": "CLIPVisionLoader",
                    "inputs": {"clip_name": "sigclip_vision_patch14_384.safetensors"}}
        wf["22"] = {"class_type": "CLIPVisionEncode",
                    "inputs": {"clip_vision": ["21", 0], "image": image_src, "crop": "center"}}
        wf["23"] = {"class_type": "StyleModelLoader",
                    "inputs": {"style_model_name": "flux1-redux-dev.safetensors"}}
        wf["24"] = {"class_type": "StyleModelApply",
                    "inputs": {"conditioning": ["6", 0], "style_model": ["23", 0],
                               "clip_vision_output": ["22", 0],
                               "strength": r.reference_strength,
                               "strength_type": r.reference_mode}}
        # Redux slots in ahead of the guidance node when there is one, so the sampler
        # always reads conditioning that has both the reference tokens and a guidance
        # value on it. StyleModelApply copies the conditioning dict either way, but
        # keeping guidance last means one place decides what the sampler sees.
        if FLUX_GUIDANCE_NODE in wf:
            wf[FLUX_GUIDANCE_NODE]["inputs"]["conditioning"] = ["24", 0]
        else:
            wf["3"]["inputs"]["positive"] = ["24", 0]

    if r.sampler:
        wf["3"]["inputs"]["sampler_name"] = r.sampler
    if r.scheduler:
        wf["3"]["inputs"]["scheduler"] = r.scheduler

    if r.lora:
        # LoraLoader sits between the checkpoint and both text encoders + the sampler.
        # The VAE still comes straight off the checkpoint. Node ids are the same in the
        # flux and juggernaut graphs above, so this rewiring covers both.
        wf["10"] = {"class_type": "LoraLoader",
                    "inputs": {"lora_name": r.lora,
                               "strength_model": r.lora_strength,
                               "strength_clip": r.lora_strength,
                               "model": ["4", 0], "clip": ["4", 1]}}
        wf["6"]["inputs"]["clip"] = ["10", 1]
        wf["7"]["inputs"]["clip"] = ["10", 1]
        wf["3"]["inputs"]["model"] = ["10", 0]
    out, secs = _run(wf)
    data = _fetch(out)
    headers = {"X-Gen-Seconds": f"{secs:.1f}", "X-Seed": str(seed),
               "X-Model": r.model,
               "X-Steps": str(wf["3"]["inputs"]["steps"])}
    if r.model == "flux-dev":
        headers["X-Guidance"] = str(r.guidance)
    if r.lora:
        headers["X-Lora"] = f"{r.lora}@{r.lora_strength}"
    if r.reference:
        headers["X-Reference"] = (f"{r.reference}@{r.reference_strength}"
                                  f"/{r.reference_mode}/x{r.reference_scale}")
    return Response(content=data, media_type="image/png", headers=headers)

# ---------- video (Wan 2.2 5B) ----------
# LTX is the production motion tier: measured 46.1s for 121 frames at 480x832 vs
# Wan's 571.1s and Hunyuan's 373.2s on the identical job (2026-08-13). Hunyuan is
# kept for shots needing a big camera move; Wan only so older results reproduce.
MOTION_MODELS = ("ltx", "hunyuan", "wan")


class VideoReq(BaseModel):
    prompt: str
    negative: str = "static, blurry, low quality, distorted, watermark, text"
    width: int = 704
    height: int = 480
    length: int = 49
    seed: int = 0
    model: str = "ltx"
    steps: int = 0        # 0 = the model's own default
    fps: float = 24.0
    # Optional start frame (base64 PNG/JPEG): Wan 2.2 is a TI2V model, so a start
    # image pins the first frame and the motion grows out of the real photo.
    image_b64: str = ""

def _wan_workflow(r, seed):
    """Wan 2.2 TI2V 5B. Slowest of the three and the least responsive to motion
    direction; retained for reproducibility, not recommended for new work."""
    return {
      "37":{"class_type":"UNETLoader","inputs":{"unet_name":"wan2.2_ti2v_5B_fp16.safetensors","weight_dtype":"default"}},
      "38":{"class_type":"CLIPLoader","inputs":{"clip_name":"umt5_xxl_fp8_e4m3fn_scaled.safetensors","type":"wan"}},
      "39":{"class_type":"VAELoader","inputs":{"vae_name":"wan2.2_vae.safetensors"}},
      "6":{"class_type":"CLIPTextEncode","inputs":{"text":r.prompt,"clip":["38",0]}},
      "7":{"class_type":"CLIPTextEncode","inputs":{"text":r.negative,"clip":["38",0]}},
      "48":{"class_type":"ModelSamplingSD3","inputs":{"shift":8.0,"model":["37",0]}},
      "55":{"class_type":"Wan22ImageToVideoLatent","inputs":{"vae":["39",0],"width":r.width,"height":r.height,"length":r.length,"batch_size":1}},
      "3":{"class_type":"KSampler","inputs":{"seed":seed,"steps":20,"cfg":5.0,"sampler_name":"uni_pc",
           "scheduler":"simple","denoise":1.0,"model":["48",0],"positive":["6",0],"negative":["7",0],"latent_image":["55",0]}},
      "8":{"class_type":"VAEDecode","inputs":{"samples":["3",0],"vae":["39",0]}},
      "9":{"class_type":"SaveWEBM","inputs":{"images":["8",0],"filename_prefix":"timmedia","codec":"vp9","fps":r.fps,"crf":20.0}}}


def _ltx_workflow(r, seed, start_image):
    """LTX-Video 2B 0.9.8 distilled. One checkpoint carries model+VAE; the text
    encoder is a separate t5xxl. Sampling is SamplerCustom driven by LTXVScheduler,
    NOT a plain KSampler, and cfg must be 1.0 on the distilled weights.

    Requires a start image: this pipeline animates a still it already rendered."""
    steps = r.steps or 8
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "ltxv-2b-0.9.8-distilled.safetensors"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "ltxv"}},
        "3": {"class_type": "LoadImage", "inputs": {"image": start_image}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": r.prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": r.negative, "clip": ["2", 0]}},
        "6": {"class_type": "LTXVImgToVideo",
              "inputs": {"positive": ["4", 0], "negative": ["5", 0], "vae": ["1", 2],
                         "image": ["3", 0], "width": r.width, "height": r.height,
                         "length": r.length, "batch_size": 1, "strength": 1.0}},
        "7": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["6", 0], "negative": ["6", 1], "frame_rate": r.fps}},
        "8": {"class_type": "ModelSamplingLTXV",
              "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95,
                         "latent": ["6", 2]}},
        "9": {"class_type": "LTXVScheduler",
              "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1, "latent": ["6", 2]}},
        "10": {"class_type": "SamplerCustom",
               "inputs": {"model": ["8", 0], "add_noise": True, "noise_seed": seed,
                          "cfg": 1.0, "positive": ["7", 0], "negative": ["7", 1],
                          "sampler": ["11", 0], "sigmas": ["9", 0],
                          "latent_image": ["6", 2]}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "13": {"class_type": "SaveWEBM",
               "inputs": {"images": ["12", 0], "filename_prefix": "timmedia",
                          "codec": "vp9", "fps": r.fps, "crf": 20.0}},
    }


def _hunyuan_workflow(r, seed, start_image):
    """HunyuanVideo 1.5 480p i2v step-distilled. Performs bigger camera moves and
    gestures than LTX at roughly 8x the cost. Text encoding is a PAIR loaded through
    DualCLIPLoader type hunyuan_video_15; cfg is 1.0 (cfg-distilled) and 4 steps is
    visibly degraded, so 8 is the floor."""
    steps = r.steps or 8
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "hunyuanvideo1.5_480p_i2v_step_distilled_fp8_scaled.safetensors",
                         "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                         "clip_name2": "byt5_small_glyphxl_fp16.safetensors",
                         "type": "hunyuan_video_15"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "hunyuanvideo15_vae_fp16.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": start_image}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": r.prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": r.negative, "clip": ["2", 0]}},
        "7": {"class_type": "HunyuanVideo15ImageToVideo",
              "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["3", 0],
                         "width": r.width, "height": r.height, "length": r.length,
                         "batch_size": 1, "start_image": ["4", 0]}},
        "8": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 1.0, "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0, "model": ["1", 0],
                         "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["7", 2]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveWEBM",
               "inputs": {"images": ["9", 0], "filename_prefix": "timmedia",
                          "codec": "vp9", "fps": r.fps, "crf": 20.0}},
    }


def _stage_start_image(image_b64):
    """Write a base64 start frame into ComfyUI's input dir and return its name."""
    import base64
    from pathlib import Path
    name = f"timmedia_start_{uuid.uuid4().hex}.png"
    (Path.home() / "ComfyUI" / "input" / name).write_bytes(base64.b64decode(image_b64))
    return name


@app.post("/video")
def video(r: VideoReq):
    if r.model not in MOTION_MODELS:
        raise HTTPException(400, f"model must be one of {MOTION_MODELS}")
    if r.model in ("ltx", "hunyuan"):
        # Both are image-to-video here: the pipeline animates a still it rendered.
        if not r.image_b64:
            raise HTTPException(400, f"{r.model} needs image_b64 (a start frame)")
        if (r.length - 1) % 8:
            raise HTTPException(400, f"length must be 8n+1 for {r.model}, got {r.length}")
        if r.width % 32 or r.height % 32:
            raise HTTPException(400, "width and height must be multiples of 32")
    seed = _seed(r.seed)
    start = _stage_start_image(r.image_b64) if r.image_b64 else None
    if r.model == "ltx":
        wf = _ltx_workflow(r, seed, start)
    elif r.model == "hunyuan":
        wf = _hunyuan_workflow(r, seed, start)
    else:
        wf = _wan_workflow(r, seed)
        if start:
            wf["56"] = {"class_type": "LoadImage", "inputs": {"image": start}}
            wf["55"]["inputs"]["start_image"] = ["56", 0]
    out, secs = _run(wf, timeout_s=1800)
    data = _fetch(out)
    return Response(content=data, media_type="video/webm",
                    headers={"X-Gen-Seconds": f"{secs:.1f}", "X-Seed": str(seed),
                             "X-Model": r.model})

# ---------- tts (Kokoro, CPU) ----------
_kok = None
class TTSReq(BaseModel):
    text: str
    voice: str = "af_heart"
    engine: str = "kokoro"  # kokoro | chatterbox

CHATTERBOX_WORKER = "http://127.0.0.1:8791/tts"

@app.post("/tts")
def tts(r: TTSReq):
    global _kok
    if r.engine == "chatterbox":
        # Proxy to the chatterbox worker (separate venv, loopback :8791).
        voice = r.voice if r.voice in ("stock", "tony", "partner") else "stock"
        try:
            rq = urllib.request.Request(CHATTERBOX_WORKER,
                data=json.dumps({"text": r.text, "voice": voice}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq, timeout=900) as resp:
                return Response(content=resp.read(), media_type="audio/wav",
                                headers={"X-Engine": "chatterbox",
                                         "X-Gen-Seconds": resp.headers.get("X-Gen-Seconds", ""),
                                         "X-Audio-Seconds": resp.headers.get("X-Audio-Seconds", "")})
        except Exception as e:
            raise HTTPException(502, f"chatterbox worker unavailable: {e}")
    import soundfile as sf, numpy as np
    if _kok is None:
        from kokoro import KPipeline
        _kok = KPipeline(lang_code="a")
    t0 = time.time()
    audio = [a for _, _, a in _kok(r.text, voice=r.voice)]
    if not audio:
        raise HTTPException(500, "no audio")
    wav = np.concatenate(audio)
    buf = io.BytesIO(); sf.write(buf, wav, 24000, format="WAV"); buf.seek(0)
    return Response(content=buf.read(), media_type="audio/wav",
                    headers={"X-Gen-Seconds": f"{time.time()-t0:.1f}", "X-Audio-Seconds": f"{len(wav)/24000:.1f}"})

# ---------- ocr (Qwen3.6-35B VLM served by vLLM on :8000) ----------
# No GPU work happens in this process: /ocr is an HTTP passthrough to vLLM,
# exactly as /image and /video pass through to ComfyUI. Qwen3.6-35B-A3B is
# multimodal (27-layer vision tower), so the model already serving chat reads
# documents too -- no Tesseract, no second model resident, no per-page API cost.
#
# Pages are transcribed CONCURRENTLY. vLLM runs --max-num-seqs 64, so a 40-page
# document costs roughly what a few pages cost sequentially. This is the one
# workload Tim is unambiguously best at.
#
# SECURITY: document contents are untrusted input. The prompts below ask only
# for transcription or extraction, and the result is handed back to the caller
# verbatim; nothing here executes tools or acts on text found inside a document.
# Callers piping this into a tool-calling agent must treat it as data, not
# instructions.
import base64, glob, re, subprocess, tempfile
import concurrent.futures as _futures
from fastapi import UploadFile, File, Form

VLLM = os.environ.get("TIM_VLLM_URL", "http://127.0.0.1:8000").rstrip("/")
VLLM_MODEL = os.environ.get("TIM_VLLM_MODEL", "tim-qwen")
OCR_MAX_BYTES = 80 * 1024 * 1024
OCR_HARD_PAGE_CAP = 200

TRANSCRIBE = (
    "Transcribe every piece of text in this page image into clean "
    "GitHub-flavoured Markdown.\n"
    "Rules:\n"
    "- Output raw Markdown only. Never wrap your whole answer in a code fence.\n"
    "- Never use LaTeX. Any table must be a Markdown pipe table with a proper "
    "header row and one row per printed row.\n"
    "- Include ALL text wherever it sits on the page, not just the main body: "
    "stamps, rotated or diagonal text, handwriting, margin notes, headers, "
    "footers, and anything overlaid on top of other content. Render a stamp or "
    "overlay as its own line like [STAMP: PAID 08/02/26]. Missing a stamp "
    "changes the meaning of a document, so look for one before you finish.\n"
    "- Keep headings, labels, dates and amounts exactly as printed. Never "
    "round, reformat, re-order or correct a number, and preserve minus signs.\n"
    "- Do not summarise, explain, add commentary, or emit coordinate "
    "annotations.\n"
    "- Mark any region you genuinely cannot read as [illegible].\n"
)


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n?\s*```\s*$", re.S)


def _strip_fence(text: str) -> str:
    """Models wrap transcriptions in a fence inconsistently -- some pages yes,
    some no. Unwrap only when the fence encloses the WHOLE reply, so genuine
    fenced code inside a document survives."""
    m = _FENCE_RE.match(text or "")
    return m.group(1) if m else text


def _vllm_chat(content, max_tokens: int) -> dict:
    """One call to the vLLM chat endpoint. `content` is an OpenAI content list."""
    body = {
        "model": VLLM_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0,
        # Qwen3.6 is served without a reasoning parser, so thinking would leak
        # into `content` as prose. See the vLLM runbook.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        VLLM + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"vllm error {e.code}: {e.read().decode()[:300]}")
    except Exception as e:
        raise HTTPException(502, f"vllm unreachable: {type(e).__name__}: {e}")
    return {
        "text": _strip_fence(d["choices"][0]["message"]["content"]),
        "completion_tokens": d.get("usage", {}).get("completion_tokens"),
    }


def _vision_content(jpeg: bytes, instruction: str):
    b64 = base64.b64encode(jpeg).decode()
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": instruction},
    ]


def _pdf_to_jpegs(pdf: bytes, dpi: int, max_pages: int) -> list:
    """Rasterise with poppler. Image-only (scanned) PDFs are the whole point,
    so never try to pull a text layer -- there usually isn't one."""
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(pdf)
        cmd = [
            "pdftoppm", "-jpeg", "-jpegopt", "quality=88",
            "-r", str(dpi), "-f", "1", "-l", str(max_pages),
            src, os.path.join(td, "pg"),
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=900)
        if res.returncode != 0:
            raise HTTPException(400, f"pdftoppm failed: {res.stderr.decode()[:300]}")
        files = glob.glob(os.path.join(td, "pg-*.jpg"))
        if not files:
            raise HTTPException(400, "pdftoppm produced no pages (is this a PDF?)")
        # pdftoppm zero-pads according to total page count, so sort on the
        # integer rather than lexicographically.
        def _pageno(p):
            m = re.search(r"pg-(\d+)\.jpg$", p)
            return int(m.group(1)) if m else 0
        return [open(f, "rb").read() for f in sorted(files, key=_pageno)]


def _ocr_pages(pages: list, concurrency: int, max_tokens: int) -> list:
    """Transcribe every page. Concurrent, order preserved."""
    out = [None] * len(pages)

    def one(i):
        return i, _vllm_chat(_vision_content(pages[i], TRANSCRIBE), max_tokens)

    workers = max(1, min(concurrency, len(pages), 32))
    with _futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in _futures.as_completed([ex.submit(one, i) for i in range(len(pages))]):
            i, r = fut.result()
            out[i] = r
    return out


def _extract(merged: str, fields: str, max_tokens: int) -> str:
    """Second pass: turn the transcription into JSON. Done once over the whole
    document rather than per page, so values spanning pages resolve correctly."""
    want = fields.strip() or "every field that appears to be a labelled value"
    instruction = (
        "Below is the full text of a document, transcribed from images.\n"
        f"Extract the following and return ONLY minified JSON, no markdown "
        f"fence and no commentary: {want}\n"
        "Use null for anything genuinely absent. Never invent a value.\n"
        "Keep numbers as numbers, preserving sign.\n\n"
        "--- DOCUMENT TEXT ---\n" + merged
    )
    return _vllm_chat([{"type": "text", "text": instruction}], max_tokens)["text"]


class OcrReq(BaseModel):
    pdf_b64: str | None = None
    image_b64: str | None = None
    url: str | None = None
    mode: str = "markdown"        # markdown | extract
    fields: str | None = None     # extract mode: what to pull out
    dpi: int = 200
    max_pages: int = 40
    concurrency: int = 8
    max_tokens: int = 2048


def _load_source(r: OcrReq) -> tuple:
    """Returns (kind, bytes) where kind is 'pdf' or 'image'."""
    given = [k for k in ("pdf_b64", "image_b64", "url") if getattr(r, k)]
    if len(given) != 1:
        raise HTTPException(400, "supply exactly one of pdf_b64, image_b64, url")
    if r.pdf_b64:
        return "pdf", base64.b64decode(r.pdf_b64)
    if r.image_b64:
        return "image", base64.b64decode(r.image_b64)
    if not r.url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must be http(s)")
    with urllib.request.urlopen(r.url, timeout=120) as resp:
        data = resp.read(OCR_MAX_BYTES + 1)
        ctype = (resp.headers.get("Content-Type") or "").lower()
    if len(data) > OCR_MAX_BYTES:
        raise HTTPException(413, "download exceeds size limit")
    kind = "pdf" if ("pdf" in ctype or data[:5] == b"%PDF-") else "image"
    return kind, data


def _run_ocr(r: OcrReq) -> dict:
    if r.mode not in ("markdown", "extract"):
        raise HTTPException(400, "mode must be markdown or extract")
    if r.mode == "extract" and not (r.fields or "").strip():
        raise HTTPException(400, "extract mode requires `fields`")
    if not 50 <= r.dpi <= 400:
        raise HTTPException(400, "dpi must be 50-400")
    max_pages = max(1, min(r.max_pages, OCR_HARD_PAGE_CAP))

    kind, data = _load_source(r)
    if len(data) > OCR_MAX_BYTES:
        raise HTTPException(413, "input exceeds size limit")

    t0 = time.time()
    if kind == "pdf":
        pages = _pdf_to_jpegs(data, r.dpi, max_pages)
    else:
        pages = [data]
    raster_s = time.time() - t0

    t1 = time.time()
    results = _ocr_pages(pages, r.concurrency, r.max_tokens)
    ocr_s = time.time() - t1

    merged = "\n\n".join(
        f"<!-- page {i + 1} -->\n{res['text']}" for i, res in enumerate(results)
    )
    payload = {
        "pages": [
            {"page": i + 1, "text": res["text"], "completion_tokens": res["completion_tokens"]}
            for i, res in enumerate(results)
        ],
        "merged": merged,
        "page_count": len(pages),
        "model": VLLM_MODEL,
        "timing": {
            "rasterize_s": round(raster_s, 2),
            "ocr_s": round(ocr_s, 2),
            "total_s": round(time.time() - t0, 2),
        },
    }

    if r.mode == "extract":
        t2 = time.time()
        raw = _extract(merged, r.fields, r.max_tokens)
        payload["timing"]["extract_s"] = round(time.time() - t2, 2)
        payload["timing"]["total_s"] = round(time.time() - t0, 2)
        payload["extracted_raw"] = raw
        # The model is asked for bare JSON, but be forgiving about a fence.
        cleaned = re.sub(r"^\s*```(?:json)?|```\s*$", "", raw.strip())
        try:
            payload["extracted"] = json.loads(cleaned)
        except Exception:
            payload["extracted"] = None
            payload["extract_parse_error"] = "model did not return valid JSON; see extracted_raw"
    return payload


@app.post("/ocr")
def ocr(r: OcrReq):
    return _run_ocr(r)


@app.post("/ocr/file")
async def ocr_file(
    file: UploadFile = File(...),
    mode: str = Form("markdown"),
    fields: str = Form(""),
    dpi: int = Form(200),
    max_pages: int = Form(40),
    concurrency: int = Form(8),
    max_tokens: int = Form(2048),
):
    """Multipart variant, so `curl -F file=@lease.pdf` works and n8n can post a
    binary straight through without base64ing it first."""
    data = await file.read()
    if len(data) > OCR_MAX_BYTES:
        raise HTTPException(413, "input exceeds size limit")
    is_pdf = data[:5] == b"%PDF-" or (file.filename or "").lower().endswith(".pdf")
    req = OcrReq(
        pdf_b64=base64.b64encode(data).decode() if is_pdf else None,
        image_b64=None if is_pdf else base64.b64encode(data).decode(),
        mode=mode, fields=fields or None, dpi=dpi, max_pages=max_pages,
        concurrency=concurrency, max_tokens=max_tokens,
    )
    return _run_ocr(req)

@app.get("/health")
def health():
    try:
        _get("/system_stats"); comfy = True
    except Exception:
        comfy = False
    return {"ok": True, "comfy": comfy}
