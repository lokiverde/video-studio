#!/usr/bin/env python3
"""Publish kit: the text a video needs before it can be posted.

Writes three files into jobs/<job>/out/:
  transcript.txt   the full narration, one paragraph per scene
  transcript.srt   the same words as timed captions (upload to YouTube as subtitles)
  youtube.md       title, description with a chapter timeline, comma-separated tags
and, once a final is rendered, route.md and video_library_entry.txt (kit_extras.py).
With a links.json article URL (fv.py bloglink) it is the first line of the description.

Title, description and tags come from the "youtube" block in scenes.json when the
script's author wrote one (best quality: the author knows the hook). Without it, Tim's
LLM drafts them; without Tim, they are derived from the title and captions. The
timeline is always computed from the real scene durations, never guessed.
"""
import argparse
import json
import re

import common
import kit_links
import lanes
import mograph

PAD = 0.35                 # mirrors assemble.PAD: silence after each scene's narration
MIN_CHAPTER_S = 10         # YouTube ignores the whole list if any chapter is shorter
TITLE_MAX = 100            # YouTube hard limit; the prompt asks for 60
TAGS_MAX_CHARS = 500       # YouTube hard limit on the combined tag field
SRT_MAX_CHARS = 84         # two comfortable subtitle lines


def clean(text):
    """House rules: no em or en dashes, anywhere, ever. No "#" before a license number,
    Instagram and YouTube read "DRE #00000001" as a hashtag (Tony, 2026-10-20)."""
    text = re.sub(r"\s*[—–]\s*", ", ", str(text or ""))
    text = re.sub(r"#\s?(\d{6,})", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def scene_durations(job_id, data):
    """Real per-scene durations. assemble stores them; older jobs are probed."""
    stored = common.get_state(job_id).get("scene_durations")
    if stored and len(stored) == len(data["scenes"]):
        return [float(d) for d in stored]
    import assemble
    work = common.job_dir(job_id) / "work"
    durations = []
    for scene in data["scenes"]:
        audio = assemble.audio_file(work, scene["id"])
        durations.append(assemble.probe_dur(audio) + PAD if audio
                         else float(scene.get("duration", assemble.SILENT_SCENE_DUR)))
    return durations


def clock(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def srt_clock(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcript_text(data):
    paragraphs = [clean(s.get("narration")) for s in data["scenes"]]
    body = "\n\n".join(p for p in paragraphs if p)
    return f"{clean(data.get('title', ''))}\n\n{body}\n"


def caption_chunks(narration):
    """Sentences, with any sentence too long for two subtitle lines split at a comma or
    the nearest space."""
    chunks = []
    for sentence in re.split(r"(?<=[.!?])\s+", clean(narration)):
        while len(sentence) > SRT_MAX_CHARS:
            cut = sentence.rfind(", ", 0, SRT_MAX_CHARS)
            cut = cut + 1 if cut > 20 else sentence.rfind(" ", 0, SRT_MAX_CHARS)
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            chunks.append(sentence)
    return chunks


def transcript_srt(data, durations):
    """Cue times are apportioned inside each scene by character count. Scene boundaries
    are exact; within a scene this lands within a few tenths of a second of the voice."""
    cues, start = [], 0.0
    for scene, dur in zip(data["scenes"], durations):
        chunks = caption_chunks(scene.get("narration"))
        speech = max(dur - PAD, 0.1)
        total_chars = sum(len(c) for c in chunks) or 1
        cursor = start
        for chunk in chunks:
            length = speech * len(chunk) / total_chars
            cues.append((cursor, cursor + length, chunk))
            cursor += length
        start += dur
    return "".join(f"{i}\n{srt_clock(a)} --> {srt_clock(b)}\n{text}\n\n"
                   for i, (a, b, text) in enumerate(cues, 1))


def chapters(data, durations):
    """(start_seconds, label) per chapter. Scenes shorter than YouTube's 10s minimum are
    folded into the chapter before them so the list is actually honoured."""
    out, start = [], 0.0
    for scene, dur in zip(data["scenes"], durations):
        label = clean(scene.get("chapter") or scene.get("caption")
                      or mograph.chapter_label(scene) or f"Part {scene['id']}")
        if out and (start - out[-1][0]) < MIN_CHAPTER_S:
            pass  # previous chapter is still too short: this scene joins it
        else:
            out.append((start, label))
        start += dur
    if len(out) > 1 and (start - out[-1][0]) < MIN_CHAPTER_S:
        out = out[:-1]
    return out


def draft_with_tim(data, cfg):
    """Ask Tim's LLM for the metadata. Returns {} on any failure: the kit must never
    block a finished video."""
    try:
        import write_script
        narration = " ".join(clean(s.get("narration")) for s in data["scenes"])
        prompt = (
            "Write YouTube metadata for this short explainer video. Reply with ONE JSON "
            'object: {"title": str, "description": str, "tags": [str]}. Rules: title under '
            "60 characters, specific, no clickbait caps, no emoji. Description is 2 to 3 "
            "plain sentences that say what the viewer learns, no hashtags, no timestamps, "
            "no calls to subscribe. 12 to 15 tags, lowercase, mix of broad and specific "
            "search phrases. Never use em dashes. Neutral and factual, no advice.\n\n"
            f"Working title: {data.get('title', '')}\nNarration: {narration}")
        payload = {"model": "tim-qwen", "temperature": 0.4, "max_tokens": 700,
                   "messages": [{"role": "user", "content": prompt}],
                   "chat_template_kwargs": {"enable_thinking": False}}
        raw = common.http_json(f"{cfg['TIM_LLM_URL']}/v1/chat/completions", payload,
                               timeout=120, retries=1)
        return write_script.extract_json(raw["choices"][0]["message"]["content"])
    except Exception as exc:  # noqa: BLE001  any failure falls through to the derived kit
        print(f"[kit] Tim draft unavailable ({type(exc).__name__}: {exc}); deriving from script")
        return {}


def derived_meta(data):
    scenes = data["scenes"]
    first = clean(scenes[0].get("narration")) if scenes else ""
    words = re.findall(r"[a-z][a-z0-9%-]{3,}", " ".join(
        [data.get("title", "")] + [s.get("caption", "") for s in scenes]).lower())
    return {"title": clean(data.get("title", "")), "description": first,
            "tags": list(dict.fromkeys(words))[:15]}


def youtube_meta(data, cfg):
    """Author's block wins field by field, then Tim's draft, then the derived fallback."""
    authored = data.get("youtube") or {}
    needs_draft = not all(authored.get(k) for k in ("title", "description", "tags"))
    drafted = draft_with_tim(data, cfg) if needs_draft else {}
    fallback = derived_meta(data)
    meta = {key: authored.get(key) or drafted.get(key) or fallback[key]
            for key in ("title", "description", "tags")}
    tags = meta["tags"] if isinstance(meta["tags"], list) else str(meta["tags"]).split(",")
    source = "scenes.json" if not needs_draft else ("tim-qwen" if drafted else "derived")
    return {"title": clean(meta["title"])[:TITLE_MAX],
            "description": clean(meta["description"]),
            "tags": fit_tags([clean(t).lower() for t in tags if clean(t)]),
            "hashtags": [clean(h).lstrip("#") for h in authored.get("hashtags", [])][:3],
            "source": source}


def fit_tags(tags):
    kept, used = [], 0
    for tag in dict.fromkeys(tags):
        cost = len(tag) + (2 if kept else 0)
        if used + cost > TAGS_MAX_CHARS:
            break
        kept.append(tag)
        used += cost
    return kept


AI_DISCLOSURE_DEFAULT = "This video contains AI-generated footage."
STUDIO_REMINDER = ("In YouTube Studio, set the altered or synthetic content disclosure to Yes "
                   "before publishing: this video contains realistic AI-generated footage. "
                   "The kit cannot set it for you.")


def ai_disclosure(data, cfg):
    """The description line for a video with realistic footage (any clip scene), or None.
    Always on, no switch (Tony, 2026-10-24); config may only reword it."""
    if not any(scene.get("clip") for scene in data["scenes"]):
        return None
    return clean((cfg.get("AI_DISCLOSURE_LINE") or "").strip() or AI_DISCLOSURE_DEFAULT)


def youtube_markdown(meta, chapter_list, total, footer, disclosure=None):
    timeline = "\n".join(f"{clock(start)} {label}" for start, label in chapter_list)
    hashtags = " ".join(f"#{h.replace(' ', '')}" for h in meta["hashtags"])
    description = "\n\n".join(part for part in (
        meta["description"], disclosure, f"Timeline\n{timeline}" if timeline else "",
        clean(footer), hashtags) if part)
    return (f"# YouTube kit\n\n"
            f"Length {clock(total)}. Metadata source: {meta['source']}. "
            f"Timeline is computed from the rendered scene lengths.\n\n"
            f"## Title\n\n{meta['title']}\n\n"
            f"## Description\n\n{description}\n\n"
            f"## Tags\n\n{', '.join(meta['tags'])}\n"
            + (f"\n## Before you publish\n\n{STUDIO_REMINDER}\n" if disclosure else ""))


def run(job_id):
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    disclosure = ai_disclosure(data, cfg)
    if not any((s.get("narration") or "").strip() for s in data["scenes"]):
        print("[kit] silent video: no transcript to write, skipping")
        if disclosure:
            print(f"[kit] AI footage: paste this into the YouTube description: {disclosure}")
            print(f"[kit] {STUDIO_REMINDER}")
        return []
    durations = scene_durations(job_id, data)
    jdir = common.job_dir(job_id)
    out = jdir / "out"
    out.mkdir(parents=True, exist_ok=True)
    meta = youtube_meta(data, cfg)
    chapter_list = chapters(data, durations)
    shown = {**meta, "description": kit_links.with_blog_line(meta["description"],
                                                             kit_links.load(jdir).get("blog_url"))}
    files = {
        "transcript.txt": transcript_text(data),
        "transcript.srt": transcript_srt(data, durations),
        "youtube.md": youtube_markdown(shown, chapter_list, sum(durations),
                                       lanes.footer_for(lanes.job_lane(jdir), cfg,
                                                       signer=lanes.job_signer(jdir)), disclosure),
    }
    for name, text in files.items():
        (out / name).write_text(text)
    common.set_state(job_id, kit={"title": meta["title"], "tags": meta["tags"],
                                  "source": meta["source"]})
    print(f"[kit] {out / 'transcript.txt'}")
    print(f"[kit] {out / 'transcript.srt'}")
    print(f"[kit] {out / 'youtube.md'}  (metadata from {meta['source']})")
    if disclosure:
        print(f"[kit] AI footage: {STUDIO_REMINDER}")
    import kit_extras                     # lazy: library_entry imports this module
    import library_entry
    kit_extras.run(jdir, "faceless", meta, chapter_list,
                   library_entry.paragraphs(files["transcript.txt"], data.get("title")),
                   (data.get("youtube") or {}).get("takeaways"),
                   [s.get("narration", "") for s in data["scenes"] if (s.get("narration") or "").strip()],
                   source="narration script")
    return [out / name for name in files]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("job")
    run(p.parse_args().job)


if __name__ == "__main__":
    main()
