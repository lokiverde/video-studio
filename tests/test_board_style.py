"""Board style (Peverelli format, reviewed 2026-10-12): Tony full frame, a recurring
full-screen board that lights up the current item, real screenshot receipts, key-word
captions, and a sound layer (SFX cues + suspense-then-bed music) mixed after the render."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import th_lib  # noqa: E402

ITEMS = [{"label": "cost", "sub": "18 comments"}, {"label": "lifestyle"}, {"label": "jobs"},
         {"label": "family"}, {"label": "weather"}]


def board_job(**extra):
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 120.0, "cuts": [], "style": "board",
           "board": {"items": ITEMS, "shows": [{"from": 10.0, "to": 13.0, "active": 0, "revealed": 1},
                                               {"from": 100.0, "to": 104.0, "active": 4, "revealed": 5}]},
           "sections": [{"evidence": [20.0, 26.0], "theme": "glow",
                         "blocks": [{"type": "receipt", "file": "receipts/q1.png", "at": 20.5, "highlight": [0.1, 0.4, 0.8, 0.2]}]},
                        {"evidence": [40.0, 45.0], "blocks": [{"type": "steps", "items": [
                            {"text": "a", "at": 40.5}, {"text": "b", "at": 42.0}, {"text": "c", "at": 43.5}]}]}]}
    return {**job, **extra}


def test_a_clean_board_job_validates():
    assert th_lib.validate(board_job()) == []


def test_board_punches_like_studio():
    assert th_lib.punch_boundaries(board_job(punches=[30.0])) == [30.0]


def test_board_show_problems_are_caught():
    bad = board_job(board={"items": ITEMS, "shows": [
        {"from": 115.0, "to": 125.0, "active": 0, "revealed": 1},     # past the end
        {"from": 50.0, "to": 52.0, "active": 7, "revealed": 1},       # no item 7
        {"from": 60.0, "to": 62.0, "active": 0, "revealed": 9},       # more revealed than items
        {"from": 21.0, "to": 23.0, "active": 0, "revealed": 1},       # on top of a section
    ]})
    problems = " ".join(th_lib.validate(bad))
    assert "past" in problems or "bad range" in problems
    assert "active" in problems and "revealed" in problems and "section" in problems


def test_a_teaser_show_lights_no_card():
    job = board_job(board={"items": ITEMS, "shows": [{"from": 10.0, "to": 13.0, "active": -1, "revealed": 0}]})
    assert th_lib.validate(job) == []


def test_receipt_highlight_must_be_fractions():
    job = board_job()
    job["sections"][0]["blocks"][0]["highlight"] = [0.1, 0.4, 1.4, 0.2]
    assert any("highlight" in p for p in th_lib.validate(job))


def test_receipt_line_boxes_must_be_fractions_too():
    job = board_job()
    job["sections"][0]["blocks"][0]["lines"] = [[0.1, 0.4, 0.8, 0.1], [0.1, 0.95, 0.5, 0.1]]
    assert any("highlight" in p for p in th_lib.validate(job))


def test_receipts_are_render_files():
    assert "receipts/q1.png" in th_lib.job_files(board_job())


def test_board_shows_change_the_picture_and_get_a_sheet_frame():
    job = board_job()
    events = th_lib._visual_events(job)
    assert 10.0 in events and 13.0 in events
    assert any(10.0 < m < 13.0 for m in th_lib.sheet_moments(job))


def test_each_board_reveal_is_a_youtube_chapter():
    job = board_job()
    job["board"]["items"] = [{"tag": "#5", "label": "Cost"}, *ITEMS[1:]]
    job["board"]["shows"].insert(0, {"from": 2.0, "to": 4.0, "active": -1, "revealed": 0})   # teaser: no chapter
    marks = th_lib.chapters(job, intro="Why they come back")
    assert marks[0] == (0.0, "Why they come back")
    assert (10.0, "#5 Cost") in marks                    # a tag reads "#5 Cost"
    assert (100.0, "weather") in marks                   # no tag: the label alone
    assert all(label != "" for _, label in marks) and len(marks) == 3


def test_glow_is_a_theme():
    assert "glow" in th_lib.STUDIO_THEMES


def test_sfx_cues_follow_the_picture():
    cues = th_lib.sfx_cues(board_job())
    kinds = {(round(c["t"], 2), c["kind"]) for c in cues}
    assert (10.0, "whoosh") in kinds                   # board slides in
    assert any(k == "riser" and 8.0 <= t < 10.0 for t, k in kinds)   # builds into each show
    assert (100.0, "impact") in kinds                  # the #1 reveal lands
    assert (20.5, "pop") in kinds                      # a receipt pops in
    assert (42.0, "tick") in kinds and (43.5, "tick") in kinds   # later steps tick


def test_back_to_back_graphics_whoosh_once_at_the_start_of_the_run():
    job = board_job()
    job["sections"] = [
        {"evidence": [20.0, 26.0], "blocks": [{"type": "headline", "text": "a", "at": 20.4}]},
        {"evidence": [26.0, 31.0], "blocks": [{"type": "headline", "text": "b", "at": 26.3}]},
        {"evidence": [31.5, 36.0], "blocks": [{"type": "headline", "text": "c", "at": 31.8}]},   # 0.5s gap: same run
        {"evidence": [50.0, 55.0], "blocks": [{"type": "headline", "text": "d", "at": 50.4}]},   # Tony in between
    ]
    whooshes = sorted(round(c["t"], 2) for c in th_lib.sfx_cues(job) if c["kind"] == "whoosh")
    assert 20.0 in whooshes and 50.0 in whooshes
    assert 26.0 not in whooshes and 31.5 not in whooshes
    pops = {round(c["t"], 2) for c in th_lib.sfx_cues(job) if c["kind"] == "pop"}
    assert {26.3, 31.8} <= pops                          # the swap still pops its card in


def test_sfx_cues_sit_on_the_output_timeline_and_never_stack():
    job = board_job(cuts=[[2.0, 4.0]])
    cues = th_lib.sfx_cues(job)
    assert any(abs(c["t"] - 8.0) < 0.01 and c["kind"] == "whoosh" for c in cues)   # 10.0 minus the 2s cut
    times = sorted(c["t"] for c in cues)
    assert all(b - a >= th_lib.SFX_MIN_GAP for a, b in zip(times, times[1:]))


def test_sfx_can_be_muted_or_turned_off():
    assert th_lib.sfx_cues(board_job(sfx=False)) == []
    muted = th_lib.sfx_cues(board_job(sfx={"mute": [20.5]}))
    assert not any(abs(c["t"] - 20.5) < 0.05 for c in muted)
    added = th_lib.sfx_cues(board_job(sfx={"add": [{"at": 60.0, "kind": "click"}]}))
    assert any(c["kind"] == "click" and abs(c["t"] - 60.0) < 0.01 for c in added)


def test_mix_filter_wires_bed_hook_and_sfx():
    fc = th_lib.mix_filter(bed_gain=-12.0, total=300.0, hook_gain=-10.0, switch=50.0, sfx=True)
    assert "[1:a]" in fc and "[2:a]" in fc and "[3:a]" in fc and fc.endswith("[out]")
    plain = th_lib.mix_filter(bed_gain=-12.0, total=300.0)
    assert "[2:a]" not in plain and "sidechaincompress" in plain



def test_music_mix_stays_under_minus_one_dbtp(tmp_path):
    """The bed + SFX mix ended in alimiter with ffmpeg's default auto-level, which pushes the
    output back up to 0 dB: the bizplan music cuts peaked at -0.1 dBTP (audio QC 2026-11-10)."""
    import subprocess
    import audio_qc
    # A hot voice (float audio, peaks over full scale) so the mix reaches the limiter.
    video, bed, out = tmp_path / "v.mkv", tmp_path / "bed.wav", tmp_path / "mix.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=12",
                    "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=12:sample_rate=48000:seed=3",
                    "-af", "volume=6dB", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_f32le", str(video)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anoisesrc=color=brown:duration=12:sample_rate=48000:seed=4", str(bed)], check=True)
    fc = th_lib.mix_filter(bed_gain=-6.0, total=12.0)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(bed),
                    "-filter_complex", fc, "-map", "0:v", "-map", "[out]", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    assert audio_qc.measure(out)["TP"] <= -1.0


# ---- split layout (quiz tips look, Simon Scrapes review 2026-10-13) --------------------
# Tony stays on the right third, the graphics sit in a light card on the left, graphics in
# one run pan sideways, and a big countdown number sweeps across before each item.

def test_split_layout_validates_on_a_board_job():
    assert th_lib.validate(board_job(layout="split")) == []
    assert th_lib.validate(board_job(layout="full")) == []


def test_unknown_layout_or_split_outside_board_is_caught():
    assert any("layout" in p for p in th_lib.validate(board_job(layout="sideways")))
    assert any("layout" in p for p in th_lib.validate(board_job(layout="split", style="studio")))


def test_board_wipe_must_be_true_or_false():
    job = board_job(layout="split")
    job["board"]["wipe"] = "yes"
    assert any("wipe" in p for p in th_lib.validate(job))


def test_split_layout_sheets_a_frame_of_each_number_wipe():
    job = board_job(layout="split")
    job["board"]["shows"].insert(0, {"from": 2.0, "to": 4.0, "active": -1, "revealed": 0})   # teaser: no number
    moments = th_lib.sheet_moments(job)
    for show in job["board"]["shows"][1:]:
        assert any(abs(m - (show["from"] + th_lib.WIPE_SHEET_S)) < 1e-6 for m in moments)
    assert not any(abs(m - (2.0 + th_lib.WIPE_SHEET_S)) < 1e-6 for m in moments)


def test_no_wipe_frames_when_the_wipe_is_off_or_the_layout_is_full():
    off = board_job(layout="split")
    off["board"]["wipe"] = False
    full = board_job()
    for job in (off, full):
        moments = th_lib.sheet_moments(job)
        assert not any(abs(m - (10.0 + th_lib.WIPE_SHEET_S)) < 1e-6 for m in moments)
