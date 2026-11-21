"""Go and --edit for fv.py publish: what Tony approved, sending it to Blotato, and changing
it afterwards. Every channel's result is saved the moment it comes back, so a crash or a
Ctrl-C never loses the id of a post that went out. A create call that timed out is never
retried blindly: it is looked up in Blotato first. Spec: docs/briefs/2026-10-29-auto-poster.md."""
from __future__ import annotations

import csv
import hashlib
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import blotato
import platform_util
import common
import kit_links
import lanes
import publish_blog
import publish_plan as pp
import publish_rows
import publish_store
import upload

LI_POLL_S = 10
LI_POLL_MAX_S = 300
SCOREBOARD = common.ROOT / "docs" / "scoreboard.csv"
DRE_MARK = "DRE"


# ---- what Tony approves -------------------------------------------------------------------

def active(row: dict) -> bool:
    return not row.get("dropped") and row.get("status") not in pp.SENT and bool(row.get("channels"))


def blog_due(row: dict) -> bool:
    """Row B still to publish: it has no Blotato channels, so active() never counts it."""
    return row["kind"] == "blog" and not row.get("dropped") and row.get("status") not in pp.SENT


def file_sig(path: Path) -> list[int]:
    st = Path(path).stat()
    return [st.st_size, st.st_mtime_ns]


def rendered(jdir: Path, record: dict, cfg: dict) -> dict[str, dict[str, dict]]:
    """Every caption that Go would send, by row id and channel key."""
    job = publish_rows.load_job(jdir)
    ai = lanes.ai_footage(jdir)
    return {row["id"]: {key: publish_rows.copy_for(row, lanes.channel(key), jdir, job, record["lane"], cfg,
                                                   record.get("youtube_id"), record.get("blog_url"), ai,
                                                   record.get("signer"))
                        for key in row.get("channels") or []}
            for row in record["rows"] if not row.get("dropped")}


def _sha(copy: dict) -> str:
    return blotato.text_sha(f"{copy.get('title', '')}\n{copy['text']}")


def with_seen(jdir: Path, record: dict, cfg: dict) -> dict:
    """Each unsent row carries what the table showed: its file's size and mtime and a hash of
    every caption. The Go check compares these, so an edit to shorts.md, linkedin.md, the blog
    link or a re-cut between the table and Go stops Go."""
    copies = rendered(jdir, record, cfg)

    def seen(row: dict) -> dict:
        if blog_due(row):
            return {**row, "seen": {"file": file_sig(Path(jdir) / "out" / row["file"]), "site": row.get("site"),
                                    "entry": row.get("entry_sha")}}
        if not active(row):
            return row
        return {**row, "seen": {"file": file_sig(Path(jdir) / "out" / row["file"]),
                                "copy": {k: _sha(c) for k, c in copies.get(row["id"], {}).items()}}}

    return {**record, "rows": [seen(row) for row in record["rows"]]}


def footer_problems(record: dict, copies: dict) -> list[str]:
    """Real estate and training must carry the DRE line on every post; tech must never. A job
    signed by someone other than Tony must carry that signer's own license number."""
    problems = []
    signer = record.get("signer") or lanes.DEFAULT_SIGNER
    number = lanes.signer_dre(signer) if signer != lanes.DEFAULT_SIGNER else None
    for row in record["rows"]:
        if not active(row):
            continue
        for key, copy in copies.get(row["id"], {}).items():
            has = DRE_MARK in copy["text"]
            if lanes.carries_dre(record["lane"]) and not has:
                problems.append(f"row {row['id']} > {key}: {lanes.spec()['lanes'][record['lane']]['label']} "
                                "caption has no DRE line (set YOUTUBE_FOOTER in config.env)")
            if not lanes.carries_dre(record["lane"]) and has:
                problems.append(f"row {row['id']} > {key}: tech caption carries a DRE line")
            if lanes.carries_dre(record["lane"]) and number and number not in copy["text"]:
                problems.append(f"row {row['id']} > {key}: signed {lanes.signer_label(signer)} but the "
                                f"caption lacks license {number} (a footer in job.json overrides the signer's)")
    return problems


