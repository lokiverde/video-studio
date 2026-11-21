"""The preview gate: Tony looks at the contact sheet and says go BEFORE anything renders.
An approval covers exactly what the sheet showed. Edit the job or reroll a still and the
approval is void until he has seen a fresh sheet."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import approval  # noqa: E402


def job(tmp_path, scenes='{"a": 1}', stills=("scene_01.png", "p_scene_01.png")):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (tmp_path / "scenes.json").write_text(scenes)
    for name in stills:
        (work / name).write_bytes(b"img-" + name.encode())
    return tmp_path


def test_fingerprint_is_stable_for_an_unchanged_job(tmp_path):
    j = job(tmp_path)
    assert approval.fingerprint(j, "faceless") == approval.fingerprint(j, "faceless")


def test_editing_the_scenes_file_changes_the_fingerprint(tmp_path):
    j = job(tmp_path)
    before = approval.fingerprint(j, "faceless")
    (j / "scenes.json").write_text('{"a": 2}')
    assert approval.fingerprint(j, "faceless") != before


def test_rerolling_a_still_changes_the_fingerprint(tmp_path):
    j = job(tmp_path)
    before = approval.fingerprint(j, "faceless")
    (j / "work" / "scene_01.png").write_bytes(b"a different image")
    assert approval.fingerprint(j, "faceless") != before


def test_files_made_by_finish_do_not_void_an_approval(tmp_path):
    j = job(tmp_path)
    before = approval.fingerprint(j, "faceless")
    for name in ("caption_01.png", "clip_01.mp4", "scene_01.wav", "contact_sheet.jpg"):
        (j / "work" / name).write_bytes(b"x")
    assert approval.fingerprint(j, "faceless") == before


def test_talking_head_fingerprint_covers_job_json_and_public_images(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "job.json").write_text("{}")
    (tmp_path / "public" / "broll1.png").write_bytes(b"one")
    before = approval.fingerprint(tmp_path, "talking-head")
    (tmp_path / "public" / "broll1.png").write_bytes(b"two!")
    assert approval.fingerprint(tmp_path, "talking-head") != before


def test_gate_blocks_a_job_nobody_approved():
    assert "not been approved" in approval.gate({}, "abc")


def test_gate_blocks_when_the_job_changed_after_approval():
    reason = approval.gate({"approved_fingerprint": "old"}, "new")
    assert "changed since" in reason


def test_gate_opens_for_an_approved_unchanged_job():
    assert approval.gate({"approved_fingerprint": "abc"}, "abc") is None


def test_gate_opens_when_tony_waived_the_preview():
    assert approval.gate({}, "abc", waived=True) is None


def test_approving_needs_a_sheet_of_the_current_job():
    assert "stale" in approval.can_approve({"sheet_fingerprint": "old"}, "new")
    assert "no contact sheet" in approval.can_approve({}, "new")
    assert approval.can_approve({"sheet_fingerprint": "new"}, "new") is None


def test_a_sheet_older_than_any_input_is_stale():
    assert approval.sheet_is_stale(sheet_mtime=100.0, input_mtimes=[90.0, 101.0]) is True


def test_a_sheet_newer_than_every_input_is_fresh():
    assert approval.sheet_is_stale(sheet_mtime=100.0, input_mtimes=[90.0, 99.0]) is False


def test_a_missing_sheet_counts_as_stale():
    assert approval.sheet_is_stale(sheet_mtime=None, input_mtimes=[1.0]) is True


def test_faceless_approval_reads_staleness_from_the_files(tmp_path):
    import os
    j = job(tmp_path, stills=("scene_01.png",))
    sheet = j / "work" / "contact_sheet.jpg"
    sheet.write_bytes(b"sheet")
    os.utime(sheet, (2_000_000_000, 2_000_000_000))
    assert approval.faceless_sheet_problem(j) is None
    os.utime(j / "scenes.json", (2_000_000_500, 2_000_000_500))
    assert "stale" in approval.faceless_sheet_problem(j)


def made_in_order(j, *names):
    """Date the job's files 100 seconds apart, in the order given."""
    import os
    for i, name in enumerate(names):
        path = j / name if name == "scenes.json" else j / "work" / name
        if not path.exists():
            path.write_bytes(name.encode())
        os.utime(path, (2_000_000_000 + 100 * i, 2_000_000_000 + 100 * i))


