"""Slot planning (brief decisions 5, 13, 16, 22): 09:00 and 12:00 Pacific per lane, Tony LI
once a day on the 9:00 Short, drops slide later Shorts up, pins stay put. Pure: the clock and
the other jobs' bookings are passed in."""
from datetime import date, datetime, timedelta

import pytest

import kit_fixtures  # noqa: F401  (puts scripts/ on the path)
import publish_plan as pp  # noqa: E402

TECH = ["me_tiktok", "me_youtube", "me_linkedin", "me_x"]
LI = "me_linkedin"


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=pp.TZ)


def shorts(n, seconds=50):
    return [{"id": str(i), "kind": "short", "seconds": seconds} for i in range(1, n + 1)]


def plan(rows, now, lane="tech", **kw):
    return pp.assign(rows, lane=lane, lane_channels=TECH if lane == "tech" else
                     ["biz_instagram", "biz_facebook", "biz_x", "biz_tiktok", "brand_youtube", LI],
                     now=now, **kw)


def times(rows):
    return [r["at"] for r in rows if r["kind"] == "short" and not r.get("dropped")]


# ---- slots ------------------------------------------------------------------------------

def test_shorts_take_the_next_9_and_12_slots_in_order():
    rows = plan(shorts(3), now=at(2026, 10, 29, 8, 0))
    assert times(rows) == [at(2026, 10, 29, 9).isoformat(), at(2026, 10, 29, 12).isoformat(),
                           at(2026, 10, 30, 9).isoformat()]


def test_a_slot_less_than_ten_minutes_away_is_skipped():
    rows = plan(shorts(1), now=at(2026, 10, 29, 8, 55))
    assert times(rows) == [at(2026, 10, 29, 12).isoformat()]


def test_slots_booked_by_other_jobs_in_the_lane_are_skipped():
    taken = {at(2026, 10, 29, 9), at(2026, 10, 29, 12)}
    rows = plan(shorts(1), now=at(2026, 10, 29, 8), taken=taken)
    assert times(rows) == [at(2026, 10, 30, 9).isoformat()]


def test_start_date_holds_everything_until_that_day():
    rows = plan(shorts(1), now=at(2026, 10, 29, 8), start=date(2026, 11, 2))
    assert times(rows) == [at(2026, 11, 2, 9).isoformat()]


def test_urgent_adds_a_3pm_slot():
    rows = plan(shorts(3), now=at(2026, 10, 29, 8), urgent=True)
    assert times(rows) == [at(2026, 10, 29, 9).isoformat(), at(2026, 10, 29, 12).isoformat(),
                           at(2026, 10, 29, 15).isoformat()]


def test_slots_follow_pacific_daylight_time_changes():
    # DST ends 2026-11-01: 9:00 Pacific is 16:00 UTC before and 17:00 UTC after.
    rows = plan(shorts(4), now=at(2026, 10, 31, 8))
    utc = [datetime.fromisoformat(t).astimezone(pp.UTC).hour for t in times(rows)]
    assert utc == [16, 19, 17, 20]


# ---- Tony LI, once a day --------------------------------------------------------------------

def test_tony_li_only_on_the_9am_short_of_the_lanes_own_day():
    # 2026-10-30 is an odd ordinal day: tech's. 2026-10-31 is real estate's.
    assert date(2026, 10, 30).toordinal() % 2 == 1
    rows = plan(shorts(3), now=at(2026, 10, 30, 8))
    assert LI in rows[0]["channels"]
    assert LI not in rows[1]["channels"]           # 12:00
    assert LI not in rows[2]["channels"]           # 10-31 belongs to real estate


def test_a_lane_borrows_the_other_lanes_li_day_when_that_lane_has_no_9am_short():
    rows = plan(shorts(3), now=at(2026, 10, 30, 8), other_nine=set())
    assert LI in rows[2]["channels"]


def test_no_borrowing_when_the_other_lane_has_a_9am_short_that_day():
    rows = plan(shorts(3), now=at(2026, 10, 30, 8), other_nine={date(2026, 10, 31)})
    assert LI not in rows[2]["channels"]