def signer_problems(jdir: Path, record: dict) -> list[str]:
    """A signed job never posts to a channel its signer must not use, and is never narrated
    in a voice its signer must not use (Partner's job in Tony's cloned voice)."""
    signer = record.get("signer") or lanes.DEFAULT_SIGNER
    label = lanes.signer_label(signer)
    never = set(lanes.signer_never(signer))
    problems = [f"row {row['id']} > {lanes.channel(key)['label']}: signed {label}, never posts there"
                for row in record["rows"] if active(row) for key in row["channels"] if key in never]
    voice = common.get_state(Path(jdir).name).get("voice")
    if voice and voice in lanes.signer_voice_never(signer):
        problems.append(f"signed {label} but narrated in the {voice!r} voice: re-voice it first")
    return problems


def needs_episode(jdir: Path, record: dict) -> bool:
    """True when a row still to send points back at the long episode: the LinkedIn full video,
    or a Short that is not standalone. Standalone Shorts (a talk cut into pieces with no long
    upload, 2026-11-15) carry no "Full episode" line, so they go without a YouTube id."""
    shorts = publish_rows.load_job(jdir).get("shorts") or []
    for row in record["rows"]:
        if row.get("dropped") or row.get("status") in pp.SENT:
            continue
        if row["kind"] == "linkedin_full":
            return True
        if row["kind"] == "short":
            n = int(row["id"]) - 1
            if not (0 <= n < len(shorts) and shorts[n].get("standalone")):
                return True
    return False


def check(jdir: Path, record: dict, cfg: dict, dry_run: bool) -> None:
    if not dry_run and not cfg.get("BLOTATO_API_KEY"):
        raise ValueError("BLOTATO_API_KEY is not in config.env (blotato.com > Settings > API key)")
    if record["route"] == "LONG" and not record.get("youtube_id") and needs_episode(jdir, record):
        raise ValueError("no YouTube id yet: upload the 16:9 in Studio, then --youtube <id or URL>")
    blog = next((r for r in record["rows"] if blog_due(r)), None)
    if blog and blog.get("problems"):
        raise ValueError("the blog cannot go out (fix blog.md, or --drop B):\n  " + "\n  ".join(blog["problems"]))
    if blog and not record.get("youtube_id"):
        raise ValueError("the blog embeds the 16:9: upload it (Unlisted for SHORT), then --youtube <id or URL>, "
                         "or --drop B")
    keys = {k for r in record["rows"] if active(r) for k in r["channels"]}
    blocked = sorted(k for k in keys if lanes.channel(k).get("verified") is False)
    if blocked:
        raise ValueError(f"unconfirmed Blotato ids on {', '.join(blocked)}: run fv.py blotato-accounts and set "
                         f"verified in assets/publish/channels.json, or --drop N:{blocked[0]}")
    problems = signer_problems(jdir, record) + footer_problems(record, rendered(jdir, record, cfg))
    if problems:
        raise ValueError("captions break the footer rule:\n  " + "\n  ".join(problems))


# ---- sending ---------------------------------------------------------------------------------------

def _file_sha8(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:8]


def media(jdir: Path, row: dict, cfg: dict, key: str) -> dict:
    """The file on Bunny under a name that changes with its content (a same-path re-upload
    can keep serving the old bytes), then Blotato's copy. Reused while the file is unchanged."""
    path = Path(jdir) / "out" / row["file"]
    sig = file_sig(path)
    if row.get("media_sig") == sig and row.get("blotato_media"):
        return {k: row[k] for k in ("media_url", "blotato_media", "media_sig")}
    remote = f"faceless/{Path(jdir).name}/publish/{path.stem}_{_file_sha8(path)}{path.suffix}"
    media_url = upload.put_file(cfg, path, remote)
    return {"media_url": media_url, "blotato_media": blotato.upload_media(key, media_url), "media_sig": sig}


def _resolve_unknown(key: str, post: dict, account: str, when: str | None, sha: str,
                     retry_unknown: bool) -> dict | None:
    """A post whose create call timed out. Scheduled: look for it in Blotato. Immediate: only
    retried with --retry-unknown, after Tony checked it did not go out."""
    if when:
        found = blotato.find_schedule(key, account, when, sha)
        if found:
            return {**post, "submission_id": found, "schedule_id": found, "unknown": False, "error": None}
        return None                     # not there: safe to create it again
    if retry_unknown:
        return None
    return post


