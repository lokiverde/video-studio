"""Multi-take pipeline: Parakeet transcripts in Whisper's shape, script-section alignment
across takes, splice plans, and the post-render QC that runs before Tony sees a file."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import takes  # noqa: E402
import th_lib  # noqa: E402
import transcribe  # noqa: E402


def tok(text, start, end, conf=1.0):
    return {"text": text, "start": start, "end": end, "duration": end - start, "confidence": conf}


PARAKEET = {
    "text": "Why are we here? Number five.",
    "sentences": [
        {"text": "Why are we here?", "start": 0.5, "end": 1.9, "confidence": 0.9,
         "tokens": [tok(" W", 0.5, 0.6, 0.9), tok("hy", 0.6, 0.8), tok(" are", 0.8, 1.0), tok(" we", 1.0, 1.2),
                    tok(" here", 1.2, 1.6, 0.7), tok("?", 1.6, 1.9)]},
        {"text": "Number five.", "start": 2.4, "end": 3.2, "confidence": 1.0,
         "tokens": [tok(" Number", 2.4, 2.8), tok(" five", 2.8, 3.1), tok(".", 3.1, 3.2)]},
    ],
}


def test_parakeet_tokens_merge_into_whisper_words():
    out = transcribe.parakeet_to_whisper(PARAKEET)
    words = [w for s in out["segments"] for w in s["words"]]
    assert [w["word"] for w in words] == [" Why", " are", " we", " here?", " Number", " five."]
    assert words[0]["start"] == 0.5 and words[0]["end"] == 0.8
    assert words[3]["probability"] == 0.7  # the weakest piece decides


def test_parakeet_segments_keep_sentence_text_and_bounds():
    out = transcribe.parakeet_to_whisper(PARAKEET)
    assert [s["text"].strip() for s in out["segments"]] == ["Why are we here?", "Number five."]
    assert out["segments"][1]["start"] == 2.4 and out["segments"][1]["end"] == 3.2


def test_a_sentence_without_tokens_is_skipped():
    data = {"sentences": [{"text": "", "start": 0, "end": 0, "tokens": []}, *PARAKEET["sentences"]]}
    assert len(transcribe.parakeet_to_whisper(data)["segments"]) == 2


SCRIPT = """---
title: x
---

## Filming notes
Ignore me.

# Why Are We Here?

## HOOK

Why are we here in twenty twenty-six? We counted it.

## #5 Cost

Number five, the cost. Only eighteen were about money.

## END CTA

Book a free call with me.

---