def test_no_tony_li_on_a_day_that_already_has_one():
    rows = plan(shorts(1), now=at(2026, 10, 30, 8), li_days={date(2026, 10, 30)})
    assert LI not in rows[0]["channels"]
    assert "already" in rows[0]["skipped"][LI]


def test_x_skips_a_short_over_140_seconds_and_says_why():
    rows = plan(shorts(1, seconds=150), now=at(2026, 10, 29, 8))
    assert "me_x" not in rows[0]["channels"]
    assert "140" in rows[0]["skipped"]["me_x"]


# ---- edits ------------------------------------------------------------------------------------

def test_dropping_a_short_slides_the_next_one_into_its_slot():
    rows = pp.drop(shorts(3), "1")
    out = plan(rows, now=at(2026, 10, 29, 8))
    assert out[0]["dropped"] and "at" not in out[0]
    assert times(out) == [at(2026, 10, 29, 9).isoformat(), at(2026, 10, 29, 12).isoformat()]


def test_dropping_one_channel_keeps_the_rest():
    rows = pp.drop(shorts(1), "1:me_x")
    out = plan(rows, now=at(2026, 10, 29, 8))
    assert "me_x" not in out[0]["channels"] and "me_tiktok" in out[0]["channels"]
    assert out[0]["skipped"]["me_x"] == "dropped"


def test_a_pinned_short_stays_put_and_nothing_slides_into_its_time():
    rows = pp.pin(shorts(3), "1", at(2026, 10, 30, 9))
    out = plan(rows, now=at(2026, 10, 29, 8))
    assert out[0]["at"] == at(2026, 10, 30, 9).isoformat()
    assert times(out)[1:] == [at(2026, 10, 29, 9).isoformat(), at(2026, 10, 29, 12).isoformat()]


def test_restore_undoes_a_drop():
    rows = pp.restore(pp.drop(pp.drop(shorts(1), "1"), "1:me_x"), "1")
    assert not rows[0].get("dropped") and not rows[0].get("drop_channels")


def test_edits_never_mutate_their_input():
    rows = shorts(2)
    pp.drop(rows, "1")
    pp.pin(rows, "2", at(2026, 11, 1, 9))
    assert rows == shorts(2)


def test_unknown_rows_and_channels_are_refused():
    with pytest.raises(ValueError):
        pp.drop(shorts(1), "9")
    with pytest.raises(ValueError):
        pp.drop(shorts(1), "1:myspace", channels=TECH)


def test_scheduled_rows_never_move():
    rows = [{**shorts(1)[0], "status": "scheduled", "at": at(2026, 10, 29, 12).isoformat(),
             "channels": ["me_tiktok"]}] + shorts(2)[1:]
    out = plan(rows, now=at(2026, 10, 29, 8))
    assert out[0]["at"] == at(2026, 10, 29, 12).isoformat() and out[0]["channels"] == ["me_tiktok"]
    assert out[1]["at"] == at(2026, 10, 29, 9).isoformat()


# ---- the LinkedIn full post and parsing ---------------------------------------------------------

def test_linkedin_full_goes_at_go_and_claims_that_days_li():
    rows = [{"id": "L", "kind": "linkedin_full", "seconds": 300}] + shorts(1)
    out = plan(rows, now=at(2026, 10, 30, 8))
    assert out[0]["at"] == "go" and out[0]["channels"] == [LI]
    assert LI not in out[1]["channels"]
    assert "already" in out[1]["skipped"][LI]


def test_linkedin_full_listed_last_still_claims_the_day_first():
    rows = shorts(1) + [{"id": "L", "kind": "linkedin_full", "seconds": 300}]
    out = plan(rows, now=at(2026, 10, 30, 8))
    assert LI not in out[0]["channels"] and out[1]["channels"] == [LI]


def test_the_12pm_short_says_li_only_takes_the_9am_one():
    out = plan(shorts(2), now=at(2026, 10, 30, 8))
    assert out[1]["skipped"][LI] == "Tony LI only takes the 9:00 Short"