def push_row(jdir: Path, record: dict, row: dict, cfg: dict, at: datetime,
             save: Callable[[dict], None], dry_run: bool = False, retry_unknown: bool = False) -> dict:
    """Send one row to every channel it still owes, saving after each channel."""
    key = cfg.get("BLOTATO_API_KEY", "")
    copies = rendered(jdir, {**record, "rows": [row]}, cfg)[row["id"]]
    when = None if row["at"] == "go" else row["at"]
    if not dry_run:
        row = {**row, **media(jdir, row, cfg, key)}
        save(row)
    posts = dict(row.get("posts") or {})
    times = row.get("times") or {}
    for ch_key in row["channels"]:
        post = posts.get(ch_key) or {}
        if post.get("submission_id") or post.get("cancelled"):
            continue
        ch, copy = lanes.channel(ch_key), copies[ch_key]
        ch_when = times.get(ch_key, when) if when else None
        sha = blotato.text_sha(copy["text"])
        if post.get("unknown") and not dry_run:
            kept = _resolve_unknown(key, post, ch["accountId"], ch_when, sha, retry_unknown)
            if kept is not None:
                posts[ch_key] = kept
                if not kept.get("submission_id"):
                    print(f"[publish] {row['id']} > {ch['label']}: the last send timed out and may have posted. "
                          f"Check {ch['label']}; if it is not there, run --go --retry-unknown")
                row = {**row, "posts": posts}
                save(row)
                continue
        body = blotato.post_body(ch, copy["text"], row.get("blotato_media") or f"(dry run) {row['file']}",
                                 ch_when, copy.get("title", ""), lanes.ai_footage(jdir))
        if dry_run:
            print(f"[publish] dry run {row['id']} > {ch['label']} {body.get('scheduledTime', 'now')}")
            continue
        stamp = ch_when or at.isoformat()
        try:
            result = blotato.create_post(key, body)
            posts[ch_key] = {"submission_id": result["postSubmissionId"], "at": stamp,
                             "scheduled_time": result.get("scheduledTime"), "text_sha": sha}
            print(f"[publish] {row['id']} > {ch['label']} {pp.when_label(ch_when)}  {result['postSubmissionId']}")
        except blotato.UnknownOutcome as err:
            posts[ch_key] = {"unknown": True, "error": str(err), "at": stamp, "text_sha": sha}
            print(f"[publish] {row['id']} > {ch['label']} UNKNOWN (may have posted): {err}")
        except (blotato.BlotatoError, KeyError, ValueError) as err:
            posts[ch_key] = {"error": str(err), "text_sha": sha}
            print(f"[publish] {row['id']} > {ch['label']} FAILED: {err}")
        row = {**row, "posts": posts}
        save(row)
        time.sleep(blotato.POST_GAP_S)
    if dry_run:
        return row
    done = all(posts.get(k, {}).get("submission_id") for k in row["channels"])
    row = {**row, "posts": posts, "status": "scheduled" if done else "partial",
           **({"at": at.isoformat()} if row["at"] == "go" and done else {})}
    save(row)
    return row


def _not_live(row: dict) -> bool:
    return row["kind"] == "blog" and not row.get("dropped") and row.get("status") == "published" \
        and not row.get("live")


