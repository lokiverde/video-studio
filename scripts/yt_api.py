#!/usr/bin/env python3
"""YouTube Data API client for the Example Realty channel. Standard library only.

One-time setup (Tony, Google Cloud console, ~5 minutes): enable "YouTube Data API v3"
and "YouTube Reporting API", create an OAuth client of type "Desktop app", download the
JSON to ~/.config/video-studio-youtube/client_secret.json, set the consent screen to "In
production" (Testing mode kills the refresh token every 7 days). Then:

  yt_api.py setup                       paste client ID + secret instead of the JSON
  yt_api.py auth                        browser consent, pick the Example Realty channel
  yt_api.py list                        uploads: id, privacy, length, views, title
  yt_api.py retitle <id> "New title"    logs the old title to docs/youtube-changes.jsonl
  yt_api.py describe <id> <file> [--dry-run]
                                        new description from a text file or a youtube.md kit,
                                        logs the old one the same way. Only on Tony's go.
  yt_api.py thumb <id> <file.jpg>       custom thumbnail (channel must be phone-verified)
  yt_api.py reach-start                 create the daily reach report job (impressions, CTR)
  yt_api.py reach <id> [<id>...] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                                        impressions + CTR per video from those reports,
                                        all time or only the days in the window

Uploads are deliberately missing: videos uploaded through an unaudited API project are
locked private by YouTube. Upload Shorts in Studio or the app.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import getpass
import http.server
import io
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import common

CONFIG_DIR = Path.home() / ".config" / "video-studio-youtube"
CLIENT_FILE = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
CHANGE_LOG = common.ROOT / "docs" / "youtube-changes.jsonl"
SCOPES = ("https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly")
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
REPORTING = "https://youtubereporting.googleapis.com/v1"
REACH_REPORT = "channel_reach_basic_a1"
PORT = 8765
WRITABLE_SNIPPET = ("title", "description", "categoryId", "tags", "defaultLanguage")
MAX_TITLE = 100
MAX_DESCRIPTION_BYTES = 5000


# ---------- pure helpers (tested) ----------

def auth_url(client_id: str, redirect: str, state: str) -> str:
    return AUTH_URI + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "state": state})


def retitle_body(video_id: str, snippet: dict, title: str) -> dict:
    title = title.strip()
    if not title or len(title) > MAX_TITLE or "<" in title or ">" in title:
        raise ValueError(f"invalid YouTube title ({len(title)} chars, no < or > allowed)")
    kept = {k: snippet[k] for k in WRITABLE_SNIPPET if k in snippet}
    return {"id": video_id, "snippet": {**kept, "title": title}}


def description_from_file(text: str) -> str:
    """A plain text file as it is, or just the Description section of a youtube.md kit."""
    _, mark, rest = text.partition("## Description\n\n")
    return (rest.split("\n\n## ", 1)[0] if mark else text).strip()


def describe_body(video_id: str, snippet: dict, description: str) -> dict:
    description = description.strip()
    if (not description or len(description.encode()) > MAX_DESCRIPTION_BYTES
            or "<" in description or ">" in description):
        raise ValueError(f"invalid YouTube description ({len(description.encode())} bytes, "
                         f"max {MAX_DESCRIPTION_BYTES}, no < or > allowed)")
    kept = {k: snippet[k] for k in WRITABLE_SNIPPET if k in snippet}
    return {"id": video_id, "snippet": {**kept, "description": description}}


def token_expired(token: dict, now: float | None = None) -> bool:
    return (now or time.time()) > token.get("expires_at", 0) - 60


def day_key(day: str | None) -> str | None:
    """2026-09-27 -> 20260927, the reach report's date format. Anything else is refused."""
    if not day:
        return None
    try:
        return datetime.date.fromisoformat(day).strftime("%Y%m%d")
    except ValueError:
        raise ValueError(f"dates are YYYY-MM-DD, got {day!r}") from None


def in_window(day: str, start: str | None, end: str | None) -> bool:
    return (not start or day >= start) and (not end or day <= end)


def latest_per_day(reports: list[dict]) -> list[dict]:
    """One report per day. YouTube can regenerate a day's report; the newest one wins, so a
    corrected day is never counted twice."""
    best: dict[str, dict] = {}
    for rep in reports:
        day = rep.get("startTime", "")[:10]
        if day not in best or rep.get("createTime", "") > best[day].get("createTime", ""):
            best[day] = rep
    return [best[day] for day in sorted(best)]


def reach_summary(csv_text: str, video_ids: set[str], start: str | None = None,
                  end: str | None = None) -> dict:
    """Impressions and clicks per video. start and end (YYYYMMDD, inclusive) keep only the
    rows dated inside the window; without them every row counts (lifetime)."""
    totals: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        vid = row.get("video_id")
        if vid not in video_ids or not in_window(row.get("date", ""), start, end):
            continue
        shown = int(float(row.get("video_thumbnail_impressions") or 0))
        ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
        prev = totals.get(vid, {"impressions": 0, "clicks": 0.0})
        totals[vid] = {"impressions": prev["impressions"] + shown,
                       "clicks": prev["clicks"] + shown * ctr}
    return totals


