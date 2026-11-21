"""The no-spend dry run, end to end (docs/briefs/2026-10-24-realistic-footage.md, 5.7 and
Appendix A): rf new on the fox idea, the Appendix prompts lint clean and pack, a locally
made still and clip ingest as if the engine returned them, and a faceless job with one clip
scene renders both cuts behind the preview gate with the disclosure line and no on-screen
tag (YouTube Studio's own label does that job).
FLUX and TTS are local stand-ins and every network connection fails the test: no OpenArt."""
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rf_fixtures import FOX, STILL, clip  # noqa: E402

import common  # noqa: E402
import fv  # noqa: E402
import gen_images  # noqa: E402
import rf  # noqa: E402
import tts  # noqa: E402

IDEA = "a fox in a call-center headset tells a man not to reply to a scam email"
NARRATED = (1, 2, 3)


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def refuse(*_a, **_k):
    raise AssertionError("the dry run tried to use the network")


def fake_flux(cfg, _theme, _scene, out_path, seed=None, figure=None):
    """Stands in for FLUX on Tim: a flat white still at the size asked for."""
    ff("-f", "lavfi", "-i", f"color=c=white:s={cfg['IMG_W']}x{cfg['IMG_H']}", "-frames:v", "1",
       str(out_path))
    return {"seed": seed or 1, "model": "flux", "gen_s": 0.0}


def fake_tts(job_id, _voice=None, _engine="tim"):
    """Stands in for Tim's TTS: one second of tone per narrated scene."""
    for i in NARRATED:
        ff("-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-ar", "44100",
           str(common.job_dir(job_id) / "work" / f"scene_{i:02d}.wav"))


def fv_run(mp, *args):
    mp.setattr(sys, "argv", ["fv.py", *args])
    fv.main()


def job_named(root, word):
    (jdir,) = [p for p in root.iterdir() if p.is_dir() and p.name.endswith(f"-{word}")]
    return jdir


def write_prompts(rf_dir):
    """What Claude does between rf new and rf lint: the Appendix A prompts go in."""
    data = json.loads((rf_dir / "shots.json").read_text())
    s01, s02 = data["shots"]
    fox = clip()
    shots = [{**s01, "mode": "text2image", "prompt": STILL},
             {**s02, "prompt": FOX, "refs": fox["refs"], "dialogue": fox["dialogue"]}]
    (rf_dir / "shots.json").write_text(json.dumps({**data, "shots": shots}, indent=2))


def engine_returns(rf_dir):
    """A still and an 8 second 9:16 clip with sound, saved where the engine saves them."""
    incoming = rf_dir / "incoming"
    incoming.mkdir()
    ff("-f", "lavfi", "-i", "color=c=orange:s=576x1024", "-frames:v", "1", str(incoming / "S01.png"))
    ff("-f", "lavfi", "-i", "color=c=orange:s=270x480:d=8:r=24",
       "-f", "lavfi", "-i", "sine=frequency=440:duration=8:sample_rate=44100",
       "-shortest", "-pix_fmt", "yuv420p", str(incoming / "S02.mp4"))
    return incoming / "S01.png", incoming / "S02.mp4"


