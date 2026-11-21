"""Countdown video: research tally, read-aloud script, studio sections and quiz links.
Covers scripts/countdown.py. (tests/test_countdown.py is the older chill-dude theme, not this.)"""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import countdown  # noqa: E402
import th_lib  # noqa: E402

HOOK = ("I kept hearing that landlords are leaving Los Angeles, and I did not believe it, so I investigated. "
        "I read the comments in threads on two subreddits. Patterns emerged. The same five reasons over and over. "
        "Counting down from five to the number one reason.")
ITEM_FIVE = ("Number five, jobs. I thought this would rank higher than it did. People keep saying the job market "
             "here is drying up, and they cannot afford to stay while they look for work. Some commenters moved for a job "
             "and lost it within months, and the rent did not wait for them.")
ITEM_FOUR = ("Number four, market. Every comment about the market had a different story about the same block. "
             "Take my quiz on the screen and below. Don't want to be quizzed? Reach out directly.")
ITEM_THREE = ("Number three, insurance. Premiums jumped for a lot of owners, and several readers said the insurance bill "
              "was the reason they sold the duplex. The insurance numbers are real, but sales tell a more mixed story.")
ITEM_TWO = ("Number two, property taxes. Owners complained about reassessments after a sale and about bills that doubled "
            "in a couple of years. The tax rules are the same ones everyone in California lives under.")
ITEM_ONE = ("Number one, rent control. This one came up in almost every thread, usually in the most heated replies. "
            "Owners said the rules kept them from raising rent to cover costs. The rent data tells a different story.")
OUTRO = "Thanks for watching. Book a call if you want to talk it through."
TEXT = " ".join([HOOK, ITEM_FIVE, ITEM_FOUR, ITEM_THREE, ITEM_TWO, ITEM_ONE, OUTRO])
CALL = countdown.CALL_URL_DEFAULT


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    """No real config.env or environment override leaks into these tests."""
    monkeypatch.delenv("COUNTDOWN_CALL_URL", raising=False)
    monkeypatch.setattr(countdown.common, "load_config", lambda: {})


# ---- fixtures --------------------------------------------------------------------------

def _clean(token):
    return re.sub(r"[^a-z0-9#]", "", token.lower())


def when(tokens, *phrase, nth=0):
    """Source-second start of the nth place the phrase's words occur, using the same 0.5 s word spacing."""
    want = [_clean(p) for p in phrase]
    hits = [i for i in range(len(tokens) - len(want) + 1)
            if [_clean(t) for t in tokens[i:i + len(want)]] == want]
    return round(1.0 + hits[nth] * 0.5, 2)


def make_transcript(text):
    tokens = text.split()
    words = [{"word": f" {tok}", "start": round(1.0 + i * 0.5, 2), "end": round(1.4 + i * 0.5, 2), "probability": 0.99}
             for i, tok in enumerate(tokens)]
    return {"text": text, "language": "en",
            "segments": [{"id": 0, "start": 1.0, "end": words[-1]["end"], "text": text, "words": words}]}


def words_of(transcript):
    return [w for seg in transcript["segments"] for w in seg["words"]]


def cue_times(block):
    """Every source-second cue a block carries: its own 'at', or one per bar."""
    if "items" in block:
        return [item["at"] for item in block["items"]]
    return [block["at"]]


def reason(rid, label, count, value, url_tag, quotes=None):
    default_quote = {"text": f"{label} is the reason I am writing this, honestly.",
                     "url": f"https://www.reddit.com/r/LosAngeles/comments/{url_tag}/", "community": "r/LosAngeles"}
    return {"id": rid, "label": label, "count": count, "quotes": quotes or [default_quote],
            "rebuttal": {"stat": f"{label} data point", "value": value, "source": "Zillow ORI",
                         "url": "https://www.zillow.com/research/data/"},
            "surprise": f"I thought {label.lower()} would rank higher."}


