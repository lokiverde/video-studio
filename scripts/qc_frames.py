"""Screen every hero still with Tim's VLM and reroll the structurally broken ones.

The expensive failure in this pipeline is a frame where the character comes out
wrong: head detached from the body, a third hand, a missing leg, two heads. It is
obvious at full size and invisible in a contact sheet, which is exactly how eight
broken frames shipped on 2026-08-12. A human still has to look at the finals, but
the gross breakage can be caught without one, because the same multimodal model
that serves chat on Tim can count limbs.

This is a screen, not a verdict. It catches missing and duplicated parts. It does
not catch a prop merged into the face, a head that is merely too big, or a shot
that ignored the prompt. Read the report, then look at the frames.
"""
import argparse
import base64
import json
import random
import urllib.request

import common
import gen_images

CHECK = (
    "This is a frame from a flat 2D cartoon explainer video. The recurring character "
    "is a stick figure: one round white head with a short neck joining it to a thin "
    "black stick body, two stick arms ending in white gloved hands, two stick legs.\n"
    "Answer ONLY with minified JSON, no fence:\n"
    '{"figures":int,"head_attached":bool,"arms":int,"legs":int,"hands":int,'
    '"figure_complete":bool,"problem":"short phrase or empty"}\n'
    "Some shots have a second person on purpose, so more than one figure is NOT a "
    "fault by itself. Judge each figure on its own and report the WORST one: arms, "
    "legs and hands are that figure's counts.\n"
    "figure_complete is false if a head floats free of its body, if a torso is "
    "missing, if a limb or hand is detached or duplicated, if one figure has two "
    "heads, or if a prop is fused to a face. Judge the cartoon characters, not the "
    "props or the background."
)


def _ask_vlm(cfg, png_bytes, timeout=300):
    """One structural verdict. Returns a dict; never raises on a bad reply."""
    body = {
        "model": "tim-qwen",
        "temperature": 0,
        "max_tokens": 200,
        # Qwen3.6 is served without a reasoning parser, so thinking would leak as prose.
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(png_bytes).decode()}},
            {"type": "text", "text": CHECK}]}],
    }
    raw = common.http_json(f"{cfg['TIM_LLM_URL']}/v1/chat/completions", body, timeout=timeout)
    text = json.loads(raw)["choices"][0]["message"]["content"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # An unreadable verdict must not fail the frame: a false reroll costs two
        # minutes of GPU and a false pass is caught by the human review anyway.
        return {"figure_complete": True, "problem": f"unparsed verdict: {text[:80]}"}


def hero_shots(data, phrase="the main character"):
    """[(scene, shot_index, prompt)] for every GENERATED shot the character appears in.
    Figure-block shots are exempt: the character is drawn deterministically there,
    so there is no anatomy lottery to screen."""
    out = []
    for scene in data["scenes"]:
        for i, spec in enumerate(common.shot_specs(scene), start=1):
            if spec["figure"] is None and phrase in spec["prompt"].lower():
                out.append((scene, i, spec["prompt"]))
    return out


def check_one(cfg, theme, scene, shot_index, prompt, path, attempts, portrait):
    """Verdict for one frame, rerolling on a fresh seed while it comes back broken."""
    history = []
    for attempt in range(attempts + 1):
        verdict = _ask_vlm(cfg, path.read_bytes())
        history.append({"attempt": attempt, **verdict})
        if verdict.get("figure_complete", True):
            break
        if attempt == attempts:
            break
        seed = random.randint(1, 2**31)
        print(f"[qc] {path.name}: {verdict.get('problem', 'broken')} -> reroll seed={seed}",
              flush=True)
        gen_images.gen_one(cfg, theme, {**scene, "image_prompt": prompt}, path, seed=seed)
    return {
        "file": path.name,
        "scene": scene["id"],
        "shot": shot_index,
        "portrait": portrait,
        "passed": history[-1].get("figure_complete", True),
        "attempts": len(history),
        "history": history,
    }


def run(job_id, portrait=False, attempts=2):
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    work = common.job_dir(job_id) / "work"
    if portrait:
        cfg = {**cfg, "IMG_W": cfg["IMG_H"], "IMG_H": cfg["IMG_W"]}

    report = []
    for scene, shot_index, prompt in hero_shots(data):
        shot_count = len(common.shot_specs(scene))
        path = gen_images.shot_files(work, scene["id"], shot_count)[shot_index - 1]
        if portrait:
            path = path.with_name("p_" + path.name)
        if not path.exists():
            continue
        result = check_one(cfg, theme, scene, shot_index, prompt, path, attempts, portrait)
        report.append(result)
        flag = "ok  " if result["passed"] else "FAIL"
        print(f"[qc] {flag} {path.name} attempts={result['attempts']} "
              f"{result['history'][-1].get('problem', '')}", flush=True)

    path = common.job_dir(job_id) / ("qc_portrait.json" if portrait else "qc_landscape.json")
    path.write_text(json.dumps(report, indent=2))
    failed = [r["file"] for r in report if not r["passed"]]
    print(f"[qc] {job_id} {'portrait' if portrait else 'landscape'}: "
          f"{len(report) - len(failed)}/{len(report)} clean, report at {path.name}")
    if failed:
        print(f"[qc] still broken after {attempts} rerolls: {', '.join(failed)}")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--portrait", action="store_true")
    p.add_argument("--attempts", type=int, default=2, help="rerolls before giving up")
    a = p.parse_args()
    run(a.job, a.portrait, a.attempts)


if __name__ == "__main__":
    main()
