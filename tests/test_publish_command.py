"""fv.py publish end to end with Blotato, Bunny and the clock replaced: the Go table first,
Go only for the plan Tony saw, ids recorded, retries only what failed, --edit cancels."""
import json
from datetime import datetime

import pytest

from kit_fixtures import FOOTER, YOUTUBE, jobs, make_faceless  # noqa: F401

import blotato  # noqa: E402
import common  # noqa: E402
import format_route  # noqa: E402
import lanes  # noqa: E402
import publish  # noqa: E402
import platform_util  # noqa: E402
import publish_go  # noqa: E402
import publish_plan as pp  # noqa: E402
import publish_store  # noqa: E402
import upload  # noqa: E402

NOW = datetime(2026, 10, 30, 8, 0, tzinfo=pp.TZ)            # a tech day (odd ordinal)
TAGLINE = "Tech Tony | AI for operators, not engineers | techtony.co"
ROUTE = {"kind": "LONG", "seconds": 300, "chapters": 3, "fmt": "faceless", "source": "final_16x9.mp4"}


@pytest.fixture
def world(jobs, monkeypatch, tmp_path):
    sent, cancelled, shell = [], [], []
    cfg = {"YOUTUBE_FOOTER": FOOTER, "BLOTATO_API_KEY": "test-key"}
    monkeypatch.setattr(common, "load_config", lambda: dict(cfg))
    monkeypatch.setattr(publish, "now", lambda: NOW)
    monkeypatch.setattr(format_route, "probe_seconds", lambda path: 50.0)
    monkeypatch.setattr(upload, "put_file", lambda c, path, remote: f"https://cdn.test/{remote}")
    monkeypatch.setattr(blotato, "upload_media", lambda key, url: url.replace("cdn.test", "blotato.test"))
    monkeypatch.setattr(blotato, "POST_GAP_S", 0)
    monkeypatch.setattr(publish_go, "LI_POLL_S", 0)
    fail, timeout, crash = set(), set(), {"after": None}
    schedules = []

    def create(key, body):
        account = body["post"]["accountId"]
        if crash["after"] is not None and len(sent) >= crash["after"]:
            raise KeyboardInterrupt
        if account in fail:
            raise blotato.BlotatoError("account not found", 400)
        if account in timeout:
            raise blotato.UnknownOutcome("timed out")
        sent.append(body)
        return {"postSubmissionId": f"sub-{len(sent)}", "scheduledTime": body.get("scheduledTime")}

    monkeypatch.setattr(blotato, "create_post", create)
    monkeypatch.setattr(blotato, "post_status",
                        lambda key, sub: {"status": "published", "publicUrl": "https://linkedin.test/post/1"})
    monkeypatch.setattr(blotato, "cancel", lambda key, post, account: cancelled.append((post["submission_id"], account)))
    moved = []
    monkeypatch.setattr(blotato, "reschedule", lambda key, post, account, when: moved.append((account, when)))
    monkeypatch.setattr(blotato, "find_schedule", lambda key, account, when, sha=None:
                        next((s["id"] for s in schedules if s["account"] == account), None))
    monkeypatch.setattr(publish_go.subprocess, "run", lambda cmd, **kw: shell.append(cmd))
    board = tmp_path / "scoreboard.csv"
    board.write_text("date_published,job,youtube_id,channel,format,lane,title,blog_url,notes\n")
    monkeypatch.setattr(publish_go, "SCOREBOARD", board)
    return {"sent": sent, "cancelled": cancelled, "shell": shell, "cfg": cfg, "fail": fail, "board": board,
            "timeout": timeout, "crash": crash, "schedules": schedules, "moved": moved}


def staggered(lane, slots, skip=()):
    """(account id, UTC Z) for every lane channel at its stagger time, per slot {"09:00": date}."""
    spec = lanes.spec()
    out = set()
    for slot, day in slots.items():
        anchor = datetime.fromisoformat(f"{day}T{slot}").replace(tzinfo=pp.TZ)
        keys = [k for k in spec["lanes"][lane]["channels"] if k not in skip]
        if slot != "09:00":
            keys = [k for k in keys if k != "me_linkedin"]
        for key, when in pp.channel_times(anchor, keys, spec["lanes"][lane]["stagger"]).items():
            out.add((spec["channels"][key]["accountId"], blotato.utc_z(when)))
    return out


def make_job(root, name=None):
    if name:                                       # make_faceless always uses one folder name
        jdir = make_faceless(root / "_staging").rename(root / name)
    else:
        jdir = make_faceless(root)
    for f in ("short_1.mp4", "short_2.mp4", "final_9x16.mp4"):
        (jdir / "out" / f).write_bytes(b"")
    state = json.loads((jdir / "state.json").read_text())
    (jdir / "state.json").write_text(json.dumps({**state, "route": ROUTE}))
    return jdir


