"""Blotato request shapes (openapi.json, 2026-10-29) and how cancel and retime find a schedule.
No network: blotato.send or urlopen is replaced."""
import io
import json
import urllib.error

import pytest

import kit_fixtures  # noqa: F401  (puts scripts/ on the path)
import blotato  # noqa: E402

YT = {"key": "me_youtube", "platform": "youtube", "accountId": "90002"}
FB = {"key": "biz_facebook", "platform": "facebook", "accountId": "90006", "pageId": "900000000000001"}
LI = {"key": "me_linkedin", "platform": "linkedin", "accountId": "90003"}
QUEUED = {"submission_id": "123e4567-e89b-12d3-a456-426614174000", "at": "2026-10-30T09:00:00-07:00",
          "text_sha": blotato.text_sha("ours")}
SCHEDULED = {"id": "4417", "account": {"id": "90002"}, "scheduledAt": "2026-10-30T16:00:00Z",
             "draft": {"content": {"text": "ours"}}}


def test_scheduled_time_sits_at_the_root_in_utc_z():
    body = blotato.post_body(YT, "text", "https://m/x.mp4", "2026-10-30T09:00:00-07:00", title="T")
    assert body["scheduledTime"] == "2026-10-30T16:00:00Z"
    assert "scheduledTime" not in body["post"]
    assert body["post"]["accountId"] == "90002"
    assert body["post"]["content"] == {"text": "text", "mediaUrls": ["https://m/x.mp4"], "platform": "youtube"}


def test_no_time_posts_now():
    assert "scheduledTime" not in blotato.post_body(LI, "t", "u", None)


def test_youtube_target_carries_the_required_fields_and_the_ai_flag():
    t = blotato.target_for(YT, "Title", ai=True)
    assert t == {"targetType": "youtube", "title": "Title", "privacyStatus": "public",
                 "shouldNotifySubscribers": False, "isMadeForKids": False, "containsSyntheticMedia": True}


def test_tiktok_target_has_every_required_field():
    t = blotato.target_for({"platform": "tiktok"}, ai=True)
    for field in ("privacyLevel", "disabledComments", "disabledDuet", "disabledStitch",
                  "isBrandedContent", "isYourBrand", "isAiGenerated"):
        assert field in t
    assert t["isAiGenerated"] is True and t["privacyLevel"] == "PUBLIC_TO_EVERYONE"


def test_facebook_video_is_a_reel_on_the_page():
    assert blotato.target_for(FB) == {"targetType": "facebook", "pageId": "900000000000001", "mediaType": "reel"}


def test_linkedin_personal_has_no_page_id():
    assert blotato.target_for(LI) == {"targetType": "linkedin"}


def test_unknown_platform_is_refused():
    with pytest.raises(ValueError):
        blotato.target_for({"platform": "myspace"})


def test_send_refuses_without_a_key():
    with pytest.raises(blotato.BlotatoError):
        blotato.send("GET", "/users/me/accounts", "")


def test_reschedule_patches_the_new_time(monkeypatch):
    seen = {}
    monkeypatch.setattr(blotato, "send", lambda m, p, k, payload=None, **kw: seen.update(m=m, p=p, body=payload) or {})
    blotato.reschedule("k", {"schedule_id": "4417", "at": "x"}, "1", "2026-10-31T15:00:00-07:00")
    assert seen == {"m": "PATCH", "p": "/schedules/4417", "body": {"patch": {"scheduledTime": "2026-10-31T22:00:00Z"}}}


def test_other_errors_are_not_swallowed(monkeypatch):
    def fake(*a, **kw):
        raise blotato.BlotatoError("bad key", 401)
    monkeypatch.setattr(blotato, "send", fake)
    with pytest.raises(blotato.BlotatoError):
        blotato.cancel("k", {"submission_id": "s", "at": "2026-10-30T09:00:00-07:00"}, "1")


def test_creating_a_post_is_never_retried_after_a_timeout(monkeypatch):
    calls = []

    def slow(req, timeout=None):
        calls.append(req.get_method())
        raise TimeoutError("read timed out")

    monkeypatch.setattr(blotato.urllib.request, "urlopen", slow)
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    with pytest.raises(blotato.UnknownOutcome):
        blotato.create_post("k", {"post": {}})
    assert calls == ["POST"]


def test_reads_are_retried_after_a_timeout(monkeypatch):
    calls = []

    def slow(req, timeout=None):
        calls.append(req.get_method())
        raise TimeoutError("read timed out")

    monkeypatch.setattr(blotato.urllib.request, "urlopen", slow)
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    with pytest.raises(blotato.BlotatoError):
        blotato.accounts("k")
    assert calls == ["GET", "GET", "GET"]