def make_research():
    return {
        "question": "Why are landlords LEAVING Los Angeles in 2026?",
        "topic": "los angeles landlords",
        "place": "Los Angeles",
        "quiz": "investor-type",
        "sources": [
            {"url": "https://www.reddit.com/r/LosAngeles/comments/abc123/", "community": "r/LosAngeles", "comments_read": 180},
            {"url": "https://www.reddit.com/r/RealEstate/comments/def456/", "community": "r/RealEstate", "comments_read": 232},
        ],
        "reasons": [
            reason("rent-control", "Rent control", 61, "4%", "abc123", quotes=[
                {"text": "Rent control is why I am out, plain and simple.",
                 "url": "https://www.reddit.com/r/LosAngeles/comments/abc123/x/", "community": "r/LosAngeles"},
                {"text": "Every landlord I know is selling to avoid the rules.",
                 "url": "https://www.reddit.com/r/LosAngeles/comments/abc123/y/", "community": "r/LosAngeles"}]),
            reason("property-tax", "Property taxes", 44, "1.2%", "abc123"),
            reason("insurance", "Insurance", 30, "18%", "def456"),
            reason("market", "Market", 20, "3%", "def456"),
            reason("jobs", "Jobs", 12, "5%", "def456"),
        ],
    }


def make_job(text):
    last_end = 1.4 + (len(text.split()) - 1) * 0.5
    return {
        "title": "Why are landlords leaving",
        "source": "footage.mp4",
        "style": "studio",
        "srcEnd": round(last_end + 1.2, 2),
        "cuts": [],
        "sections": [],
        "framing": {"full": {"x": 0.5, "y": 0.45, "zoom": 1.05}},
        "lowerThird": {"from": 1.0, "to": 4.0, "name": "Tony Self", "line": "California Broker"},
        "endCard": {"seconds": 3.0, "kicker": "", "headline": "", "sub": ""},
        "youtube": {"title": "Why are landlords LEAVING Los Angeles in 2026?",
                    "description": "Original body line.\nSecond body line.", "tags": ["los angeles landlords"]},
        "shorts": [{"start": "Number five", "end": "rank higher", "hook": "Jobs",
                    "title": "Jobs short", "description": "Short one."}],
    }


def make_job_dir(tmp_path, text=TEXT, research=None, job=None):
    jdir = tmp_path / "20261011-120000-beach"
    (jdir / "work").mkdir(parents=True)
    (jdir / "out").mkdir()
    (jdir / "transcript.json").write_text(json.dumps(make_transcript(text)))
    (jdir / "research.json").write_text(json.dumps(research or make_research()))
    (jdir / "job.json").write_text(json.dumps(job or make_job(text), indent=2))
    return jdir


def countdown_for(research=None):
    return countdown.build_countdown(research or make_research())


# ---- tally -----------------------------------------------------------------------------

def test_tally_ranks_by_count_and_lists_items_from_last_to_first():
    cd = countdown_for()
    assert [i["id"] for i in cd["items"]] == ["jobs", "market", "insurance", "property-tax", "rent-control"]
    assert [i["rank"] for i in cd["items"]] == [5, 4, 3, 2, 1]


def test_equal_counts_keep_input_order():
    data = make_research()
    data["reasons"] = [reason("a", "Aaa", 10, "1%", "x"), reason("b", "Bbb", 10, "2%", "x"),
                       reason("c", "Ccc", 5, "3%", "x")]
    ranked = countdown.rank_reasons(data["reasons"])
    assert [(r["id"], r["rank"]) for r in ranked] == [("a", 1), ("b", 2), ("c", 3)]


def test_share_is_count_over_total_rounded_to_three_places():
    cd = countdown_for()
    rent = next(i for i in cd["items"] if i["id"] == "rent-control")
    assert rent["share"] == round(61 / 167, 3) == 0.365
    assert sum(i["count"] for i in cd["items"]) == 167


def test_countdown_totals_come_from_the_sources():
    cd = countdown_for()
    assert cd["comments_read"] == 412
    assert cd["threads"] == 2
    assert cd["communities"] == ["r/LosAngeles", "r/RealEstate"]
    assert cd["quiz"]["url_base"] == "https://quiz.example.com/investor-type"