def run(*argv):
    args = publish.parse(["publish", *argv])
    args.fn(args)


def record(jdir):
    return publish_store.load(jdir)


def test_the_first_run_plans_and_posts_nothing(world, jobs, capsys):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech")
    out = capsys.readouterr().out
    assert "Fri 10-30 09:00" in out and "Fri 10-30 12:00" in out and "at Go" in out
    assert world["sent"] == []
    assert [r["id"] for r in record(jdir)["rows"]] == ["1", "2", "L"]


def test_go_without_a_table_first_shows_the_table_and_sends_nothing(world, jobs, capsys):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE, "--go")
    assert world["sent"] == []
    assert "review it, then --go again" in capsys.readouterr().out


def test_go_schedules_every_short_and_posts_linkedin_now(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    rows = {r["id"]: r for r in record(jdir)["rows"]}
    assert all(r["status"] == "scheduled" for r in rows.values())
    shorts_sent = {(b["post"]["accountId"], b["scheduledTime"]) for b in world["sent"] if "scheduledTime" in b}
    assert shorts_sent == staggered("tech", {"09:00": "2026-10-30", "12:00": "2026-10-30"}, skip={"me_linkedin"})
    li_now = [b for b in world["sent"] if "scheduledTime" not in b]
    assert len(li_now) == 1 and li_now[0]["post"]["accountId"] == "90003"
    clip = platform_util.clipboard_cmd()
    assert clip is None or clip in world["shell"]
    assert platform_util.open_cmd("https://linkedin.test/post/1") in world["shell"]
    assert rows["1"]["posts"]["me_tiktok"]["submission_id"].startswith("sub-")


def test_tech_captions_end_with_the_tagline_and_never_the_dre_line(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    for body in world["sent"]:
        text = body["post"]["content"]["text"]
        assert "DRE" not in text
        assert TAGLINE in text


def test_rerunning_go_sends_nothing_new(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    count = len(world["sent"])
    run(jdir.name, "--go")
    assert len(world["sent"]) == count


def test_a_failed_channel_is_retried_alone_at_the_same_time(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    world["fail"].add("90004")                                 # Tony X
    run(jdir.name, "--go")
    row = record(jdir)["rows"][0]
    assert row["status"] == "partial" and "error" in row["posts"]["me_x"]
    first_at = row["at"]
    world["fail"].clear()
    before = len(world["sent"])
    run(jdir.name, "--go")
    retried = world["sent"][before:]
    assert {b["post"]["accountId"] for b in retried} == {"90004"}
    assert record(jdir)["rows"][0]["at"] == first_at and record(jdir)["rows"][0]["status"] == "scheduled"


def test_a_second_job_in_the_lane_takes_the_next_free_slots(world, jobs):
    first = make_job(jobs)
    run(first.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(first.name, "--go")
    second = make_job(jobs, name="20261029-090000-second")
    run(second.name, "--lane", "tech", "--youtube", YOUTUBE)
    times = [r["at"] for r in record(second)["rows"] if r["kind"] == "short"]
    assert times == [datetime(2026, 10, 31, 9, tzinfo=pp.TZ).isoformat(),
                     datetime(2026, 10, 31, 12, tzinfo=pp.TZ).isoformat()]


def test_an_unconfirmed_channel_blocks_go_until_it_is_dropped(world, jobs, monkeypatch):
    spec = lanes.spec()
    spec["channels"]["brand_youtube"] = {**spec["channels"]["brand_youtube"], "verified": False}
    monkeypatch.setattr(lanes, "spec", lambda: spec)
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []
    run(jdir.name, "--drop", "1:brand_youtube", "--drop", "2:brand_youtube")
    run(jdir.name, "--go")
    assert world["sent"] and all(b["post"]["accountId"] != "90009" for b in world["sent"])


def test_realestate_captions_keep_the_dre_line(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE, "--drop", "1:brand_youtube", "--drop", "2:brand_youtube")
    run(jdir.name, "--go")
    assert all(FOOTER in b["post"]["content"]["text"] for b in world["sent"])


def test_dropping_a_scheduled_row_needs_edit_and_then_cancels_it_in_blotato(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    with pytest.raises(SystemExit):
        run(jdir.name, "--drop", "1")
    run(jdir.name, "--edit", "--drop", "1")
    row = record(jdir)["rows"][0]
    assert row["dropped"] and row["status"] == "cancelled"
    assert len(world["cancelled"]) == len(row["posts"])


def test_go_refuses_without_a_key(world, jobs, monkeypatch):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    monkeypatch.setattr(common, "load_config", lambda: {"YOUTUBE_FOOTER": FOOTER})
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")


def test_long_route_go_refuses_without_a_youtube_id(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech")
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []


def standalone_shorts(jdir):
    """A talk cut into Shorts that each stand alone: no long episode, no LinkedIn full video."""
    (jdir / "out" / "linkedin.md").unlink()
    job = json.loads((jdir / "job.json").read_text())
    (jdir / "job.json").write_text(json.dumps({**job, "shorts": [{**s, "standalone": True}
                                                                for s in job["shorts"]]}))
    return jdir


def test_long_route_go_sends_standalone_shorts_without_a_youtube_id(world, jobs):
    jdir = standalone_shorts(make_job(jobs))
    run(jdir.name, "--lane", "tech", "--route", "long")
    run(jdir.name, "--go")
    assert world["sent"]
    assert not any("Full episode" in b["post"]["content"]["text"] for b in world["sent"])


def test_one_short_that_points_at_the_episode_still_needs_the_youtube_id(world, jobs):
    jdir = standalone_shorts(make_job(jobs))
    job = json.loads((jdir / "job.json").read_text())
    shorts = [{**job["shorts"][0], "standalone": False}, *job["shorts"][1:]]
    (jdir / "job.json").write_text(json.dumps({**job, "shorts": shorts}))
    run(jdir.name, "--lane", "tech", "--route", "long")
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []


def test_lane_none_never_posts(world, jobs):
    jdir = make_job(jobs)
    with pytest.raises(SystemExit):
        run(jdir.name, "--lane", "none")


def test_scheduled_shorts_land_on_the_scoreboard_once(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    run(jdir.name, "--go")
    lines = world["board"].read_text().strip().splitlines()
    assert len(lines) == 1 + 2
    assert "TechTony" in lines[1] and "no related video" in lines[1]


def test_dry_run_builds_every_request_and_sends_nothing(world, jobs, capsys):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go", "--dry-run")
    assert world["sent"] == []
    assert "dry run 1 > Tony TikTok" in capsys.readouterr().out
    assert all(r.get("status") is None for r in record(jdir)["rows"])


# ---- review findings (2026-10-29) ----------------------------------------------------------

def test_a_timed_out_scheduled_post_is_looked_up_not_resent(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    world["timeout"].add("90001")                              # Tony TikTok
    run(jdir.name, "--go")
    assert record(jdir)["rows"][0]["posts"]["me_tiktok"]["unknown"]
    world["timeout"].clear()
    world["schedules"].append({"id": "sch-found", "account": "90001"})
    before = len(world["sent"])
    run(jdir.name, "--go")
    assert len(world["sent"]) == before                        # found in Blotato: nothing resent
    assert record(jdir)["rows"][0]["posts"]["me_tiktok"]["submission_id"] == "sch-found"


def test_a_timed_out_scheduled_post_missing_from_blotato_is_sent_again(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    world["timeout"].add("90001")
    run(jdir.name, "--go")
    world["timeout"].clear()
    before = len(world["sent"])
    run(jdir.name, "--go")
    assert [b["post"]["accountId"] for b in world["sent"][before:]] == ["90001", "90001"]


def test_a_timed_out_immediate_post_waits_for_retry_unknown(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    world["timeout"].add("90003")                               # Tony LI, the full video at Go
    run(jdir.name, "--go")
    world["timeout"].clear()
    before = len(world["sent"])
    run(jdir.name, "--go")
    assert not [b for b in world["sent"][before:] if "scheduledTime" not in b]
    run(jdir.name, "--go", "--retry-unknown")
    assert [b for b in world["sent"][before:] if "scheduledTime" not in b]


def test_a_crash_mid_row_keeps_the_ids_already_sent(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    world["crash"]["after"] = 2
    with pytest.raises(KeyboardInterrupt):
        run(jdir.name, "--go")
    posts = record(jdir)["rows"][0]["posts"]
    assert sum(1 for p in posts.values() if p.get("submission_id")) == 2
    world["crash"]["after"] = None
    before = len(world["sent"])
    run(jdir.name, "--go")
    row = record(jdir)["rows"][0]
    mine = {(lanes.channel(k)["accountId"], blotato.utc_z(row["times"][k])) for k in row["channels"]}
    first_row = [b for b in world["sent"][before:] if (b["post"]["accountId"], b.get("scheduledTime")) in mine]
    assert len(first_row) == len(row["channels"]) - 2


def test_a_caption_change_after_the_table_stops_go(world, jobs, capsys):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    job = json.loads((jdir / "job.json").read_text())
    job["shorts"][0]["description"] = "A new lead line nobody reviewed."
    (jdir / "job.json").write_text(json.dumps(job))
    run(jdir.name, "--go")
    assert world["sent"] == []
    assert "caption or a file" in capsys.readouterr().out


def test_a_recut_short_after_the_table_stops_go(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    (jdir / "out" / "short_1.mp4").write_bytes(b"recut")
    run(jdir.name, "--go")
    assert world["sent"] == []


def test_todays_earlier_linkedin_post_blocks_another_today(world, jobs, monkeypatch):
    first = make_job(jobs)
    run(first.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(first.name, "--go")                                    # full video on Tony LI at 08:00
    second = make_job(jobs, name="20261029-090000-second")
    monkeypatch.setattr(publish, "now", lambda: NOW.replace(hour=8, minute=30))
    run(second.name, "--lane", "tech", "--youtube", YOUTUBE)
    full = next(r for r in record(second)["rows"] if r["kind"] == "linkedin_full")
    assert full["channels"] == [] and "already" in full["skipped"]["me_linkedin"]


def test_edit_moving_the_9am_short_to_noon_cancels_its_linkedin_post(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE, "--drop", "L")
    run(jdir.name, "--lane", "tech", "--drop", "L", "--go")
    row = record(jdir)["rows"][0]
    assert "me_linkedin" in row["channels"]
    run(jdir.name, "--edit", "--at", "1=2026-10-31 12:00")
    row = record(jdir)["rows"][0]
    assert "me_linkedin" not in row["channels"] and row["posts"]["me_linkedin"]["cancelled"]
    assert world["moved"] and all(account != "90003" for account, _ in world["moved"])


def test_edit_refuses_a_time_in_the_past(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    with pytest.raises(SystemExit):
        run(jdir.name, "--edit", "--at", "1=2026-10-29 09:00")


def test_a_pin_in_the_past_is_refused(world, jobs):
    jdir = make_job(jobs)
    with pytest.raises(SystemExit):
        run(jdir.name, "--lane", "tech", "--at", "1=2026-10-29T09:00")


def test_a_corrupt_sidecar_stops_everything(world, jobs):
    jdir = make_job(jobs)
    (jdir / "publish.json").write_text("{not json")
    with pytest.raises(SystemExit):
        run(jdir.name, "--lane", "tech")
    assert (jdir / "publish.json").read_text() == "{not json"


def test_realestate_go_refuses_when_the_dre_footer_is_missing(world, jobs, monkeypatch):
    jdir = make_job(jobs)
    monkeypatch.setattr(common, "load_config", lambda: {"BLOTATO_API_KEY": "k", "YOUTUBE_FOOTER": ""})
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE, "--drop", "1:brand_youtube", "--drop", "2:brand_youtube")
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []


def test_media_goes_to_a_content_named_bunny_path(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    url = record(jdir)["rows"][0]["media_url"]
    assert f"faceless/{jdir.name}/publish/short_1_" in url and url.endswith(".mp4")


# ---- per-platform times and the night LinkedIn hold -----------------------------------------------

def test_the_go_table_shows_each_channels_own_time(world, jobs, capsys):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    out = capsys.readouterr().out
    tiktok = lanes.spec()["lanes"]["tech"]["stagger"]["09:00"]["me_tiktok"]
    assert f"Tony TikTok {tiktok}" in out


def pre_stagger(jdir, row_id):
    """Rewrite a sent row the way rows looked before stagger: every post on the anchor minute."""
    rec = record(jdir)
    rows = [{**r, "times": None, "posts": {k: {**p, "at": r["at"]} for k, p in r["posts"].items()}}
            if r["id"] == row_id else r for r in rec["rows"]]
    publish_store.save(jdir, {**rec, "rows": rows})


def test_edit_restaggers_a_row_that_went_out_on_one_minute(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE, "--drop", "L")
    run(jdir.name, "--lane", "tech", "--drop", "L", "--go")
    rec = record(jdir)
    anchor = rec["rows"][0]["at"]                    # make row 1 look like a pre-stagger post
    old = {**rec["rows"][0], "times": None,
           "posts": {k: {**p, "at": anchor} for k, p in rec["rows"][0]["posts"].items()}}
    publish_store.save(jdir, {**rec, "rows": [old, *rec["rows"][1:]]})
    run(jdir.name, "--edit", "--at", "1=2026-10-30 09:00")
    row = record(jdir)["rows"][0]
    spec = lanes.spec()
    tiktok = spec["channels"]["me_tiktok"]["accountId"]
    want = pp.channel_times(datetime.fromisoformat(anchor), ["me_tiktok"], spec["lanes"]["tech"]["stagger"])
    assert (tiktok, want["me_tiktok"]) in world["moved"]
    assert row["posts"]["me_tiktok"]["at"] == want["me_tiktok"] == row["times"]["me_tiktok"]
    # Tony LI's 08:00 is already under ten minutes away at 08:00: it stays on 9:00, untouched.
    assert all(account != "90003" for account, _ in world["moved"])
    assert row["posts"]["me_linkedin"]["at"] == anchor


def test_a_night_go_holds_the_linkedin_video_for_the_morning(world, jobs, monkeypatch, capsys):
    night = NOW.replace(hour=1, minute=22)
    monkeypatch.setattr(publish, "now", lambda: night)
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    li_time = lanes.spec()["lanes"]["tech"]["stagger"]["09:00"]["me_linkedin"]
    assert f"Tony LI {li_time}" in capsys.readouterr().out      # the table shows when it really posts
    run(jdir.name, "--go")
    li = [b for b in world["sent"] if b["post"]["accountId"] == "90003"]
    li_time = lanes.spec()["lanes"]["tech"]["stagger"]["09:00"]["me_linkedin"]
    morning = datetime.fromisoformat(f"2026-10-30T{li_time}").replace(tzinfo=pp.TZ)
    assert [b.get("scheduledTime") for b in li] == [blotato.utc_z(morning)]
    clip = platform_util.clipboard_cmd()
    assert clip is None or clip in world["shell"]
    assert platform_util.open_cmd("x")[:-1] not in [cmd[:-1] for cmd in world["shell"]]    # nothing to open until it posts


def test_a_pinned_linkedin_video_never_blocks_the_lanes_9am_short(world, jobs):
    first = make_job(jobs)
    run(first.name, "--lane", "tech", "--youtube", YOUTUBE, "--at", "L=2026-10-31T09:00")
    run(first.name, "--go")
    booked = publish_store.bookings(jobs, NOW)
    assert datetime(2026, 10, 31, 9, tzinfo=pp.TZ) not in booked["taken"].get("tech", set())
    assert NOW.date().replace(day=31) in booked["li_days"]
    assert ("me_linkedin", pp.minute(datetime(2026, 10, 31, 8, tzinfo=pp.TZ))) in booked["busy"]


def test_edit_refuses_a_move_onto_a_minute_another_post_holds(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE, "--drop", "L")
    run(jdir.name, "--lane", "tech", "--drop", "L", "--go")
    with pytest.raises(SystemExit):                  # row 2 already has X at 13:00 today
        run(jdir.name, "--edit", "--at", "1=2026-10-30 12:00")
    assert world["moved"] == [] and world["cancelled"] == []


def test_edit_refuses_moving_the_linkedin_video_onto_a_booked_li_day(world, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE, "--at", "L=2026-10-31T09:00")
    run(jdir.name, "--go")                           # Short 1 has Tony LI on 10-30
    with pytest.raises(SystemExit):
        run(jdir.name, "--edit", "--at", "L=2026-10-30 12:00")
    assert world["moved"] == []


def test_restaggering_on_the_same_day_keeps_a_borrowed_li_post(world, jobs):
    # Tech borrows Tony LI on 10-31 (real estate's day), then real estate books its 9:00 Short
    # there. Re-staggering the tech row on the same day must move its LI post, not cancel it.
    tech = make_job(jobs)
    run(tech.name, "--lane", "tech", "--youtube", YOUTUBE, "--drop", "L", "--start", "2026-10-31")
    run(tech.name, "--lane", "tech", "--drop", "L", "--go")
    assert "me_linkedin" in record(tech)["rows"][0]["channels"]
    pre_stagger(tech, "1")
    home = make_job(jobs, name="20261029-090000-realestate")
    run(home.name, "--lane", "realestate", "--youtube", YOUTUBE, "--drop", "L", "--start", "2026-10-31")
    rows = record(home)["rows"]
    assert rows[0]["at"] == datetime(2026, 10, 31, 9, tzinfo=pp.TZ).isoformat()   # not pushed off 9:00
    run(home.name, "--lane", "realestate", "--drop", "L", "--go")
    run(tech.name, "--edit", "--at", "1=2026-10-31 09:00")
    row = record(tech)["rows"][0]
    assert world["cancelled"] == [] and "me_linkedin" in row["channels"]
    assert ("90003", row["times"]["me_linkedin"]) in world["moved"]
