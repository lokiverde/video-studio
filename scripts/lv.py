#!/usr/bin/env python3
"""Example Realty listing video: photo folder + MLS Agent Full PDF -> 16:9 and 9:16 tours.

  make     new job: parse the MLS PDF, inventory the photos, draw inventory sheets
  sheet    validate picks.json, render preview stills + both contact sheets
  swap     replace one pick and redraw the sheets
  approve  Tony has seen the sheets and said go
  finish   render both cuts, write post.md, upload to BunnyCDN
  status   print the job state

Previews stay on this Mac. Nothing is uploaded before Tony approves.
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image

import approval
import common
import gen_images
import lv_cards
import lv_mls
import lv_map
import lv_photos
import lv_pop
import lv_render
import upload

KIND = "listing"
# Branded cuts for YouTube/Instagram; MLS cuts carry no logo or contact info (MLS rules).
OUTPUTS = {("landscape", "branded"): "final_16x9.mp4", ("portrait", "branded"): "final_9x16.mp4",
           ("landscape", "mls"): "mls_16x9.mp4", ("portrait", "mls"): "mls_9x16.mp4"}
VARIANTS = ("branded", "mls")
SHEETS = {"landscape": ("contact_sheet.jpg", 480, 3, None),
          "portrait": ("contact_sheet_9x16.jpg", 270, 6, gen_images._vertical_guides)}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


# ---------- make ----------

def inventory_sheets(photos: list[dict], work: Path, per_sheet: int = 30) -> list[Path]:
    """Numbered thumbnails of every photo, so the picks can be chosen by eye."""
    from PIL import Image, ImageDraw
    out = []
    for start in range(0, len(photos), per_sheet):
        chunk = photos[start:start + per_sheet]
        tw, th, cols = 360, 270, 6
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * (tw + 6) + 6, rows * (th + 36) + 6), "white")
        d = ImageDraw.Draw(sheet)
        font = lv_cards.captions.load_font(18)
        for k, p in enumerate(chunk):
            img = lv_render.load_photo(p["path"])
            img.thumbnail((tw, th))
            x, y = 6 + (k % cols) * (tw + 6), 6 + (k // cols) * (th + 36)
            sheet.paste(img, (x, y))
            d.text((x, y + th + 6), f"{p['n']}. {p['name'][:34]}", font=font, fill="black")
        path = work / f"inventory_{start // per_sheet + 1}.jpg"
        sheet.save(path, quality=85)
        out.append(path)
    return out


def cmd_make(a) -> None:
    brand = lv_cards.load_brand(a.brand)
    facts = lv_mls.from_pdf(Path(a.mls).expanduser())
    photos = lv_photos.scan(Path(a.photos))
    if len(photos) < 6:
        common.die(f"only {len(photos)} photos in {a.photos}")
    job_id, jdir = common.new_job(a.word, facts.get("city"))
    point = lv_map.geocode(facts.get("address") or "", facts.get("city"), facts.get("zip"))
    listing = {**facts, "url": a.url or "", "brand": a.brand, "photos_dir": str(Path(a.photos).expanduser()),
               "mls_pdf": str(Path(a.mls).expanduser()),
               "lat": point[0] if point else None, "lon": point[1] if point else None}
    write_json(jdir / "listing.json", listing)
    write_json(jdir / "inventory.json", photos)
    sheets = inventory_sheets(photos, jdir / "work")
    common.set_state(job_id, status="new", kind=KIND, brand=a.brand)
    rooms = {}
    for p in photos:
        rooms[p["room"]] = rooms.get(p["room"], 0) + 1
    print(f"[lv] job {job_id}\n     {jdir}")
    print(f"     {facts.get('address')}, {lv_cards.city_line(facts)}  {lv_mls.fmt_price(facts)}")
    print(f"     {lv_mls.stat_line(facts)}  ({facts['listing_type']}, MLS# {facts.get('listing_id')})")
    print(f"     photos: {len(photos)}  " + ", ".join(f"{k} {v}" for k, v in rooms.items()))
    if not point:
        print("     CONFIRM: could not geocode the address; set lat/lon in listing.json for the map")
    for c in facts["conflicts"]:
        print(f"     CONFIRM: {c}")
    print("     inventory: " + " ".join(str(s) for s in sheets))
    print(f"     music: {', '.join(brand['music'])} (default {brand['default_music']})")
    print("     next: write picks.json, then `lv.py sheet --job ...`")


# ---------- sheet ----------

def load_job(job_id: str):
    jdir = common.job_dir(job_id)
    listing = read_json(jdir / "listing.json")
    brand = lv_cards.load_brand(listing.get("brand", "examplerealty"))
    photos = read_json(jdir / "inventory.json")
    return jdir, listing, brand, photos


def music_for(picks: dict, brand: dict) -> tuple[str, dict]:
    name = picks.get("music") or brand["default_music"]
    if name not in brand["music"]:
        common.die(f"unknown music {name!r}; choose from {', '.join(brand['music'])}")
    return name, brand["music"][name]


def build_cuts(jdir: Path, listing: dict, brand: dict, photos: list[dict], mls: bool = False) -> dict:
    picks = lv_photos.load_picks(jdir / "picks.json")
    problems = lv_photos.validate_picks(picks, photos)
    if problems:
        common.die("picks.json:\n  " + "\n  ".join(problems))
    _, track = music_for(picks, brand)
    if picks.get("style") == "pop":
        return {cut: lv_pop.build(lv_photos.resolve(picks, photos, cut), listing, brand, cut, track["bpm"], mls,
                                  picks.get("city", "redondo-beach"), jdir / "work")
                for cut in lv_photos.CUTS}
    return {cut: lv_render.Cut(lv_photos.resolve(picks, photos, cut), listing, brand, cut, track["bpm"], mls)
            for cut in lv_photos.CUTS}


def describe(cut) -> str:
    if hasattr(cut, "shots"):
        kinds = [s.kind for s in cut.shots]
        photo = next((s.dur for s in cut.shots if s.kind == "photo"), 0)
        return (f"map + {kinds.count('clip')} city clips + hero + {kinds.count('photo')} photos "
                f"at {photo:.2f}s + card")
    per = cut.segments[1].dur if len(cut.segments) > 1 else 0
    return f"{len(cut.segments)} photos, {per:.2f}s each"


def cmd_sheet(a) -> None:
    jdir, listing, brand, photos = load_job(a.job)
    if a.music:
        picks = lv_photos.load_picks(jdir / "picks.json")
        write_json(jdir / "picks.json", {**picks, "music": a.music})
    cuts = build_cuts(jdir, listing, brand, photos)
    preview = jdir / "work" / "preview"
    preview.mkdir(exist_ok=True)
    for old in preview.glob("*.jpg"):
        old.unlink()
    for cut_name, cut in cuts.items():
        files = []
        for n, t in enumerate(cut.preview_times()):
            path = preview / f"{cut_name[0].upper()}_{n:02d}.jpg"
            frame = cut.frame_at(t)
            (frame if hasattr(frame, "save") else Image.fromarray(frame)).save(path, quality=88)
            files.append(path)
        name, width, cols, guide = SHEETS[cut_name]
        gen_images._sheet(files, jdir / "work" / name, width, cols, guide=guide)
        print(f"[lv] {cut_name}: {describe(cut)}, {cut.duration:.1f}s total -> work/{name}")
    for cut_name, size in (("L", (1920, 1080)), ("P", (1080, 1920))):
        lv_cards.mls_card(listing, brand, size).convert("RGB").save(preview / f"mls_card_{cut_name}.jpg", quality=88)
    print("[lv] MLS end cards (no contact info): work/preview/mls_card_L.jpg, mls_card_P.jpg")
    music = read_json(jdir / "picks.json").get("music") or brand["default_music"]
    common.set_state(a.job, status="previewed", music=music,
                     sheet_fingerprint=approval.fingerprint(jdir, KIND))
    print(f"[lv] music {music}. Show Tony both sheets, then `lv.py approve --job {a.job}`")


def cmd_swap(a) -> None:
    jdir = common.job_dir(a.job)
    picks = lv_photos.load_picks(jdir / "picks.json")
    entries = list(picks[a.cut])
    if not 0 <= a.index < len(entries):
        common.die(f"{a.cut} has {len(entries)} picks, index {a.index} is out of range")
    old = lv_photos.normalize_pick(entries[a.index])
    entries[a.index] = {**old, "photo": a.photo}
    write_json(jdir / "picks.json", {**picks, a.cut: entries})
    print(f"[lv] {a.cut}[{a.index}]: {old['photo']} -> {a.photo}")
    cmd_sheet(argparse.Namespace(job=a.job, music=None))


# ---------- approve / finish ----------

def cmd_approve(a) -> None:
    jdir = common.job_dir(a.job)
    state = common.get_state(a.job)
    problem = approval.can_approve(state, approval.fingerprint(jdir, KIND))
    if problem:
        common.die(problem)
    common.set_state(a.job, approved_fingerprint=state["sheet_fingerprint"], status="approved")
    print(f"[lv] approved {a.job}. Next: `lv.py finish --job {a.job}`")


LINK_LABELS = (("final_16x9.mp4", "Branded 16:9 (YouTube)"), ("final_9x16.mp4", "Branded 9:16 (Instagram, Reels, TikTok)"),
               ("mls_16x9.mp4", "MLS 16:9 (no contact info, for the MLS)"), ("mls_9x16.mp4", "MLS 9:16 (no contact info)"),
               ("post.md", "Captions + links (post.md)"))


STYLE_NAMES = {"pop": "Pop (map, kinetic type, depth motion)", None: "Classic (slow pans, crossfades)"}
INDEX_NAME = "Listing Videos.md"


def job_style(job: str) -> str:
    picks = common.ROOT / "jobs" / job / "picks.json"
    style = read_json(picks).get("style") if picks.exists() else None
    return STYLE_NAMES.get(style, style or STYLE_NAMES[None])


def links_section(job: str, cfg: dict) -> list[str]:
    """Labeled Bunny links, so the file alone says where every video lives."""
    base = f"{cfg['BUNNY_PUBLIC_BASE'].rstrip('/')}/listings/{job}"
    return ["## Video links (Bunny)", "", f"Style: {job_style(job)}", "",
            *(f"- {label}: {base}/{name}" for name, label in LINK_LABELS),
            "", f"Job folder: faceless-video/jobs/{job}/out/", ""]


def write_listing_index(listing: dict, cfg: dict) -> Path | None:
    """`Listing Videos.md` beside the MLS PDF in the listing folder, one section per job, newest first."""
    pdf = listing.get("mls_pdf")
    if not pdf or not Path(pdf).parent.is_dir():
        return None
    folder = Path(pdf).parent
    jobs = sorted((d.name for d in (common.ROOT / "jobs").iterdir()
                   if (d / "listing.json").exists() and (d / "out" / "post.md").exists()
                   and Path(read_json(d / "listing.json").get("mls_pdf") or "/").parent == folder), reverse=True)
    lines = [f"# {listing.get('address')}, {listing.get('city')}: listing videos", ""]
    for job in jobs:
        lines += [f"## {job}", *links_section(job, cfg)[2:]]
    path = folder / INDEX_NAME
    path.write_text("\n".join(lines).strip() + "\n")
    return path


def listing_team(listing: dict, brand: dict) -> list[dict]:
    """Placard contacts who are agents on this listing (matched by DRE); all of them if none match."""
    contacts = brand["placard"]["contacts"]
    licenses = {a.get("license") for a in listing.get("agents") or []}
    return [c for c in contacts if c.get("dre") in licenses] or contacts


def dre_credit(c: dict) -> str:
    return f"{c['name']}{', ' + c['title'] if c.get('title') else ''}, CA DRE {c['dre']}"


def contact_lines(listing: dict, brand: dict) -> tuple[str, str]:
    """(caption contact line, YouTube footer) with every listing agent's DRE plus the office DRE."""
    team = listing_team(listing, brand)
    card = brand["placard"]
    # A second brand (e.g. Tony + a teammate) names its own pair; the house brand stays "Your Team".
    who = card.get("team_name", "Your Team") if len(team) > 1 else team[0]["name"]
    # No "#" before license numbers: Instagram and YouTube count "#00000001" as a hashtag
    # (IG caps posts at 5 and Blotato rejects the whole post).
    office = f"{card['office']}, Corp DRE {card['office_dre']}"
    caption = (f"Call or text {who} for a private showing: "
               + ", ".join(f"{c['name']} {c['phone']} (DRE {c['dre']})" for c in team)
               + f". {office}.")
    footer = " | ".join([*( [who] if len(team) > 1 else []), *(dre_credit(c) for c in team), office, card["site"]])
    return caption, footer


