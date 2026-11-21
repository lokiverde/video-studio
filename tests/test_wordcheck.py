"""wordcheck: re-transcribe what we made and compare it with what should be there.
Pins the token normalisation (numbers, money, contractions) and which differences count
as a problem: a word lost next to a cut, a skipped or repeated TTS phrase, a swallowed
last word. Single-word ASR disagreements away from a join are noise and only counted."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import wordcheck  # noqa: E402


def heard(*pairs):
    """Heard tokens with output times, one word every 0.3 s from the given start."""
    out = []
    for text, start in pairs:
        for i, w in enumerate(wordcheck.tokens(text)):
            out.append({"w": w, "s": start + i * 0.3, "e": start + i * 0.3 + 0.25})
    return out


def src(*pairs):
    return [{"word": " " + w, "start": s, "end": s + 0.25} for w, s in pairs]


# --- tokens -------------------------------------------------------------------------

def test_tokens_lowercase_and_drop_punctuation():
    assert wordcheck.tokens("Hello, World. It's fine!") == ["hello", "world", "its", "fine"]


def test_tokens_spell_out_numbers_and_money():
    assert wordcheck.tokens("$2,500 rent") == ["two", "thousand", "five", "hundred", "dollars", "rent"]
    assert wordcheck.tokens("15% of 1,757") == [
        "fifteen", "percent", "of", "one", "thousand", "seven", "hundred", "fifty", "seven"]


def test_tokens_split_hyphens_and_slashes():
    assert wordcheck.tokens("move-out 24/7") == ["move", "out", "twenty", "four", "seven"]


def test_tokens_split_a_spoken_domain():
    """california-board, 2026-10-29: Parakeet wrote the CTA as one dotted token."""
    assert wordcheck.tokens("quiz.siteone.com") == ["quiz", "siteone", "com"]
    assert wordcheck.tokens("2.5 percent") == ["two", "point", "five", "percent"]


def test_regrouped_letters_are_not_a_problem():
    """hermosabeach, 2026-10-29: "guest stays" heard as "guests stay" next to a cut."""
    expected = [{"w": w, "s": 14.2, "e": 14.5} for w in ["guest", "stays"]]
    assert wordcheck.differences(expected, heard(("guests stay", 14.2))) == []


def test_one_word_swap_is_never_treated_as_regrouping():
    """A clipped "t" turns can't into can: that must still show up at a join."""
    words = src(("you", 1.0), ("can't", 1.3), ("stay", 4.0))
    exp = wordcheck.expected_final(words, cuts=[[1.6, 3.9]], src_end=10.0)
    problems, _ = wordcheck.final_problems(exp, heard(("you can stay", 1.0)), wordcheck.joins([[1.6, 3.9]]))
    assert len(problems) == 1 and "cant" in problems[0]


def test_word_starting_just_before_a_cut_is_expected_gone():
    """HOA, 2026-10-21: "Assembly" began 0.02 s before the cut and the cut took the rest."""
    words = [{"word": " California", "start": 50.36, "end": 51.0}, {"word": " Assembly", "start": 51.0, "end": 51.4},
             {"word": " This", "start": 52.92, "end": 53.24}]
    exp = wordcheck.expected_final(words, cuts=[[51.02, 52.92]], src_end=60.0)
    assert [e["w"] for e in exp] == ["california", "this"]


def test_number_spelling_disagreement_is_not_a_problem():
    expected = [{"w": w, "s": 0.0, "e": 0.1} for w in wordcheck.tokens("it costs $2,500 a month")]
    got = heard(("it costs twenty five hundred dollars a month", 0.0))
    assert wordcheck.differences(expected, got) == []


# --- talking head final ------------------------------------------------------------

def test_expected_final_drops_cut_words_and_moves_the_rest_to_output_time():
    words = src(("Before", 1.0), ("oops", 5.0), ("after", 9.0))
    exp = wordcheck.expected_final(words, cuts=[[4.0, 8.0]], src_end=20.0)
    assert [e["w"] for e in exp] == ["before", "after"]
    assert exp[1]["s"] == 5.0


def test_joins_are_output_times_of_each_cut():
    assert wordcheck.joins([[4.0, 8.0], [20.0, 22.0]]) == [4.0, 16.0]


def test_identical_final_has_no_problems():
    words = src(("the", 1.0), ("rent", 1.3), ("went", 1.6), ("up", 1.9))
    exp = wordcheck.expected_final(words, cuts=[], src_end=10.0)
    problems, minor = wordcheck.final_problems(exp, heard(("the rent went up", 1.0)), joins=[])
    assert problems == [] and minor == 0


def test_word_lost_at_a_join_is_a_problem():
    words = src(("first", 1.0), ("we", 1.3), ("cut", 6.0), ("here", 6.3), ("today", 6.6))
    cuts = [[2.0, 5.5]]
    exp = wordcheck.expected_final(words, cuts, src_end=10.0)   # cut lands at output 2.0
    got = heard(("first we", 1.0), ("here today", 2.8))          # "cut" is gone
    problems, _ = wordcheck.final_problems(exp, got, wordcheck.joins(cuts))
    assert len(problems) == 1
    assert "cut" in problems[0] and "2.0" in problems[0]


def test_single_word_mishear_away_from_a_join_is_only_counted():
    words = src(("the", 1.0), ("tenant", 1.3), ("pays", 1.6), ("rent", 1.9), ("monthly", 30.0))
    exp = wordcheck.expected_final(words, cuts=[[10.0, 12.0]], src_end=40.0)
    got = heard(("the tenants pays rent", 1.0), ("monthly", 28.0))
    problems, minor = wordcheck.final_problems(exp, got, wordcheck.joins([[10.0, 12.0]]))
    assert problems == [] and minor == 1


def test_run_of_lost_words_far_from_any_join_is_a_problem():
    """The enhanced voice dropping a phrase is not a cut problem, and it still matters."""
    words = src(("we", 1.0), ("never", 1.3), ("raised", 1.6), ("the", 1.9), ("rent", 2.2))
    exp = wordcheck.expected_final(words, cuts=[], src_end=10.0)
    problems, _ = wordcheck.final_problems(exp, heard(("we rent", 1.0)), joins=[])
    assert len(problems) == 1 and "never raised the" in problems[0]


# --- faceless narration ------------------------------------------------------------

def test_clean_narration_has_no_problems():
    problems, minor = wordcheck.narration_problems("Rent is due on the first.", heard(("rent is due on the first", 0)))
    assert problems == [] and minor == 0


def test_skipped_phrase_is_a_problem():
    problems, _ = wordcheck.narration_problems(
        "Rent is due on the first of every month.", heard(("rent is due every month", 0)))
    assert problems and "skipped" in problems[0] and "on the first of" in problems[0]


def test_repeated_phrase_is_a_problem():
    problems, _ = wordcheck.narration_problems(
        "Call your landlord today.", heard(("call your landlord call your landlord today", 0)))
    assert problems and "added" in problems[0]


def test_swallowed_last_word_is_a_problem_even_alone():
    problems, _ = wordcheck.narration_problems("Read the lease before you sign.", heard(("read the lease before you", 0)))
    assert problems and "last" in problems[0] and "sign" in problems[0]


def test_silent_scene_is_a_problem():
    problems, _ = wordcheck.narration_problems("Read the lease.", [])
    assert problems == ["nothing heard"]


def test_one_misheard_word_mid_line_is_minor():
    problems, minor = wordcheck.narration_problems("Rent control caps the increase.", heard(("rent control caps the increases", 0)))
    assert problems == [] and minor == 1
