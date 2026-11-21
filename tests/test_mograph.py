"""Motion graphic scenes: a scene whose picture is an animated graphic (stat compare,
kinetic punch line, animated list) rendered by the Remotion template in talking-head/,
then played through the same path as a clip scene. docs/mograph.md.

The unit tests fake the Remotion call. The render tests at the bottom run the real
template and are skipped where talking-head/node_modules is missing."""
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assemble  # noqa: E402
import common  # noqa: E402
import gen_images  # noqa: E402
import mograph  # noqa: E402
import publish_kit  # noqa: E402

COMPARE = {"kind": "compare", "title": "Median price",
           "items": [{"label": "Redondo Beach", "value": 1.45},
                     {"label": "Torrance", "value": 1.02}],
           "prefix": "$", "suffix": "M", "decimals": 2}
PUNCH = {"kind": "punch", "text": "Rent control does not cap your property tax", "em": ["property", "tax"]}
LIST = {"kind": "list", "title": "Three things to check",
        "items": ["The CC&Rs", {"text": "The reserve study", "sub": "fully funded?"}, "Pending litigation"]}


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_narration(path, dur):
    ff("-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}", "-ar", "44100", str(path))


def make_render(path, w, h, dur, color="green", fps=30):
    """Stands in for a Remotion render: a silent mp4 at the cut's native size."""
    ff("-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d={dur}:r={fps}", "-pix_fmt", "yuv420p", str(path))
    return path


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height:format=duration", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    return video["width"], video["height"], float(info["format"]["duration"])


def pixel(path, seconds, x, y):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", f"format=rgb24,crop=2:2:{x}:{y}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(out.stdout[:3])


def write_job(root, job_id, scenes, theme="sketch", **extra):
    jdir = root / job_id
    (jdir / "work").mkdir(parents=True)
    (jdir / "out").mkdir()
    (jdir / "scenes.json").write_text(json.dumps({"theme": theme, "scenes": scenes, **extra}))
    return jdir


def scenes_with(first):
    rest = [{"id": i, "narration": "x", "caption": "c", "image_prompt": "a room"} for i in (2, 3)]
    return {"scenes": [{"id": 1, "narration": "x", "caption": "c", **first}, *rest]}


def rejected(data, capsys):
    with pytest.raises(SystemExit):
        common.validate_scenes(data)
    return capsys.readouterr().err


# ---- validation ----------------------------------------------------------------------

@pytest.mark.parametrize("spec", [COMPARE, PUNCH, LIST])
def test_each_kind_passes_validation(spec):
    common.validate_scenes(scenes_with({"mograph": spec}))


@pytest.mark.parametrize("other", [
    {"clip": "rf/returns/S02.mp4"},
    {"photo": "shop.jpg"},
    {"figure": {"pose": "wave"}},
    {"motion": {}},
    {"shots": ["a room", "a street"]},
    {"image_prompt": "a room"},
    {"card": 3},
    {"graphic": {"kind": "stamp"}},
    {"hold": True},
    {"tag": "OCT 24"},
    {"note": "fake"},
])
def test_a_mograph_scene_stands_alone(other, capsys):
    err = rejected(scenes_with({"mograph": PUNCH, **other}), capsys)
    assert "'mograph'" in err and f"'{next(iter(other))}'" in err


@pytest.mark.parametrize("spec, words", [
    ({"kind": "chart"}, "compare, punch or list"),
    ("punch", "must be an object"),
    ({"kind": "compare", "items": [{"label": "Only one", "value": 3}]}, "2 to 5"),
    ({"kind": "compare", "items": [{"label": "A", "value": "3"}, {"label": "B", "value": 4}]}, "number"),
    ({"kind": "compare", "items": [{"label": "A", "value": True}, {"label": "B", "value": 4}]}, "number"),
    ({"kind": "compare", "items": [{"label": "A", "value": 0}, {"label": "B", "value": 0}]}, "above zero"),
    ({"kind": "compare", "items": [{"label": "", "value": 1}, {"label": "B", "value": 4}]}, "label"),
    ({**COMPARE, "highlight": 2}, "highlight"),
    ({**COMPARE, "decimals": 5}, "decimals"),
    ({"kind": "punch", "text": ""}, "text"),
    ({"kind": "punch", "text": " ".join(["word"] * 15)}, "14 words"),
    ({"kind": "punch", "text": "Short line", "em": ["missing"]}, "em"),
    ({"kind": "list", "items": ["Only one"]}, "2 to 6"),
    ({"kind": "list", "items": ["Fine", {"sub": "no text"}]}, "text"),
    ({"kind": "list", "items": ["Fine", "x" * 60]}, "52"),
    ({**PUNCH, "colors": {"accent": "orange"}}, "hex"),
    ({**PUNCH, "colors": {"glow": "#ffffff"}}, "glow"),
    ({"kind": "compare", "items": [{"label": "A", "value": float("nan")}, {"label": "B", "value": 4}]}, "number"),
    ({"kind": "compare", "items": [{"label": "A", "value": float("inf")}, {"label": "B", "value": 4}]}, "number"),
])
def test_bad_specs_stop_with_a_clear_message(spec, words, capsys):
    err = rejected(scenes_with({"mograph": spec}), capsys)
    assert "scene 1" in err and words in err


