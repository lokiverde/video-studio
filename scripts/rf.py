"""Realistic footage jobs: fv.py rf new | lint | pack | status | ingest.

A real-footage job keeps its own folder, jobs/<job>/rf/: brief.md, the shot list
(shots.json), the files that come back from the generator (returns/) and a ledger of
every file ingested (ledger.jsonl). The prompts are written and linted here; the
video-engine skill generates them on OpenArt behind its AUTH gate; ingest brings the
files back. Spec: docs/briefs/2026-10-24-realistic-footage.md, sections 5.2 and 5.3.
"""
import argparse
import json
import sys
from pathlib import Path

import common
import rf_ingest
import rf_library
import rf_lint
import rf_pack

DEFAULT_LANE = "techtony"
STILL_MODEL = "nano-banana-pro"
CLIP_MODELS = {"draft": "byte-plus-seedance-2-5-draft", "final": "byte-plus-seedance-2-5"}


def starter_shots(job_id, idea, lane, style="", technique=""):
    """The shot list a new job starts from: one reference still, then the clip that
    anchors on it, both in `style`, the clip moving with `technique`. Prompts are blank
    until Claude writes them."""
    return {
        "job": job_id,
        "idea": idea,
        "lane": lane,
        "ai_disclosure": True,
        "likeness": {},
        "defaults": {"provider": "openart", "aspect": "9:16", "draft_first": True,
                     "ref_tag_syntax": "image N by position (OpenArt, 2026-10-24)"},
        "shots": [
            {"id": "S01", "kind": "still", "purpose": "reference frame for S02",
             "model": STILL_MODEL, "mode": "image2image", "style": style, "refs": [], "prompt": "",
             "settings": {"resolution": "2K", "aspect": "9:16"}, "status": "drafted"},
            {"id": "S02", "kind": "clip", "technique": technique, "style": style,
             "model": dict(CLIP_MODELS),
             "mode": "element2video", "duration_s": 8, "refs": [], "dialogue": [], "prompt": "",
             "settings": {"draft": "480p", "final": "1080p", "aspect": "9:16"},
             "status": "drafted", "returns": []},
        ],
    }


def brief_text(idea, lane):
    return (f"# Real-footage brief\n\n"
            f"**Idea:** {idea}\n\n"
            f"**Lane:** {lane}\n\n"
            "Rule: every video with a clip says so in its YouTube description and in Studio's "
            "altered or synthetic content setting; there is no off switch. "
            "Generate drafts first; finals only for drafts Tony passes.\n\n"
            "Likeness: only Tony or Partner, and only when Tony sets them to \"approved\" "
            "in shots.json. Claude never fills that block in.\n")


def ladder_text(idea):
    """The four-level idea ladder (spec 3.5): the idea as given is level 0, and each
    level above keeps the last and adds one unexpected layer. Claude fills 1 to 3, Tony
    picks the level the clip is built from."""
    return ("\n## Idea ladder (pick a level)\n\n"
            "Each level keeps the one below it and adds one unexpected layer.\n\n"
            f"- Level 0: {idea} (the expected version)\n"
            "- Level 1: same subject, plus a small human problem:\n"
            "- Level 2: give it a personality:\n"
            "- Level 3: flip the emotional register:\n")


def cmd_new(a):
    rf_library.require_names(a.style, a.technique)
    if (common.JOBS_DIR / a.job).is_dir():
        job_id, jdir = a.job, common.JOBS_DIR / a.job
    else:
        job_id, jdir = common.new_job(word=a.job)
    rf_dir = jdir / "rf"
    if rf_dir.exists():
        common.die(f"job {job_id} already has a real-footage folder; edit {rf_dir / 'shots.json'}")
    rf_dir.mkdir()
    brief = brief_text(a.idea, a.lane) + (ladder_text(a.idea) if a.ladder else "")
    (rf_dir / "brief.md").write_text(brief)
    (rf_dir / "shots.json").write_text(json.dumps(starter_shots(job_id, a.idea, a.lane, a.style or "",
                                                              a.technique or ""), indent=2))
    print(f"[rf] job {job_id}: {rf_dir / 'brief.md'} + shots.json")


def shots_path(job_id):
    path = common.job_dir(job_id) / "rf" / "shots.json"
    if not path.exists():
        common.die(f"job {job_id} has no real-footage shot list (run: fv.py rf new {job_id} --idea ...)")
    return path


def load_shots(job_id):
    """The job's shot list. Realistic footage is always disclosed (Tony, 2026-10-24), so a
    list that turns disclosure off is refused before anything else reads it."""
    data = json.loads(shots_path(job_id).read_text())
    if data.get("ai_disclosure") is not True:
        common.die(f"job {job_id} rf/shots.json: 'ai_disclosure' must be true (AI footage is "
                   f"always disclosed, there is no off switch), got {json.dumps(data.get('ai_disclosure'))}")
    return data


def save_shots(job_id, data):
    shots_path(job_id).write_text(json.dumps(data, indent=2))


STATUS_COLUMNS = ("shot", "kind", "technique", "style", "status", "returns", "lint")


def status_row(shot):
    returns = ",".join(p.rsplit("/", 1)[-1] for p in shot.get("returns", []))
    cells = (shot.get("id"), shot.get("kind"), shot.get("technique"), shot.get("style"),
             shot.get("status"), returns, shot.get("lint"))
    return [str(c) if c else "-" for c in cells]


