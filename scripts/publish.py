"""fv.py publish: schedule a finished job's Shorts and its LinkedIn video in Blotato.

  fv.py publish JOB [--lane tech|realestate|training|none] [--route short|long] [--youtube ID|URL]
                    [--uploaded 2026-10-29] [--site sitetwo.com] [--drop 2] [--drop 2:me_x] [--drop B] [--restore 2]
                    [--add 1:partner_linkedin] [--signer tony|partner]
                    [--at 2=2026-10-31T15:00] [--start 2026-11-02] [--urgent | --no-urgent]
                                         plan, then print the Go table (nothing is posted)
  fv.py publish JOB --go [--dry-run] [--retry-unknown]
                                         post what the last table showed
  fv.py publish JOB --edit --drop 2 | --at 2=...   cancel or retime posts already in Blotato
  fv.py blotato-accounts [--pages]       the account ids channels.json should carry

The training lane (agent training, Example Realty Training YouTube + the HM LinkedIn page)
posts no full LinkedIn video; --add 1:partner_linkedin puts Partner's LinkedIn on Short 1.
--signer partner (or "signer": "partner" in job.json) is for a video Partner is on: every
DRE caption carries her license line (PARTNER_FOOTER), Tony LI and the full LinkedIn video
come off the job, and her LinkedIn goes on Short 1.
Row B is the companion article (out/blog.md): Go publishes it first (publish_blog.py), then
the Shorts carry its link. Run it after the 16:9 is up in Studio (public for LONG, Unlisted for SHORT). --go refuses
when the plan, a caption or a file changed since the table Tony saw; it re-prints the table
instead. Re-running --go only retries what failed. Go and --edit live in publish_go.py.
Spec: docs/briefs/2026-10-29-auto-poster.md."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import blotato
import common
import format_route
import kit_links
import lanes
import publish_blog
import publish_go
import publish_plan as pp
import publish_rows
import publish_store


def now() -> datetime:
    return datetime.now(pp.TZ)


# ---- planning -----------------------------------------------------------------------------

def _lane(args, record: dict, job: dict) -> str:
    lane = args.lane or record.get("lane") or lanes.default_lane(job)
    if lane not in lanes.LANES:
        raise ValueError("no lane for this job: add --lane tech, --lane realestate, --lane training or --lane none")
    if lane == "none":
        raise ValueError("lane none never posts (YourShop, Partner, one-offs)")
    return lane


def _route(jdir: Path, args, record: dict) -> str:
    route = (args.route or record.get("route") or format_route.recorded_kind(jdir) or "").upper()
    if route not in ("SHORT", "LONG"):
        found = route or "none recorded"
        raise ValueError(f"route is {found}: pick one with --route short or --route long")
    return route


def _youtube(jdir: Path, args, record: dict) -> str | None:
    if args.uploaded:
        kit_links.save(jdir, upload_date=kit_links.upload_date(args.uploaded))
    if args.youtube:
        vid = kit_links.video_id(args.youtube)
        kit_links.save(jdir, youtube_id=vid)
        kit_links.refresh(jdir)                # the Full episode line and the LinkedIn comment
        return vid
    return kit_links.load(jdir).get("youtube_id") or record.get("youtube_id")


def _signer(args, record: dict, job: dict) -> str:
    signer = getattr(args, "signer", None) or record.get("signer") or job.get("signer") or lanes.DEFAULT_SIGNER
    lanes.signer_label(signer)                 # refuses a signer channels.json does not know
    return signer


def _signer_rows(rows: list[dict], signer: str, lane: str) -> list[dict]:
    """The signer's own LinkedIn on Short 1, unless a row already has it or Tony dropped it."""
    linkedin = lanes.signer_linkedin(signer)
    if not linkedin or linkedin not in lanes.optional_channels(lane):
        return rows
    if any(linkedin in r.get("add_channels", []) or linkedin in r.get("drop_channels", []) for r in rows):
        return rows
    first = next((r for r in rows if r["id"] == "1" and r["kind"] == "short"
                  and r.get("status") not in pp.SENT and not r.get("dropped")), None)
    return pp.add(rows, f"1:{linkedin}", lanes.optional_channels(lane)) if first else rows