# ---------- auth ----------

def _client() -> dict:
    if not CLIENT_FILE.exists():
        common.die(f"missing {CLIENT_FILE}. See the setup steps at the top of this file.")
    data = json.loads(CLIENT_FILE.read_text())
    if "installed" not in data:
        common.die(f"{CLIENT_FILE} is not a Desktop app client (project "
                   f"{next(iter(data.values()), {}).get('project_id', '?')}). "
                   "Download the Desktop OAuth client from the YouTube project.")
    return data["installed"]


def _save_token(token: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token))
    os.chmod(TOKEN_FILE, 0o600)


def _post_form(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def cmd_setup(_args) -> None:
    """Write client_secret.json from a pasted client ID and secret, for when the console
    will not let you download the JSON again. The secret is read without echo."""
    client_id = input("OAuth client ID (ends in .apps.googleusercontent.com): ").strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        common.die("that does not look like an OAuth client ID")
    secret = getpass.getpass("Client secret (hidden as you paste): ").strip()
    if len(secret) < 20:
        common.die("that secret looks too short")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_FILE.write_text(json.dumps({"installed": {
        "client_id": client_id, "client_secret": secret, "project_id": "video-studio-youtube",
        "auth_uri": AUTH_URI, "token_uri": TOKEN_URI,
        "redirect_uris": ["http://localhost"]}}))
    os.chmod(CLIENT_FILE, 0o600)
    print(f"[yt_api] saved {CLIENT_FILE}. Next: yt_api.py auth")


def cmd_auth(_args) -> None:
    client = _client()
    redirect, state, box = f"http://127.0.0.1:{PORT}", secrets.token_urlsafe(16), {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
            if "code" not in q and "error" not in q:
                self.send_response(404)  # favicon and prefetches: not the callback
                self.end_headers()
                return
            box.update(q)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Consent received, finishing in the terminal. You can close this tab."
                             if "code" in q else f"Google returned: {q['error']}".encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = auth_url(client["client_id"], redirect, state)
    print(f"[yt_api] opening consent page. If it does not open:\n{url}", flush=True)
    webbrowser.open(url)
    while "code" not in box and "error" not in box:
        server.handle_request()
    if box.get("state") != state or "error" in box:
        common.die(f"[yt_api] consent failed: {box.get('error', 'state mismatch')}")
    token = _post_form(TOKEN_URI, {
        "code": box["code"], "client_id": client["client_id"],
        "client_secret": client["client_secret"], "redirect_uri": redirect,
        "grant_type": "authorization_code"})
    _save_token({**token, "expires_at": time.time() + token["expires_in"]})
    me = api_get("/channels", part="snippet", mine="true")
    names = [c["snippet"]["title"] for c in me.get("items", [])]
    print(f"[yt_api] authorized for channel: {', '.join(names) or '(none)'}", flush=True)


def access_token() -> str:
    if not TOKEN_FILE.exists():
        common.die("[yt_api] not authorized yet. Run: yt_api.py auth")
    token = json.loads(TOKEN_FILE.read_text())
    if token_expired(token):
        client = _client()
        fresh = _post_form(TOKEN_URI, {
            "refresh_token": token["refresh_token"], "client_id": client["client_id"],
            "client_secret": client["client_secret"], "grant_type": "refresh_token"})
        token = {**token, **fresh, "expires_at": time.time() + fresh["expires_in"]}
        _save_token(token)
    return token["access_token"]


# ---------- calls ----------

def _call(method: str, url: str, body: bytes | None = None, ctype: str = "application/json"):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {access_token()}")
    if body is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="ignore")[:600]
        raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {err.code}: {detail}") from err
    return raw


def api_get(path: str, base: str = API, **params) -> dict:
    return json.loads(_call("GET", f"{base}{path}?{urllib.parse.urlencode(params)}"))


def cmd_list(args) -> None:
    channel = api_get("/channels", part="contentDetails", mine="true")["items"][0]
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    items = api_get("/playlistItems", part="contentDetails", playlistId=uploads,
                    maxResults=str(args.limit))["items"]
    ids = ",".join(i["contentDetails"]["videoId"] for i in items)
    for v in api_get("/videos", part="snippet,status,contentDetails,statistics", id=ids)["items"]:
        print(f"{v['id']} | {v['status']['privacyStatus']:8} | "
              f"{v['contentDetails']['duration']:>8} | {v['statistics'].get('viewCount', '0'):>5} v"
              f" | {v['snippet']['title']}")


def _log(entry: dict) -> None:
    CHANGE_LOG.parent.mkdir(exist_ok=True)
    with CHANGE_LOG.open("a") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}) + "\n")


