"""Blotato v2 client for fv.py publish: accounts, media, scheduled posts, cancel and retime.
Shapes checked against https://backend.blotato.com/openapi.json on 2026-10-29. The request
builders are pure; only send() touches the network, so tests replace it.
Spec: docs/briefs/2026-10-29-auto-poster.md."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://backend.blotato.com/v2"
POST_GAP_S = 2.1                  # POST /v2/posts allows 30 a minute
RETRY_STATUS = (429, 500, 502, 503, 504)


class BlotatoError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class UnknownOutcome(BlotatoError):
    """A create call that may or may not have gone through (timeout, 5xx, garbled answer)."""


def send(method: str, path: str, key: str, payload: dict | None = None,
         timeout: int = 120, retries: int = 3, idempotent: bool = True) -> dict:
    """One API call. Retries rate limits, and server errors or timeouts when the call is
    idempotent; raises BlotatoError otherwise. Creating a post is not idempotent: a timeout
    may still have posted, so the caller decides (UnknownOutcome), never a blind retry."""
    if not key:
        raise BlotatoError("BLOTATO_API_KEY is not set in config.env")
    body = json.dumps(payload).encode() if payload is not None else None
    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(f"{API}{path}", data=body, method=method)
        req.add_header("blotato-api-key", key)
        if body is not None:      # Blotato 400s a JSON content type with an empty body
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read()[:400].decode(errors="replace")
            last = BlotatoError(f"Blotato {method} {path} -> HTTP {err.code}: {detail}", err.code)
            if err.code != 429 and (err.code not in RETRY_STATUS or not idempotent):
                if not idempotent and err.code >= 500:
                    raise UnknownOutcome(str(last), err.code) from None
                raise last from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last = BlotatoError(f"Blotato {method} {path} unreachable: {err}")
            if not idempotent:
                raise UnknownOutcome(str(last)) from None
        else:
            try:
                return json.loads(raw) if raw.strip() else {}
            except ValueError:
                message = f"Blotato {method} {path} answered 200 with a body that is not JSON"
                raise (BlotatoError(message) if idempotent else UnknownOutcome(message)) from None
        if attempt < retries:
            time.sleep(5 * attempt)
    raise last


# ---- pure request builders ----------------------------------------------------------------

def target_for(channel: dict, title: str = "", ai: bool = False) -> dict:
    """The platform target. Defaults Tony accepted: YouTube public without notifying
    subscribers, TikTok public with comments, duets and stitches on, video as a reel."""
    platform = channel["platform"]
    if platform == "youtube":
        return {"targetType": "youtube", "title": title or "Video", "privacyStatus": "public",
                "shouldNotifySubscribers": False, "isMadeForKids": False,
                "containsSyntheticMedia": bool(ai)}
    if platform == "tiktok":
        return {"targetType": "tiktok", "privacyLevel": "PUBLIC_TO_EVERYONE", "disabledComments": False,
                "disabledDuet": False, "disabledStitch": False, "isBrandedContent": False,
                "isYourBrand": False, "isAiGenerated": bool(ai)}
    if platform == "facebook":
        return {"targetType": "facebook", "pageId": str(channel["pageId"]), "mediaType": "reel"}
    if platform == "instagram":
        return {"targetType": "instagram", "mediaType": "reel"}
    if platform == "linkedin":
        return {"targetType": "linkedin", **({"pageId": str(channel["pageId"])} if channel.get("pageId") else {})}
    if platform == "twitter":
        return {"targetType": "twitter"}
    raise ValueError(f"no Blotato target for platform {platform!r}")


def utc_z(when: str | datetime) -> str:
    """ISO 8601 in UTC with a Z, the form Blotato documents."""
    value = datetime.fromisoformat(when) if isinstance(when, str) else when
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post_body(channel: dict, text: str, media_url: str, scheduled_at: str | None,
              title: str = "", ai: bool = False) -> dict:
    """POST /v2/posts body. scheduledTime sits beside post at the root (nested, it is
    ignored and the post goes out now). None posts immediately."""
    body = {"post": {"accountId": str(channel["accountId"]),
                     "content": {"text": text, "mediaUrls": [media_url], "platform": channel["platform"]},
                     "target": target_for(channel, title, ai)}}
    if scheduled_at:
        body["scheduledTime"] = utc_z(scheduled_at)
    return body


# ---- calls ------------------------------------------------------------------------------------

def accounts(key: str) -> list[dict]:
    return send("GET", "/users/me/accounts", key).get("items") or []


def subaccounts(key: str, account_id: str) -> list[dict]:
    return send("GET", f"/users/me/accounts/{account_id}/subaccounts", key).get("items") or []


def upload_media(key: str, url: str) -> str:
    """Blotato copies the file from a public URL and returns its own hosted URL."""
    return send("POST", "/media", key, {"url": url}, timeout=600)["url"]


def create_post(key: str, body: dict) -> dict:
    return send("POST", "/posts", key, body, idempotent=False)


def post_status(key: str, submission_id: str) -> dict:
    return send("GET", f"/posts/{submission_id}", key)


def schedules(key: str) -> list[dict]:
    items, cursor = [], None
    while True:
        page = send("GET", "/schedules?limit=100" + (f"&cursor={cursor}" if cursor else ""), key)
        items += page.get("items") or []
        cursor = page.get("cursor") or page.get("nextCursor")
        if not cursor or not page.get("items"):
            return items


def text_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def find_schedule(key: str, account_id: str, when: str, sha: str | None = None) -> str | None:
    """The schedule id of our post: same account, same minute, and the same text when the
    schedule carries it. None when nothing matches; refuses when more than one does."""
    target = utc_z(when)[:16]
    matches = []
    for item in schedules(key):
        account = (item.get("account") or {}).get("id")
        at = item.get("scheduledAt") or ""
        if str(account) != str(account_id) or not at or utc_z(at.replace("Z", "+00:00"))[:16] != target:
            continue
        text = ((item.get("draft") or {}).get("content") or {}).get("text")
        if sha and text is not None and text_sha(text) != sha:
            continue
        matches.append(item["id"])
    if len(matches) > 1:
        raise BlotatoError(f"{len(matches)} scheduled posts on account {account_id} at {target}Z look like "
                           "ours: cancel or move it in Blotato by hand")
    return matches[0] if matches else None


def _schedule_id(key: str, post: dict, account_id: str) -> str:
    """Schedule ids are numbers, not the UUID a new post gets back, and Blotato answers a UUID
    with a 500. So find the schedule by account, time and text unless the row already holds it."""
    if post.get("schedule_id"):
        return post["schedule_id"]
    found = find_schedule(key, account_id, post["at"], post.get("text_sha"))
    if not found:
        raise BlotatoError(f"no scheduled Blotato post for account {account_id} at {post['at']}")
    return found


def cancel(key: str, post: dict, account_id: str) -> None:
    send("DELETE", f"/schedules/{_schedule_id(key, post, account_id)}", key)


def reschedule(key: str, post: dict, account_id: str, when: str) -> None:
    send("PATCH", f"/schedules/{_schedule_id(key, post, account_id)}", key,
         {"patch": {"scheduledTime": utc_z(when)}})