def _edits(rows: list[dict], args, lane: str) -> list[dict]:
    """--drop, --restore, --add and --at on rows not sent yet. A row already in Blotato needs
    --edit, which edit() handles; --add never reaches a sent row."""
    optional = lanes.optional_channels(lane)
    channels = [*lanes.lane_channels(lane), *optional]
    sent = {r["id"] for r in rows if r.get("status") in pp.SENT}

    blog = next((r for r in rows if r["kind"] == "blog"), None)

    def pending(row_id: str) -> bool:
        if blog and row_id == "B" and blog.get("status") == "published":
            raise ValueError(f"the blog is already pushed to {blog.get('url')}: fv.py publish never takes a post down")
        if row_id not in sent:
            return True
        if not args.edit:
            raise ValueError(f"row {row_id} is already in Blotato: add --edit to change it there")
        return False

    for target in args.drop or []:
        if pending(target.partition(":")[0]):
            rows = pp.drop(rows, target, channels)
    for row_id in args.restore or []:
        if pending(row_id):
            rows = pp.restore(rows, row_id)
    for target in getattr(args, "add", None) or []:
        if target.partition(":")[0] in sent:
            raise ValueError(f"row {target.partition(':')[0]} is already in Blotato: --add works only before Go")
        rows = pp.add(rows, target, optional)
    for spec in args.at or []:
        row_id, _, when = spec.partition("=")
        if row_id == "B":
            raise ValueError("the blog (row B) goes out at Go, before the Shorts: it cannot be pinned")
        if pending(row_id):
            rows = pp.pin(rows, row_id, pp.parse_when(when))
    return rows


def plan(jdir: Path, args, at: datetime) -> dict:
    """The record with fresh slots for everything not yet in Blotato. Writes nothing except
    links.json when --youtube is given."""
    record = publish_store.load(jdir)
    job = publish_rows.load_job(jdir)
    lane, route = _lane(args, record, job), _route(jdir, args, record)
    signer = _signer(args, record, job)
    vid = _youtube(jdir, args, record)
    site = args.site or record.get("blog_site")
    fresh = publish_rows.build(jdir, job, route, format_route.probe_seconds)
    if not lanes.full_linkedin(lane) or pp.LI_KEY in lanes.signer_never(signer):
        # training: episodes live on YouTube; Partner's job: row L posts only to Tony LI
        fresh = [r for r in fresh if r["kind"] != "linkedin_full"]
    blog = next((r for r in record.get("rows") or [] if r["kind"] == "blog" and r.get("status") in pp.SENT), None) \
        or publish_blog.plan_row(jdir, lane, site, vid, kit_links.load(jdir), at.astimezone(pp.TZ).date())
    rows = _edits(publish_rows.merge(record.get("rows"), [blog, *fresh] if blog else fresh), args, lane)
    rows = _signer_rows(rows, signer, lane)
    start = args.start or record.get("start")
    urgent = record.get("urgent", False) if args.urgent is None else args.urgent
    booked = publish_store.bookings(common.JOBS_DIR, at, skip=Path(jdir).name)
    other = "realestate" if lane == "tech" else "tech"
    platforms = {k: v["platform"] for k, v in lanes.spec()["channels"].items()}
    assigned = pp.assign(rows, lane=lane, lane_channels=lanes.signer_channels(lane, signer), now=at,
                         taken=booked["taken"].get(lane), li_days=booked["li_days"],
                         other_nine=booked["nine"].get(other, set()),
                         start=date.fromisoformat(start) if start else None, urgent=urgent,
                         platforms=platforms, stagger=lanes.stagger(lane), busy=booked["busy"],
                         accounts=lanes.accounts())
    return {**record, "job": Path(jdir).name, "lane": lane, "signer": signer, "route": route, "youtube_id": vid,
            "blog_url": _blog_url(jdir, assigned), "blog_site": site, "start": start, "urgent": urgent,
            "rows": assigned, "planned_at": at.isoformat(), "lane_booked_through": _through(booked, lane)}


