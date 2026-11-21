"""Talking-head wrapper: cue times are written in SOURCE seconds, cuts remove dead air,
and captions, highlights and the contact sheet all have to land on the same output
timeline. These tests pin that mapping down."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import th_lib  # noqa: E402


def words(*pairs):
    return [{"word": w, "start": s, "end": s + 0.3} for w, s in pairs]


def test_time_before_a_cut_is_unchanged():
    assert th_lib.to_output(50.0, [[114.0, 121.9]]) == 50.0


def test_time_after_a_cut_shifts_by_its_length():
    assert th_lib.to_output(131.9, [[114.0, 121.9]]) == pytest.approx(124.0)


def test_time_inside_a_cut_collapses_to_the_cut_start():
    assert th_lib.to_output(118.0, [[114.0, 121.9]]) == pytest.approx(114.0)


def test_multiple_cuts_accumulate_in_any_order():
    assert th_lib.to_output(100.0, [[60.0, 70.0], [10.0, 15.0]]) == pytest.approx(85.0)


def test_captions_drop_words_inside_cuts_and_remap_the_rest():
    w = words(("Before.", 1.0), ("Oops", 5.0), ("After.", 9.0))
    caps = th_lib.build_captions(w, cuts=[[4.0, 8.0]], src_end=20.0)
    assert [c["t"] for c in caps] == ["Before.", "After."]
    assert caps[1]["s"] == pytest.approx(5.0)


def test_captions_break_on_sentence_end_and_word_limit():
    w = words(*[(f"w{i}", i * 0.35) for i in range(9)])
    caps = th_lib.build_captions(w, cuts=[], src_end=20.0, max_words=7)
    assert [len(c["t"].split()) for c in caps] == [7, 2]


def test_caption_fixes_replace_misheard_phrases():
    w = words(("the", 1.0), ("loss", 1.3), ("is", 1.6), ("clear", 1.9))
    caps = th_lib.build_captions(w, cuts=[], src_end=20.0, fixes=[["the loss is", "The law says"]])
    assert caps[0]["t"] == "The law says clear"


def test_captions_never_contain_em_dashes():
    caps = th_lib.build_captions(words(("wait—what", 1.0)), cuts=[], src_end=20.0)
    assert "—" not in caps[0]["t"]


# Real stamps from jobs/20261021-192637-hoa/transcript.json. Parakeet starts lead the
# sound by 0.2 to 0.3 s: "HOA" is heard from about 8.0, "Second," from about 49.6.
HOA_WORDS = [{"word": f" {w}", "start": s, "end": e} for w, s, e in [
    ("HOA", 7.76, 8.64), ("boards.", 8.64, 9.52), ("Two", 9.52, 9.92),
    ("get", 46.12, 46.28), ("conventional", 46.28, 47.0), ("loans.", 47.0, 49.4),
    ("Second,", 49.4, 50.36), ("California", 50.36, 51.0), ("Assembly", 51.0, 51.4),
    ("Bill", 51.48, 51.64), ("25.", 51.88, 52.92), ("This", 52.92, 53.24), ("is", 53.24, 53.48),
    ("law.", 53.48, 54.04), ("Starting", 54.04, 54.44),
    ("your", 72.08, 72.24), ("annual", 72.24, 72.8), ("budget.", 72.8, 74.56),
    ("Now", 74.56, 74.88), ("supporters", 75.04, 75.76), ("say", 75.76, 76.0),
]]
HOA_FIXES = [["FANDE", "Fannie"], ["California Assembly", "California."]]
HOA_CUTS = [[0.0, 7.74], [47.4, 49.38], [51.02, 52.92], [73.0, 74.45]]
# the first render's cuts: each edge sat a hair past a word's start stamp
HOA_OLD_CUTS = [[0.0, 7.85], [47.4, 49.45], [51.02, 52.92], [73.0, 74.45]]


def test_captions_keep_words_whose_start_stamp_sits_just_inside_a_cut():
    caps = th_lib.build_captions(HOA_WORDS, HOA_OLD_CUTS, 115.9, HOA_FIXES)
    texts = [c["t"] for c in caps]
    assert texts[0] == "HOA boards."
    assert "Second, California." in texts


def test_a_kept_word_captions_from_the_cut_end():
    caps = th_lib.build_captions(HOA_WORDS, HOA_OLD_CUTS, 115.9, HOA_FIXES)
    second = next(c for c in caps if c["t"].startswith("Second,"))
    assert caps[0]["s"] == pytest.approx(th_lib.to_output(7.85, HOA_OLD_CUTS))
    assert second["s"] == pytest.approx(round(th_lib.to_output(49.45, HOA_OLD_CUTS), 2))


def test_captions_that_were_right_stay_the_same():
    caps = th_lib.build_captions(HOA_WORDS, HOA_CUTS, 115.9, HOA_FIXES)
    assert caps == [
        {"s": 0.02, "e": 1.93, "t": "HOA boards."},
        {"s": 1.78, "e": 2.33, "t": "Two"},
        {"s": 38.38, "e": 39.83, "t": "get conventional loans."},
        {"s": 39.68, "e": 41.45, "t": "Second, California."},
        {"s": 41.3, "e": 42.57, "t": "This is law."},
        {"s": 42.42, "e": 42.97, "t": "Starting"},
        {"s": 60.46, "e": 61.64, "t": "your annual budget."},
        {"s": 61.49, "e": 63.08, "t": "Now supporters say"},
    ]


def test_a_caption_fix_that_already_restores_a_cut_word_is_not_doubled():
    # jobs/20261017-141711-incognito patched "what" and "can" back in with caption fixes
    w = [{"word": f" {t}", "start": s, "end": e} for t, s, e in [
        ("But", 48.2, 48.44), ("what", 48.44, 48.6), ("I", 48.6, 48.76), ("like", 48.76, 48.92),
        ("about", 48.92, 49.08), ("it", 49.08, 49.24), ("because", 49.32, 49.48),
        ("time,", 56.32, 56.8), ("uh", 56.8, 56.96), ("I", 57.12, 57.44), ("can", 57.44, 57.76),
        ("see", 57.76, 58.08), ("just", 58.08, 58.32),
    ]]
    fixes = [["I like about it", "What I like about it"], ["time, uh see", "time, I can see"]]
    caps = th_lib.build_captions(w, [[44.6, 48.47], [56.86, 57.49]], 100.0, fixes)
    assert [c["t"] for c in caps] == ["What I like about it because", "time, I can see just"]


def test_a_word_mostly_inside_a_cut_still_drops():
    w = [{"word": "gone", "start": 51.5, "end": 53.0}, {"word": "kept.", "start": 53.0, "end": 53.4}]
    caps = th_lib.build_captions(w, [[51.02, 52.92]], 60.0)
    assert [c["t"] for c in caps] == ["kept."]


def test_cut_edge_flags_both_hoa_words_and_suggests_the_edge_that_fixed_them():
    hits = th_lib.cut_edge_words(HOA_WORDS, HOA_OLD_CUTS, 115.9)
    assert [(h["word"], h["edge"], h["fate"], h["suggest"]) for h in hits] == [
        ("HOA", "end", "kept", 7.74),
        ("Second,", "end", "kept", 49.38),
    ]


def test_cut_edge_is_quiet_for_the_hoa_job_cuts():
    assert th_lib.cut_edge_words(HOA_WORDS, HOA_CUTS, 115.9) == []


def test_cut_edge_flags_a_word_whose_tail_runs_into_a_cut():
    w = [{"word": "almost", "start": 10.0, "end": 10.3}]
    hits = th_lib.cut_edge_words(w, [[10.1, 12.0]], 20.0)
    assert [(h["edge"], h["fate"], h["suggest"]) for h in hits] == [("start", "clipped", 10.32)]


def test_cut_edge_flags_a_short_word_dropped_just_before_a_cut_end():
    w = [{"word": "uh,", "start": 11.8, "end": 11.95}]
    hits = th_lib.cut_edge_words(w, [[10.0, 12.0]], 20.0)
    assert [(h["edge"], h["fate"], h["suggest"]) for h in hits] == [("end", "dropped", 11.78)]


def test_cut_edge_ignores_words_past_the_source_end():
    w = [{"word": "after", "start": 11.9, "end": 12.4}]
    assert th_lib.cut_edge_words(w, [[10.0, 12.0]], 11.0) == []


def test_find_phrase_ignores_case_and_punctuation():
    w = words(("It's", 1.0), ("called", 1.4), ("SB", 2.0), ("326.", 2.4))
    assert th_lib.find_phrase(w, "sb 326") == [2.0]


def test_suggest_cuts_only_flags_long_silences_and_keeps_breathing_room():
    silences = [(8.2, 9.4), (113.4, 121.9)]
    assert th_lib.suggest_cuts(silences, min_len=2.5, pad=0.35) == [[113.75, 121.55]]


def test_cue_times_collects_every_at_in_order_without_duplicates():
    job = {"sections": [{"evidence": [28, 38], "blocks": [
        {"type": "statute", "cite": "x", "parts": ["a", {"hl": "b", "at": 29.8}]},
        {"type": "list", "items": [{"name": "n", "at": 31.0}]},
        {"type": "strike", "value": "2026", "note": "n", "at": 30.0, "noteAt": 31.0},
    ]}]}
    assert th_lib.cue_times(job) == [29.8, 30.0, 31.0]


def test_validate_rejects_a_cue_outside_its_evidence_window():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [], "sections": [
        {"evidence": [10, 20], "blocks": [{"type": "note", "text": "late", "at": 25}]}]}
    assert any("outside" in p for p in th_lib.validate(job))


def test_validate_rejects_a_cue_that_lands_inside_a_cut():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [[12, 15]], "sections": [
        {"evidence": [10, 20], "blocks": [{"type": "note", "text": "gone", "at": 13}]}]}
    assert any("cut" in p for p in th_lib.validate(job))


def test_validate_passes_a_clean_job():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [], "sections": [
        {"evidence": [10, 20], "blocks": [{"type": "note", "text": "ok", "at": 12}]}]}
    assert th_lib.validate(job) == []


def test_whisper_split_tokens_are_glued_back_before_fixes_run():
    # Whisper emits "1120", "-8" and "70", "%" as separate words
    w = words(("federal", 1.0), ("1120", 1.3), ("-8", 1.6), ("in", 1.9), ("70", 2.2), ("%", 2.5))
    caps = th_lib.build_captions(w, cuts=[], src_end=20.0, fixes=[["1120-8 in", "1120-H, a"]])
    assert caps[0]["t"] == "federal 1120-H, a 70%"


def test_whisper_split_dollars_and_decimals_are_glued_back():
    # Whisper emits "$4", ",500" and "8", ".7", "%" as separate words
    w = words(("or", 1.0), ("$4", 1.3), (",500,", 1.6), ("max", 1.9), ("8", 2.2), (".7", 2.5), ("%", 2.8))
    caps = th_lib.build_captions(w, cuts=[], src_end=20.0)
    assert caps[0]["t"] == "or $4,500, max 8.7%"


def test_a_comma_word_after_a_non_number_is_not_glued():
    w = words(("Yes", 1.0), (",and", 1.3))
    caps = th_lib.build_captions(w, cuts=[], src_end=20.0)
    assert caps[0]["t"] == "Yes ,and"


def clean_job(**extra):
    return {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [[30, 35]], "sections": [], **extra}


def test_a_cutaway_inside_the_video_is_valid():
    assert th_lib.validate(clean_job(cutaways=[{"from": 10, "to": 14, "file": "roof.mp4"}])) == []


def test_a_cutaway_that_overlaps_a_cut_is_rejected():
    problems = th_lib.validate(clean_job(cutaways=[{"from": 28, "to": 32, "file": "roof.mp4"}]))
    assert any("cut" in p for p in problems)


def test_a_cutaway_past_the_end_or_backwards_is_rejected():
    assert th_lib.validate(clean_job(cutaways=[{"from": 58, "to": 70, "file": "a.mp4"}]))
    assert th_lib.validate(clean_job(cutaways=[{"from": 20, "to": 12, "file": "a.mp4"}]))


def test_overlapping_cutaways_are_rejected():
    problems = th_lib.validate(clean_job(cutaways=[
        {"from": 10, "to": 14, "file": "a.mp4"}, {"from": 13, "to": 16, "file": "b.png"}]))
    assert any("overlap" in p for p in problems)


def test_the_contact_sheet_shows_every_cutaway():
    job = clean_job(cutaways=[{"from": 10, "to": 14, "file": "a.mp4"}])
    assert 12.0 in th_lib.sheet_moments(job)


def test_job_files_lists_every_asset_the_render_needs():
    job = clean_job(hook={"from": 0, "to": 8, "broll": ["a.png", "b.mp4"], "title": "x"},
                    cutaways=[{"from": 10, "to": 14, "file": "roof.mp4"}])
    assert th_lib.job_files(job) == ["footage.mp4", "a.png", "b.mp4", "roof.mp4"]


def pacing_job(**extra):
    return {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [], "sections": [
        {"tag": {"n": 1, "topic": "q", "from": 10, "to": 13}, "evidence": [13, 40],
         "blocks": [{"type": "note", "text": "a", "at": 15}, {"type": "note", "text": "b", "at": 19}]}], **extra}


def test_a_long_stretch_with_nothing_changing_is_flagged():
    gaps = th_lib.static_stretches(pacing_job(), max_gap=7)
    assert (19, 40) in [(g["from"], g["to"]) for g in gaps]


def test_stretches_at_or_under_the_limit_are_fine():
    gaps = th_lib.static_stretches(pacing_job(), max_gap=7)
    assert all(g["to"] - g["from"] > 7 for g in gaps)
    assert (15, 19) not in [(g["from"], g["to"]) for g in gaps]


def test_a_cutaway_breaks_up_a_long_stretch():
    job = pacing_job(cutaways=[{"from": 25, "to": 29, "file": "a.png"}, {"from": 34, "to": 37, "file": "b.png"}])
    spans = [(g["from"], g["to"]) for g in th_lib.static_stretches(job, max_gap=7)]
    assert (19, 40) not in spans and not any(19 <= a and b <= 40 for a, b in spans)


def test_dead_air_that_gets_cut_does_not_count_as_static_time():
    job = pacing_job(cuts=[[20, 38]])
    spans = [(g["from"], g["to"]) for g in th_lib.static_stretches(job, max_gap=7)]
    assert (19, 40) not in spans


def test_each_flagged_stretch_says_what_is_on_screen():
    gaps = th_lib.static_stretches(pacing_job(), max_gap=7)
    by_span = {(g["from"], g["to"]): g["showing"] for g in gaps}
    assert by_span[(19, 40)] == "evidence panel"
    assert by_span[(0, 10)] == "Tony full frame"


def test_srt_numbers_cues_and_formats_timestamps():
    srt = th_lib.build_srt([{"s": 0.0, "e": 2.5, "t": "Hello there."}, {"s": 62.25, "e": 64.0, "t": "Second line."}])
    assert srt == ("1\n00:00:00,000 --> 00:00:02,500\nHello there.\n\n"
                   "2\n00:01:02,250 --> 00:01:04,000\nSecond line.\n\n")


def test_srt_cues_never_overlap_the_next_one():
    srt = th_lib.build_srt([{"s": 1.0, "e": 3.2, "t": "a"}, {"s": 3.0, "e": 4.0, "t": "b"}])
    assert "00:00:01,000 --> 00:00:03,000" in srt


def test_chapters_start_at_zero_and_follow_the_question_tags_on_the_output_timeline():
    job = {"cuts": [[0, 2], [20, 25]], "srcEnd": 100, "sections": [
        {"tag": {"n": 1, "topic": "Your last board election", "from": 12, "to": 15}, "evidence": [15, 19], "blocks": []},
        {"tag": {"n": 2, "topic": "The balcony inspection", "from": 30, "to": 33}, "evidence": [33, 50], "blocks": []},
        {"evidence": [60, 90], "blocks": [], "chapter": "How to read your answers"}]}
    assert th_lib.chapters(job, intro="Self-manage or hire?") == [
        (0.0, "Self-manage or hire?"), (10.0, "1. Your last board election"),
        (23.0, "2. The balcony inspection"), (53.0, "How to read your answers")]


def test_youtube_needs_at_least_three_chapters_ten_seconds_apart():
    job = {"cuts": [], "srcEnd": 100, "sections": [
        {"tag": {"n": 1, "topic": "A", "from": 4, "to": 6}, "evidence": [6, 9], "blocks": []},
        {"tag": {"n": 2, "topic": "B", "from": 30, "to": 33}, "evidence": [33, 50], "blocks": []}]}
    labels = [label for _, label in th_lib.chapters(job, intro="Intro")]
    assert labels == ["Intro", "2. B"]  # the chapter 4s after the intro is dropped, YouTube wants 10s minimum


def test_several_lower_thirds_each_count_as_a_picture_change():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 30, "cuts": [], "sections": [],
           "lowerThird": [{"from": 2, "to": 8, "name": "Tony", "line": "a"}, {"from": 16, "to": 24, "name": "Call", "line": "b"}]}
    spans = [(g["from"], g["to"]) for g in th_lib.static_stretches(job, max_gap=7)]
    assert (2, 16) in spans and (16, 30) in spans and (2, 30) not in spans


def test_a_single_lower_third_object_still_works():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 12, "cuts": [], "sections": [],
           "lowerThird": {"from": 6, "to": 10, "name": "Tony", "line": "a"}}
    assert th_lib.static_stretches(job, max_gap=7) == []


def test_the_contact_sheet_shows_every_name_bar_and_the_counter():
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60, "cuts": [], "sections": [],
           "counter": {"from": 10, "to": 13, "count": 5},
           "lowerThird": [{"from": 20, "to": 26, "name": "Tony", "line": "a"}, {"from": 50, "to": 58, "name": "Call", "line": "b"}]}
    moments = th_lib.sheet_moments(job)
    assert 11.2 in moments and 21.5 in moments and 51.5 in moments


# ---- studio style (Wes McDowell format): punch-ins, kinetic phrases, stat icon rows ----

def studio_job(**extra):
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60.0, "cuts": [[20.0, 22.0]],
           "style": "studio", "sections": []}
    return {**job, **extra}


def test_bigstat_icon_row_cue_counts_as_a_cue():
    block = {"type": "bigstat", "value": "1 in 4", "at": 10.0, "icons": {"kind": "person", "of": 4, "filled": 1, "at": 11.5}}
    assert th_lib._block_times(block) == [10.0, 11.5]


def test_steps_items_are_cues():
    block = {"type": "steps", "title": "x", "items": [{"text": "a", "at": 3.0}, {"text": "b", "at": 5.0}]}
    assert th_lib._block_times(block) == [3.0, 5.0]


def test_punch_boundaries_are_cut_points_plus_explicit_punches():
    job = studio_job(punches=[40.0])
    assert th_lib.punch_boundaries(job) == [22.0, 40.0]


def test_evidence_style_has_no_punches():
    job = studio_job(style="evidence", punches=[40.0])
    assert th_lib.punch_boundaries(job) == []


def test_punch_off_disables_them_in_studio():
    job = studio_job(punch=False, punches=[40.0])
    assert th_lib.punch_boundaries(job) == []


def test_punches_and_phrases_break_up_a_static_stretch():
    bare = studio_job(style="evidence", cuts=[])
    assert th_lib.static_stretches(bare)
    busy = studio_job(cuts=[], punches=[6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0],
                      phrases=[{"from": 52.0, "to": 55.0, "text": "x"}])
    assert th_lib.static_stretches(busy) == []


def test_phrase_inside_a_cut_is_a_problem():
    job = studio_job(phrases=[{"from": 20.5, "to": 23.0, "text": "oops"}])
    assert any("phrase" in p for p in th_lib.validate(job))


def test_phrase_with_bad_range_is_a_problem():
    job = studio_job(phrases=[{"from": 30.0, "to": 29.0, "text": "x"}])
    assert any("phrase" in p for p in th_lib.validate(job))


def test_unknown_theme_is_a_problem():
    job = studio_job(sections=[{"evidence": [1.0, 5.0], "theme": "neon", "blocks": []}])
    assert any("theme" in p for p in th_lib.validate(job))


def test_sheet_shows_each_phrase():
    job = studio_job(phrases=[{"from": 30.0, "to": 33.0, "text": "x"}])
    assert 31.2 in [round(m, 1) for m in th_lib.sheet_moments(job)]


def test_screen_block_files_are_required_in_public():
    job = studio_job(sections=[{"evidence": [1.0, 5.0], "full": True, "blocks": [{"type": "screen", "file": "site.png", "at": 1.5}]}])
    assert "site.png" in th_lib.job_files(job)


# ---- voice enhancement: denoise, EQ, compression, loudness to YouTube's -14 LUFS ----

def test_voice_chain_order_cleanup_then_tone_then_dynamics():
    chain = th_lib.voice_chain(noise_floor=-44.0)
    names = [f.split("=")[0] for f in chain.split(",")]
    assert names[0] == "highpass"
    assert names.index("afftdn") < names.index("equalizer") < names.index("acompressor")
    assert names[-1] == "alimiter"


def test_voice_chain_uses_the_measured_noise_floor():
    assert "nf=-44" in th_lib.voice_chain(noise_floor=-44.2)


def test_voice_chain_clamps_a_silly_noise_floor():
    assert "nf=-20" in th_lib.voice_chain(noise_floor=-3.0)
    assert "nf=-80" in th_lib.voice_chain(noise_floor=-120.0)


def _band_gain(chain, freq):
    for f in chain.split(","):
        if f.startswith("equalizer=") and f"f={freq}:" in f:
            return float(f.split("g=")[1])
    return 0.0


def test_broadcast_adds_chest_warmth():
    default = th_lib.voice_chain(noise_floor=-44.0, preset="broadcast")
    assert _band_gain(default, 120) >= 3
    assert _band_gain(th_lib.voice_chain(-44.0, preset="clean"), 120) == 0


def test_broadcast_keeps_the_mud_cut_and_softens_the_air():
    broadcast = th_lib.voice_chain(-44.0, preset="broadcast")
    clean = th_lib.voice_chain(-44.0, preset="clean")
    assert _band_gain(broadcast, 280) < 0
    assert _band_gain(broadcast, 11000) < _band_gain(clean, 11000)


def test_unknown_voice_preset_raises():
    import pytest as _pt
    with _pt.raises(ValueError):
        th_lib.voice_chain(-44.0, preset="chipmunk")


def test_studio_is_the_default_and_matches_adobe_direction():
    studio = th_lib.voice_chain(-44.0)
    assert studio == th_lib.voice_chain(-44.0, preset="studio")
    assert _band_gain(studio, 4000) <= -3      # Adobe cut 4 kHz about 4 dB
    assert _band_gain(studio, 8000) < 0        # and 8 kHz about 3 dB
    assert _band_gain(studio, 125) > 0         # slight warmth
    assert "agate=" in studio                  # silent pauses, like Adobe
    names = [f.split("=")[0] for f in studio.split(",")]
    assert names.index("acompressor") < names.index("agate") < names.index("alimiter")


def test_studio_compresses_gently():
    comp = [f for f in th_lib.voice_chain(-44.0).split(",") if f.startswith("acompressor")][0]
    assert float(comp.split("ratio=")[1].split(":")[0]) <= 2.0


def test_external_audio_must_match_the_footage_length():
    assert th_lib.external_audio_problem(300.0, 300.02) is None
    assert "longer" in th_lib.external_audio_problem(300.0, 301.5)
    assert "shorter" in th_lib.external_audio_problem(300.0, 290.0)


def test_external_level_chain_lifts_to_target_and_limits_peaks():
    chain = th_lib.external_level_chain(-24.36)
    assert chain.startswith("volume=10.4dB")
    assert "alimiter=limit=0.79" in chain
    assert th_lib.external_level_chain(-24.36, extra_db=1.5).startswith("volume=11.9dB")


def test_local_ai_eq_matches_the_fitted_adobe_curve():
    chain = th_lib.local_ai_eq_chain()
    assert chain.count("equalizer=") == 9
    assert "f=4000:t=q:w=1.0:g=-6.7" in chain


def test_ai_and_adobe_both_count_as_finished_voice():
    assert th_lib.voice_is_final({"voice": "ai"})
    assert th_lib.voice_is_final({"voice": "adobe"})
    assert not th_lib.voice_is_final({"voice": "studio"})
    assert not th_lib.voice_is_final({})


def test_loudnorm_second_pass_feeds_back_the_measurement():
    measured = {"input_i": "-19.2", "input_tp": "-0.4", "input_lra": "5.1", "input_thresh": "-29.6", "target_offset": "0.3"}
    f = th_lib.loudnorm_pass2(measured)
    assert f.startswith("loudnorm=I=-14")
    assert "measured_I=-19.2" in f and "measured_TP=-0.4" in f and "offset=0.3" in f
    assert "linear=true" in f


# ---- background music: a bed under Tony's voice that ducks when he talks ----

def test_music_filter_ducks_the_bed_under_the_voice():
    fc = th_lib.music_filter(gain_db=-14.0, total=342.4)
    assert "sidechaincompress" in fc
    assert fc.index("asplit") < fc.index("sidechaincompress") < fc.index("amix")


def test_music_filter_keeps_voice_level_and_fades_out_at_the_end():
    fc = th_lib.music_filter(gain_db=-14.0, total=342.4, fade_out=3.0)
    assert "normalize=0" in fc
    assert "afade=t=out:st=339.400:d=3.000" in fc
    assert "volume=-14.0dB" in fc


def test_music_gain_brings_the_track_to_the_bed_level():
    assert th_lib.music_gain(track_lufs=-12.0, bed_lufs=-30.0) == -18.0


# ---- news style (news desk format): typed text over Tony, cutout stickers, framed photos ----

def news_job(**extra):
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 60.0, "cuts": [[20.0, 22.0]],
           "style": "news", "sections": []}
    return {**job, **extra}


def test_an_unknown_style_is_a_problem():
    assert any("style" in p for p in th_lib.validate(news_job(style="newz")))


def test_news_style_punches_in_like_studio():
    assert th_lib.punch_boundaries(news_job(punches=[40.0])) == [22.0, 40.0]


def test_a_clean_typed_line_is_valid():
    job = news_job(typed=[{"from": 5.0, "to": 9.0, "text": "The date was February 20th",
                           "hl": [{"text": "February 20th", "color": "green"}]}])
    assert th_lib.validate(job) == []


def test_typed_line_that_runs_into_a_cut_is_a_problem():
    job = news_job(typed=[{"from": 19.0, "to": 23.0, "text": "x"}])
    assert any("typed" in p for p in th_lib.validate(job))


def test_typed_highlight_must_be_words_from_the_line():
    job = news_job(typed=[{"from": 5.0, "to": 9.0, "text": "Signed August 22", "hl": [{"text": "August 23", "color": "green"}]}])
    assert any("highlight" in p for p in th_lib.validate(job))


def test_typed_highlight_color_must_be_known():
    job = news_job(typed=[{"from": 5.0, "to": 9.0, "text": "Signed August 22", "hl": [{"text": "August 22", "color": "purple"}]}])
    assert any("color" in p for p in th_lib.validate(job))


def test_two_typed_lines_cannot_be_up_at_once():
    job = news_job(typed=[{"from": 5.0, "to": 9.0, "text": "a"}, {"from": 8.0, "to": 12.0, "text": "b"}])
    assert any("overlap" in p for p in th_lib.validate(job))


def test_typed_lines_and_stickers_break_up_a_static_stretch():
    job = news_job(cuts=[], punch=False, srcEnd=20.0,
                   typed=[{"from": 3.0, "to": 8.0, "text": "a"}],
                   stickers=[{"from": 12.0, "to": 16.0, "file": "gavel.png"}])
    assert th_lib.static_stretches(job) == []


def test_sticker_files_are_required_in_public():
    job = news_job(stickers=[{"from": 12.0, "to": 16.0, "file": "gavel.png"}])
    assert "gavel.png" in th_lib.job_files(job)


def test_sticker_with_unknown_position_is_a_problem():
    job = news_job(stickers=[{"from": 12.0, "to": 16.0, "file": "gavel.png", "pos": "middle"}])
    assert any("sticker" in p for p in th_lib.validate(job))


def test_sticker_inside_a_cut_is_a_problem():
    job = news_job(stickers=[{"from": 20.5, "to": 24.0, "file": "gavel.png"}])
    assert any("sticker" in p for p in th_lib.validate(job))


def test_the_contact_sheet_shows_typed_lines_fully_typed_and_each_sticker():
    job = news_job(typed=[{"from": 5.0, "to": 9.0, "text": "a"}], stickers=[{"from": 30.0, "to": 34.0, "file": "g.png"}])
    moments = [round(m, 1) for m in th_lib.sheet_moments(job)]
    assert 8.7 in moments and 31.0 in moments


def test_cutaway_fit_must_be_cover_or_blur():
    job = news_job(cutaways=[{"from": 10, "to": 14, "file": "p.jpg", "fit": "stretch"}])
    assert any("fit" in p for p in th_lib.validate(job))
    assert th_lib.validate(news_job(cutaways=[{"from": 10, "to": 14, "file": "p.jpg", "fit": "blur"}])) == []


def test_pullquote_logo_is_a_required_file_and_its_cue_counts():
    block = {"type": "pullquote", "text": "q", "source": "Deseret News", "logo": "deseret.png", "at": 3.0}
    job = news_job(sections=[{"evidence": [2.0, 8.0], "full": True, "blocks": [block]}])
    assert "deseret.png" in th_lib.job_files(job)
    assert th_lib.cue_times(job) == [3.0]


def test_explicit_chapters_join_the_timeline_in_order():
    job = news_job(cuts=[], chapters=[{"at": 40.0, "label": "The lawsuit"}],
                   sections=[{"evidence": [12.0, 18.0], "chapter": "The bill", "blocks": []}])
    assert th_lib.chapters(job, intro="Intro") == [(0.0, "Intro"), (12.0, "The bill"), (40.0, "The lawsuit")]