def test_tally_cli_writes_countdown_json(tmp_path):
    jdir = make_job_dir(tmp_path)
    countdown.main(["tally", str(jdir)])
    written = json.loads((jdir / "countdown.json").read_text())
    assert written["items"][0]["label"] == "Jobs"


# ---- validation ------------------------------------------------------------------------

def test_valid_research_has_no_problems():
    assert countdown.validate_research(make_research()) == []


def test_username_in_a_quote_is_rejected():
    data = make_research()
    data["reasons"][0]["quotes"][0]["text"] = "Ask u/landlordguy about the rent control rules."
    problems = countdown.validate_research(data)
    assert any("u/username" in p for p in problems)


def test_missing_rebuttal_is_rejected():
    data = make_research()
    del data["reasons"][2]["rebuttal"]
    problems = countdown.validate_research(data)
    assert any("missing rebuttal" in p for p in problems)


def test_rebuttal_without_a_source_is_rejected():
    data = make_research()
    data["reasons"][1]["rebuttal"]["source"] = ""
    assert any("rebuttal is missing source" in p for p in countdown.validate_research(data))


def test_unknown_quiz_is_rejected():
    data = make_research()
    data["quiz"] = "nope"
    assert any("unknown quiz" in p for p in countdown.validate_research(data))


def test_too_few_reasons_is_rejected():
    data = make_research()
    data["reasons"] = data["reasons"][:2]
    assert any("need 3 to 7 reasons, got 2" in p for p in countdown.validate_research(data))


def test_quote_over_200_characters_is_rejected():
    data = make_research()
    data["reasons"][0]["quotes"][0]["text"] = "x" * 201
    assert any("limit is 200" in p for p in countdown.validate_research(data))


def test_zero_comments_read_is_rejected():
    data = make_research()
    for source in data["sources"]:
        source["comments_read"] = 0
    assert any("totals 0" in p for p in countdown.validate_research(data))


def test_duplicate_ids_are_rejected():
    data = make_research()
    data["reasons"][1]["id"] = "rent-control"
    assert any("duplicate id" in p for p in countdown.validate_research(data))


def test_title_warns_without_caps_word_or_year():
    assert countdown.title_warnings("why are landlords leaving los angeles?") == [
        "title has no CAPS word (formula: question, one CAPS word, the year)", "title has no year"]
    assert countdown.title_warnings("Why are landlords LEAVING Los Angeles in 2026?") == []


def test_tally_cli_refuses_bad_research(tmp_path):
    data = make_research()
    data["quiz"] = "nope"
    jdir = make_job_dir(tmp_path, research=data)
    with pytest.raises(SystemExit):
        countdown.main(["tally", str(jdir)])


# ---- script ----------------------------------------------------------------------------

def test_script_has_the_honest_source_line_with_real_numbers():
    text = countdown.script_markdown(countdown_for(), "jobs/20261011-120000-beach")
    assert "I read 412 comments across 2 threads in r/LosAngeles and r/RealEstate." in text
    assert "I created" not in text and "I posted" not in text


def test_mid_roll_cta_sits_after_rank_four_and_before_rank_three():
    text = countdown.script_markdown(countdown_for(), "jobs/20261011-120000-beach")
    four, cta, three = text.index("## #4 Market"), text.index("MID-ROLL QUIZ CTA"), text.index("## #3 Insurance")
    assert four < cta < three
    assert "What kind of real estate investor are you?" in text[cta:three]


def test_mid_roll_moves_to_second_item_when_under_four_reasons():
    data = make_research()
    data["reasons"] = data["reasons"][:3]
    cd = countdown_for(data)
    assert countdown.mid_roll_rank(cd["items"]) == cd["items"][1]["rank"] == 2


def test_script_has_no_em_dash_and_names_each_reason():
    text = countdown.script_markdown(countdown_for(), "jobs/20261011-120000-beach")
    assert chr(0x2014) not in text and chr(0x2013) not in text
    for rank, label in ((5, "Jobs"), (4, "Market"), (3, "Insurance"), (2, "Property taxes"), (1, "Rent control")):
        assert f"## #{rank} {label}" in text