def _blog_url(jdir: Path, rows: list[dict]) -> str | None:
    """The captions' article link: row B's URL (known before it is published), else links.json."""
    blog = next((r for r in rows if r["kind"] == "blog" and not r.get("dropped") and r.get("url")), None)
    return blog["url"] if blog else kit_links.load(jdir).get("blog_url")


def _through(booked: dict, lane: str) -> str | None:
    taken = booked["taken"].get(lane)
    return max(taken).isoformat() if taken else None


def signature(rows: list[dict] | None) -> list:
    """What Tony approves when he says Go: every unsent row's time, channels, file and
    caption hashes (publish_go.with_seen)."""
    return [(r["id"], r.get("at"), tuple(r.get("channels") or ()), bool(r.get("dropped")),
             json.dumps(r.get("seen"), sort_keys=True), json.dumps(r.get("times"), sort_keys=True))
            for r in rows or [] if r.get("status") not in pp.SENT]


# ---- the Go table --------------------------------------------------------------------------

def channel_list(row: dict) -> str:
    """'Tony LI 08:00, Tony X 10:00' when channels post at their own times, else the labels."""
    times = row.get("times") or {}
    keys = row.get("channels") or []
    if not times or all(times.get(k, row.get("at")) == row.get("at") for k in keys):
        return lanes.labels(keys)
    return ", ".join(f"{lanes.channel(k)['label']} {_clock(times[k])}" if k in times else lanes.channel(k)["label"]
                     for k in keys)


def _clock(at: str) -> str:
    return datetime.fromisoformat(at).astimezone(pp.TZ).strftime("%H:%M")


def unverified(record: dict) -> list[str]:
    keys = {k for r in record["rows"] if not r.get("dropped") for k in r.get("channels") or []}
    return sorted(k for k in keys if lanes.channel(k).get("verified") is False)


def table(record: dict, preview: Path | None = None) -> str:
    lane_label = lanes.spec()["lanes"][record["lane"]]["label"]
    signer = record.get("signer") or lanes.DEFAULT_SIGNER
    signed = f"signed {lanes.signer_label(signer)}   " if signer != lanes.DEFAULT_SIGNER else ""
    lines = [f"publish {record['job']}   lane {record['lane']} ({lane_label})   {signed}route {record['route']}   "
             f"video {record.get('youtube_id') or 'none yet'}", "",
             f"{'#':>2}  {'file':<22} {'len':>5}  {'when (Pacific)':<16} {'status':<10} channels"]
    for row in record["rows"]:
        length = f"{float(row.get('seconds') or 0):.0f}s"
        if row.get("dropped"):
            lines.append(f"{row['id']:>2}  {row['file']:<22} {length:>5}  {'DROPPED':<16}")
            continue
        if row["kind"] == "blog":
            lines += _blog_lines(row)
            continue
        status = row.get("status") or "planned"
        lines.append(f"{row['id']:>2}  {row['file']:<22} {length:>5}  {pp.when_label(row.get('at')):<16} "
                     f"{status:<10} {channel_list(row)}")
        for key, reason in (row.get("skipped") or {}).items():
            lines.append(f"{'':>2}  {'':<22} {'':>5}  {'':<16} {'':<10} skips {lanes.channel(key)['label']}: {reason}")
        for key, post in (row.get("posts") or {}).items():
            if post.get("error"):
                lines.append(f"{'':>2}  {'':<22} {'':>5}  {'':<16} {'':<10} FAILED {lanes.channel(key)['label']}: "
                             f"{post['error'][:120]}")
    if record.get("lane_booked_through"):
        lines += ["", f"{record['lane']} lane already booked through {pp.when_label(record['lane_booked_through'])} "
                      "by other jobs"]
    for key in unverified(record):
        ch = lanes.channel(key)
        lines += ["", f"{ch['label']} (Blotato id {ch['accountId']}) is unconfirmed: Go refuses it. "
                      f"Run fv.py blotato-accounts, or drop it (--drop N:{key})."]
    if record["route"] == "LONG" and not record.get("youtube_id"):
        lines += ["", "No YouTube id yet: upload the 16:9, then add --youtube <id or URL>."]
    if preview:
        lines += ["", f"Every caption: {preview}"]
    adds = "".join(f" | --add 1:{key}" for key in lanes.optional_channels(record["lane"]))
    lines += ["", f"Edit: --drop 2 | --drop 2:me_x | --drop B | --site sitetwo.com | --restore 2 | "
                  f"--at 2=2026-10-31T15:00 | --start 2026-11-02 | --urgent{adds}",
              f"Go:   fv.py publish {record['job']} --go"]
    return "\n".join(lines)