def post_text(listing: dict, job: str | None = None, brand: dict | None = None) -> str:
    cfg = common.load_config()
    brand = brand or lv_cards.load_brand(listing.get("brand", "examplerealty"))
    caption_contact, footer = contact_lines(listing, brand)
    price = lv_mls.fmt_price(listing)
    head = ("For lease" if listing["listing_type"] == "lease"
            else "New price" if lv_mls.price_reduced(listing) else "Just listed")
    lines = [
        f"# {listing.get('address')}, {listing.get('city')}",
        "",
        *(links_section(job, cfg) if job and cfg.get("BUNNY_PUBLIC_BASE") else []),
        "## Instagram / Facebook caption",
        "",
        f"{head} in {listing.get('city')}. {listing.get('address')}, "
        f"{lv_mls.stat_line(listing).replace('  |  ', ', ')}, {price}.",
        "",
        caption_contact,
        "",
        f"#{(listing.get('city') or '').replace(' ', '')} #{brand['placard'].get('region_tag', 'YourRegion')} {'#PriceReduced' if lv_mls.price_reduced(listing) else '#JustListed'} #@examplerealty",
        "",
        "## YouTube",
        "",
        f"Title: {listing.get('address')}, {listing.get('city')} | {price} | "
        f"{lv_mls.stat_line(listing).replace('  |  ', ' ')}",
        "",
        listing.get("url") or "",
        "",
        listing.get("description", ""),
        "",
        footer,
    ]
    return "\n".join(lines).strip() + "\n"


