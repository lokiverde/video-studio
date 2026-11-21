"""Local Adobe-Enhance-style voice restoration with Resemble Enhance (denoise + generative
enhancer: removes room echo and noise, rebuilds bandwidth). Runs in .venv-enhance.
  enhance_voice.py in.wav out.wav [--mode enhance|denoise] [--lambd 0.9] [--tau 0.5] [--nfe 64]
"""
import argparse, time, warnings
warnings.filterwarnings("ignore")
import soundfile as sf
import torch
from resemble_enhance.enhancer.inference import denoise, enhance

p = argparse.ArgumentParser()
p.add_argument("inp"); p.add_argument("out")
p.add_argument("--mode", default="enhance", choices=["enhance", "denoise"])
p.add_argument("--lambd", type=float, default=0.9, help="denoise strength before enhancing, 0..1")
p.add_argument("--tau", type=float, default=0.5, help="prior temperature, lower = more conservative")
p.add_argument("--nfe", type=int, default=64)
p.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
a = p.parse_args()
data, sr = sf.read(a.inp, dtype="float32", always_2d=True)
wav = torch.from_numpy(data.mean(1))
t = time.time()
try:
    if a.mode == "denoise":
        out, osr = denoise(wav, sr, a.device)
    else:
        out, osr = enhance(wav, sr, a.device, nfe=a.nfe, solver="midpoint", lambd=a.lambd, tau=a.tau)
except (RuntimeError, NotImplementedError) as err:
    if a.device == "cpu":
        raise
    print(f"[enhance_voice] {a.device} failed ({str(err)[:120]}), retrying on cpu")
    a.device = "cpu"
    out, osr = (denoise(wav, sr, "cpu") if a.mode == "denoise" else
                enhance(wav, sr, "cpu", nfe=a.nfe, solver="midpoint", lambd=a.lambd, tau=a.tau))
sf.write(a.out, out.cpu().numpy(), osr)
print(f"[enhance_voice] {a.mode} on {a.device}: {len(wav)/sr:.1f}s audio in {time.time()-t:.1f}s -> {a.out} @ {osr} Hz")