def _blog_lines(row: dict) -> list[str]:
    status = row.get("status") or "planned"
    pad = f"{'':>2}  {'':<22} {'':>5}  {'':<16} {'':<10}"
    if row.get("problems"):
        return [f"{row['id']:>2}  {row['file']:<22} {'':>5}  {'at Go':<16} {'BLOCKED':<10} the blog cannot go out",
                *[f"{pad} {p}" for p in row["problems"]], f"{pad} fix blog.md, or --drop B"]
    where = row["url"].split("://", 1)[-1]
    action = publish_blog.ACTIONS.get(row.get("action"), row.get("action") or "")
    lines = [f"{row['id']:>2}  {row['file']:<22} {'':>5}  {pp.when_label(row.get('at')):<16} {status:<10} "
             f"{where} ({row.get('category') or 'no category'}, {action})"]
    notes = [f"site from {row['site_why']}" if row.get("site_why") else "", row.get("library") or "",
             row.get("note") or "", "" if row.get("live", True) else "NOT live yet: check the Vercel deploy"]
    return lines + [f"{pad} {n}" for n in notes if n]


def write_preview(jdir: Path, record: dict, cfg: dict) -> Path:
    """out/publish_preview.md: the exact text every channel will get."""
    copies = publish_go.rendered(jdir, record, cfg)
    parts = [f"# Publish preview: {record['job']}\n\nLane {record['lane']}, route {record['route']}. "
             "Nothing here is posted until Go.\n"]
    for row in record["rows"]:
        if row["kind"] == "blog" and row.get("entry") and not row.get("dropped"):
            parts.append(f"\n## B blog.md > {row['url']} ({publish_blog.ACTIONS[row['action']]}, at Go)\n\n"
                         f"The date is set to the day of Go.\n\n```ts\n{row['entry']}```\n")
        for key, copy in copies.get(row["id"], {}).items():
            title = f"Title: {copy['title']}\n\n" if copy.get("title") else ""
            when = (row.get("times") or {}).get(key) or row.get("at")
            parts.append(f"\n## {row['id']} {row['file']} > {lanes.channel(key)['label']} "
                         f"({pp.when_label(when)})\n\n{title}```\n{copy['text']}\n```\n")
    path = Path(jdir) / "out" / "publish_preview.md"
    path.write_text("".join(parts))
    return path


# ---- commands --------------------------------------------------------------------------------------

def cmd_publish(args) -> None:
    jdir = kit_links.resolve(args.job)
    cfg = common.load_config()
    at = now()
    try:
        saved = publish_store.load(jdir)
        if args.edit:
            saved = publish_go.edit(jdir, saved, cfg, args, at, lambda rec: publish_store.save(jdir, rec))
        record = publish_go.with_seen(jdir, plan(jdir, args, at), cfg)
        if args.go and not args.edit:
            if signature(saved.get("rows")) != signature(record["rows"]):
                publish_store.save(jdir, record)
                print(table(record, write_preview(jdir, record, cfg)))
                print("\n[publish] the plan, a caption or a file is new or changed since the last table: "
                      "review it, then --go again")
                return
            record = publish_go.go(jdir, record, cfg, at, args.dry_run, args.retry_unknown)
        if not args.dry_run:
            publish_store.save(jdir, record)
        print(table(record, write_preview(jdir, record, cfg)))
    except (ValueError, blotato.BlotatoError, RuntimeError, OSError) as err:
        common.die(f"[publish] {err}")