def cmd_retitle(args) -> None:
    items = api_get("/videos", part="snippet", id=args.video)["items"]
    if not items:
        common.die(f"[yt_api] no video {args.video} on this channel")
    old = items[0]["snippet"]
    body = retitle_body(args.video, old, args.title)
    _call("PUT", f"{API}/videos?part=snippet", json.dumps(body).encode())
    _log({"video": args.video, "change": "title", "old": old["title"], "new": body["snippet"]["title"]})
    print(f"[yt_api] {args.video}: '{old['title']}' -> '{body['snippet']['title']}'")


def cmd_describe(args) -> None:
    new = description_from_file(Path(args.file).read_text())
    items = api_get("/videos", part="snippet", id=args.video)["items"]
    if not items:
        common.die(f"[yt_api] no video {args.video} on this channel")
    old = items[0]["snippet"]
    body = describe_body(args.video, old, new)
    if args.dry_run:
        print(f"[yt_api] DRY RUN {args.video} '{old['title']}'\n--- old\n{old.get('description', '')}\n"
              f"--- new\n{body['snippet']['description']}")
        return
    _call("PUT", f"{API}/videos?part=snippet", json.dumps(body).encode())
    _log({"video": args.video, "change": "description", "old": old.get("description", ""),
          "new": body["snippet"]["description"]})
    print(f"[yt_api] {args.video}: description updated, the old one is in {CHANGE_LOG.name}")


def cmd_thumb(args) -> None:
    path = Path(args.file)
    if path.stat().st_size > 2 * 1024 * 1024:
        common.die("[yt_api] thumbnails must be under 2 MB")
    _call("POST", f"{UPLOAD_API}/thumbnails/set?videoId={args.video}", path.read_bytes(), "image/jpeg")
    _log({"video": args.video, "change": "thumbnail", "file": str(path)})
    print(f"[yt_api] {args.video}: thumbnail set from {path.name}")


def cmd_reach_start(_args) -> None:
    jobs = api_get("/jobs", base=REPORTING).get("jobs", [])
    existing = [j for j in jobs if j["reportTypeId"] == REACH_REPORT]
    if existing:
        print(f"[yt_api] reach job already exists: {existing[0]['id']}")
        return
    body = json.dumps({"reportTypeId": REACH_REPORT, "name": "hm reach"}).encode()
    job = json.loads(_call("POST", f"{REPORTING}/jobs", body))
    print(f"[yt_api] reach job {job['id']} created. First reports land in about 48 hours.")


def cmd_reach(args) -> None:
    jobs = [j for j in api_get("/jobs", base=REPORTING).get("jobs", [])
            if j["reportTypeId"] == REACH_REPORT]
    if not jobs:
        common.die("[yt_api] no reach job yet. Run: yt_api.py reach-start")
    reports = api_get(f"/jobs/{jobs[0]['id']}/reports", base=REPORTING).get("reports", [])
    if not reports:
        print("[yt_api] no reports yet (YouTube takes about 48 hours after reach-start)")
        return
    start, end = day_key(args.start), day_key(args.end)
    reports = [r for r in latest_per_day(reports) if in_window(r.get("startTime", "")[:10].replace("-", ""), start, end)]
    days = sorted({r["startTime"][:10] for r in reports})
    print(f"[yt_api] {len(days)} daily reports" + (f", {days[0]} to {days[-1]}" if days else ""))
    totals: dict[str, dict] = {}
    for rep in reports:
        text = _call("GET", rep["downloadUrl"]).decode()
        for vid, t in reach_summary(text, set(args.videos), start, end).items():
            prev = totals.get(vid, {"impressions": 0, "clicks": 0.0})
            totals[vid] = {"impressions": prev["impressions"] + t["impressions"],
                           "clicks": prev["clicks"] + t["clicks"]}
    for vid in args.videos:
        t = totals.get(vid, {"impressions": 0, "clicks": 0.0})
        ctr = t["clicks"] / t["impressions"] * 100 if t["impressions"] else 0.0
        print(f"{vid} | {t['impressions']:>6} impressions | CTR {ctr:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("auth").set_defaults(fn=cmd_auth)
    p = sub.add_parser("list"); p.add_argument("--limit", type=int, default=25); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("retitle"); p.add_argument("video"); p.add_argument("title"); p.set_defaults(fn=cmd_retitle)
    p = sub.add_parser("describe"); p.add_argument("video"); p.add_argument("file")
    p.add_argument("--dry-run", action="store_true", help="show old and new, change nothing"); p.set_defaults(fn=cmd_describe)
    p = sub.add_parser("thumb"); p.add_argument("video"); p.add_argument("file"); p.set_defaults(fn=cmd_thumb)
    sub.add_parser("reach-start").set_defaults(fn=cmd_reach_start)
    p = sub.add_parser("reach"); p.add_argument("videos", nargs="+")
    p.add_argument("--start", help="first day counted, YYYY-MM-DD (default: all time)")
    p.add_argument("--end", help="last day counted, YYYY-MM-DD, inclusive"); p.set_defaults(fn=cmd_reach)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, urllib.error.URLError) as err:
        print(f"[yt_api] {err}", file=sys.stderr)
        sys.exit(1)