def test_script_cli_refuses_to_overwrite_without_force(tmp_path):
    jdir = make_job_dir(tmp_path)
    countdown.main(["tally", str(jdir)])
    out = tmp_path / "script.md"
    countdown.main(["script", str(jdir), "--out", str(out), "--date", "10112026"])
    assert out.read_text().startswith("---\n")
    with pytest.raises(SystemExit):
        countdown.main(["script", str(jdir), "--out", str(out)])


def test_headline_lowercases_common_words_and_keeps_places_and_acronyms():
    assert countdown.headline_text("Rent control in Los Angeles", ["Los Angeles"]) == "rent control in Los Angeles"
    assert countdown.headline_text("HOA Dues Fights", []) == "HOA dues fights"
    assert countdown.headline_text("Owners in Redondo", ["Redondo"]) == "owners in Redondo"


# ---- sections --------------------------------------------------------------------------

def test_number_phrases_are_found_in_spoken_form():
    cd = countdown_for()
    tokens = TEXT.split()
    words = words_of(make_transcript(TEXT))
    found, missing = countdown.locate_numbers(cd["items"], words)
    assert missing == []
    assert found[5] == when(tokens, "number", "five")
    assert found[4] == when(tokens, "number", "four")
    assert found[1] == when(tokens, "number", "one", nth=1)  # the hook's "number one" comes first and is skipped


def test_number_phrases_are_found_in_digit_form():
    digits = (TEXT.replace("Number five,", "Number 5,").replace("Number four,", "#4")
              .replace("Number three,", "number 3,").replace("Number one,", "Number 1,"))
    tokens = digits.split()
    words = words_of(make_transcript(digits))
    found, missing = countdown.locate_numbers(countdown_for()["items"], words)
    assert missing == []
    assert found[5] == when(tokens, "number", "5")
    assert found[4] == when(tokens, "#4")
    assert found[3] == when(tokens, "number", "3")
    assert found[1] == when(tokens, "number", "1")


def test_missing_number_is_reported():
    text = TEXT.replace("Number three, insurance.", "And then the next one.")
    words = words_of(make_transcript(text))
    _, missing = countdown.locate_numbers(countdown_for()["items"], words)
    assert missing == [3]


def test_every_cue_lands_inside_its_window_and_validates():
    cd = countdown_for()
    job = make_job(TEXT)
    plan = countdown.build_plan(cd, words_of(make_transcript(TEXT)), job)
    candidate = countdown.merge_job(job, plan)
    assert th_lib.validate(candidate) == []
    for section in candidate["sections"]:
        lo, hi = section["evidence"]
        assert lo < hi
        for block in section["blocks"]:
            for at in cue_times(block):
                assert lo <= at <= hi, (block, section["evidence"])


def test_beat_sections_carry_the_chapter_label_only_on_their_first_beat():
    plan = countdown.build_plan(countdown_for(), words_of(make_transcript(TEXT)), make_job(TEXT))
    chapters = [s["chapter"] for s in plan["sections"] if "chapter" in s]
    assert chapters == ["#5 Jobs", "#4 Market", "#3 Insurance", "#2 Property taxes", "#1 Rent control"]


def test_quiz_bar_and_cta_card_sit_at_the_take_my_quiz_line():
    tokens = TEXT.split()
    plan = countdown.build_plan(countdown_for(), words_of(make_transcript(TEXT)), make_job(TEXT))
    at = when(tokens, "take", "my", "quiz")
    assert plan["lowerThird"]["from"] == at
    assert plan["lowerThird"]["name"] == "What kind of real estate investor are you?"
    assert plan["lowerThird"]["line"] == "quiz.example.com/investor-type"
    cta = [s for s in plan["sections"] if s["blocks"][0].get("sub") == "quiz.example.com/investor-type"]
    assert len(cta) == 1 and cta[0]["evidence"][0] <= at <= cta[0]["evidence"][1]