def cmd_finish(a) -> None:
    jdir, listing, brand, photos = load_job(a.job)
    state = common.get_state(a.job)
    problem = approval.gate(state, approval.fingerprint(jdir, KIND), waived=a.no_preview)
    if problem:
        common.die(problem)
    picks = lv_photos.load_picks(jdir / "picks.json")
    name, track = music_for(picks, brand)
    music = common.ROOT / "assets" / "music" / f"{name}.mp3"
    out = jdir / "out"
    for variant in (a.variants or VARIANTS):
        cuts = build_cuts(jdir, listing, brand, photos, mls=variant == "mls")
        for cut_name in (a.only or lv_photos.CUTS):
            path = out / OUTPUTS[(cut_name, variant)]
            lv_render.encode(cuts[cut_name], path, music, track["offset"], brand["loudness"])
            print(f"[lv] wrote {path}")
    (out / "post.md").write_text(post_text(listing, a.job))
    common.set_state(a.job, status="rendered")
    import yt_thumb                       # lazy: the Test & compare set, branded 16:9 only
    for problem in yt_thumb.kit_problems(jdir):
        print(f"[lv] KIT (branded 16:9 YouTube upload, never the MLS cuts): {problem}")
    if a.no_upload:
        return
    cfg = common.load_config()
    urls = [upload.put_file(cfg, f, f"listings/{a.job}/{f.name}")
            for f in (out / n for n in (*OUTPUTS.values(), "post.md")) if f.exists()]
    for url in urls:
        print(f"[upload] {url}")
    common.set_state(a.job, status="uploaded", video_urls=urls)
    index = write_listing_index(listing, cfg)
    if index:
        print(f"[lv] wrote {index}")