def test_the_portrait_pass_after_the_16x9_sheet_leaves_the_job_approvable(tmp_path):
    # fv.py make: 16:9 stills, the 16:9 sheet, then the portrait stills and their own sheet
    j = job(tmp_path)
    made_in_order(j, "scenes.json", "scene_01.png", "contact_sheet.jpg", "p_scene_01.png",
                  "contact_sheet_9x16.jpg")
    assert approval.faceless_sheet_problem(j) is None


def test_a_portrait_still_rerolled_after_its_sheet_makes_the_9x16_sheet_stale(tmp_path):
    j = job(tmp_path)
    made_in_order(j, "scenes.json", "scene_01.png", "contact_sheet.jpg",
                  "contact_sheet_9x16.jpg", "p_scene_01.png")
    assert "9:16 contact sheet is stale" in approval.faceless_sheet_problem(j)


def test_portrait_stills_without_their_sheet_cannot_be_approved(tmp_path):
    # a portrait pass that stopped before its sheet: Tony has never seen those stills
    j = job(tmp_path)
    made_in_order(j, "scenes.json", "scene_01.png", "contact_sheet.jpg", "p_scene_01.png")
    assert "no 9:16 contact sheet" in approval.faceless_sheet_problem(j)


def test_a_job_with_no_16x9_sheet_cannot_be_approved_even_before_its_stills(tmp_path):
    j = job(tmp_path, stills=())
    assert "no contact sheet" in approval.faceless_sheet_problem(j)


def test_a_job_with_no_portrait_stills_needs_no_9x16_sheet(tmp_path):
    j = job(tmp_path, stills=("scene_01.png",))
    made_in_order(j, "scenes.json", "scene_01.png", "contact_sheet.jpg")
    assert approval.faceless_sheet_problem(j) is None


def test_swapping_a_broll_video_voids_a_talking_head_approval(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "job.json").write_text("{}")
    (tmp_path / "public" / "roof.mp4").write_bytes(b"clip one")
    before = approval.fingerprint(tmp_path, "talking-head")
    (tmp_path / "public" / "roof.mp4").write_bytes(b"clip two")
    assert approval.fingerprint(tmp_path, "talking-head") != before


def test_swapping_a_receipt_in_a_public_subfolder_voids_a_talking_head_approval(tmp_path):
    # board style keeps its comment screenshots in public/receipts/
    (tmp_path / "public" / "receipts").mkdir(parents=True)
    (tmp_path / "job.json").write_text("{}")
    (tmp_path / "public" / "receipts" / "q1.png").write_bytes(b"shot one")
    before = approval.fingerprint(tmp_path, "talking-head")
    (tmp_path / "public" / "receipts" / "q1.png").write_bytes(b"shot two")
    assert approval.fingerprint(tmp_path, "talking-head") != before


def test_a_job_without_subfolders_keeps_its_old_fingerprint(tmp_path):
    # approvals made before subfolders counted must still match
    import hashlib
    (tmp_path / "public").mkdir()
    (tmp_path / "job.json").write_text("{}")
    (tmp_path / "public" / "roof.png").write_bytes(b"still")
    old = hashlib.sha256()
    for path in (tmp_path / "job.json", tmp_path / "public" / "roof.png"):
        old.update(f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    assert approval.fingerprint(tmp_path, "talking-head") == old.hexdigest()


def test_the_source_footage_is_not_rehashed_for_every_approval(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "job.json").write_text("{}")
    before = approval.fingerprint(tmp_path, "talking-head")
    (tmp_path / "public" / "footage.mp4").write_bytes(b"x" * 1000)
    assert approval.fingerprint(tmp_path, "talking-head") == before


def test_editing_the_youtube_text_does_not_void_a_talking_head_approval(tmp_path):
    import json
    (tmp_path / "public").mkdir()
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps({"title": "t", "sections": [], "youtube": {"title": "first draft"}}))
    before = approval.fingerprint(tmp_path, "talking-head")
    job_file.write_text(json.dumps({"title": "t", "sections": [], "youtube": {"title": "better title"}}, indent=2))
    assert approval.fingerprint(tmp_path, "talking-head") == before


def test_editing_anything_visual_still_voids_a_talking_head_approval(tmp_path):
    import json
    (tmp_path / "public").mkdir()
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps({"title": "t", "sections": [], "youtube": {"title": "x"}}))
    before = approval.fingerprint(tmp_path, "talking-head")
    job_file.write_text(json.dumps({"title": "t", "sections": [{"evidence": [1, 2], "blocks": []}], "youtube": {"title": "x"}}))
    assert approval.fingerprint(tmp_path, "talking-head") != before