def publish_blog_row(jdir: Path, record: dict, at: datetime, dry_run: bool) -> dict:
    """Row B before anything goes to Blotato: the captions point at it. A failure, or a page
    that is not live yet, raises, so no Short goes out with a link to a page that is not
    there. The next --go only re-checks a pushed page; it never pushes it twice."""
    i, row = next(((i, r) for i, r in enumerate(record["rows"]) if blog_due(r) or _not_live(r)), (None, None))
    if row is None:
        return record
    if dry_run:
        action = "waits for the pushed page" if _not_live(row) else publish_blog.ACTIONS[row["action"]]
        print(f"[publish] dry run B > {row['url']} ({action}): nothing pushed")
        return record
    if _not_live(row):
        result = {"live": publish_blog.wait_live(row["url"], record["youtube_id"])}
    else:
        result = publish_blog.publish(jdir, row, record["youtube_id"], kit_links.load(jdir), at)
    rows = [*record["rows"][:i], {**row, **result}, *record["rows"][i + 1:]]
    record = publish_store.save(jdir, {**record, "rows": rows, "blog_url": rows[i]["url"]})
    kit_links.save(jdir, blog_url=rows[i]["url"])
    kit_links.refresh(jdir)                    # youtube.md, the LinkedIn comment, the library entry
    if not result["live"]:
        raise RuntimeError(f"the blog is pushed but {rows[i]['url']} is not live yet: check the Vercel deploy, "
                           "then --go again (no Short went out, the blog is not pushed twice)")
    return record


def go(jdir: Path, record: dict, cfg: dict, at: datetime, dry_run: bool = False,
       retry_unknown: bool = False) -> dict:
    check(jdir, record, cfg, dry_run)
    record = publish_blog_row(jdir, record, at, dry_run)
    state = {"record": record}

    def save_row(i: int):
        def save(row: dict) -> None:
            rows = list(state["record"]["rows"])
            rows[i] = row
            state["record"] = {**state["record"], "rows": rows}
            publish_store.save(jdir, state["record"])
        return save

    for i, row in enumerate(record["rows"]):
        if row.get("dropped") or row.get("status") in ("scheduled", "cancelled") or not row.get("channels"):
            continue
        pushed = push_row(jdir, state["record"], row, cfg, at, save_row(i), dry_run, retry_unknown)
        if dry_run:
            continue
        state["record"] = {**state["record"], "rows": [*state["record"]["rows"][:i], pushed,
                                                       *state["record"]["rows"][i + 1:]]}
    record = state["record"]
    if dry_run:
        return record
    record = {**record, "approved_at": record.get("approved_at") or at.isoformat()}
    _record_state(jdir, record, at)
    scoreboard(record)
    linkedin = next((r for r in record["rows"] if r["kind"] == "linkedin_full" and r.get("status") == "scheduled"
                     and not r.get("comment_handed_off")), None)
    if linkedin:
        linkedin_comment(jdir, cfg, linkedin, at)
        record = {**record, "rows": [{**r, "comment_handed_off": True} if r["id"] == linkedin["id"] else r
                                     for r in record["rows"]]}
    publish_store.save(jdir, record)
    return record


def _record_state(jdir: Path, record: dict, at: datetime) -> None:
    """state.json keeps the submission ids too (decision 17), next to the job's other state."""
    common.set_state(str(jdir), published={
        "at": at.isoformat(), "lane": record["lane"], "blog_url": record.get("blog_url"),
        "rows": {r["id"]: {"status": r.get("status"), "at": r.get("at"),
                           "posts": {k: p.get("submission_id") for k, p in (r.get("posts") or {}).items()}}
                 for r in record["rows"]}})


def _to_clipboard(path):
    cmd = platform_util.clipboard_cmd()
    if cmd:
        subprocess.run(cmd, input=Path(path).read_bytes(), check=False)


def linkedin_comment(jdir: Path, cfg: dict, row: dict, at: datetime | None = None) -> None:
    """Blotato cannot post a LinkedIn comment: wait for the post, put the comment on the
    clipboard and open the post, so Tony pastes it once. A post scheduled for later has
    nothing to wait for: the comment goes on the clipboard and Tony pastes it when it posts."""
    comment = Path(jdir) / "out" / "linkedin_comment.txt"
    sub = row["posts"][pp.LI_KEY]["submission_id"]
    posts_at = (row.get("times") or {}).get(pp.LI_KEY) or row.get("at")
    if at is not None and posts_at not in (None, "go") and datetime.fromisoformat(posts_at) > at + pp.MIN_LEAD:
        if comment.exists():
            _to_clipboard(comment)
        print(f"[publish] LinkedIn video posts {pp.when_label(posts_at)}: paste the first comment then "
              f"(out/{comment.name}, on the clipboard now)")
        return
    deadline = time.time() + LI_POLL_MAX_S
    url = None
    while time.time() < deadline:
        try:
            status = blotato.post_status(cfg["BLOTATO_API_KEY"], sub)
        except blotato.BlotatoError as err:
            print(f"[publish] could not read the LinkedIn post status: {err}")
            break
        if status.get("status") == "failed":
            print(f"[publish] LinkedIn post failed in Blotato: {status.get('errorMessage')}")
            return
        url = status.get("publicUrl")
        if url:
            break
        time.sleep(LI_POLL_S)
    if comment.exists():
        _to_clipboard(comment)
        print(f"[publish] first comment is on the clipboard ({comment.name})")
    if url:
        subprocess.run(platform_util.open_cmd(url), check=False)
        print(f"[publish] LinkedIn post: {url}  (paste the first comment there)")
    else:
        print("[publish] LinkedIn post not live yet: paste the comment when it shows up")