def test_parse_when_accepts_iso_and_short_forms():
    assert pp.parse_when("2026-10-31T15:00") == at(2026, 10, 31, 15)
    assert pp.parse_when("2026-10-31 3pm") == at(2026, 10, 31, 15)
    assert pp.parse_when("2026-10-31 9:30am") == at(2026, 10, 31, 9, 30)
    with pytest.raises(ValueError):
        pp.parse_when("Thursday")


def test_horizon_is_bounded():
    # A lane with every slot taken for a year is an error, not an endless loop.
    now = at(2026, 10, 29, 8)
    taken = {now.replace(hour=h) + timedelta(days=d) for d in range(400) for h in (9, 12)}
    with pytest.raises(ValueError):
        plan(shorts(1), now=now, taken=taken)


# ---- per-platform times inside a slot (stagger) -----------------------------------------------

STAGGER = {"09:00": {LI: "08:00", "me_x": "10:00", "me_youtube": "13:00", "me_tiktok": "18:00"},
           "12:00": {"me_x": "13:00", "me_youtube": "16:00", "me_tiktok": "21:00"}}


def clock(row, key):
    return datetime.fromisoformat(row["times"][key]).astimezone(pp.TZ).strftime("%m-%d %H:%M")


def test_each_channel_posts_at_its_own_time_inside_the_slot():
    rows = plan(shorts(2), now=at(2026, 10, 30, 7), stagger=STAGGER)
    assert rows[0]["at"] == at(2026, 10, 30, 9).isoformat()          # the slot stays the anchor
    assert {k: clock(rows[0], k) for k in rows[0]["channels"]} == {
        "me_tiktok": "10-30 18:00", "me_youtube": "10-30 13:00", LI: "10-30 08:00", "me_x": "10-30 10:00"}
    assert {k: clock(rows[1], k) for k in rows[1]["channels"]} == {
        "me_tiktok": "10-30 21:00", "me_youtube": "10-30 16:00", "me_x": "10-30 13:00"}


def test_a_channel_time_already_past_posts_at_the_slot_instead():
    rows = plan(shorts(1), now=at(2026, 10, 30, 8), stagger=STAGGER)
    assert clock(rows[0], LI) == "10-30 09:00"
    assert clock(rows[0], "me_tiktok") == "10-30 18:00"


def test_a_pin_at_a_slot_time_gets_that_slots_stagger():
    rows = pp.pin(shorts(1), "1", at(2026, 10, 31, 9))
    out = plan(rows, now=at(2026, 10, 30, 7), other_nine=set(), stagger=STAGGER)
    assert clock(out[0], "me_tiktok") == "10-31 18:00" and clock(out[0], LI) == "10-31 08:00"


def test_a_pin_outside_the_table_posts_every_channel_at_the_pin():
    rows = pp.pin(shorts(1), "1", at(2026, 10, 31, 15, 30))
    out = plan(rows, now=at(2026, 10, 30, 7), stagger=STAGGER)
    assert {clock(out[0], k) for k in out[0]["channels"]} == {"10-31 15:30"}


def test_without_a_stagger_table_every_channel_posts_at_the_slot():
    rows = plan(shorts(1), now=at(2026, 10, 30, 7))
    assert {clock(rows[0], k) for k in rows[0]["channels"]} == {"10-30 09:00"}


def test_a_dropped_row_carries_no_times():
    out = plan(pp.drop(shorts(1), "1"), now=at(2026, 10, 30, 7), stagger=STAGGER)
    assert "times" not in out[0]


def test_channel_times_is_pure_and_keyed_by_the_slots_clock():
    anchor = at(2026, 11, 2, 12)                      # after DST ends: still the 12:00 row
    got = pp.channel_times(anchor, ["me_x", "me_tiktok"], STAGGER)
    assert got == {"me_x": at(2026, 11, 2, 13).isoformat(), "me_tiktok": at(2026, 11, 2, 21).isoformat()}


# ---- the LinkedIn full video never posts in the middle of the night --------------------------------

