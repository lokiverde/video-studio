"""Turn an article (url/text) or an outline into scenes.json via Tim's vLLM.

Skipped entirely when an LLM caller (Claude Code) authors scenes.json itself.
"""
import argparse
import html.parser
import json
import re
import sys
import urllib.request

import common

SYSTEM_PROMPT = """You write scripts for short faceless explainer videos (60-120 seconds).
Return ONLY a JSON object, no markdown fences, shaped exactly like:
{"title": "...", "hook_category": "...", "framework": "...", "tone": "...",
 "scenes": [{"id": 1, "narration": "...", "image_prompt": "...", "caption": "..."}]}

Rules:
- 6 to 10 scenes. Total narration 150-300 words. Scene 1 is a HOOK: the first sentence
  must stop the viewer (curiosity, tension, surprise, or a contrarian claim). Never open
  with a greeting, an introduction, or a description of the video. Pick one hook category
  (curiosity, contrarian, problem, result, warning, story, question, number,
  unexpected-fact) and one framework (problem-agitation-solution, myth-truth-proof, list,
  before-change-after, case-study) and report them in the JSON. The last scene delivers
  the payoff the hook promised, then ends with an insight, action step, or question,
  not a generic follow request. Avoid any hook category or opening phrase listed as
  recently used in the user message.
- narration: 1-3 spoken sentences, conversational, one idea per scene.
- image_prompt: a visual DESCRIPTION of the scene only. Describe people as generic figures.
  NEVER include text, words, numbers, signs, or logos in the image_prompt.
- caption: max 8 words, the on-screen takeaway phrase.
- Neutral, factual tone for legal or news topics. No hype, no advice."""


class _TextExtractor(html.parser.HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form"}

    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.chunks.append(data.strip())


def fetch_article(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 faceless-video/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(raw)
    text = "\n".join(parser.chunks)
    return re.sub(r"\n{3,}", "\n\n", text)[:20000]


def extract_json(text):
    """Model replies sometimes wrap JSON in prose or fences. Pull the object out."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON object in model reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def recent_history(limit=10):
    """Hook categories + opening phrases from the last N scripts, for variety."""
    path = common.ROOT / "history" / "scripts.jsonl"
    if not path.exists():
        return ""
    entries = [json.loads(line) for line in path.read_text().strip().splitlines()[-limit:]]
    used = [f"- {e.get('hook_category', '?')}: \"{e.get('opening_phrase', '')}\"" for e in entries]
    return "\n\nRecently used hooks and openings (do not repeat):\n" + "\n".join(used)


def generate_scenes(source_text, is_outline, cfg):
    mode = ("Convert this outline into the JSON script, staying faithful to its structure"
            if is_outline else "Write the video script JSON for this article")
    payload = {
        "model": "tim-qwen",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{mode}:\n\n{source_text}{recent_history()}"},
        ],
        "temperature": 0.6,
        "max_tokens": 4000,
    }
    raw = common.http_json(f"{cfg['TIM_LLM_URL']}/v1/chat/completions", payload, timeout=600)
    reply = json.loads(raw)["choices"][0]["message"]["content"]
    data = extract_json(reply)
    for i, scene in enumerate(data.get("scenes", []), 1):
        scene.setdefault("id", i)
    common.validate_scenes(data)
    return data


def run(job_id, article_url=None, article_file=None, outline_file=None,
        theme="sketch", voice="stock"):
    cfg = common.load_config()
    if article_url:
        source, is_outline = fetch_article(article_url), False
    elif article_file:
        source, is_outline = open(article_file).read(), False
    elif outline_file:
        source, is_outline = open(outline_file).read(), True
    else:
        common.die("need --article-url, --article-file, or --outline-file")

    data = generate_scenes(source, is_outline, cfg)
    data["theme"] = theme
    data["voice"] = voice
    if article_url:
        data["source_url"] = article_url

    path = common.job_dir(job_id) / "scenes.json"
    path.write_text(json.dumps(data, indent=2))
    common.set_state(job_id, status="scripted", title=data.get("title", ""))
    print(f"[write_script] {len(data['scenes'])} scenes -> {path}")
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--article-url")
    p.add_argument("--article-file")
    p.add_argument("--outline-file")
    p.add_argument("--theme", default="sketch")
    p.add_argument("--voice", default="stock")
    a = p.parse_args()
    run(a.job, a.article_url, a.article_file, a.outline_file, a.theme, a.voice)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        common.die(str(err))