def scoreboard(record: dict) -> None:
    """One row per newly scheduled Short, so the 90-day check-in sees them."""
    if not SCOREBOARD.exists():
        return
    with SCOREBOARD.open() as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        logged = {(r.get("job"), r.get("title")) for r in reader}
    channel = lanes.scoreboard_name(record["lane"])
    new = [{"date_published": datetime.fromisoformat(r["at"]).astimezone(pp.TZ).date().isoformat(),
            "job": record["job"], "channel": channel, "format": "short",
            "lane": lanes.spec()["lanes"][record["lane"]]["label"], "title": r.get("title", ""),
            "blog_url": record.get("blog_url") or "",
            "notes": f"fv.py publish via Blotato at {pp.when_label(r['at'])} on "
                     f"{lanes.labels(r.get('channels') or [])}; no related video"}
           for r in record["rows"]
           if r["kind"] == "short" and r.get("status") == "scheduled" and (record["job"], r.get("title")) not in logged]
    if new:
        with SCOREBOARD.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=header, extrasaction="ignore").writerows(new)


# ---- edits after Go ---------------------------------------------------------------------------------

def _li_days_without(jdir: Path, record: dict, row_id: str, at: datetime) -> tuple[set, set]:
    """Tony LI days and the other lane's 9:00 days, leaving out the row being moved."""
    booked = publish_store.bookings(common.JOBS_DIR, at, skip=Path(jdir).name)
    days = set(booked["li_days"])
    for row in record["rows"]:
        if row["id"] != row_id and row.get("status") in ("scheduled", "partial") \
                and pp.LI_KEY in (row.get("channels") or []) and row.get("at") not in (None, "go"):
            days.add(datetime.fromisoformat(row["at"]).astimezone(pp.TZ).date())
    other = "realestate" if record["lane"] == "tech" else "tech"
    return days, booked["nine"].get(other, set())


