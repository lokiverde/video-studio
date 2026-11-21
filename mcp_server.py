"""MCP server exposing the faceless-video pipeline (for ChatGPT connectors etc).

Run:  pip install "mcp[cli]"   then   python3 mcp_server.py
Serves streamable HTTP on 0.0.0.0:8790 (path /mcp). Put it behind a Cloudflare
tunnel with Cloudflare Access (or another auth layer); the server itself trusts
its callers. Long steps run in background threads; poll with get_status.

Tim renders the media, so this host only needs tailnet access to Tim + ffmpeg.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import common  # noqa: E402

mcp = FastMCP("faceless-video", host="0.0.0.0", port=8790)
_procs = {}


def _run_bg(job_id, args):
    """Run an fv.py subcommand in a thread; capture output into job state."""
    def worker():
        proc = subprocess.run([sys.executable, str(SCRIPTS / "fv.py"), *args],
                              capture_output=True, text=True)
        tail = (proc.stdout + proc.stderr)[-2000:]
        common.set_state(job_id, last_output=tail,
                         **({"status": "error"} if proc.returncode else {}))
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    _procs[job_id] = thread


@mcp.tool()
def make_faceless_video(article_url: str = "", article_text: str = "",
                        outline: str = "", theme: str = "sketch",
                        voice: str = "stock", skip_preview: bool = False,
                        word: str = "") -> str:
    """Start a faceless video job from an article URL, article text, or an outline.
    Returns a job_id immediately; poll get_status. Unless skip_preview, the job
    pauses at 'previewed' with image URLs for approval (then call approve)."""
    if not (article_url or article_text or outline):
        return "error: provide article_url, article_text, or outline"
    job_id, jdir = common.new_job(word=word or None)
    args = ["make", "--theme", theme, "--voice", voice]
    if skip_preview:
        args.append("--no-preview")
    if article_url:
        args += ["--article-url", article_url]
    else:
        src = jdir / ("outline.md" if outline else "article.txt")
        src.write_text(outline or article_text)
        args += ["--outline-file" if outline else "--article-file", str(src)]
    common.set_state(job_id, status="starting")
    _run_bg(job_id, args)
    return json.dumps({"job_id": job_id, "note": "poll get_status until 'previewed' (or 'uploaded' when skip_preview)"})


@mcp.tool()
def get_status(job_id: str) -> str:
    """Job state: status (starting|scripted|imaged|previewed|narrated|rendered|uploaded|error),
    preview_urls, video_urls, and the last pipeline output."""
    try:
        return json.dumps(common.get_state(job_id))
    except SystemExit:
        return f"error: unknown job {job_id}"


@mcp.tool()
def get_preview(job_id: str) -> str:
    """CDN URLs of the per-scene stills + contact sheet for user approval."""
    state = common.get_state(job_id)
    urls = state.get("preview_urls", [])
    return json.dumps(urls) if urls else "no previews yet; check get_status"


@mcp.tool()
def regen_scene(job_id: str, scene: int, prompt: str = "", seed: int = 0) -> str:
    """Reroll one scene's image (new seed, or a replacement visual prompt)."""
    args = ["regen-scene", job_id, str(scene)]
    if prompt:
        args += ["--prompt", prompt]
    if seed:
        args += ["--seed", str(seed)]
    _run_bg(job_id, args)
    return "regenerating; poll get_status then get_preview"


@mcp.tool()
def approve(job_id: str, voice: str = "", music: str = "") -> str:
    """Approve the previewed images: narrate, assemble, upload. Poll get_status
    for status 'uploaded' and video_urls."""
    args = ["finish", job_id]
    if voice:
        args += ["--voice", voice]
    if music:
        args += ["--music", music]
    _run_bg(job_id, args)
    return "finishing; poll get_status for video_urls"


@mcp.tool()
def list_themes() -> str:
    """Available visual themes."""
    themes = {p.stem: json.loads(p.read_text()).get("description", "")
              for p in sorted(common.THEMES_DIR.glob("*.json"))}
    return json.dumps(themes)


@mcp.tool()
def list_characters() -> str:
    """The character library: named recurring characters with descriptions.
    Themes reference one by name so the same character appears across videos."""
    chars = {p.stem: json.loads(p.read_text()).get("description", "")
             for p in sorted(common.CHARACTERS_DIR.glob("*.json"))}
    return json.dumps(chars)


@mcp.tool()
def save_theme(name: str, from_job: str, character_desc: str = "") -> str:
    """Save a finished job's look as a reusable theme; character_desc pins a
    recurring character into every future image prompt."""
    args = ["save-theme", name, "--from-job", from_job]
    if character_desc:
        args += ["--character", character_desc]
    proc = subprocess.run([sys.executable, str(SCRIPTS / "fv.py"), *args],
                          capture_output=True, text=True)
    return proc.stdout + proc.stderr


def _fv(*args):
    """Run a quick fv.py subcommand and hand back everything it printed."""
    proc = subprocess.run([sys.executable, str(SCRIPTS / "fv.py"), *args],
                          capture_output=True, text=True)
    return proc.stdout + proc.stderr


@mcp.tool()
def rf_new(job: str, idea: str, lane: str = "techtony", ladder: bool = False, style: str = "",
           technique: str = "") -> str:
    """Start a realistic-footage job: a brief and a starter shot list under jobs/<job>/rf/.
    job is one word for a new job (fox) or an existing job id. style names a camera style
    (assets/real-footage/styles/) for both shots, technique a camera behavior
    (assets/real-footage/behaviors/) for the clip; an unknown name is refused. ladder adds
    the four-level idea ladder to the brief."""
    args = ["rf", "new", job, "--idea", idea, "--lane", lane]
    if style:
        args += ["--style", style]
    if technique:
        args += ["--technique", technique]
    return _fv(*args, *(["--ladder"] if ladder else []))


@mcp.tool()
def rf_lint(job_id: str, shot: str = "") -> str:
    """Check a realistic-footage job's prompts against the rules (I1-I5, C1-C13, likeness).
    FAIL lines block rf_pack; WARN lines print and the pack goes ahead. shot lints one shot
    (S02); the job-wide rules still run. Each shot's result shows in rf_status."""
    return _fv("rf", "lint", job_id, *(["--shot", shot] if shot else []))


@mcp.tool()
def rf_pack(job_id: str) -> str:
    """Write the prompt pack the video-engine generates from: rf/pack.md (shots in
    generation order, stills first, each with model and mode, settings, status, references,
    draft-then-final and a copy block) and rf/prompts/<id>.txt. No prices. Packed shots
    show as packed in rf_status."""
    return _fv("rf", "pack", job_id)


@mcp.tool()
def rf_status(job_id: str) -> str:
    """One table for a realistic-footage job: every shot, its status, returned files, lint."""
    return _fv("rf", "status", job_id)


@mcp.tool()
def rf_ingest(job_id: str, files: list[str], shot: str, model: str = "", creation: str = "",
              credits: float | None = None, record: str = "") -> str:
    """Check, copy and ledger files the generator returned for one shot (S01, S02...).
    Pass model, creation and the quoted credits when the engine made the file, plus record:
    the path of the JSON it saved for the call (creation record, quote, balances). Leave
    them out for a file from anywhere else, which is ledgered as provider manual."""
    args = ["rf", "ingest", job_id, *files, "--shot", shot]
    if model:
        args += ["--model", model]
    if creation:
        args += ["--creation", creation]
    if credits is not None:
        args += ["--credits", str(credits)]
    if record:
        args += ["--record", record]
    return _fv(*args)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