def test_a_silent_mograph_scene_runs_for_its_duration(capsys):
    common.validate_scenes(scenes_with({"narration": "", "duration": 3.0, "mograph": PUNCH}))


# ---- colors ---------------------------------------------------------------------------

def test_default_palette_is_brokerage_navy():
    assert mograph.palette({}, PUNCH) == mograph.DEFAULT_PALETTE
    assert mograph.DEFAULT_PALETTE["bg"] == "#1d3557"


def test_a_theme_army_style_colors_the_graphics():
    theme = common.load_theme("army")
    assert mograph.palette(theme, PUNCH)["accent"] == theme["army_style"]["accent"]


def test_mograph_style_beats_army_style_and_scene_colors_beat_both():
    theme = {"army_style": {"accent": "#111111"}, "mograph_style": {"accent": "#222222", "bg": "#333333"}}
    assert mograph.palette(theme, PUNCH)["accent"] == "#222222"
    got = mograph.palette(theme, {**PUNCH, "colors": {"accent": "#444444"}})
    assert got["accent"] == "#444444" and got["bg"] == "#333333"
    assert got["text"] == mograph.DEFAULT_PALETTE["text"]


# ---- timing ---------------------------------------------------------------------------

def test_items_land_when_the_narration_names_them():
    narration = ("First the CC&Rs then wait for it the reserve study and last of all "
                 "any pending litigation against the association")
    times = mograph.reveal_times(["The CC&Rs", "The reserve study", "Pending litigation"],
                                 narration, speech_s=9.0, scene_s=9.35)
    words = narration.split()
    expect = [9.0 * words.index(w) / len(words) for w in ("CC&Rs", "reserve", "pending")]
    for got, want in zip(times, expect):
        assert abs(got - (want - mograph.CUE_LEAD)) < 0.05


def test_items_not_named_spread_evenly_and_never_go_backwards():
    times = mograph.reveal_times(["Alpha", "Beta", "Gamma", "Delta"], "nothing matches here at all",
                                 speech_s=8.0, scene_s=8.35)
    assert times == sorted(times)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert max(gaps) - min(gaps) < 0.01
    assert times[0] >= mograph.FIRST_REVEAL and times[-1] <= 8.0 * mograph.SPREAD_END + 0.01


def test_items_named_out_of_order_still_land_in_order_with_a_gap():
    times = mograph.reveal_times(["Beta", "Alpha"], "alpha comes first then beta much later",
                                 speech_s=6.0, scene_s=6.35)
    assert times[1] - times[0] >= mograph.MIN_GAP - 1e-9


def test_every_item_lands_before_the_scene_ends():
    times = mograph.reveal_times(["one", "two", "three"], "one two three",
                                 speech_s=2.5, scene_s=2.85)
    assert times[-1] <= 2.85 - mograph.SETTLE and times == sorted(times)


def test_a_scene_too_short_to_settle_lands_everything_early_and_in_order():
    times = mograph.reveal_times(["one", "two", "three"], "one two three",
                                 speech_s=1.0, scene_s=1.35)
    assert times == sorted(times) and times[-1] <= mograph.MIN_START