def edit(jdir: Path, record: dict, cfg: dict, args, at: datetime, save: Callable[[dict], None]) -> dict:
    """Cancel or retime rows already in Blotato, saving after every call. Rows not sent yet
    are edited by the plan."""
    key = cfg.get("BLOTATO_API_KEY", "")
    state = {"record": record}

    def put(row: dict) -> None:
        state["record"] = {**state["record"], "rows": [row if r["id"] == row["id"] else r
                                                       for r in state["record"]["rows"]]}
        save(state["record"])

    def sent(row_id: str) -> dict | None:
        row = next((r for r in state["record"]["rows"] if r["id"] == row_id), None)
        return row if row and row.get("status") in ("scheduled", "partial") else None

    for target in args.drop or []:
        row_id, _, only = target.partition(":")
        row = sent(row_id)
        if row is None:
            continue
        for ch_key in [only] if only else list(row.get("posts") or {}):
            post = (row.get("posts") or {}).get(ch_key) or {}
            if post.get("submission_id") and not post.get("cancelled"):
                blotato.cancel(key, post, lanes.channel(ch_key)["accountId"])
                row = {**row, "posts": {**row["posts"], ch_key: {**post, "cancelled": True}}}
                put(row)
                print(f"[publish] cancelled {row_id} > {lanes.channel(ch_key)['label']}")
        if only:
            row = {**row, "channels": [c for c in row.get("channels") or [] if c != only],
                   "drop_channels": sorted({*row.get("drop_channels", []), only})}
        else:
            row = {**row, "dropped": True, "status": "cancelled"}
        put(row)
    for spec in args.at or []:
        row_id, _, when_text = spec.partition("=")
        row = sent(row_id)
        if row is None:
            continue
        new = pp.parse_when(when_text)
        if new < at + pp.MIN_LEAD:
            raise ValueError(f"{when_text} is past or under 10 minutes away: pick a later time")
        days, other_nine = _li_days_without(jdir, state["record"], row_id, at)
        same_day = datetime.fromisoformat(row["at"]).astimezone(pp.TZ).date() == new.astimezone(pp.TZ).date()
        # Re-staggering on its own day keeps a LI post already there: the owner rule only
        # decides who gets a day's Tony LI, and this row already has it.
        li_block = pp.li_reason(new, state["record"]["lane"], days, set() if same_day else other_nine)
        live = [k for k, p in (row.get("posts") or {}).items() if p.get("submission_id") and not p.get("cancelled")]
        targets = pp.channel_times(new, live, lanes.stagger(state["record"]["lane"]), at + pp.MIN_LEAD)
        keep = [k for k in live if not (k == pp.LI_KEY and li_block and row["kind"] == "short")]
        _refuse_clash(jdir, state["record"], row, {k: targets[k] for k in keep}, days, at)
        # the new plan first, so bookings see where this row is going even if a call fails
        row = {**row, "at": new.isoformat(), "times": {k: targets[k] for k in row.get("channels") or [] if k in keep}}
        put(row)
        for ch_key in live:
            post = row["posts"][ch_key]
            label = lanes.channel(ch_key)["label"]
            if ch_key == pp.LI_KEY and li_block and row["kind"] == "short":
                blotato.cancel(key, post, lanes.channel(ch_key)["accountId"])
                row = {**row, "posts": {**row["posts"], ch_key: {**post, "cancelled": True}},
                       "channels": [c for c in row["channels"] if c != ch_key],
                       "skipped": {**(row.get("skipped") or {}), ch_key: li_block}}
                print(f"[publish] cancelled {row_id} > {label}: {li_block}")
            elif _same_minute(post.get("at"), targets[ch_key]):
                print(f"[publish] {row_id} > {label} stays at {pp.when_label(targets[ch_key])}")
                continue
            else:
                blotato.reschedule(key, post, lanes.channel(ch_key)["accountId"], targets[ch_key])
                row = {**row, "posts": {**row["posts"], ch_key: {**post, "at": targets[ch_key]}}}
                print(f"[publish] moved {row_id} > {label} to {pp.when_label(targets[ch_key])}")
            put(row)
    return state["record"]


def _refuse_clash(jdir: Path, record: dict, row: dict, targets: dict[str, str], li_days: set, at: datetime) -> None:
    """Stop an edit before any Blotato call when a moved post would share its channel and
    minute with another post (the schedule lookup would be ambiguous), or when the full
    LinkedIn video would land on a day Tony LI already has."""
    busy = set(publish_store.bookings(common.JOBS_DIR, at, skip=Path(jdir).name)["busy"])
    for other in record["rows"]:
        if other["id"] != row["id"] and other.get("status") in ("scheduled", "partial"):
            busy |= pp.row_minutes(other)
    hit = pp.clashes(targets, busy, lanes.accounts())
    if hit:
        raise ValueError(f"moving row {row['id']} puts {', '.join(hit)} on a minute another post already has: "
                         "pick another time")
    li_at = targets.get(pp.LI_KEY)
    if row["kind"] == "linkedin_full" and li_at and datetime.fromisoformat(li_at).astimezone(pp.TZ).date() in li_days:
        raise ValueError(f"Tony LI already has its post on {pp.when_label(li_at)[:9]}: pick another day")


def _same_minute(a: str | None, b: str) -> bool:
    if not a or a == "go":
        return False
    return datetime.fromisoformat(a).replace(second=0, microsecond=0) == \
        datetime.fromisoformat(b).replace(second=0, microsecond=0)