def cmd_links(a) -> None:
    """Rewrite post.md with the labeled links and re-upload it (for jobs finished before links existed)."""
    jdir = common.job_dir(a.job)
    post = jdir / "out" / "post.md"
    post.write_text(post_text(read_json(jdir / "listing.json"), a.job))
    cfg = common.load_config()
    print(f"[upload] {upload.put_file(cfg, post, f'listings/{a.job}/post.md')}")
    index = write_listing_index(read_json(jdir / "listing.json"), cfg)
    if index:
        print(f"[lv] wrote {index}")
    print(post.read_text().split("## Instagram")[0])


def cmd_geocode(a) -> None:
    jdir = common.job_dir(a.job)
    listing = read_json(jdir / "listing.json")
    point = lv_map.geocode(listing.get("address") or "", listing.get("city"), listing.get("zip"))
    if not point:
        common.die("geocoding failed; set lat/lon in listing.json by hand")
    write_json(jdir / "listing.json", {**listing, "lat": point[0], "lon": point[1]})
    print(f"[lv] {listing.get('address')}: {point[0]:.6f}, {point[1]:.6f}")


def cmd_status(a) -> None:
    print(json.dumps(common.get_state(a.job), indent=2))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--photos", required=True, help="folder of Photo Batch processed photos")
    m.add_argument("--mls", required=True, help="MLS Agent Full PDF")
    m.add_argument("--url", help="listing page URL for the post text")
    m.add_argument("--word", help="one word for the job folder (city or topic)")
    m.add_argument("--brand", default="examplerealty")
    s = sub.add_parser("sheet")
    s.add_argument("--job", required=True)
    s.add_argument("--music", help="music bed name from the brand file")
    w = sub.add_parser("swap")
    w.add_argument("--job", required=True)
    w.add_argument("--cut", choices=lv_photos.CUTS, required=True)
    w.add_argument("--index", type=int, required=True)
    w.add_argument("--photo", required=True, help="file name from inventory.json")
    ap = sub.add_parser("approve")
    ap.add_argument("--job", required=True)
    f = sub.add_parser("finish")
    f.add_argument("--job", required=True)
    f.add_argument("--no-upload", action="store_true")
    f.add_argument("--no-preview", action="store_true", help="Tony's explicit waiver of the preview gate")
    f.add_argument("--only", nargs="+", choices=lv_photos.CUTS)
    f.add_argument("--variants", nargs="+", choices=VARIANTS, help="default: both branded and mls")
    g = sub.add_parser("geocode")
    g.add_argument("--job", required=True)
    ln = sub.add_parser("links")
    ln.add_argument("--job", required=True)
    st = sub.add_parser("status")
    st.add_argument("--job", required=True)
    a = p.parse_args(argv)
    handlers = {"make": cmd_make, "sheet": cmd_sheet, "swap": cmd_swap, "approve": cmd_approve,
                "finish": cmd_finish, "status": cmd_status, "geocode": cmd_geocode,
                "links": cmd_links}
    try:
        handlers[a.cmd](a)
    except RuntimeError as err:
        common.die(str(err))


if __name__ == "__main__":
    sys.exit(main())
