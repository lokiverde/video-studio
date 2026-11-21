"""Storyboard reel: the post kit. Every render writes out/post.txt (the short version) and
out/posts.md (Instagram Reels, TikTok, YouTube Shorts, Facebook Reels), and every caption
ends with the Shop signature block, verbatim (Tony, 2026-10-18). Layout copied from
jobs/20261017-222408-wizard/out/posts.md. The copy itself is written into job.json `post`."""
import re

SIGNATURE = """YOURSHOP NEW DROP

Fresh from the shop.

Shop: https://yourshop.com/

TAGS: #YourShop #streetwear #skatewear"""

# (job.json key, heading, the field holding the caption)
PLATFORMS = (("instagram", "Instagram Reels", "caption"), ("tiktok", "TikTok", "caption"),
             ("youtube", "YouTube Shorts", "description"), ("facebook", "Facebook Reels", "caption"))
# The same names vhs_look.py uses: the clean final, and the tape cut beside it.
VIDEO, VHS_VIDEO, COVER = "final_9x16.mp4", "final_9x16_vhs.mp4", "cover.jpg"
_PLACEHOLDER = re.compile(r"<[^<>\n]+>")


def signature(job):
    return (job.get("post") or {}).get("signature") or SIGNATURE


def _tags(tags):
    return " ".join(f"#{t.lstrip('#')}" for t in tags or [])


def _block(text, job, tags=None):
    """A caption as a code block: the copy, the signature block, then any extra hashtags."""
    parts = [text, signature(job)] + ([_tags(tags)] if tags else [])
    return "```\n" + "\n\n".join(parts) + "\n```"


def _notes(notes):
    return "**Notes**\n" + "\n".join(f"- {n}" for n in notes)


def post_text(job):
    """out/post.txt: headline, caption with the signature block, link, notes."""
    product, post = job["product"], job.get("post") or {}
    head = post.get("headline") or (f"{job['title'].upper()} ({product['title'].title()}) - 9:16. "
                                    "Per-platform captions: posts.md")
    blocks = [head, "CAPTION\n" + post.get("caption", "") + "\n\n" + signature(job), "LINK\n" + product["url"]]
    if post.get("notes"):
        blocks.append("NOTES\n" + "\n".join(f"- {n}" for n in post["notes"]))
    return "\n\n".join(blocks) + "\n"


def vhs_strength(job):
    vhs = job.get("vhs") or 0
    return vhs if isinstance(vhs, (int, float)) else vhs.get("strength", 0)


def main_video(job):
    """The deliverable: the tape cut when the job turns VHS on, else the clean final."""
    return VHS_VIDEO if vhs_strength(job) else VIDEO


def _header(job, clean):
    product, post = job["product"], job.get("post") or {}
    strength = vhs_strength(job)
    look = f", VHS overlay at {round(strength * 100)}%" if strength else ""
    video = (f"**Video:** `{main_video(job)}` ({job['length']:g}s, 9:16{look})."
             + (f" Clean version: `{VIDEO}`." if clean and strength else ""))
    note = ((post.get("cover") or {}).get("note"))
    cover = f"**Cover:** `{COVER}`" + (f" ({note})" if note else "") + ". Use it as the cover on every platform."
    bits = [product["title"].title(), product.get("price"), (product.get("sizes") or "").replace("-", " to "),
            ", ".join(product.get("color_names") or [])]
    lines = [video, cover, "**Product:** " + ". ".join(b for b in bits if b) + ".", f"**Link:** {product['url']}"]
    return (f"# {job['title']}: social posts\n\n" + "\n".join(lines) +
            "\n\nEvery caption ends with the Shop signature block, exactly as written:\n\n"
            f"```\n{signature(job)}\n```")


def _platform(job, key, heading, field, vhs_on):
    p = (job.get("post") or {}).get(key) or {}
    parts = [f"## {heading}"]
    if p.get("cover_text"):
        parts.append(f"**Cover text** (optional, if you add text in IG): {p['cover_text']}")
    if p.get("on_screen"):
        clears = "the PLAY readout and the side buttons" if vhs_on else "the side buttons"
        parts.append(f"**On-screen text** (add in the TikTok editor, first 2 seconds, upper middle so it "
                     f"clears {clears}): `{p['on_screen']}`")
    if p.get("title"):
        parts.append(f"**Title:** {p['title']}")
    parts.append(f"**{field.title()}:**\n\n" + _block(p.get(field, ""), job, p.get("hashtags")))
    if p.get("pin"):
        parts.append(f"**Pin this comment:** {p['pin']}")
    if p.get("notes"):
        parts.append(_notes(p["notes"]))
    return "\n\n".join(parts)


def posts_md(job, clean=False):
    """out/posts.md. clean: a clean (no VHS) cut sits beside the tape cut."""
    post = job.get("post") or {}
    vhs_on = bool(vhs_strength(job))
    sections = [_header(job, clean)] + [_platform(job, key, heading, field, vhs_on)
                                        for key, heading, field in PLATFORMS]
    tail = []
    if post.get("hooks"):
        tail.append("## Hooks to test\n\nSwap the first line of any caption to A/B test across posts:\n\n"
                    + "\n".join(f"- {h}" for h in post["hooks"]))
    if post.get("order"):
        tail.append(f"## Order of play\n\n{post['order']}")
    if tail:
        sections.append("\n\n".join(tail))
    return "\n\n---\n\n".join(sections) + "\n"


def _strings(value, path):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


def post_problems(job):
    """Copy that is not ready to hand Tony: empty captions, template <placeholders>."""
    post = job.get("post") or {}
    problems = [] if post.get("caption") else ["post.caption is empty"]
    for key, _, field in PLATFORMS:
        if not (post.get(key) or {}).get(field):
            problems.append(f"post.{key}.{field} is empty")
    for path, text in _strings(post, "post"):
        for match in _PLACEHOLDER.findall(text):
            problems.append(f"{path}: still has {match}")
    return problems
