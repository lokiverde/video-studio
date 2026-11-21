"""Archive reel: sound. Every effect is synthesized (numpy), so nothing is sampled, licensed or AI.

job.json "audio":
  {"mode": "drums"}                                    built war drums + low drone (Tony's pick, the first test)
  {"mode": "record", "file": "danse_macabre_1925_side2.flac", "start": 88.54, "speed": 1.21,
   "booms": true}                                      a public-domain 78 from archive/music, sped to the grid
  optional "variants": [ {...}, {...} ]                extra versions to compare, same picture
Always under it: projector clatter, shellac crackle, crowd/fire from shot `sfx` tags, whoosh into reveals.
Records must be US public domain: released before 1926 as of 2026 (100-year rule for 1923 to 1946).
"""
import subprocess

import numpy as np

import ar_film
import ar_lib

SR = 48000
MUSIC = ar_film.ARCHIVE / "music"


class Synth:
    def __init__(self, total, seed=1924):
        self.dur, self.n, self.rng = total, int(total * SR), np.random.default_rng(seed)

    def secs(self, s):
        return np.arange(int(s * SR)) / SR

    def band(self, x, lo=None, hi=None):
        spec, freqs = np.fft.rfft(x), np.fft.rfftfreq(len(x), 1 / SR)
        if lo:
            spec[freqs < lo] = 0
        if hi:
            spec[freqs > hi] = 0
        return np.fft.irfft(spec, len(x))

    def place(self, track, clip, at, gain=1.0):
        start = max(0, int(at * SR))
        end = min(len(track), start + len(clip))
        if start < len(track):
            track[start:end] += clip[: end - start] * gain

    def reverb(self, x, tail, mix):
        ir = self.rng.standard_normal(int(tail * SR)) * np.exp(-self.secs(tail) * 5)
        size = len(x) + len(ir)
        wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size))[: len(x)]
        return x * (1 - mix) + wet / (np.abs(wet).max() + 1e-9) * mix * np.abs(x).max()

    def drum(self, low, high, decay, length, skin_decay, tail, mix):
        t = self.secs(length)
        body = np.sin(2 * np.pi * np.cumsum(low + (high - low) * np.exp(-t * (12 if length > 1.5 else 18))) / SR)
        skin = self.band(self.rng.standard_normal(len(t)), 60, 1500) * np.exp(-t * skin_decay) * 0.55
        return norm(self.reverb(body * np.exp(-t * decay) + skin, tail, mix))

    def kit(self):
        return {"big": self.drum(38, 120, 2.4, 2.2, 70, 1.8, 0.35),
                "low": self.drum(52, 122, 6, 0.9, 35, 1.0, 0.25),
                "high": self.drum(68, 138, 6, 0.9, 35, 1.0, 0.25)}

    def projector(self):
        out = np.zeros(self.n)
        click = self.band(self.rng.standard_normal(int(0.004 * SR)), 900, 5000) * np.exp(-self.secs(0.004) * 900)
        for k in range(int(self.dur * 24)):  # shutter at 24 fps, sprocket accent every other frame
            self.place(out, click, k / 24 + self.rng.normal(0, 0.0015),
                       (1.0 if k % 2 else 0.55) * self.rng.uniform(0.7, 1.0))
        t = self.secs(self.dur)
        motor = 0.25 * np.sin(2 * np.pi * 50 * t) + 0.12 * np.sin(2 * np.pi * 100 * t)
        whir = self.band(self.rng.standard_normal(self.n), 200, 900) * 0.4
        return (out + motor + whir) * (1 + 0.15 * np.sin(2 * np.pi * 0.35 * t))

    def crackle(self):
        out = np.zeros(self.n)
        pop = np.exp(-self.secs(0.002) * 2500)
        for rate, amp in ((14, 0.5), (1.2, 1.0)):
            for at in self.rng.uniform(0, self.dur, int(rate * self.dur)):
                self.place(out, pop * self.rng.choice((-1, 1)), at, amp * self.rng.uniform(0.3, 1))
        return self.band(out, 700) + self.band(self.rng.standard_normal(self.n), 3000, 9000) * 0.05

    def roar(self, length):
        t = self.secs(length)
        shape = np.sin(np.pi * t / length) ** 0.6 * (1 + 0.3 * np.sin(2 * np.pi * 3.1 * t) * np.sin(2 * np.pi * 0.7 * t))
        return self.band(self.rng.standard_normal(len(t)), 250, 1400) * shape

    def fire(self, length):
        t = self.secs(length)
        snaps = np.zeros(len(t))
        for at in self.rng.uniform(0, length, int(35 * length)):
            self.place(snaps, np.exp(-self.secs(0.006) * 600), at, self.rng.uniform(0.2, 1))
        return self.band(self.rng.standard_normal(len(t)), 60, 300) * 0.6 + self.band(snaps, 1500, 7000) * 2

    def whoosh(self, length):
        t = self.secs(length)
        out, y = np.zeros(len(t)), 0.0
        for i, s in enumerate(self.rng.standard_normal(len(t))):  # lowpass sweeping up then down
            y += (0.02 + 0.25 * np.sin(np.pi * i / len(t)) ** 2) * (s - y)
            out[i] = y
        return out * np.sin(np.pi * t / length) ** 2

    def drone(self, end_at):
        t = self.secs(self.dur)
        swell = np.clip(t / end_at, 0, 1) ** 1.5 * np.where(t > end_at, np.exp(-(t - end_at) * 0.8), 1)
        tone = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in ((55, 1, 0), (82.4, 0.5, 1), (110.3, 0.3, 2)))
        return tone * (0.4 + 0.6 * swell) * (1 + 0.1 * np.sin(2 * np.pi * 0.25 * t))