def test_missing_quiz_line_skips_the_cta_with_a_warning():
    text = TEXT.replace("Take my quiz on the screen and below.", "Take a look on the screen.")
    text = text.replace("Don't want to be quizzed?", "Thoughts?")
    plan = countdown.build_plan(countdown_for(), words_of(make_transcript(text)), make_job(text))
    assert plan["lowerThird"] is None
    assert any("no 'quiz' after #4" in w for w in plan["warnings"])


def test_cue_on_a_cut_is_pushed_out_of_the_cut():
    tokens = TEXT.split()
    start = when(tokens, "number", "five")
    job = make_job(TEXT)
    job["cuts"] = [[round(start + 0.3, 2), round(start + 0.9, 2)]]
    plan = countdown.build_plan(countdown_for(), words_of(make_transcript(TEXT)), job)
    candidate = countdown.merge_job(job, plan)
    assert th_lib.validate(candidate) == []


def test_apply_keeps_unrelated_keys_and_turns_a_dict_lowerthird_into_a_list(tmp_path):
    jdir = make_job_dir(tmp_path)
    before = json.loads((jdir / "job.json").read_text())
    countdown.main(["tally", str(jdir)])
    countdown.main(["sections", str(jdir), "--apply"])
    after = json.loads((jdir / "job.json").read_text())
    for key in ("title", "source", "style", "srcEnd", "cuts", "framing", "youtube", "shorts"):
        assert after[key] == before[key]
    assert isinstance(after["lowerThird"], list)
    assert after["lowerThird"][0] == before["lowerThird"]
    assert after["lowerThird"][-1]["name"] == "What kind of real estate investor are you?"
    assert after["endCard"]["seconds"] == 3.0
    # Studio panels run to the right edge, where the counter column sat on top of the text
    assert "counter" not in after
    assert len(after["sections"]) > 5


def test_apply_twice_does_not_duplicate_the_quiz_bar(tmp_path):
    jdir = make_job_dir(tmp_path)
    countdown.main(["tally", str(jdir)])
    countdown.main(["sections", str(jdir), "--apply"])
    once = json.loads((jdir / "job.json").read_text())
    countdown.main(["sections", str(jdir), "--apply"])
    twice = json.loads((jdir / "job.json").read_text())
    assert twice["lowerThird"] == once["lowerThird"]
    assert len(twice["lowerThird"]) == 2


def test_apply_refuses_when_a_number_is_missing(tmp_path):
    text = TEXT.replace("Number three, insurance.", "And then the next one.")
    jdir = make_job_dir(tmp_path, text=text)
    countdown.main(["tally", str(jdir)])
    with pytest.raises(SystemExit):
        countdown.main(["sections", str(jdir), "--apply"])
    assert json.loads((jdir / "job.json").read_text())["sections"] == []


def test_merge_does_not_mutate_the_loaded_job():
    job = make_job(TEXT)
    snapshot = copy.deepcopy(job)
    plan = countdown.build_plan(countdown_for(), words_of(make_transcript(TEXT)), job)
    countdown.merge_job(job, plan)
    assert job == snapshot


# ---- quizlink --------------------------------------------------------------------------

def test_quiz_url_carries_the_utm_tags_and_the_folder_word():
    quiz = countdown.quiz_for("investor-type")
    assert countdown.quiz_url(quiz, "beach") == (
        "https://quiz.example.com/investor-type?v=beach&utm_source=youtube&utm_medium=video&utm_campaign=beach")


def test_folder_word_is_the_trailing_word_and_skips_a_collision_suffix():
    assert countdown.folder_word(Path("jobs/20260923-190000-wes1")) == "wes1"
    assert countdown.folder_word(Path("jobs/20261011-120000-beach-2")) == "beach"


def test_folder_word_skips_a_style_copy_suffix():
    # a board copy of the studio job keeps the topic word in the quiz tracker
    assert countdown.folder_word(Path("jobs/20261012-210030-california-board")) == "california"
    assert countdown.folder_word(Path("jobs/20261012-210030-california-board-2")) == "california"
    assert countdown.folder_word(Path("jobs/20261012-210030-california-split")) == "california"