def cmd_accounts(args) -> None:
    key = common.load_config().get("BLOTATO_API_KEY", "")
    known = {str(v["accountId"]): k for k, v in lanes.spec()["channels"].items()}
    try:
        items = blotato.accounts(key)
        for item in sorted(items, key=lambda i: (i.get("platform", ""), i.get("fullname", ""))):
            mark = f"  <- {known[str(item['id'])]}" if str(item["id"]) in known else ""
            print(f"{item.get('platform', ''):<10} {item['id']:>7}  {item.get('fullname', '')}  "
                  f"{item.get('username', '')}{mark}")
            if args.pages and item.get("platform") in ("facebook", "linkedin"):
                for page in blotato.subaccounts(key, item["id"]):
                    print(f"{'':<10} {'':>7}    page {page['id']}  {page.get('name', '')}")
    except blotato.BlotatoError as err:
        common.die(f"[publish] {err}")


def add_parsers(sub) -> None:
    p = sub.add_parser("publish", help="schedule a job's Shorts and LinkedIn video in Blotato (Go table first)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("job")
    p.add_argument("--lane", choices=lanes.LANES)
    p.add_argument("--route", choices=("short", "long"))
    p.add_argument("--youtube", help="the 16:9's YouTube id or URL (recorded in links.json)")
    p.add_argument("--uploaded", metavar="YYYY-MM-DD",
                   help="the 16:9's YouTube publish date, for the blog's video library entry (links.json)")
    p.add_argument("--site", help="the blog's site (siteone.com, sitetwo.com, sitethree.com, "
                                  "brokerage.example, techtony.co), over blog.md and the lane")
    p.add_argument("--drop", action="append", metavar="ROW[:CHANNEL]")
    p.add_argument("--restore", action="append", metavar="ROW")
    p.add_argument("--signer", choices=lanes.signers(),
                   help="whose license line the captions carry (default tony; partner for their videos)")
    p.add_argument("--add", action="append", metavar="ROW:CHANNEL",
                   help="put a lane's optional channel on one row, e.g. 1:partner_linkedin (training)")
    p.add_argument("--at", action="append", metavar="ROW=WHEN", help="pin a row, e.g. 2=2026-10-31T15:00")
    p.add_argument("--start", metavar="YYYY-MM-DD", type=lambda v: date.fromisoformat(v).isoformat())
    p.add_argument("--urgent", dest="urgent", action="store_true", default=None, help="add a 15:00 slot")
    p.add_argument("--no-urgent", dest="urgent", action="store_false")
    p.add_argument("--go", action="store_true", help="post what the last table showed")
    p.add_argument("--edit", action="store_true", help="cancel or retime rows already in Blotato")
    p.add_argument("--dry-run", action="store_true", help="with --go: build every request, send nothing")
    p.add_argument("--retry-unknown", action="store_true",
                   help="with --go: resend immediate posts whose last send timed out (check first)")
    p.set_defaults(fn=cmd_publish)
    a = sub.add_parser("blotato-accounts", help="list Blotato account ids (for assets/publish/channels.json)")
    a.add_argument("--pages", action="store_true", help="also list Facebook and LinkedIn pages")
    a.set_defaults(fn=cmd_accounts)


def parse(argv: list[str]):
    """The publish command's arguments on their own (tests, and scripts that skip fv.py)."""
    parser = argparse.ArgumentParser()
    add_parsers(parser.add_subparsers(dest="cmd", required=True))
    return parser.parse_args(argv)
