#!/usr/bin/env python3
"""Post-publication links for a job: the companion article URL, the long-form YouTube ID and
the Short IDs. They live in links.json in the job folder, a sidecar that no approval hash
covers, so adding a link never sends Tony back through the preview gate (faceless approval
hashes scenes.json as raw bytes, talking-head approval hashes job.json). Faceless and
talking-head jobs use the same file. A job without it behaves exactly as before.

  fv.py bloglink <job> <url>                          article URL, then refresh the kit
  fv.py links <job> [--youtube ID] [--blog URL] [--shorts ID ...]
                                                      fill the LinkedIn first comment too

Every apply function is pure and idempotent: it strips its own line before adding it back,
so applying twice equals applying once (the countdown quizlink pattern). The kit writers
(publish_kit, th.py, th_shorts) apply them on every run, so a kit re-run never drops a link.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

import common

LINKS_FILE = "links.json"
BLOG_MARK = "Written version with sources:"
VIDEO_MARK = "Full video:"
FIRST_COMMENT = "## First comment"
YOUTUBE_PENDING = "[YouTube link, after upload]"
BLOG_PENDING = "[article link, after it is published]"
ID_PENDING = "TODO_YOUTUBE_ID"
OWNER_PENDING = "TODO_ARTICLE_URL"
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL_ID = re.compile(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
FIRST_COMMENT_SECTION = re.compile(r"\n*^#{1,2}[ \t]+first comment[^\n]*\n.*\Z", re.M | re.S | re.I)


# ---------- the record ----------

def load(jdir: Path) -> dict:
    """links.json as a dict, empty when the job has none (or it is unreadable)."""
    try:
        data = json.loads((Path(jdir) / LINKS_FILE).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(jdir: Path, **updates) -> dict:
    """New record with the non-empty updates merged in, written back to links.json."""
    links = {**load(jdir), **{k: v for k, v in updates.items() if v}}
    (Path(jdir) / LINKS_FILE).write_text(json.dumps(links, indent=2, sort_keys=True) + "\n")
    return links


def check_url(url: str) -> str:
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s/]+\.[^\s]+$", url):
        raise ValueError(f"not a full http(s) URL: {url!r}")
    return url


def video_id(value: str) -> str:
    """An 11 character YouTube ID, from the ID itself or any youtu.be / watch / shorts URL."""
    value = (value or "").strip()
    if YOUTUBE_ID.match(value):
        return value
    found = YOUTUBE_URL_ID.search(value)
    if not found:
        raise ValueError(f"not a YouTube video ID or URL: {value!r}")
    return found.group(1)


def upload_date(value: str) -> str:
    """YYYY-MM-DD or a full ISO 8601 timestamp (YouTube's publishedAt), as given."""
    value = (value or "").strip()
    try:
        (datetime if "T" in value else date).fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"not an ISO 8601 date: {value!r}") from None
    return value


def youtube_url(vid: str) -> str:
    return f"https://youtu.be/{vid}"


# ---------- pure apply functions ----------

def blog_line(url: str) -> str:
    return f"{BLOG_MARK} {url}"


def with_blog_line(description: str, url: str | None) -> str:
    """The description with the article link as its first line, then a blank line, then the
    rest. No URL leaves the description untouched, byte for byte."""
    if not url:
        return description
    kept = [ln for ln in (description or "").split("\n") if not ln.startswith(BLOG_MARK)]
    body = "\n".join(kept).lstrip("\n")
    return f"{blog_line(url)}\n\n{body}" if body.strip() else blog_line(url)


def youtube_md_with_blog(md: str, url: str | None) -> str:
    """youtube.md with the blog line first in its Description section, nothing else touched."""
    head, mark, rest = md.partition("## Description\n\n")
    if not url or not mark:
        return md
    description, end, tail = rest.partition("\n\n## ")
    return head + mark + with_blog_line(description, url) + end + tail


def first_comment_lines(links: dict) -> list[str]:
    vid, blog = links.get("youtube_id"), links.get("blog_url")
    return [f"{VIDEO_MARK} {youtube_url(vid) if vid else YOUTUBE_PENDING}",
            f"{BLOG_MARK} {blog or BLOG_PENDING}"]


def with_first_comment(md: str, lines: list[str]) -> str:
    """linkedin.md ending in exactly one '## First comment' section, replacing any earlier one."""
    base = FIRST_COMMENT_SECTION.sub("", md).rstrip("\n")
    return f"{base}\n\n{FIRST_COMMENT}\n\n" + "\n".join(lines) + "\n"