## On screen (do not read aloud)
- quote
"""


def test_script_sections_come_from_the_read_aloud_body_only():
    secs = takes.script_sections(SCRIPT)
    assert [s["name"] for s in secs] == ["HOOK", "#5 Cost", "END CTA"]
    assert secs[1]["words"][:3] == ["number", "five", "the"]


def test_spoken_numbers_and_digits_normalize_the_same():
    assert takes.norm_words("Number 5, in 2026 we read 1,757!") == [
        "number", "five", "in", "twenty", "twenty", "six", "we", "read", "1757"]
    assert takes.norm_words("22 miles") == takes.norm_words("twenty-two miles")


def test_a_common_word_said_twice_is_not_a_restart():
    script = takes.norm_words("If that's the part pulling you back, I built a quiz for it. Which city fits?")
    take = takes.norm_words("If that's a part pulling you back, I built a quiz for it. Which city fits?")
    assert takes.restarts(take, script) == []


def test_a_real_restart_is_found():
    script = takes.norm_words("And number one beat this one by three comments.")
    take = takes.norm_words("And number one beats the one by three comments. And number one beats this one by three comments.")
    assert takes.restarts(take, script) == [(0, 9)]


def W(text, start=0.0, step=0.3):
    return [{"word": f" {w}", "start": round(start + i * step, 2), "end": round(start + i * step + 0.25, 2)}
            for i, w in enumerate(text.split())]


def test_attempts_find_every_restart_and_score_the_complete_one_higher():
    section = takes.script_sections(SCRIPT)[1]
    words = W("number five the cost only eighteen", 10) + W("number five the cost only eighteen were about money", 20)
    found = takes.find_attempts(words, section)
    assert [round(a["start"], 2) for a in found] == [10.0, 20.0]
    assert found[1]["score"] > found[0]["score"]


def test_propose_prefers_the_best_score_and_breaks_ties_toward_the_main_take():
    sections = takes.script_sections(SCRIPT)
    hook = "why are we here in 2026 we counted it"
    five = "number five the cost only eighteen were about money"
    end = "book a free call with me"
    main = W(hook, 1) + W(five, 10) + W(end, 30)
    alt = W(hook, 1) + W("number five the cost", 10) + W(end, 30)
    plan = takes.propose(sections, {"main": main, "alt": alt}, main="main")
    assert [p["take"] for p in plan] == ["main", "main", "main"]
    worse_main = W("why are we", 1) + W(five, 10) + W(end, 30)
    plan = takes.propose(sections, {"main": worse_main, "alt": alt}, main="main")
    assert plan[0]["take"] == "alt"


def test_splice_points_are_running_sums_of_segment_lengths():
    segs = [{"take": "a", "from": 1.0, "to": 11.0}, {"take": "b", "from": 5.0, "to": 7.5}, {"take": "a", "from": 20.0, "to": 21.0}]
    assert takes.splice_points(segs) == [10.0, 12.5]


def test_qc_flags_black_frames_long_silence_and_av_drift():
    problems = th_lib.qc_problems(black=[(10.0, 10.8)], silences=[(30.0, 33.5)], video_s=100.0, audio_s=99.5, tail_ok=3.0)
    joined = " ".join(problems)
    assert "black" in joined and "silence" in joined and "drift" in joined


def test_qc_ignores_silence_inside_the_end_card_and_tiny_blips():
    assert th_lib.qc_problems(black=[(5.0, 5.1)], silences=[(97.5, 100.0)], video_s=100.0, audio_s=100.05, tail_ok=3.0) == []


def test_qc_passes_a_pause_tony_made_and_flags_silence_the_render_made():
    tony = [(119.55, 121.65)]                        # in the source audio, mapped to the output
    same_pause = [(119.6, 121.7)]                    # the render keeps it, a few ms later
    assert th_lib.qc_problems(black=[], silences=same_pause, video_s=300.0, audio_s=300.0, tail_ok=3.0, expected=tony) == []
    dropout = [(200.0, 203.0)]                       # nothing in the source explains this one
    assert th_lib.qc_problems(black=[], silences=dropout, video_s=300.0, audio_s=300.0, tail_ok=3.0, expected=tony)
    joined = [(119.6, 124.0)]                        # a cut that runs a pause into more dead air
    assert th_lib.qc_problems(black=[], silences=joined, video_s=300.0, audio_s=300.0, tail_ok=3.0, expected=tony)


def test_qc_passes_tonys_last_pause_running_into_the_end_card():
    tony = [(269.5, 271.44)]                         # his last pause, up to the end of speech
    into_card = [(269.5, 274.0)]                     # then the silent 2.5 s end card
    assert th_lib.qc_problems(black=[], silences=into_card, video_s=273.96, audio_s=273.96, tail_ok=3.0, expected=tony) == []
    mid_pause = [(150.0, 152.0)]
    early = [(150.0, 155.0)]                         # starts in a pause but ends far from the card
    assert th_lib.qc_problems(black=[], silences=early, video_s=273.96, audio_s=273.96, tail_ok=3.0, expected=mid_pause)
    to_the_end = [(150.0, 274.0)]                    # a mid-video pause that never comes back
    assert th_lib.qc_problems(black=[], silences=to_the_end, video_s=273.96, audio_s=273.96, tail_ok=3.0, expected=mid_pause)


def test_qc_counts_only_the_silence_before_the_end_card():
    # tail_ok is the card plus 0.5 s, so the card starts at video_s - tail_ok + 0.5 = 271.46
    last_breath = [(269.5, 274.0)]                   # 1.96 s before the card, the rest is the card
    assert th_lib.qc_problems(black=[], silences=last_breath, video_s=273.96, audio_s=273.96, tail_ok=3.0) == []
    dead_air = [(268.0, 274.0)]                      # 3.46 s of nothing before the card
    assert th_lib.qc_problems(black=[], silences=dead_air, video_s=273.96, audio_s=273.96, tail_ok=3.0)


def test_an_attempt_never_runs_into_the_next_section():
    sections = takes.script_sections(SCRIPT)
    hook = W("why are we here in 2026 we counted it", 1)
    five = W("number five the cost only eighteen were about money", 10)
    stretched = [dict(w) for w in hook]
    stretched[-1]["end"] = 9.9          # Parakeet stretches the last word through the pause
    plan = takes.propose(sections, {"main": stretched + five + W("book a free call with me", 30)}, main="main")
    assert plan[0]["to"] < 10.0


def test_a_restarted_line_inside_a_section_is_dropped():
    sections = takes.script_sections(SCRIPT)
    hook = W("why are we here in 2026 we counted it", 1)
    five = (W("number five the cost only eighteen", 10) + W("only eighteen were about", 13)
            + W("only eighteen were about money", 20))
    plan = takes.propose(sections, {"main": hook + five + W("book a free call with me", 30)}, main="main")
    five_plan = plan[1]
    assert five_plan["drop"] and five_plan["drop"][0][0] < 13.0 + 0.01 and five_plan["drop"][-1][1] <= 20.0
    segs = takes.segments_for(five_plan)
    assert len(segs) == 2 and segs[0]["to"] <= 13.0 and segs[1]["from"] >= 19.7


def test_a_shared_word_in_an_ad_lib_is_not_a_restart():
    script = takes.norm_words("Ride on a Tuesday. A cheaper house doesn't come with your Saturdays.")
    take = takes.norm_words("Ride on a Tuesday. Not me, that's a long way. A cheaper house doesn't come with your Saturdays.")
    assert takes.restarts(take, script) == []


def test_touching_segments_from_one_take_merge_into_one():
    segs = [{"take": "a", "from": 1.0, "to": 64.2}, {"take": "a", "from": 64.0, "to": 132.0},
            {"take": "a", "from": 132.4, "to": 179.4}, {"take": "a", "from": 207.5, "to": 239.9},
            {"take": "b", "from": 211.6, "to": 269.8}]
    merged = takes.merge_segments(segs)
    assert [(s["take"], s["from"], s["to"]) for s in merged] == [("a", 1.0, 179.4), ("a", 207.5, 239.9), ("b", 211.6, 269.8)]
