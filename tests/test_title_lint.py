"""Title warnings at kit time: one case per rule, and a clean title raises nothing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import title_lint  # noqa: E402


def _has(warnings, phrase):
    return any(phrase in w for w in warnings)


def test_clean_titles_raise_nothing():
    assert title_lint.lint("Ogdenville Has Two Rent Caps. Which One Is Yours?") == []
    assert title_lint.lint("LA County Caps Rent at 1.9%. Is Your Rental Inside It?", short=True) == []


def test_over_sixty_characters():
    assert _has(title_lint.lint("Five bills that change how you run a California rental are on the desk"), "over 60")


def test_hashtag_in_a_title():
    assert _has(title_lint.lint("Springfield Rent Rules 2026 #shorts"), "hashtag")
    assert _has(title_lint.lint("Springfield Rent Rules 2026 #RentControl"), "hashtag")


def test_no_number_no_question_no_place():
    assert _has(title_lint.lint("Realtors: AI without the computer geeks"), "no number, no question and no place")
    assert not _has(title_lint.lint("Is your HOA board even legal?"), "no number, no question and no place")
    assert not _has(title_lint.lint("Torrance landlords: the notice rule"), "no number, no question and no place")


def test_shorts_need_a_searchable_noun_in_the_first_forty_characters():
    late = "Here is the one thing nobody tells you about Springfield"
    assert _has(title_lint.lint(late, short=True), "first 40 characters")
    assert not _has(title_lint.lint(late), "first 40 characters")
    assert not _has(title_lint.lint("AB 1482 in plain English for owners", short=True), "first 40")
    assert not _has(title_lint.lint("Rent control rules owners miss", short=True), "first 40")


def test_tool_promo_phrasing():
    assert _has(title_lint.lint("The Best AI Tool for Agents in 2026?"), "tool-promo")
    assert _has(title_lint.lint("This AI Is a Game Changer for Torrance?"), "tool-promo")


def test_lowercase_la_is_not_a_place():
    assert _has(title_lint.lint("Why la la land loves landlords"), "no number, no question and no place")
