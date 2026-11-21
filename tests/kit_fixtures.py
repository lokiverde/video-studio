"""Job folders for the publishing-rules tests: a faceless job (scenes.json, stills, state with
scene lengths, a job.json carrying its Shorts) and a talking-head job (job.json + transcript).
No network, no render: a final is an empty file and its length is patched in."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import format_route  # noqa: E402

FOOTER = "Tony Self, Broker, CA DRE 00000001"
BLOG = "https://sitetwo.com/news/springfield-rent-control-hearing-2026"
YOUTUBE = "AbCdEfGhIjK"
FACELESS_ID = "20261022-120000-springfield"
TH_ID = "20261022-130000-riverside"

YOUTUBE_BLOCK = {"title": "Springfield Has No Rent Control. Why Can Tenants Get a Hearing?",
                 "description": "Springfield has no rent cap, but a rent hearing still applies over 5%.",
                 "tags": ["springfield rent control", "springfield landlord"], "hashtags": ["Springfield", "Landlord"]}
SCENES = {
    "title": "Springfield rent hearings",
    "theme": "sketch",
    "youtube": YOUTUBE_BLOCK,
    "scenes": [
        {"id": 1, "image_prompt": "a quiet apartment street", "caption": "No rent control", "narration": "Springfield has no rent control. Tenants still get a hearing."},
        {"id": 2, "image_prompt": "a quiet apartment street", "caption": "The 5% line", "narration": "Raise the rent more than 5% and a tenant can ask for one."},
        {"id": 3, "image_prompt": "a quiet apartment street", "caption": "The notice", "narration": "Your notice has to say so. Most notices miss it."},
        {"id": 4, "image_prompt": "a quiet apartment street", "caption": "The fee", "narration": "There is also a fee per unit. Budget for it."},
    ],
}
DURATIONS = [22.0, 30.0, 25.0, 18.0]          # 95 s on the kit timeline
SHORTS_JOB = {
    "title": "Springfield rent hearings",
    "youtube": YOUTUBE_BLOCK,
    "shorts": [
        {"start": "a", "end": "b", "hook": "SPRINGFIELD 5%", "title": "Raising Rent Over 5% in Springfield? Your Notice Needs This"},
        {"start": "c", "end": "d", "hook": "FEE", "title": "Springfield Landlords: a $3,000 a Unit Fee",
         "description": "The per-unit fee, in one minute."},
    ],
}
LINKEDIN = "---\nvideo: pending\n---\n\nSpringfield has no rent control.\n\nWhat would you do?\n\n#Springfield #Landlord\n"


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(common, "load_config", lambda: {"YOUTUBE_FOOTER": FOOTER})
    return tmp_path


def make_faceless(root, final=True, shorts=True, linkedin=True):
    jdir = root / FACELESS_ID
    (jdir / "work").mkdir(parents=True)
    (jdir / "out").mkdir()
    (jdir / "scenes.json").write_text(json.dumps(SCENES, indent=2))
    for n in range(1, 5):
        (jdir / "work" / f"scene_{n:02d}.png").write_bytes(f"still {n}".encode())
    (jdir / "state.json").write_text(json.dumps({"scene_durations": DURATIONS}))
    if shorts:
        (jdir / "job.json").write_text(json.dumps(SHORTS_JOB, indent=2))
    if linkedin:
        (jdir / "out" / "linkedin.md").write_text(LINKEDIN)
    if final:
        (jdir / "out" / "final_16x9.mp4").write_bytes(b"")
    return jdir


def patch_length(monkeypatch, seconds):
    monkeypatch.setattr(format_route, "probe_seconds", lambda path: seconds)


TH_TEXT = ("Riverside has no rent control. So what still applies? The state cap does. "
           "Number one, the cap is 8.7 percent this year. Number two, just cause after a year. "
           "That is the whole list. Thanks for watching.")


def make_talking_head(root, final=True):
    jdir = root / TH_ID
    (jdir / "public").mkdir(parents=True)
    (jdir / "out").mkdir()
    tokens = TH_TEXT.split()
    words = [{"word": f" {tok}", "start": round(1.0 + i * 0.5, 2), "end": round(1.4 + i * 0.5, 2)}
             for i, tok in enumerate(tokens)]
    (jdir / "transcript.json").write_text(json.dumps({"segments": [{"words": words}]}))
    job = {"title": "Riverside rent rules", "source": "footage.mp4", "srcEnd": words[-1]["end"] + 1.0,
           "cuts": [], "sections": [],
           "youtube": {"title": "No Rent Control in Riverside? Here's What Still Applies",
                       "description": "What Riverside landlords still follow.", "tags": ["riverside rent control"],
                       "takeaways": ["Riverside has no local rent control.", "The state cap is 8.7 percent.",
                                     "Just cause applies after a year."]}}
    (jdir / "job.json").write_text(json.dumps(job, indent=2))
    (jdir / "public" / "broll_1.png").write_bytes(b"still")
    if final:
        (jdir / "out" / "final_16x9.mp4").write_bytes(b"")
    return jdir