def test_props_carry_frames_palette_cut_and_item_times():
    scene = {"id": 4, "narration": "Redondo Beach sits at the top and Torrance below",
             "caption": "c", "mograph": COMPARE}
    props = mograph.props(scene, {}, speech_s=3.0, scene_s=3.35, fps=30, portrait=True)
    assert props["kind"] == "compare" and props["portrait"] is True
    assert props["fps"] == 30 and props["frames"] == 101           # ceil(3.35 * 30)
    assert props["palette"] == mograph.DEFAULT_PALETTE
    assert [item["label"] for item in props["items"]] == ["Redondo Beach", "Torrance"]
    assert all(isinstance(item["at"], float) for item in props["items"])
    assert props["items"][0]["at"] < props["items"][1]["at"]


def test_list_items_given_as_strings_become_objects():
    scene = {"id": 1, "narration": "x", "caption": "c", "mograph": LIST}
    props = mograph.props(scene, {}, speech_s=4.0, scene_s=4.35, fps=30, portrait=False)
    assert props["items"][0]["text"] == "The CC&Rs"
    assert props["items"][1]["sub"] == "fully funded?"
    assert props["numbered"] is True


def test_scene_seconds_follow_the_narration_or_the_duration(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    make_narration(work / "scene_02.wav", 2.0)
    speech, whole = mograph.scene_seconds(work, {"id": 2, "narration": "hi"})
    assert abs(speech - 2.0) < 0.05 and abs(whole - (2.0 + assemble.PAD)) < 0.05
    assert mograph.scene_seconds(work, {"id": 3, "narration": "", "duration": 4.0}) == (0.0, 4.0)
    assert mograph.scene_seconds(work, {"id": 3, "narration": ""}) == (0.0, assemble.SILENT_SCENE_DUR)


# ---- rendering (Remotion faked) -------------------------------------------------------

@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def fake_remotion(monkeypatch):
    """Records every Remotion call and writes a stand-in output of the right size."""
    calls = []

    def fake(cmd, props, out, frame=None):
        calls.append({"cmd": cmd, "props": props, "out": Path(out), "frame": frame})
        w, h = (1080, 1920) if props["portrait"] else (1920, 1080)
        if cmd == "still":
            from PIL import Image
            Image.new("RGB", (w, h), props["palette"]["bg"]).save(out)
        else:
            make_render(out, w, h, props["frames"] / props["fps"])
    monkeypatch.setattr(mograph, "remotion", fake)
    return calls


def mograph_job(jobs, theme="sketch"):
    scenes = [{"id": 1, "narration": "Rent control does not cap your property tax", "caption": "",
               "mograph": PUNCH},
              {"id": 2, "narration": "x", "caption": "c", "image_prompt": "a room"},
              {"id": 3, "narration": "", "duration": 2.0, "caption": "c", "mograph": LIST}]
    jdir = write_job(jobs, "mg", scenes, theme=theme, end_hold=0)
    make_narration(jdir / "work" / "scene_01.wav", 1.5)
    return jdir


def test_run_renders_both_cuts_of_every_mograph_scene_timed_to_its_narration(jobs, fake_remotion):
    jdir = mograph_job(jobs)
    mograph.run("mg")
    outs = sorted(c["out"].name for c in fake_remotion)
    assert outs == ["mograph_01.mp4", "mograph_03.mp4", "mographv_01.mp4", "mographv_03.mp4"]
    first = next(c for c in fake_remotion if c["out"].name == "mograph_01.mp4")
    assert first["props"]["frames"] == math.ceil((1.5 + assemble.PAD) * 30)
    silent = next(c for c in fake_remotion if c["out"].name == "mograph_03.mp4")
    assert silent["props"]["frames"] == 60
    assert (jdir / "work" / "mograph_01.mp4").exists()


def test_run_skips_a_render_whose_props_have_not_changed(jobs, fake_remotion):
    jdir = mograph_job(jobs)
    mograph.run("mg")
    first = len(fake_remotion)
    mograph.run("mg")
    assert len(fake_remotion) == first
    data = json.loads((jdir / "scenes.json").read_text())
    data["scenes"][0]["mograph"] = {**PUNCH, "text": "Rent control caps rent, not tax"}
    data["scenes"][0]["mograph"].pop("em")
    (jdir / "scenes.json").write_text(json.dumps(data))
    mograph.run("mg")
    assert sorted(c["out"].name for c in fake_remotion[first:]) == ["mograph_01.mp4", "mographv_01.mp4"]


def test_a_portrait_only_theme_renders_only_the_vertical_cut(jobs, fake_remotion):
    mograph_job(jobs, theme="shirt-ad")
    assert common.load_theme("shirt-ad").get("portrait_only")
    mograph.run("mg")
    assert all(c["out"].name.startswith("mographv_") for c in fake_remotion)


@pytest.mark.parametrize("portrait, size, name", [(False, (1280, 720), "scene_01.png"),
                                                  (True, (720, 1280), "p_scene_01.png")])
def test_the_contact_sheet_still_is_the_settled_last_frame_with_a_badge(jobs, fake_remotion, portrait, size, name):
    jdir = mograph_job(jobs)
    scene = json.loads((jdir / "scenes.json").read_text())["scenes"][0]
    out = jdir / "work" / name
    mograph.still(scene, {}, out, *size, portrait=portrait)
    call = fake_remotion[-1]
    assert call["cmd"] == "still" and call["props"]["portrait"] is portrait
    assert call["frame"] == call["props"]["frames"] - 1      # everything has landed
    from PIL import Image
    image = Image.open(out)
    assert image.size == size
    m = round(min(size) * 0.03)                       # clips.draw_badge margin and padding
    assert image.convert("RGB").getpixel((m + 3, 2 * m)) == (15, 15, 15)   # the dark badge


def test_gen_images_puts_mograph_stills_on_both_sheets_without_flux(jobs, fake_remotion, monkeypatch):
    scenes = [{"id": i, "narration": "x", "caption": "c", "mograph": spec}
              for i, spec in ((1, PUNCH), (2, COMPARE), (3, LIST))]
    write_job(jobs, "sheet", scenes)

    def no_generator(*_a, **_k):
        raise AssertionError("a mograph scene must never call the image generator")
    monkeypatch.setattr(common, "http_json", no_generator)
    gen_images.run("sheet")
    gen_images.run_portrait("sheet")
    work = jobs / "sheet" / "work"
    assert [c["props"]["portrait"] for c in fake_remotion if c["cmd"] == "still"] == [False] * 3 + [True] * 3
    for i in (1, 2, 3):
        assert (work / f"scene_{i:02d}.png").exists() and (work / f"p_scene_{i:02d}.png").exists()
    assert (work / "contact_sheet.jpg").exists() and (work / "contact_sheet_9x16.jpg").exists()


# ---- assembly -------------------------------------------------------------------------

@pytest.fixture
def assembled(jobs, fake_remotion):
    jdir = mograph_job(jobs)
    from PIL import Image
    work = jdir / "work"
    Image.new("RGB", (1280, 720), "gray").save(work / "scene_02.png")
    Image.new("RGB", (720, 1280), "gray").save(work / "p_scene_02.png")
    make_narration(work / "scene_02.wav", 1.0)
    mograph.run("mg")
    assemble.run("mg")
    return jdir


def test_assembly_plays_the_renders_at_native_size_in_both_cuts(assembled):
    work = assembled / "work"
    assert probe(work / "clip_01.mp4")[:2] == (1920, 1080)
    assert probe(work / "clipv_01.mp4")[:2] == (1080, 1920)
    assert abs(probe(work / "clip_01.mp4")[2] - (1.5 + assemble.PAD)) < 0.1
    assert abs(probe(work / "clip_03.mp4")[2] - 2.0) < 0.1
    assert pixel(work / "clip_01.mp4", 0.2, 960, 540)[1] > 100      # the green stand-in


def test_a_mograph_scene_gets_no_ai_disclosure(assembled):
    data = json.loads((assembled / "scenes.json").read_text())
    assert publish_kit.ai_disclosure(data, {}) is None


def test_assembly_stops_when_a_render_is_missing(jobs, fake_remotion, capsys):
    jdir = mograph_job(jobs)
    from PIL import Image
    Image.new("RGB", (1280, 720), "gray").save(jdir / "work" / "scene_02.png")
    with pytest.raises(SystemExit):
        assemble.run("mg")
    assert "fv.py mograph mg" in capsys.readouterr().err


# ---- real Remotion renders ------------------------------------------------------------

needs_remotion = pytest.mark.skipif(
    not (ROOT / "talking-head" / "node_modules" / "remotion").exists() or not shutil.which("npx"),
    reason="talking-head/node_modules not installed")


@needs_remotion
@pytest.mark.parametrize("spec", [COMPARE, PUNCH, LIST], ids=["compare", "punch", "list"])
@pytest.mark.parametrize("portrait", [False, True], ids=["16x9", "9x16"])
def test_the_template_draws_each_kind_in_each_cut(tmp_path, spec, portrait):
    from PIL import Image, ImageStat
    scene = {"id": 1, "narration": "Redondo Beach then Torrance the CC&Rs the reserve study "
                                   "pending litigation", "caption": "c", "mograph": spec}
    out = tmp_path / "still.png"
    size = (720, 1280) if portrait else (1280, 720)
    mograph.still(scene, {}, out, *size, portrait=portrait)
    image = Image.open(out).convert("RGB")
    assert image.size == size
    # the settled frame shows text in the text color on the navy canvas: plenty of white
    white = image.convert("L").point(lambda v: 255 if v > 230 else 0).histogram()[255]
    assert white > 0.004 * size[0] * size[1]
    assert ImageStat.Stat(image).stddev[0] > 10


@needs_remotion
def test_the_template_renders_a_video_the_length_of_the_scene(tmp_path):
    scene = {"id": 1, "narration": "", "duration": 1.0, "caption": "c", "mograph": PUNCH}
    props = mograph.props(scene, {}, speech_s=0.0, scene_s=1.0, fps=30, portrait=False)
    out = tmp_path / "punch.mp4"
    mograph.remotion("render", props, out)
    w, h, dur = probe(out)
    assert (w, h) == (1920, 1080) and abs(dur - props["frames"] / 30) < 0.05


# ---- fv.py ----------------------------------------------------------------------------

def test_finish_renders_the_graphics_after_tts_and_before_assembly(jobs, monkeypatch):
    import fv
    write_job(jobs, "order", [{"id": i, "narration": "x", "caption": "c", "mograph": PUNCH} for i in (1, 2, 3)])
    calls = []
    for module, name in ((fv.tts, "tts"), (fv.motion, "motion"), (fv.mograph, "mograph"),
                         (fv.assemble, "assemble"), (fv.thumbnail, "thumbnail"),
                         (fv.publish_kit, "kit"), (fv.upload, "upload")):
        monkeypatch.setattr(module, "run", lambda *a, _n=name, **k: calls.append(_n) or [])
    fv.cmd_finish_impl("order")
    assert calls.index("tts") < calls.index("mograph") < calls.index("assemble")


def test_the_mograph_command_renders_one_scene(monkeypatch):
    import fv
    seen = []
    monkeypatch.setattr(fv.mograph, "run", lambda job, scene=None: seen.append((job, scene)))
    monkeypatch.setattr(sys, "argv", ["fv.py", "mograph", "somejob", "--scene", "4"])
    fv.main()
    assert seen == [("somejob", 4)]


# ---- review fixes ---------------------------------------------------------------------

def test_null_optional_text_reaches_the_template_as_empty_text():
    spec = {**COMPARE, "prefix": None, "suffix": None, "title": None, "source": None, "highlight": None}
    common.validate_scenes(scenes_with({"mograph": spec}))
    props = mograph.props({"id": 1, "narration": "", "mograph": spec}, {}, 0.0, 3.5, 30, False)
    assert (props["prefix"], props["suffix"], props["title"], props["source"]) == ("", "", "", "")
    assert props["highlight"] == 0
    punch = mograph.props({"id": 1, "mograph": {**PUNCH, "kicker": None, "sub": None}}, {}, 0.0, 3.5, 30, False)
    assert (punch["kicker"], punch["sub"]) == ("", "")
    listed = mograph.props({"id": 1, "mograph": {**LIST, "title": None,
                                                 "items": ["A", {"text": "B", "sub": None}]}}, {}, 0.0, 3.5, 30, False)
    assert listed["title"] == "" and listed["items"][1]["sub"] == ""


def test_the_last_item_lands_with_time_for_a_bar_to_finish_growing():
    assert mograph.SETTLE >= 1.0          # Compare.tsx GROW_S: a bar takes 1s to reach its value
    times = mograph.reveal_times(["one", "two"], "", speech_s=0.0, scene_s=3.5)
    assert times[-1] <= 3.5 - 1.0


def test_a_hold_after_a_mograph_scene_reaches_back_to_the_last_generated_background(tmp_path):
    data = {"theme": "sketch", "scenes": [
        {"id": 1, "narration": "x", "caption": "c", "image_prompt": "a room"},
        {"id": 2, "narration": "x", "caption": "", "mograph": PUNCH},
        {"id": 3, "narration": "x", "caption": "c", "shots": [{"hold": True}, "a street"]}]}
    sources = gen_images.hold_sources(data, tmp_path)
    held = gen_images.shot_files(tmp_path, 3, 2)[0]
    assert sources[held] == gen_images.bg_path(gen_images.shot_files(tmp_path, 1, 1)[0])


def test_a_template_change_re_renders_even_when_the_props_did_not_change(jobs, fake_remotion, monkeypatch):
    mograph_job(jobs)
    monkeypatch.setattr(mograph, "template_hash", lambda: "before")
    mograph.run("mg")
    first = len(fake_remotion)
    mograph.run("mg")
    assert len(fake_remotion) == first
    monkeypatch.setattr(mograph, "template_hash", lambda: "after")
    mograph.run("mg")
    assert len(fake_remotion) == 2 * first


def test_template_hash_covers_the_mograph_sources_and_the_font():
    files = [p.name for p in mograph.template_files()]
    assert {"Compare.tsx", "Punch.tsx", "List.tsx", "Root.tsx", "Anton-Regular.ttf"} <= set(files)
    assert len(mograph.template_hash()) == 64


def test_a_captionless_graphic_names_its_chapter_from_its_own_words():
    data = {"scenes": [{"id": 1, "caption": "", "mograph": COMPARE},
                       {"id": 2, "caption": "", "mograph": PUNCH},
                       {"id": 3, "caption": "", "mograph": {**LIST, "title": ""}}]}
    labels = [label for _, label in publish_kit.chapters(data, [20.0, 20.0, 20.0])]
    assert labels == ["Median price", "Rent control does not cap your property tax", "The CC&Rs"]


# ---- which node -------------------------------------------------------------------------

def fake_node(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("node", "npx"):
        (folder / name).write_text("#!/bin/sh\n")
        (folder / name).chmod(0o755)
        if sys.platform.startswith("win"):            # Windows finds npx through its .cmd shim
            (folder / f"{name}.cmd").write_text("@echo off\n")
    return folder


def test_node_dir_in_config_wins_over_path(tmp_path, monkeypatch):
    mine = fake_node(tmp_path / "node26" / "bin")
    fake_node(tmp_path / "other")
    monkeypatch.setenv("PATH", str(tmp_path / "other"))
    assert mograph.node_dir({"NODE_DIR": str(mine)}) == mine


def test_node_dir_falls_back_to_npx_on_path(tmp_path, monkeypatch):
    found = fake_node(tmp_path / "onpath")
    monkeypatch.setenv("PATH", str(found))
    assert mograph.node_dir({}) == found


def test_a_node_dir_without_npx_stops_with_a_clear_message(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        mograph.node_dir({"NODE_DIR": str(tmp_path / "empty")})
    assert "NODE_DIR" in capsys.readouterr().err


def test_no_node_anywhere_stops_with_a_clear_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SystemExit):
        mograph.node_dir({})
    err = capsys.readouterr().err
    assert "npx" in err and "NODE_DIR" in err


def test_remotion_runs_that_npx_with_its_node_first_on_path(tmp_path, monkeypatch):
    mine = fake_node(tmp_path / "node26" / "bin")
    monkeypatch.setattr(mograph.common, "load_config", lambda: {"NODE_DIR": str(mine)})
    monkeypatch.setenv("PATH", "/usr/bin")
    seen = {}

    def fake_run(args, **kw):
        seen.update(args=args, env=kw.get("env"))
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(mograph.subprocess, "run", fake_run)
    monkeypatch.setattr(mograph, "TEMPLATE", tmp_path / "th")
    (tmp_path / "th" / "node_modules" / "remotion").mkdir(parents=True)
    props = mograph.props({"id": 1, "mograph": PUNCH}, {}, 0.0, 1.0, 30, False)
    mograph.remotion("still", props, tmp_path / "out.png")
    assert seen["args"][0] == str(mine / "npx")
    assert seen["env"]["PATH"].split(os.pathsep)[:2] == [str(mine), "/usr/bin"]
