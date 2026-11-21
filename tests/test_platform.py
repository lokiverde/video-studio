"""Windows, Linux and macOS differences: venv paths, clipboard and browser commands, fonts,
the transcriber pick, and the open-model fallbacks vision.py uses off a Mac."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import platform_util  # noqa: E402
import transcribe  # noqa: E402
import vision  # noqa: E402


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(platform_util, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_util, "IS_MAC", False)


@pytest.fixture
def on_mac(monkeypatch):
    monkeypatch.setattr(platform_util, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_util, "IS_MAC", True)


@pytest.fixture
def on_linux(monkeypatch):
    monkeypatch.setattr(platform_util, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_util, "IS_MAC", False)


def test_venv_programs_live_in_scripts_on_windows(on_windows):
    venv = Path("/v")
    assert platform_util.venv_python(venv) == venv / "Scripts" / "python.exe"
    assert platform_util.venv_bin(venv, "parakeet-mlx") == venv / "Scripts" / "parakeet-mlx.exe"


def test_venv_programs_live_in_bin_elsewhere(on_mac):
    assert platform_util.venv_python(Path("/v")) == Path("/v/bin/python")


def test_studio_venvs_sit_in_the_studio_home():
    assert platform_util.studio_venv("rembg") == platform_util.STUDIO_HOME / ".venv-rembg"


def test_clipboard_and_open_commands_per_os(monkeypatch, on_windows):
    assert platform_util.clipboard_cmd() == ["clip"]
    assert platform_util.open_cmd("https://x.test") == ["cmd", "/c", "start", "", "https://x.test"]
    monkeypatch.setattr(platform_util, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_util, "IS_MAC", True)
    assert platform_util.clipboard_cmd() == ["pbcopy"]
    assert platform_util.open_cmd("https://x.test") == ["open", "https://x.test"]


def test_linux_clipboard_needs_a_tool(monkeypatch, on_linux):
    monkeypatch.setattr(platform_util.shutil, "which", lambda name: None)
    assert platform_util.clipboard_cmd() is None
    monkeypatch.setattr(platform_util.shutil, "which", lambda name: "/usr/bin/xclip" if name == "xclip" else None)
    assert platform_util.clipboard_cmd() == ["xclip", "-selection", "clipboard"]
    assert platform_util.open_cmd("u") == ["xdg-open", "u"]


def test_detached_jobs_use_creation_flags_on_windows(on_windows):
    assert set(platform_util.detached_low_priority(10)) == {"creationflags"}


def test_detached_jobs_use_a_new_session_elsewhere(on_mac):
    kw = platform_util.detached_low_priority(10)
    assert kw["start_new_session"] is True and callable(kw["preexec_fn"])


def test_pick_font_takes_the_first_that_exists(tmp_path):
    real = tmp_path / "real.ttf"
    real.write_bytes(b"x")
    assert platform_util.pick_font(tmp_path / "missing.ttf", real, fallback="fb.ttf") == str(real)
    assert platform_util.pick_font(tmp_path / "missing.ttf", fallback="fb.ttf") == "fb.ttf"
    assert platform_util.pick_font_face((tmp_path / "no.ttc", 1), fallback=("fb.ttf", 0)) == ("fb.ttf", 0)
    assert platform_util.pick_font_face((real, 1), fallback=("fb.ttf", 0)) == (str(real), 1)


def test_heavy_font_always_lands_on_a_real_file():
    assert Path(platform_util.heavy_font("/nowhere/Impact.ttf")).exists()


# ---------- transcription ----------

def _engines(monkeypatch, tmp_path, parakeet=False, whisper=False, faster=None):
    def made(name, on):
        p = tmp_path / name
        if on:
            p.write_text("")
        else:
            p.unlink(missing_ok=True)
        return p
    monkeypatch.setattr(transcribe, "PARAKEET_BIN", made("parakeet", parakeet))
    monkeypatch.setattr(transcribe, "WHISPER_PY", made("whisper", whisper))
    monkeypatch.setattr(transcribe, "_faster_python", lambda: faster)


def test_engine_order_is_parakeet_then_whisper_then_faster(monkeypatch, tmp_path):
    _engines(monkeypatch, tmp_path, parakeet=True, whisper=True, faster=Path("py"))
    assert transcribe.default_engine() == "parakeet"
    _engines(monkeypatch, tmp_path, whisper=True, faster=Path("py"))
    assert transcribe.default_engine() == "whisper"
    _engines(monkeypatch, tmp_path, faster=Path("py"))
    assert transcribe.default_engine() == "faster-whisper"
    _engines(monkeypatch, tmp_path)
    assert transcribe.default_engine() is None and not transcribe.available()


def test_faster_whisper_writes_the_shared_json(monkeypatch, tmp_path):
    _engines(monkeypatch, tmp_path, faster=Path("py"))
    seg = {"segments": [{"start": 0.0, "end": 1.0, "text": " hi", "words": []}]}
    monkeypatch.setattr(transcribe, "_run_faster", lambda audios: [seg for _ in audios])
    out = tmp_path / "t.json"
    assert transcribe.transcribe(tmp_path / "a.wav", out) == "faster-whisper"
    assert '"segments"' in out.read_text()
    assert transcribe.transcribe_many(["a", "b"]) == [seg, seg]


def test_no_transcriber_exits_with_install_help(monkeypatch, tmp_path):
    _engines(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as stop:
        transcribe.transcribe(tmp_path / "a.wav", tmp_path / "t.json")
    assert "faster-whisper" in str(stop.value)


# ---------- vision fallbacks ----------

def test_tiles_match_the_swift_scan():
    assert vision.tiles(1) == [(0.0, 0.0, 1.0, 1.0)]
    two = vision.tiles(2)
    assert len(two) == 4 and two[-1] == (0.25, 0.25, 0.75, 0.75)


def test_merge_keeps_the_most_confident_of_overlapping_boxes():
    boxes = [[0.1, 0.1, 0.2, 0.2, 0.7], [0.12, 0.11, 0.18, 0.2, 0.9], [0.6, 0.6, 0.1, 0.1, 0.8]]
    kept = vision.merge(boxes)
    assert [b[4] for b in kept] == [0.9, 0.8]


def test_mouth_box_sits_between_the_mouth_corners():
    row = [100, 100, 200, 240, 0, 0, 0, 0, 0, 0, 150, 280, 250, 280, 0.95]
    m = vision.mouth_of(row, 1000, 1000)
    assert m["face"] == [0.1, 0.1, 0.2, 0.24]
    lx, ly, lw, lh = m["lips"]
    assert lx == pytest.approx(0.15) and lw == pytest.approx(0.1) and ly < 0.28 < ly + lh
    assert m["chin"] == pytest.approx(0.34)


def test_pose_joints_use_the_apple_vision_names():
    marks = [SimpleNamespace(x=0.5, y=0.2, visibility=0.9) for _ in range(33)]
    marks[7] = SimpleNamespace(x=1.4, y=0.2, visibility=0.9)          # off frame: dropped
    joints = vision.joints_of(marks)
    assert joints["head_joint"] == [0.5, 0.2, 0.9]
    assert "left_eye_joint" in joints and "left_upLeg_joint" in joints
    assert "left_ear_joint" not in joints


def test_detect_faces_off_a_mac_uses_yunet_over_tiles(monkeypatch, tmp_path):
    from PIL import Image
    Image.new("RGB", (400, 300), "gray").save(tmp_path / "000001.jpg")
    monkeypatch.setattr(vision, "use_swift", lambda: False)
    monkeypatch.setattr(vision, "_yunet", lambda cv2: object())
    monkeypatch.setattr(vision, "_faces_in", lambda det, img: [[10, 10, 40, 40] + [0] * 10 + [0.9]])
    found = vision.detect_faces(tmp_path, grid=3)
    assert list(found) == ["000001.jpg"]
    assert all(0 <= b[0] <= 1 and b[4] == 0.9 for b in found["000001.jpg"])


def test_cutout_off_a_mac_without_rembg_says_how_to_install(monkeypatch, tmp_path):
    monkeypatch.setattr(vision.platform_util, "IS_MAC", False)
    monkeypatch.setattr(vision, "rembg_python", lambda: None)
    ok, why = vision.subject_cutout(tmp_path / "a.png", tmp_path / "b.png")
    assert not ok and "rembg" in why


def test_rembg_cutouts_refuse_without_rembg(monkeypatch):
    monkeypatch.setattr(vision, "rembg_python", lambda: None)
    with pytest.raises(RuntimeError, match="rembg"):
        vision.rembg_cutouts([(Path("a"), Path("b"))])
    vision.rembg_cutouts([])                               # nothing to cut: no error


def test_tool_finds_the_windows_cmd_shim_in_a_folder(tmp_path):
    (tmp_path / "npx.cmd").write_text("")
    assert platform_util.tool("npx", tmp_path) == str(tmp_path / "npx.cmd")
    assert platform_util.tool("node", tmp_path) == str(tmp_path / "node")      # missing: plain path


def test_tool_on_path_falls_back_to_the_bare_name(monkeypatch):
    monkeypatch.setattr(platform_util.shutil, "which", lambda name: None)
    assert platform_util.tool("npx") == "npx"
    monkeypatch.setattr(platform_util.shutil, "which", lambda name: "C:/node/npx.CMD")
    assert platform_util.tool("npx") == "C:/node/npx.CMD"