def scenes_file(path, clip_file):
    path.write_text(json.dumps({
        "title": "Never reply to a scam email", "theme": "sketch",
        "youtube": {"title": "Never reply to a scam email",
                    "description": "Why you never reply to a scam email.", "tags": ["scam email"]},
        "scenes": [
            {"id": 1, "caption": "The scam email", "narration": "An email says you won.",
             "image_prompt": "a laptop on a desk at night"},
            {"id": 2, "caption": "Never reply to a scam", "narration": "That fox is right.",
             "clip": str(clip_file)},
            {"id": 3, "caption": "Delete and block", "narration": "Delete it and move on.",
             "image_prompt": "a hand over a laptop keyboard"},
        ]}))
    return path


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    """The whole dry run, once. Returns what the tests below read."""
    root = tmp_path_factory.mktemp("jobs")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", refuse)
        mp.setattr(socket, "create_connection", refuse)
        mp.setattr(common, "JOBS_DIR", root)
        mp.setattr(common, "load_config", lambda: dict(common.DEFAULTS))   # no CDN keys
        mp.setattr(gen_images, "gen_one", fake_flux)
        mp.setattr(tts, "run", fake_tts)

        rf.main(["new", "fox", "--idea", IDEA, "--style", "phone-snapshot", "--technique", "whip-pan"])
        rf_dir = job_named(root, "fox") / "rf"
        write_prompts(rf_dir)
        rf.main(["lint", rf_dir.parent.name])
        rf.main(["pack", rf_dir.parent.name])
        still_file, clip_file = engine_returns(rf_dir)
        rf.main(["ingest", rf_dir.parent.name, str(still_file), "--shot", "S01",
                 "--model", "nano-banana-pro", "--creation", "dryrun-S01", "--credits", "0"])
        rf.main(["ingest", rf_dir.parent.name, str(clip_file), "--shot", "S02",
                 "--model", "byte-plus-seedance-2-5-draft", "--creation", "dryrun-S02", "--credits", "0"])

        returned = rf_dir / "returns" / "S02_take1.mp4"
        fv_run(mp, "make", "--scenes-file", str(scenes_file(root / "scenes.json", returned)),
               "--word", "scam")
        job = job_named(root, "scam")
        with pytest.raises(SystemExit) as blocked:
            fv_run(mp, "finish", job.name)
        fv_run(mp, "approve", job.name)
        fv_run(mp, "finish", job.name)
        yield {"rf": rf_dir, "job": job, "blocked": blocked.value.code}


def shots(rf_dir):
    return {s["id"]: s for s in json.loads((rf_dir / "shots.json").read_text())["shots"]}


def test_the_appendix_prompts_lint_clean_and_pack(dry_run):
    pack = (dry_run["rf"] / "pack.md").read_text()
    assert "S01" in pack and "S02" in pack
    assert {s["lint"] for s in shots(dry_run["rf"]).values()} == {"pass"}


def test_the_returned_files_ingest_with_model_creation_and_credits(dry_run):
    lines = [json.loads(line) for line in (dry_run["rf"] / "ledger.jsonl").read_text().splitlines()]
    assert [(e["shot"], e["model"], e["creation_id"], e["credits"]) for e in lines] == [
        ("S01", "nano-banana-pro", "dryrun-S01", 0),
        ("S02", "byte-plus-seedance-2-5-draft", "dryrun-S02", 0)]
    assert {s["status"] for s in shots(dry_run["rf"]).values()} == {"ingested"}


def test_finish_refuses_until_the_job_is_approved(dry_run):
    assert dry_run["blocked"] == 1


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return tuple(int(n) for n in out.stdout.strip().split(","))


def dark_share(path, seconds, w=320, h=120):
    """Share of near-black pixels in the top-left corner at `seconds`. The clip and the
    stills are bright there, so dark pixels could only be the AI-generated tag."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", f"format=rgb24,crop={w}:{h}:0:0", "-f", "rawvideo",
                          "-"], capture_output=True, check=True).stdout
    pixels = [out[i:i + 3] for i in range(0, len(out), 3)]
    return sum(1 for p in pixels if max(p) < 60) / len(pixels)


@pytest.mark.parametrize("final,size", [("final_16x9.mp4", (1920, 1080)), ("final_9x16.mp4", (1080, 1920))])
def test_both_cuts_render_with_no_tag_over_the_clip_scene(dry_run, final, size):
    video = dry_run["job"] / "out" / final
    assert probe(video) == size
    clip_starts = common.get_state(dry_run["job"].name)["scene_durations"][0]
    assert dark_share(video, clip_starts + 0.5) == 0


def test_the_kit_carries_the_disclosure_line(dry_run):
    assert "This video contains AI-generated footage." in (dry_run["job"] / "out" / "youtube.md").read_text()