def entry_with_links(text: str, links: dict) -> str:
    """video_library_entry.txt with the YouTube ID, upload date and article URL filled in."""
    for key, value in (("id", links.get("youtube_id")), ("uploadDate", links.get("upload_date")),
                       ("ownerUrl", links.get("blog_url"))):
        if value:
            text = re.sub(rf'^(\s*"{key}": )"[^"\n]*"', lambda m: m.group(1) + json.dumps(value), text,
                          count=1, flags=re.M)
    return text


# ---------- refresh the kit files in place ----------

def _rewrite(path: Path, fn) -> bool:
    if not path.exists():
        return False
    old = path.read_text()
    new = fn(old)
    if new != old:
        path.write_text(new)
    return True


def refresh(jdir: Path) -> list[Path]:
    """Apply the links record to every kit file that exists. Idempotent. Never touches
    scenes.json or job.json, so no approval is voided."""
    import format_route  # lazy: keeps this module light for the kit writers
    jdir = Path(jdir)
    out = jdir / "out"
    links = load(jdir)
    touched = []
    if _rewrite(out / "youtube.md", lambda md: youtube_md_with_blog(md, links.get("blog_url"))):
        touched.append(out / "youtube.md")
    if (out / "shorts.md").exists() and (jdir / "job.json").exists():
        import th_shorts
        touched.append(th_shorts.write_kit(str(jdir)))
    if _rewrite(out / "linkedin.md", lambda md: with_first_comment(md, first_comment_lines(links))):
        (out / "linkedin_comment.txt").write_text("\n".join(first_comment_lines(links)) + "\n")
        touched += [out / "linkedin.md", out / "linkedin_comment.txt"]
    if _rewrite(out / "video_library_entry.txt", lambda text: entry_with_links(text, links)):
        touched.append(out / "video_library_entry.txt")
    route = format_route.redecide(jdir)
    if route:
        touched.append(out / "route.md")
    return touched


# ---------- commands (fv.py bloglink, fv.py links) ----------

def resolve(job: str) -> Path:
    """A job id under jobs/, or a path to a job folder (anything with a slash, ~ or a dot first)."""
    if "/" in job or job.startswith(("~", ".")):
        path = Path(job).expanduser().resolve()
        if not path.is_dir():
            common.die(f"[links] no such job folder: {path}")
        return path
    return common.job_dir(job)


def _report(jdir: Path, touched: list[Path]) -> None:
    print(f"[links] {jdir / LINKS_FILE}")
    for path in touched:
        print(f"[links] {path}")
    if not touched:
        print("[links] no kit files yet; the kit picks the links up when it is written")


def cmd_bloglink(args) -> None:
    jdir = resolve(args.job)
    try:
        url = check_url(args.url)
    except ValueError as err:
        common.die(f"[links] {err}")
    save(jdir, blog_url=url)
    _report(jdir, refresh(jdir))


def cmd_links(args) -> None:
    jdir = resolve(args.job)
    try:
        updates = {"youtube_id": video_id(args.youtube) if args.youtube else None,
                   "blog_url": check_url(args.blog) if args.blog else None,
                   "short_ids": [video_id(s) for s in args.shorts] if args.shorts else None,
                   "upload_date": upload_date(args.uploaded) if args.uploaded else None}
    except ValueError as err:
        common.die(f"[links] {err}")
    save(jdir, **updates)
    touched = refresh(jdir)
    _report(jdir, touched)
    comment = jdir / "out" / "linkedin_comment.txt"
    if comment.exists():
        print(f"[links] paste after posting on LinkedIn:\n{comment.read_text()}", end="")


def add_parsers(sub) -> None:
    """The two subcommands, shared by fv.py and this module's own main()."""
    p = sub.add_parser("bloglink", help="companion article URL into links.json, then refresh the kit")
    p.add_argument("job")
    p.add_argument("url")
    p.set_defaults(fn=cmd_bloglink)
    p = sub.add_parser("links", help="YouTube ID / article URL into links.json, fill the LinkedIn first comment")
    p.add_argument("job")
    p.add_argument("--youtube", help="long-form video ID or URL")
    p.add_argument("--blog", help="companion article URL")
    p.add_argument("--shorts", nargs="+", help="Short IDs or URLs, in short_1, short_2 order")
    p.add_argument("--uploaded", help="YouTube publish date, YYYY-MM-DD or ISO 8601, for the library entry")
    p.set_defaults(fn=cmd_links)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_parsers(parser.add_subparsers(dest="cmd", required=True))
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