def full(**extra):
    return {"id": "L", "kind": "linkedin_full", "seconds": 300, **extra}


def test_linkedin_full_after_midnight_waits_for_that_mornings_li_time():
    out = plan([full()] + shorts(1), now=at(2026, 11, 5, 1, 22), stagger=STAGGER)
    assert out[0]["at"] == at(2026, 11, 5, 9).isoformat() and out[0]["channels"] == [LI]
    assert clock(out[0], LI) == "11-05 08:00"
    assert LI not in out[1]["channels"]                # that morning's Tony LI is the full video


def test_linkedin_full_late_in_the_evening_rolls_to_tomorrow_morning():
    out = plan([full()], now=at(2026, 10, 30, 22), stagger=STAGGER)
    assert out[0]["at"] == at(2026, 10, 31, 9).isoformat() and clock(out[0], LI) == "10-31 08:00"


def test_linkedin_full_at_night_skips_mornings_tony_li_already_has():
    out = plan([full()], now=at(2026, 11, 5, 1), li_days={date(2026, 11, 5), date(2026, 11, 6)}, stagger=STAGGER)
    assert out[0]["channels"] == [LI] and clock(out[0], LI) == "11-07 08:00"


# ---- one post per channel per minute (the Blotato lookup matches account + minute) -----------------

def test_a_slot_that_puts_a_channel_on_a_busy_minute_is_skipped():
    busy = {("me_youtube", pp.minute(at(2026, 10, 30, 13)))}     # another job's 13:00 YouTube
    out = plan(shorts(1), now=at(2026, 10, 30, 7), stagger=STAGGER, busy=busy)
    assert out[0]["at"] == at(2026, 10, 30, 12).isoformat()


def test_a_pin_on_a_busy_minute_is_refused():
    busy = {("me_x", pp.minute(at(2026, 10, 31, 15, 30)))}
    with pytest.raises(ValueError, match="me_x"):
        plan(pp.pin(shorts(1), "1", at(2026, 10, 31, 15, 30)), now=at(2026, 10, 30, 7), stagger=STAGGER, busy=busy)


def test_a_pinned_rows_minutes_are_kept_from_the_rest_of_the_job():
    # Row 1 pinned at 13:00 puts YouTube and X on 13:00: today's 9:00 (YouTube 13:00) and
    # 12:00 (X 13:00) rows would both collide, so row 2 waits for tomorrow's 9:00.
    rows = pp.pin(shorts(2), "1", at(2026, 10, 30, 13))
    out = plan(rows, now=at(2026, 10, 30, 7), stagger=STAGGER)
    assert out[1]["at"] == at(2026, 10, 31, 9).isoformat()


def test_no_two_posts_of_one_job_share_a_channel_minute():
    out = plan(shorts(6), now=at(2026, 10, 30, 7), stagger=STAGGER)
    pairs = [(k, pp.minute(t)) for r in out for k, t in r["times"].items()]
    assert len(pairs) == len(set(pairs))


def test_row_minutes_read_a_sent_posts_own_time_first():
    row = {"id": "1", "kind": "short", "status": "scheduled", "at": at(2026, 11, 6, 9).isoformat(),
           "channels": ["me_x", "me_tiktok"], "times": {"me_x": at(2026, 11, 6, 10).isoformat()},
           "posts": {"me_x": {"submission_id": "s1", "at": at(2026, 11, 6, 11).isoformat()},
                     "me_tiktok": {"submission_id": "s2", "cancelled": True}}}
    assert pp.row_minutes(row) == {("me_x", pp.minute(at(2026, 11, 6, 11)))}


def test_linkedin_full_during_the_day_still_goes_at_go():
    out = plan([full()], now=at(2026, 10, 30, 14), stagger=STAGGER)
    assert out[0]["at"] == "go" and "times" not in out[0]


def test_a_pinned_linkedin_full_at_9_posts_at_the_li_time():
    out = plan([full(pinned_at=at(2026, 11, 9, 9).isoformat())], now=at(2026, 11, 5, 1), stagger=STAGGER)
    assert clock(out[0], LI) == "11-09 08:00"