def cmd_status(a):
    rows = [list(STATUS_COLUMNS)] + [status_row(s) for s in load_shots(a.job)["shots"]]
    widths = [max(len(r[i]) for r in rows) for i in range(len(STATUS_COLUMNS))]
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())


def cmd_ingest(a):
    data = load_shots(a.job)
    shot = next((s for s in data["shots"] if s.get("id") == a.shot), None)
    if shot is None:
        common.die(f"job {a.job} has no shot {a.shot} "
                   f"(have: {', '.join(s.get('id', '?') for s in data['shots'])})")
    lines = rf_ingest.ingest(common.job_dir(a.job), data, shot, [Path(f) for f in a.files],
                             a.model, a.creation, a.credits, a.record)
    updated = {**shot, "status": "ingested",
               "returns": [*shot.get("returns", []), *(line["file"] for line in lines)]}
    save_shots(a.job, {**data, "shots": [updated if s is shot else s for s in data["shots"]]})


C9_REMINDER = ("C9 word lists cannot prove a prompt is clean: Tony still looks for real people, "
               "brands, property, clients, students and money.")


def run_lint(job_id, data, shot_id=None):
    """Lint the shot list against rf/brief.md, print every finding, return them."""
    brief = common.job_dir(job_id) / "rf" / "brief.md"
    found = rf_lint.findings(data, brief.read_text() if brief.exists() else "",
                             rf_lint.load_settings(), shot_id)
    for finding in found:
        print(finding)
    return found


def fail_count(found):
    return sum(1 for f in found if f.level == "FAIL")


def cmd_lint(a):
    data = load_shots(a.job)
    found = run_lint(a.job, data, a.shot)
    save_shots(a.job, rf_pack.record_lint(data, rf_lint.results(data, found, a.shot)))
    fails = fail_count(found)
    print(f"[rf] lint {a.job}: {fails} FAIL, {len(found) - fails} WARN. {C9_REMINDER}")
    if fails:
        sys.exit(1)


def cmd_pack(a):
    data = load_shots(a.job)
    rf_pack.check_all(data)
    found = run_lint(a.job, data)
    linted = rf_pack.record_lint(data, rf_lint.results(data, found))
    if fail_count(found):
        save_shots(a.job, linted)
        common.die(f"lint FAIL blocks the pack ({fail_count(found)}); fix rf/shots.json and run "
                   f"fv.py rf lint {a.job}")
    rf_dir = common.job_dir(a.job) / "rf"
    updated = rf_pack.write(rf_dir, linted)
    save_shots(a.job, updated)
    print(f"[rf] job {a.job}: {rf_dir / 'pack.md'} ({len(updated['shots'])} shots, stills first) "
          f"+ rf/prompts/*.txt")


def add_parsers(sub):
    """The rf command group, shared by fv.py and this module's own main()."""
    group = sub.add_parser("rf", help="realistic footage: new | lint | pack | status | ingest")
    rf_sub = group.add_subparsers(dest="rf_cmd", required=True)
    p = rf_sub.add_parser("new", help="start a real-footage job: brief + starter shot list")
    p.add_argument("job", help="a new job's one word (fox), or an existing job id")
    p.add_argument("--idea", required=True, help="the idea in plain English")
    p.add_argument("--lane", default=DEFAULT_LANE)
    p.add_argument("--style", help="camera style for both shots (assets/real-footage/styles/)")
    p.add_argument("--technique", help="camera behavior for the clip (assets/real-footage/behaviors/)")
    p.add_argument("--ladder", action="store_true", help="write the four-level idea ladder into the brief")
    p.set_defaults(fn=cmd_new)
    p = rf_sub.add_parser("lint", help="check every prompt: FAIL blocks the pack, WARN prints")
    p.add_argument("job")
    p.add_argument("--shot", help="lint one shot (the job-wide rules still run)")
    p.set_defaults(fn=cmd_lint)
    p = rf_sub.add_parser("pack", help="write rf/pack.md and rf/prompts/ for the engine")
    p.add_argument("job")
    p.set_defaults(fn=cmd_pack)
    p = rf_sub.add_parser("status", help="one table: every shot, its status, returns and lint result")
    p.add_argument("job")
    p.set_defaults(fn=cmd_status)
    p = rf_sub.add_parser("ingest", help="check, copy and ledger files the generator returned")
    p.add_argument("job")
    p.add_argument("files", nargs="+")
    p.add_argument("--shot", required=True, help="shot id, e.g. S02")
    p.add_argument("--model", help="OpenArt model id the engine used")
    p.add_argument("--creation", help="OpenArt creation (generation) id")
    p.add_argument("--credits", type=float, help="credits OpenArt quoted for the call")
    p.add_argument("--record", help="JSON the engine saved for the call (creation record, quote, "
                                    "balances); kept as rf/openart/<creation>.json")
    p.set_defaults(fn=cmd_ingest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_parsers(parser.add_subparsers(dest="cmd", required=True))
    args = parser.parse_args(["rf", *(sys.argv[1:] if argv is None else argv)])
    args.fn(args)


if __name__ == "__main__":
    main()