def test_call_link_defaults_to_calendly_and_config_or_env_can_override(monkeypatch):
    assert countdown.call_url() == "https://calendly.com/your-booking-link"
    monkeypatch.setattr(countdown.common, "load_config", lambda: {"COUNTDOWN_CALL_URL": "https://example.test/call"})
    assert countdown.call_url() == "https://example.test/call"
    monkeypatch.setenv("COUNTDOWN_CALL_URL", "https://example.test/env")
    assert countdown.call_url() == "https://example.test/env"


def test_quizlink_puts_the_call_on_line_one_and_the_quiz_on_line_two():
    quiz = countdown.quiz_for("investor-type")
    url = countdown.quiz_url(quiz, "beach")
    job = countdown.apply_links(make_job(TEXT), quiz, url, CALL)
    lines = job["youtube"]["description"].split("\n")
    assert lines[0] == f"Book a free call with Tony: {CALL}"
    assert lines[1] == f"What kind of real estate investor are you? Take the free quiz: {url}"
    assert lines[2] == ""
    assert lines[3:] == ["Original body line.", "Second body line."]


def test_quizlink_is_idempotent_on_the_description():
    quiz = countdown.quiz_for("investor-type")
    url = countdown.quiz_url(quiz, "beach")
    once = countdown.apply_links(make_job(TEXT), quiz, url, CALL)
    twice = countdown.apply_links(once, quiz, url, CALL)
    assert twice == once
    assert twice["youtube"]["description"].count("Take the free quiz:") == 1


def test_quizlink_updates_every_short_and_never_duplicates_the_line():
    quiz = countdown.quiz_for("investor-type")
    url = countdown.quiz_url(quiz, "beach")
    job = make_job(TEXT)
    job["shorts"].append({"start": "a", "end": "b", "hook": "h", "title": "t", "description": "Second short."})
    once = countdown.apply_links(job, quiz, url, CALL)
    twice = countdown.apply_links(once, quiz, url, CALL)
    for short in twice["shorts"]:
        assert short["description"].count(f"Take the free quiz: {url}") == 1
    assert twice["shorts"][0]["description"] == f"Short one.\n\nTake the free quiz: {url}"


def test_pinned_comment_replaces_itself_in_youtube_md():
    lines = [f"Book a free call with Tony: {CALL}", "What kind of real estate investor are you? Take the free quiz: https://x.test/q"]
    md = "# YouTube kit\n\n## Title\n\nWhy\n\n## Tags\n\na, b\n"
    once = countdown.with_pinned_comment(md, lines)
    twice = countdown.with_pinned_comment(once, lines)
    assert twice == once
    assert once.count("## Pinned comment") == 1
    assert once.index("## Tags") < once.index("## Pinned comment")
    assert lines[0] in once


def test_quizlink_cli_updates_job_and_youtube_md_idempotently(tmp_path):
    jdir = make_job_dir(tmp_path)
    (jdir / "out" / "youtube.md").write_text("# YouTube kit\n\n## Title\n\nWhy\n")
    countdown.main(["tally", str(jdir)])
    countdown.main(["quizlink", str(jdir)])
    first_job = (jdir / "job.json").read_text()
    first_md = (jdir / "out" / "youtube.md").read_text()
    countdown.main(["quizlink", str(jdir)])
    assert (jdir / "job.json").read_text() == first_job
    assert (jdir / "out" / "youtube.md").read_text() == first_md
    job = json.loads(first_job)
    assert job["youtube"]["description"].startswith(f"Book a free call with Tony: {CALL}\n")
    assert "## Pinned comment" in first_md and first_md.count("## Pinned comment") == 1
    assert "utm_campaign=beach" in first_md


def test_quizlink_quiz_override_changes_the_title_and_host(tmp_path):
    jdir = make_job_dir(tmp_path)
    countdown.main(["tally", str(jdir)])
    countdown.main(["quizlink", str(jdir), "--quiz", "home-check"])
    desc = json.loads((jdir / "job.json").read_text())["youtube"]["description"]
    assert "Is your home ready to sell? Take the free quiz: https://quiz.sitethree.com/home-check?v=beach" in desc

