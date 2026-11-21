"""The prompt linter: every rule in docs/briefs/2026-10-24-realistic-footage.md 5.5, with
the likeness rules from 5.6, checked on a passing and a failing fixture. The clean job
is the spec's own Appendix A fox clip plus the CTLT still example from the library.
Word lists and thresholds come from assets/real-footage/lint.json. No network."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rf_fixtures import FOX, MONTAGE, STILL, clip, job, still, swap  # noqa: E402

import rf_library  # noqa: E402
import rf_lint  # noqa: E402

SETTINGS = rf_lint.load_settings()


def found(data, brief="", settings=SETTINGS):
    return {(f.level, f.code) for f in rf_lint.findings(data, brief, settings)}


def test_the_appendix_fox_example_and_the_library_still_lint_clean():
    assert rf_lint.findings(job(), "", SETTINGS) == []


SEVEN_BEATS = ("ACTION: Marcus sits at a laptop. He types. He stops. He sighs. He leans in. "
               "A phone rings. The fox appears. He freezes. End on the fox.")

# (fixture name, job, expected (level, code)): each rule's failing fixture.
FAILING = [
    ("C1 no clean-frame guard",
     job(still(), clip(swap(FOX, " Clean full frame: no overlay,\ntimestamp, REC indicator, battery icon, "
                                 "focus box, grid, border, or subtitles.", ""))), ("FAIL", "C1")),
    ("C1 the guard words, but not as a guard",
     job(still(), clip(swap(FOX, "Clean full frame: no overlay,\ntimestamp, REC indicator, battery icon, focus box, "
                                 "grid, border, or subtitles.", "Overlay, timestamp, REC indicator, battery icon, "
                                 "focus box, grid, border and subtitles all show."))), ("FAIL", "C1")),
    ("C2 two behaviors in one take",
     job(still(), clip(swap(FOX, "settle on the fox in the doorway.",
                            "settle on the fox in the doorway, then a crash zoom onto its face."))), ("WARN", "C2")),
    ("C2 a second behavior named outside CAMERA",
     job(still(), clip(swap(FOX, "Marcus lifts his hand off the keyboard.",
                            "A crash zoom lands on Marcus as he lifts his hand off the keyboard."))), ("WARN", "C2")),
    ("C3 no trigger, settle or not-this",
     job(still(), clip(re.sub(r"CAMERA:.*?\n\n", "CAMERA: The camera points at the fox.\n\n", FOX,
                              flags=re.S))), ("WARN", "C3")),
    ("C4 two characters, no cast count",
     job(still(), clip(swap(FOX, "Exactly two on screen: ", "On screen: "))), ("FAIL", "C4")),
    ("C4 a reference with no supplies-only role",
     job(still(), clip(refs=[{"label": "IMG1", "file": "characters/marcus/sheet.png", "role": "Marcus"}])),
     ("FAIL", "C4")),
    ("C5 operator never placed",
     job(still(), clip(swap(swap(FOX, " The operator stands in the doorway behind Marcus's left shoulder and is never seen.", ""),
                            " The phone and the\nperson holding it never appear.", ""))), ("WARN", "C5")),
    ("C6 dialogue with no lip-sync instruction",
     job(still(), clip(swap(FOX, " Intelligible spoken words, mouth in sync.", ""))), ("WARN", "C6")),
    ("C6 dialogue with no voice source",
     job(still(), clip(dialogue=[{"speaker": "Marcus", "line": "Oh, no."}])), ("WARN", "C6")),
    ("C7 seven beats in eight seconds",
     job(still(), clip(re.sub(r"ACTION:.*?\n\n", SEVEN_BEATS + "\n\n", FOX, flags=re.S))), ("WARN", "C7")),
    ("C7 lowercase block labels still count beats",
     job(still(), clip(re.sub(r"ACTION:.*?\n\n", SEVEN_BEATS.replace("ACTION:", "Action:") + "\n\n", FOX,
                              flags=re.S))), ("WARN", "C7")),
    ("C7 a lowercase montage shot under a second",
     job(clip(swap(MONTAGE, "SHOT 2 | 1.5-3s", "Shot 2 | 1.5-2s"), technique="", refs=[], dialogue=[],
              duration_s=6)), ("WARN", "C7")),
    ("C7 a montage shot under a second",
     job(clip(swap(MONTAGE, "SHOT 2 | 1.5-3s", "SHOT 2 | 1.5-2s"), technique="", refs=[], dialogue=[],
              duration_s=6)), ("WARN", "C7")),
    ("C8 no final image",
     job(still(), clip(swap(swap(FOX, "and settle on the fox in the doorway", "and keep going"),
                            " and end on the fox in the doorway", ""))), ("WARN", "C8")),
    ("C9 a real brand",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus sips from a Starbucks cup and lifts his hand"))),
     ("FAIL", "C9")),
    ("C9 a brand without its apostrophe",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus eats McDonalds fries and lifts his hand"))),
     ("FAIL", "C9")),
    ("C9 a well-known person",
     job(still(), clip(swap(FOX, "a fictional man in his forties", "Warren Buffett"))), ("FAIL", "C9")),
    ("C9 euros",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus counts \u20ac20 notes and lifts his hand"))),
     ("FAIL", "C9")),
    ("C9 a real person",
     job(still(), clip(swap(FOX, "a fictional man in his forties", "Elon Musk"))), ("FAIL", "C9")),
    ("C9 real currency",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus counts twenty-dollar bills and lifts his hand"))),
     ("FAIL", "C9")),
    ("C9 real banknotes",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus counts a stack of banknotes and lifts his hand"))),
     ("FAIL", "C9")),
    ("C9 a real address",
     job(still(), clip(swap(FOX, "in a dim home office", "in a dim home office at 412 Elm Street"))), ("FAIL", "C9")),
    ("C9 a client",
     job(still(), clip(swap(FOX, "a fictional man in his forties", "my client Dave"))), ("FAIL", "C9")),
    ("C9 anyone but Tony or Partner in the likeness block",
     job(likeness={"marcus": "approved"}), ("FAIL", "C9")),
    ("C10 a tag left as a fill-in",
     job(still(), clip(swap(FOX, "@IMG1 supplies only", "@[IMG1] supplies only"))), ("WARN", "C10")),
    ("C10 a tag naming a reference the shot does not list",
     job(still(), clip(swap(FOX, "@IMG2 supplies only", "@IMG3 supplies only"))), ("WARN", "C10")),
    ("C11 Example Realty lane without the override", job(lane="example-realty"), ("FAIL", "C11")),
    ("C12 Tony in a prompt, not approved",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand"))), ("FAIL", "C12")),
    ("C12 Tony set to anything but approved",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand")), likeness={"tony": "yes"}),
     ("FAIL", "C12")),
    ("C12 Tony's legal first name",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Anthony lifts his hand"))), ("FAIL", "C12")),
    ("C12 Partner's voice reference, not approved",
     job(still(), clip(refs=[*clip()["refs"], {"label": "AUD1", "file": "characters/partner/voice.wav",
                                                "role": "supplies only Partner's voice"}])), ("FAIL", "C12")),
    ("C13 an approved likeness on an HOA topic",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand")), likeness={"tony": "approved"},
         idea="three HOA rules every owner should know"), ("FAIL", "C13")),
    ("C13 the topic in a shot's purpose",
     job(still(purpose="an HOA board meeting, for the S02 reference"),
         clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand")), likeness={"tony": "approved"}),
     ("FAIL", "C13")),
    ("I1 no capture device in the first sentence",
     job(still("A red fox stands in a doorway. " + STILL), clip()), ("WARN", "I1")),
    ("I2 filler quality words",
     job(still(STILL + " Masterpiece, 8K, award-winning."), clip()), ("WARN", "I2")),
    ("I3 an artifact the style does not make",
     job(still(STILL + " Heavy MPEG blocking in the shadows."), clip()), ("WARN", "I3")),
    ("I4 readable text in a still",
     job(still(STILL + ' A neon sign above it that reads "OPEN".'), clip()), ("FAIL", "I4")),
    ("I5 a FLUX still leaning on negations",
     job(still(STILL + " No people, no furniture.", model="tim-flux"), clip()), ("WARN", "I5")),
]

# (fixture name, job, brief text, code that must not appear): each rule's passing case.
PASSING = [
    ("C1 the montage carries the guard", job(clip(MONTAGE, technique="", refs=[], dialogue=[], duration_s=6)),
     "", "C1"),
    ("C2 handheld is an everyday word, not a second behavior",
     job(still(), clip(swap(FOX, "Reactive whip pan.", "Reactive whip pan, handheld."))), "", "C2"),
    ("C3 the fox clip's camera paragraph", job(), "", "C3"),
    ("C4 a count without the word exactly",
     job(still(), clip(swap(FOX, "Exactly two on screen", "Two people on screen"))), "", "C4"),
    ("C4 one character needs no count",
     job(clip(re.sub(r"CAST:.*?\n\n", "CAST: On screen: one red fox in a call-center headset. The operator "
                                       "stands in the doorway and is never seen.\n\n", FOX, flags=re.S),
              refs=[], dialogue=[]),), "", "C4"),
    ("C5 a montage needs no operator", job(clip(MONTAGE, technique="", refs=[], dialogue=[], duration_s=6)),
     "", "C5"),
    ("C6 a silent clip has nothing to sync",
     job(still(), clip(swap(FOX, 'Marcus says in a low, surprised voice: "Oh, no." Intelligible spoken words, '
                                 'mouth in sync.\n', ""), dialogue=[])), "", "C6"),
    ("C7 a montage with every shot at 1.5s",
     job(clip(MONTAGE, technique="", refs=[], dialogue=[], duration_s=6)), "", "C7"),
    ("C8 coming to rest is a final image",
     job(still(), clip(swap(swap(FOX, "and settle on the fox in the doorway", "and the frame comes to rest on the fox"),
                            " and end on the fox in the doorway", ""))), "", "C8"),
    ("C9 money in the plot is not money on screen",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "The scammer asks Marcus for money and he lifts his hand"))),
     "", "C9"),
    ("C9 fictional prop banknotes",
     job(still(), clip(swap(FOX, "Marcus lifts his hand",
                            "Marcus holds fictional prop banknotes with no readable markings and lifts his hand"))),
     "", "C9"),
    ("C9 the exclusions line is not a mention of money",
     job(still(), clip(FOX + "\nEXCLUSIONS: No real money, weapons or injuries.")), "", "C9"),
    ("C10 house tags that name the shot's references", job(), "", "C10"),
    ("C11 Example Realty lane with Tony's override",
     job(lane="example-realty"), 'Lane: example-realty\nlane_override: "tony-approved"\n', "C11"),
    ("C12 Tony approved",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand")), likeness={"tony": "approved"}),
     "", "C12"),
    ("C12 Partner approved",
     job(still(), clip(swap(FOX, "Marcus lifts his hand", "Partner lifts her hand")),
         likeness={"partner": "approved"}), "", "C12"),
    ("C13 the HOA topic without any likeness",
     job(idea="three HOA rules every owner should know"), "", "C13"),
    ("I1 a labeled CTLT still",
     job(still("CAMERA: Disposable camera snapshot, wide fixed lens, chest height, crooked crop.\n" + STILL,
               style="disposable-flash"), clip()), "", "I1"),
    ("I2 filler words inside a negation", job(still(STILL + " Not cinematic, not a masterpiece."), clip()), "", "I2"),
    ("I3 an artifact from the style's own list",
     job(still(STILL + " A small lens flare from the lamp."), clip()), "", "I3"),
    ("I4 a person who reads is not readable text",
     job(still(STILL + " A woman in the hallway that reads a letter."), clip()), "", "I4"),
    ("I4 readable text Tony approved",
     job(still(STILL + ' A neon sign above it that reads "OPEN".', text_ok=True), clip()), "", "I4"),
    ("I4 the exclusions line is not a request for text",
     job(still(STILL + " No logos, brand names or readable text."), clip()), "", "I4"),
    ("I5 negations are fine off FLUX",
     job(still(STILL + " No people, no furniture."), clip()), "", "I5"),
]


@pytest.mark.parametrize("name,data,expected", FAILING, ids=[f[0] for f in FAILING])
def test_each_rule_catches_its_failing_fixture(name, data, expected):
    assert expected in found(data)


@pytest.mark.parametrize("name,data,brief,code", PASSING, ids=[p[0] for p in PASSING])
def test_each_rule_lets_its_passing_fixture_through(name, data, brief, code):
    assert code not in {c for _, c in found(data, brief)}


def test_every_rule_has_a_failing_fixture_and_the_right_ones_are_fails():
    codes = {expected for _, _, expected in FAILING}
    assert {c for _, c in codes} == {f"I{n}" for n in range(1, 6)} | {f"C{n}" for n in range(1, 14)}
    for code in ("C1", "C4", "C9", "C11", "C12", "C13", "I4"):
        assert ("FAIL", code) in codes


def test_the_word_lists_come_from_the_settings_file():
    starbucks = job(still(), clip(swap(FOX, "Marcus lifts his hand", "Marcus sips from a Starbucks cup and lifts his hand")))
    edited = {**SETTINGS, "brands": [b for b in SETTINGS["brands"] if b != "starbucks"]}
    assert ("FAIL", "C9") in found(starbucks)
    assert ("FAIL", "C9") not in found(starbucks, settings=edited)
    seven = job(still(), clip(re.sub(r"ACTION:.*?\n\n", SEVEN_BEATS + "\n\n", FOX, flags=re.S)))
    assert ("WARN", "C7") not in found(seven, settings={**SETTINGS, "max_beats_short_clip": 10})


def test_the_topic_can_come_from_the_brief():
    data = job(still(), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand")), likeness={"tony": "approved"})
    assert ("FAIL", "C13") in found(data, "# Brief\n\nEpisode: what your HOA cannot stop you doing\n")
    assert ("FAIL", "C13") not in found(data, "# Brief\n\nEpisode: a scam call\n")


def test_the_flux_providers_come_from_the_settings_file():
    flux = job(still(STILL + " No people, no furniture.", model="tim-flux"), clip())
    assert ("WARN", "I5") in found(flux)
    assert ("WARN", "I5") not in found(flux, settings={**SETTINGS, "flux_providers": []})


def test_a_settings_file_with_a_missing_key_stops_with_its_name(tmp_path, capsys):
    path = tmp_path / "lint.json"
    path.write_text(json.dumps({k: v for k, v in SETTINGS.items() if k != "brands"}))
    with pytest.raises(SystemExit):
        rf_lint.load_settings(path)
    assert "brands" in capsys.readouterr().err


def test_a_settings_file_with_a_broken_pattern_stops_with_its_name(tmp_path, capsys):
    path = tmp_path / "lint.json"
    path.write_text(json.dumps({**SETTINGS, "address_pattern": "(unclosed"}))
    with pytest.raises(SystemExit):
        rf_lint.load_settings(path)
    assert "address_pattern" in capsys.readouterr().err


def test_every_style_names_a_device_the_linter_knows():
    words = [w.lower() for w in SETTINGS["device_words"]]
    for name in rf_library.names("style"):
        device = rf_library.front_matter("style", name)["device"].lower()
        assert any(w in device for w in words), name


@pytest.mark.parametrize("name", rf_library.names("technique"))
def test_every_behavior_paragraph_passes_the_camera_rules(name):
    text = (ROOT / "assets" / "real-footage" / "behaviors" / f"{name}.md").read_text()
    camera = text.split("```text\n", 1)[1].split("\n```", 1)[0]
    prompt = swap(FOX, FOX[FOX.index("CAMERA:"):FOX.index("SOUND:")], f"CAMERA: {camera}\n\n")
    codes = {c for _, c in found(job(still(), clip(prompt, technique=name)))}
    assert not {"C2", "C3"} & codes, (name, codes)


def test_a_finding_reads_as_one_line():
    finding = rf_lint.findings(job(lane="example-realty"), "", SETTINGS)[0]
    assert str(finding).startswith("FAIL C11 job: ")


def library_block(folder, name, index):
    """The index-th fenced text block of a library file (0 is the template itself)."""
    text = (ROOT / "assets" / "real-footage" / folder / f"{name}.md").read_text()
    return text.split("```text\n")[index + 1].split("\n```", 1)[0]


@pytest.mark.parametrize("name", ["single-take-clip", "montage", "talk-to-lens-clip"])
def test_every_clip_template_carries_the_clean_frame_guard(name):
    template = library_block("templates", name, 0)
    assert ("FAIL", "C1") not in found(job(clip(template, refs=[], dialogue=[])))



def talk_to_lens_job(likeness):
    """The talk-to-lens worked example: Tony's own take, named in its file, plus the
    person-swap still built on that take's first frame."""
    line = ("Okay, so I almost fell for it. A text from my bank, right? "
            "Except my bank doesn't text me at two in the morning.")
    talk = clip(library_block("templates", "talk-to-lens-clip", 1), technique="talk-to-lens",
                style="phone-front-talk", duration_s=10,
                refs=[{"label": "IMG1", "file": "rf/returns/S01_take1.png",
                       "role": "supplies only the exact first frame and setting"},
                      {"label": "VID1", "file": "rf/refs/VID1_tony.mp4",
                       "role": "supplies only body movement, gestures, timing and phone position"}],
                dialogue=[{"speaker": "the woman", "line": line, "voice": "generated"}])
    swapped = still(library_block("templates", "person-swap", 1), mode="image2image",
                    style="phone-front-talk",
                    refs=[{"label": "IMG1", "file": "rf/refs/VID1_tony_frame.png",
                           "role": "supplies only the frame: room, framing, phone position, light and pose"}])
    return job(swapped, talk, likeness=likeness)


def test_the_talk_to_lens_worked_example_lints_clean():
    assert rf_lint.findings(talk_to_lens_job({"tony": "approved"}), "", SETTINGS) == []


def test_a_take_named_for_tony_needs_his_approved_likeness():
    assert ("FAIL", "C12") in found(talk_to_lens_job({}))