def norm(x, peak=1.0):
    return x / (np.abs(x).max() + 1e-9) * peak


def rms_to(x, db):
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * 10 ** (db / 20)


def sfx_bed(syn, job, roar_db=-30, fire_db=-31):
    bed = rms_to(syn.projector(), -30) + rms_to(syn.crackle(), -33)
    for kind, start, end in ar_lib.sfx_cues(job):
        clip = {"roar": syn.roar, "fire": syn.fire, "whoosh": syn.whoosh}[kind](end - start)
        syn.place(bed, rms_to(clip, {"roar": roar_db, "fire": fire_db, "whoosh": -22}[kind]), start)
    return bed


def drums(syn, job):
    track, kit = np.zeros(syn.n), syn.kit()
    for at, kind, gain in ar_lib.drum_hits(job):
        syn.place(track, kit[kind], at, gain)
    _, total = ar_lib.timeline(job)
    return track + norm(syn.drone(total - job["end"]["seconds"]), 0.12)


def record(syn, spec):
    speed = spec.get("speed", 1.0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{spec['start']}", "-t", f"{syn.dur * speed + 1}",
                          "-i", str(MUSIC / spec["file"]), "-af", f"atempo={speed}", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).astype(float)[: syn.n]
    return np.pad(x, (0, syn.n - len(x)))


def mix(job, spec):
    _, total = ar_lib.timeline(job)
    syn = Synth(total)
    if spec.get("mode", "drums") == "drums":
        out = rms_to(drums(syn, job), -15) + sfx_bed(syn, job, roar_db=-27, fire_db=-30) * 0.8
    else:
        out = rms_to(record(syn, spec), -16) + sfx_bed(syn, job)
        if spec.get("booms"):
            booms = np.zeros(syn.n)
            for at, kind, _ in ar_lib.drum_hits(job):
                if kind == "big":
                    syn.place(booms, syn.kit()["big"], at, 0.7)
            out += booms * 10 ** (-6 / 20)
    env = np.ones(syn.n)
    env[-int(0.8 * SR):] = np.linspace(1, 0, int(0.8 * SR))
    env[: int(0.01 * SR)] = np.linspace(0, 1, int(0.01 * SR))
    return norm(np.tanh(out * env * 1.2) / np.tanh(1.2), 0.89)


def mux(jdir, audio, name):
    wav = jdir / "work" / f"{name}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", str(wav)],
                   input=audio.astype(np.float32).tobytes(), check=True)
    video = jdir / "out" / f"{name}.mp4"
    ar_film.run(["ffmpeg", "-v", "error", "-y", "-i", jdir / "out" / "master_silent.mp4", "-i", wav,
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                 "-shortest", "-movflags", "+faststart", video])
    return video


def score_all(jdir, job):
    """The chosen soundtrack as out/final.mp4, each variant as out/final_<n>.mp4."""
    spec = job.get("audio") or {"mode": "drums"}
    made = [mux(jdir, mix(job, spec), "final")]
    for k, variant in enumerate(spec.get("variants", []), 1):
        made.append(mux(jdir, mix(job, variant), f"final_{variant.get('name', k)}"))
    return made
