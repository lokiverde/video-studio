"""Shared real-footage fixtures: the spec's Appendix A fox clip, the library's CTLT still
example, a lint-clean montage, and builders for shots and jobs (no network)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def appendix_fox_clip():
    """The S02 clip prompt from spec Appendix A, read from the spec itself."""
    brief = (ROOT / "tests" / "fixtures" / "rf_spec_appendix.md").read_text()
    after = brief[brief.index("**S02 clip"):]
    return after.split("```\n", 1)[1].split("\n```", 1)[0]


def library_still():
    """The CTLT still example in templates/ctlt-still.md (style phone-snapshot)."""
    text = (ROOT / "assets" / "real-footage" / "templates" / "ctlt-still.md").read_text()
    return " ".join(line[2:] for line in text.splitlines() if line.startswith("> "))


FOX = appendix_fox_clip()
STILL = library_still()


def still(prompt=STILL, **changes):
    return {"id": "S01", "kind": "still", "purpose": "reference frame for S02",
            "model": "nano-banana-pro", "mode": "text2image", "style": "phone-snapshot",
            "refs": [], "prompt": prompt, "settings": {"resolution": "2K", "aspect": "9:16"},
            "status": "drafted", **changes}


def clip(prompt=FOX, **changes):
    return {"id": "S02", "kind": "clip", "technique": "whip-pan", "style": "phone-snapshot",
            "model": {"draft": "byte-plus-seedance-2-5-draft", "final": "byte-plus-seedance-2-5"},
            "mode": "element2video", "duration_s": 8,
            "refs": [{"label": "IMG1", "file": "characters/marcus/sheet.png",
                      "role": "supplies only Marcus's face and exact wardrobe"},
                     {"label": "IMG2", "file": "rf/returns/S01_take1.png",
                      "role": "supplies only the fox's body, headset, and lanyard"}],
            "dialogue": [{"speaker": "Marcus", "line": "Oh, no.", "voice": "generated"}],
            "prompt": prompt, "settings": {"draft": "480p", "final": "1080p", "aspect": "9:16"},
            "status": "drafted", "returns": [], **changes}


def job(*shots, **changes):
    data = {"job": "20261024-101500-fox", "idea": "a fox says no to a scam call",
            "lane": "techtony", "ai_disclosure": True, "likeness": {},
            "defaults": {"provider": "openart", "aspect": "9:16", "draft_first": True,
                         "ref_tag_syntax": "unverified"},
            "shots": list(shots) or [still(), clip()]}
    return {**data, **changes}


def swap(text, old, new):
    assert old in text, old
    return text.replace(old, new)


MONTAGE = """GOAL: 4 hard-cut shots, about 1.5 seconds each, 6 seconds total. Chaotic office prank energy. Filmed badly by bystanders on phones. Clean full frame: no overlay, timestamp, REC indicator, battery icon, focus box, grid, border or subtitles.
CAST: Exactly one on screen: a red fox in a call-center headset.
RHYTHM: One action per shot, from its start to its impact, then a hard cut.
SHOT 1 | 0-1.5s: hallway, the fox, drops a desk phone. HARD CUT.
SHOT 2 | 1.5-3s: kitchen, the fox, knocks a mug off the counter. HARD CUT.
SHOT 3 | 3-4.5s: office, the fox, spins a chair. HARD CUT.
SHOT 4 | 4.5-6s: doorway, the fox, slams the door. END.
CAMERA: SHOT 2 whip pan, SHOT 4 frame block.
CONTINUITY: Same fox and headset in every shot. End on the closed door."""