def strict_server(seen, scheduled=()):
    """A urlopen that answers like the live API: a JSON content type with no body is a 400, and
    a schedule id that is not a number is a 500 from Postgres, not a 404."""
    def refuse(req, code, message):
        raise urllib.error.HTTPError(req.full_url, code, "Refused", {}, io.BytesIO(message))

    def answer(req, timeout=None):
        seen.append(req)
        path = req.full_url.removeprefix(blotato.API)
        if req.has_header("Content-type") and req.data is None:
            refuse(req, 400, b"Body cannot be empty when content-type is set to 'application/json'")
        if path.startswith("/schedules?"):
            return io.BytesIO(json.dumps({"items": list(scheduled)}).encode())
        if path.startswith("/schedules/") and not path.rpartition("/")[2].isdigit():
            refuse(req, 500, b"invalid input syntax for type bigint")
        return io.BytesIO(b'{"url": "https://m/x.mp4"}')
    return answer


def sent(seen):
    return [(r.get_method(), r.full_url.removeprefix(blotato.API)) for r in seen]


def test_cancel_with_no_body_gets_past_the_json_check(monkeypatch):
    seen = []
    monkeypatch.setattr(blotato.urllib.request, "urlopen", strict_server(seen))
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    blotato.cancel("k", {**QUEUED, "schedule_id": "4417"}, "90002")
    assert sent(seen) == [("DELETE", "/schedules/4417")]
    assert seen[0].get_header("Blotato-api-key") == "k"


def test_calls_with_a_body_still_declare_json(monkeypatch):
    seen = []
    monkeypatch.setattr(blotato.urllib.request, "urlopen", strict_server(seen))
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    blotato.upload_media("k", "https://cdn/x.mp4")
    blotato.create_post("k", {"post": {}})
    blotato.reschedule("k", {**QUEUED, "schedule_id": "4417"}, "1", "2026-10-31T15:00:00-07:00")
    blotato.send("DELETE", "/schedules/4417", "k", {})
    assert [r.get_method() for r in seen] == ["POST", "POST", "PATCH", "DELETE"]
    assert all(r.get_header("Content-type") == "application/json" for r in seen)


def test_cancel_finds_the_numeric_schedule_for_a_uuid_submission(monkeypatch):
    seen = []
    monkeypatch.setattr(blotato.urllib.request, "urlopen", strict_server(seen, [SCHEDULED]))
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    blotato.cancel("k", QUEUED, "90002")
    assert sent(seen) == [("GET", "/schedules?limit=100"), ("DELETE", "/schedules/4417")]


def test_reschedule_finds_the_numeric_schedule_for_a_uuid_submission(monkeypatch):
    seen = []
    monkeypatch.setattr(blotato.urllib.request, "urlopen", strict_server(seen, [SCHEDULED]))
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    blotato.reschedule("k", QUEUED, "90002", "2026-10-31T15:00:00-07:00")
    assert sent(seen) == [("GET", "/schedules?limit=100"), ("PATCH", "/schedules/4417")]
    assert json.loads(seen[-1].data) == {"patch": {"scheduledTime": "2026-10-31T22:00:00Z"}}


@pytest.mark.parametrize("scheduled", [
    [],
    [{**SCHEDULED, "account": {"id": "90006"}}],
    [{**SCHEDULED, "scheduledAt": "2026-10-30T16:05:00Z"}],
    [{**SCHEDULED, "draft": {"content": {"text": "Tony's own"}}}],
], ids=["nothing queued", "other account", "other minute", "other text"])
def test_a_post_that_is_not_ours_is_never_deleted(monkeypatch, scheduled):
    seen = []
    monkeypatch.setattr(blotato.urllib.request, "urlopen", strict_server(seen, scheduled))
    monkeypatch.setattr(blotato.time, "sleep", lambda s: None)
    with pytest.raises(blotato.BlotatoError):
        blotato.cancel("k", QUEUED, "90002")
    assert all(method == "GET" for method, _ in sent(seen))


def test_schedule_lookup_refuses_two_lookalikes(monkeypatch):
    items = [{"id": f"s{i}", "account": {"id": "1"}, "scheduledAt": "2026-10-30T16:00:00Z"} for i in (1, 2)]
    monkeypatch.setattr(blotato, "schedules", lambda key: items)
    with pytest.raises(blotato.BlotatoError):
        blotato.find_schedule("k", "1", "2026-10-30T09:00:00-07:00")


def test_schedule_lookup_tells_posts_apart_by_text(monkeypatch):
    items = [{"id": "mine", "account": {"id": "1"}, "scheduledAt": "2026-10-30T16:00:00Z",
              "draft": {"content": {"text": "ours"}}},
             {"id": "manual", "account": {"id": "1"}, "scheduledAt": "2026-10-30T16:00:00Z",
              "draft": {"content": {"text": "Tony's own"}}}]
    monkeypatch.setattr(blotato, "schedules", lambda key: items)
    assert blotato.find_schedule("k", "1", "2026-10-30T09:00:00-07:00", blotato.text_sha("ours")) == "mine"
