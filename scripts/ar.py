#!/usr/bin/env python3
"""Archive reel CLI. A 9:16 product ad built from real public-domain silent film, cut to a
beat, with the brand logo printed into the footage and the product revealed at the end.

  ar.py new <product-url> [--title T]    job folder, product images + blurb from Shopify, job.json skeleton
  ar.py check <job>                      validate job.json (sources, beat grid, UI safe zones)
  ar.py comp <job> [--only NAME]         distant-figure composites into archive plates (public/comp_*.mp4)
  ar.py sheet <job>                      render every shot, contact sheet, shown to Tony
  ar.py approve <job>                    record Tony's go (only after he says so)
  ar.py render <job> [--no-preview]      blocked until approved: silent master + soundtrack(s) + post kit
  ar.py score <job>                      redo only the soundtrack(s) on the approved picture
  ar.py kit <job>                        rewrite out/post.txt
"""
import argparse
import json
import re
import shutil
import sys
import time
import urllib.request

import approval
import ar_audio
import ar_comp
import ar_film
import ar_lib
import common

KIND = "archive-reel"
TEMPLATE = ar_film.ARCHIVE / "templates" / "job_template.json"


def load_job(job_id):
    path = common.job_dir(job_id) / "job.json"
    if not path.exists():
        common.die(f"job {job_id} has no job.json (is it an archive-reel job?)")
    return json.loads(path.read_text())


def checked_job(job_id):
    jdir, job = common.job_dir(job_id), load_job(job_id)

    def exists(kind, src):
        folder = jdir / "public" if kind in ("public", "clip", "still") else ar_film.ARCHIVE / "clips"
        return (folder / src).exists()

    problems = ar_lib.validate(job, exists)
    if problems:
        common.die("[ar] job.json problems:\n  - " + "\n  - ".join(problems))
    return jdir, job


def cmd_new(args):
    job_id, jdir = common.new_job(word=args.word, title=args.title)
    for sub in ("public", "product"):
        (jdir / sub).mkdir()
    url = args.url.split("?")[0].rstrip("/")
    with urllib.request.urlopen(url + ".json", timeout=30) as resp:
        product = json.load(resp)["product"]
    for k, img in enumerate(product["images"], 1):
        urllib.request.urlretrieve(img["src"], jdir / "product" / f"shop_{k:02d}.jpg")
    blurb = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", product.get("body_html") or "")).strip()
    (jdir / "product" / "product.json").write_text(json.dumps(
        {"title": product["title"], "url": url, "price": product["variants"][0]["price"], "blurb": blurb}, indent=2))
    job = json.loads(TEMPLATE.read_text())
    job["title"] = args.title or product["title"].title()
    job["product"] = url
    (jdir / "job.json").write_text(json.dumps(job, indent=2))
    print(f"[ar] job {job_id}: {len(product['images'])} shop images in product/, blurb: {blurb[:120]}")
    print("[ar] add clean white-background front + back shots and the logo to product/, then author job.json")


def cmd_check(args):
    _, job = checked_job(args.job)
    rows, total = ar_lib.timeline(job)
    print(f"[ar] ok: {len(rows)} shots, {total:.2f}s, {len(ar_lib.drum_hits(job))} drum hits")


def cmd_comp(args):
    jdir, job = common.job_dir(args.job), load_job(args.job)
    ar_comp.composite_all(jdir, job, args.only)


def cmd_sheet(args):
    """Render every shot (cheap) and tile one frame each. Shown to Tony BEFORE the render."""
    jdir, job = checked_job(args.job)
    shutil.rmtree(jdir / "work" / "shots", ignore_errors=True)
    ar_film.render_shots(jdir, job)
    sheet = ar_film.contact_sheet(jdir, job)
    common.set_state(args.job, status="sheet", sheet_fingerprint=approval.fingerprint(jdir, KIND))
    print(f"[ar] {sheet}\n[ar] show Tony the sheet and wait for his go, then: ar.py approve {args.job}")


def cmd_approve(args):
    jdir = common.job_dir(args.job)
    problem = approval.can_approve(common.get_state(args.job), approval.fingerprint(jdir, KIND))
    if problem:
        common.die(f"[ar] cannot approve: {problem}")
    common.set_state(args.job, approved_fingerprint=approval.fingerprint(jdir, KIND),
                     approved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"[ar] approved {args.job}. Any edit to the picture in job.json, public/ or product/ voids this.")


def write_kit(jdir, job):
    post = job.get("post") or {}
    text = "\n\n".join(filter(None, [
        post.get("caption", ""),
        job.get("product", ""),
        " ".join(f"#{h.lstrip('#')}" for h in post.get("hashtags", [])),
        "NOTES\n" + "\n".join(f"- {n}" for n in post.get("notes", [])) if post.get("notes") else "",
    ]))
    (jdir / "out" / "post.txt").write_text(text + "\n")
    print(f"[ar] {jdir / 'out' / 'post.txt'}")


def cmd_render(args):
    jdir, job = checked_job(args.job)
    reason = approval.gate(common.get_state(args.job), approval.fingerprint(jdir, KIND), args.no_preview)
    if reason:
        common.die(f"[ar] BLOCKED: {reason}.\n      sheet: {jdir / 'work' / 'contact_sheet.jpg'}\n"
                   f"      after Tony says go: ar.py approve {args.job}   (his explicit waiver only: --no-preview)")
    if not (jdir / "work" / "shots").is_dir():
        ar_film.render_shots(jdir, job)
    master = ar_film.silent_master(jdir, job)
    print(f"[ar] {master}")
    for video in ar_audio.score_all(jdir, job):
        print(f"[ar] {video}")
    write_kit(jdir, job)
    common.set_state(args.job, status="rendered")


def cmd_score(args):
    jdir, job = common.job_dir(args.job), load_job(args.job)
    if not (jdir / "out" / "master_silent.mp4").exists():
        common.die(f"[ar] no silent master yet, run: ar.py render {args.job}")
    for video in ar_audio.score_all(jdir, job):
        print(f"[ar] {video}")


def cmd_kit(args):
    write_kit(common.job_dir(args.job), load_job(args.job))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("url"); p.add_argument("--title"); p.add_argument("--word")
    p.set_defaults(fn=cmd_new)
    for name, fn in (("check", cmd_check), ("sheet", cmd_sheet), ("approve", cmd_approve),
                     ("score", cmd_score), ("kit", cmd_kit)):
        p = sub.add_parser(name); p.add_argument("job"); p.set_defaults(fn=fn)
    p = sub.add_parser("comp"); p.add_argument("job"); p.add_argument("--only"); p.set_defaults(fn=cmd_comp)
    p = sub.add_parser("render"); p.add_argument("job"); p.add_argument("--no-preview", action="store_true")
    p.set_defaults(fn=cmd_render)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
