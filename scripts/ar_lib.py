"""Archive reel: the pure logic (no ffmpeg, no files), so it can be tested.

A reel is a list of shots cut on a beat grid. Shot kinds:
  footage  real public-domain film (archive/clips, or public/ for a composite)
  card     silent-film intertitle
  clip     generated motion graded to the archive (avoid: reads fake as the subject)
  still    still image with a slow push
Shots may carry a `logo` (printed into the film before the grade), a `tee` (product
cutout, ungraded, fades in), `accent` ("big" or "hit") for the drums, and `damage`.
"""
import numpy as np

KINDS = ("footage", "card", "clip", "still")
DAMAGE_OPACITY = {"footage": 0.35, "card": 0.5, "clip": 0.9, "still": 0.9}
BEAT_TOLERANCE = 0.02  # seconds a shot may drift off the beat grid
SAFE_TOP, SAFE_BOTTOM = 0.12, 0.80  # platform UI: status/tabs above, caption and buttons below


def timeline(job):
    """[(index, shot, start)] and the total length."""
    t, rows = 0.0, []
    for i, shot in enumerate(job["shots"]):
        rows.append((i, shot, t))
        t += shot["dur"]
    return rows, round(t, 3)


def off_beat(job):
    """Shots whose cut does not land on the music's beat grid."""
    beat = (job.get("music") or {}).get("beat")
    if not beat:
        return []
    rows, _ = timeline(job)
    bad = []
    for i, shot, start in rows:
        k = round(start / beat)
        if abs(start - k * beat) > BEAT_TOLERANCE:
            bad.append((i, shot["id"], round(start, 3)))
    return bad


def validate(job, exists=lambda kind, src: True):
    """Every problem with a job, as readable strings. Empty list = good to render."""
    problems = []
    for key in ("title", "shots", "end"):
        if key not in job:
            problems.append(f"job.json is missing `{key}`")
    if problems:
        return problems
    ids = [s.get("id") for s in job["shots"]]
    if len(set(ids)) != len(ids):
        problems.append("shot ids must be unique")
    for i, shot in enumerate(job["shots"]):
        name = shot.get("id", f"#{i}")
        kind = shot.get("kind")
        if kind not in KINDS:
            problems.append(f"{name}: kind must be one of {', '.join(KINDS)}")
            continue
        if not shot.get("dur") or shot["dur"] <= 0:
            problems.append(f"{name}: needs a positive `dur`")
        if kind == "card" and not shot.get("text"):
            problems.append(f"{name}: a card needs `text`")
        if kind != "card" and not shot.get("src"):
            problems.append(f"{name}: needs `src`")
        elif kind != "card" and not exists(kind if shot.get("dir") != "public" else "public", shot["src"]):
            problems.append(f"{name}: source not found: {shot['src']}")
        if not 0 <= shot.get("focus", 0.5) <= 1:
            problems.append(f"{name}: focus must be between 0 and 1")
        if "logo" in shot and kind != "footage":
            problems.append(f"{name}: a logo can only be printed onto footage")
        tee = shot.get("tee")
        if tee and tee.get("at", 0) + tee.get("fade", 0.08) > shot.get("dur", 0):
            problems.append(f"{name}: the tee fade runs past the end of the shot")
        if tee and not SAFE_TOP < tee.get("y", 0.44) < SAFE_BOTTOM:
            problems.append(f"{name}: the tee centre sits under the platform UI")
        if shot.get("accent") not in (None, "big", "hit"):
            problems.append(f"{name}: accent must be big or hit")
    _, total = timeline(job)
    if job["end"].get("seconds", 0) > job["shots"][-1]["dur"] + 1e-6:
        problems.append("the end card runs longer than the last shot")
    if total > 60:
        problems.append(f"reel is {total:.1f}s, keep it under 60s for Reels/TikTok")
    for i, sid, start in off_beat(job):
        problems.append(f"{sid}: cut at {start}s is off the beat grid")
    return problems


def match_mapping(src_luma, target_luma):
    """Histogram matching: a 256-entry map that gives src the target's tone distribution."""
    src_cdf = np.cumsum(np.bincount(src_luma, minlength=256)) / max(1, src_luma.size)
    tgt_hist = np.bincount(target_luma, minlength=256)
    # Only tones the archive actually uses: a flat CDF above its brightest level would
    # otherwise send the brightest generated pixels to pure white.
    used = np.nonzero(tgt_hist)[0]
    tgt_cdf = np.cumsum(tgt_hist)[used] / max(1, target_luma.size)
    return np.interp(src_cdf, tgt_cdf, used.astype(float))


def cube_1d(mapping):
    rows = "".join(f"{v / 255:.5f} {v / 255:.5f} {v / 255:.5f}\n" for v in mapping)
    return f"LUT_1D_SIZE {len(mapping)}\n{rows}"


def drum_hits(job):
    """War-drum pattern from the story: a big boom on every `big` accent, a tom on every
    other cut, a roll of half-beats into each big accent, a final boom on the end card."""
    beat = (job.get("music") or {}).get("beat", 0.604)
    rows, total = timeline(job)
    end_at = total - job["end"]["seconds"]
    hits = []
    for i, shot, start in rows:
        accent = shot.get("accent")
        if accent == "big":
            for k in range(4, 0, -1):  # roll in
                at = start - k * beat / 2
                if at > 0 and not any(abs(at - h[0]) < 0.05 for h in hits):
                    hits.append((round(at, 3), "high", round(0.7 - 0.08 * k, 2)))
            hits.append((round(start, 3), "big", 1.0))
        elif shot["kind"] != "card" or accent:
            hits.append((round(start, 3), "low" if i % 2 == 0 else "high", 0.7 if accent == "hit" else 0.55))
        for extra in shot.get("hits", []):  # extra hits inside a shot: seconds, or {at, kind}
            at, kind = (extra, "low") if isinstance(extra, (int, float)) else (extra["at"], extra.get("kind", "low"))
            hits.append((round(start + at, 3), kind, 1.0 if kind == "big" else 0.6))
    if not any(abs(h[0] - end_at) < 0.05 for h in hits):
        hits.append((round(end_at, 3), "big", 1.0))
    return sorted(hits)


def sfx_cues(job):
    """Where the sound bed reacts to picture: crowd under horde shots, fire under fire shots,
    and a whoosh into a tee reveal only when the tee sets `whoosh: true` (Tony cut them, 2026-09-23)."""
    rows, total = timeline(job)
    cues = []
    for i, shot, start in rows:
        tags = set(shot.get("sfx", []))
        if "crowd" in tags:
            cues.append(("roar", start, start + shot["dur"]))
        if "fire" in tags:
            cues.append(("fire", start, start + shot["dur"]))
        if (shot.get("tee") or {}).get("whoosh"):
            at = start + shot["tee"].get("at", 0)
            cues.append(("whoosh", max(0.0, at - 0.35), at + 0.35))
    return cues
