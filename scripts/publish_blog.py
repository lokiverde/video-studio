"""Row B of fv.py publish: the job's companion article (out/blog.md) on the right site.

Which site: --site, else blog.md `site:`, else the lane (tech goes to techtony.co), else
the topic (assets/publish/sites.json). A slug that already lives on a site in the repo
stays there. The plan reads origin/main of the site repo; Go works in its own clone
(~/.faceless-video/sites/<repo>, never a checkout other sessions use): fresh origin/main,
add-only edits (blog_entry.py), the build gate, a commit of the expected files only, then
the push. A push that loses the race is redone from the new origin/main, build and all.
Spec: docs/briefs/2026-10-29-auto-poster.md, decisions 10 and 11; my-sites PLAYBOOK rule 1."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import blog_entry
import blog_md
import common
import kit_links
import publish_plan as pp

SITES_FILE = common.ROOT / "assets" / "publish" / "sites.json"
ATTEMPTS = 3
BUILD_TIMEOUT_S = 1200
LIVE_POLL_S = 20
LIVE_MAX_S = 600
LOG_TAIL = 40
TOOL_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")
REJECTED = ("rejected", "fetch first", "non-fast-forward")
ACTIONS = {"add": "new post", "fill": "adds the video to the live post", "live": "already live, no change"}


def config() -> dict:
    return json.loads(SITES_FILE.read_text())


# ---- which site ---------------------------------------------------------------------------------

def site_key(value: str, cfg: dict) -> str:
    host = re.sub(r"^(?:https?://)?(?:www\.)?", "", (value or "").strip().lower()).split("/")[0]
    for key, site in cfg["sites"].items():
        if host == key or host in site.get("aliases", []):
            return key
    raise ValueError(f"blog site {value!r} is not in assets/publish/sites.json "
                     f"({', '.join(s['label'] for s in cfg['sites'].values())})")


def topic_site(p: dict, cfg: dict) -> str:
    words = " ".join([p["title"], p["slug"], *p["tags"], p["category"]]).lower().replace("-", " ")
    scores = {key: sum(len(re.findall(rf"(?<![\w&]){re.escape(k.replace('-', ' '))}(?![\w&])", words))
                       for k in kws)
              for key, kws in cfg["topics"].items()}
    best = max(scores.values(), default=0)
    return next(k for k, v in scores.items() if v == best) if best else cfg["topic_default"]


def choose_site(p: dict, lane: str, override: str | None, cfg: dict) -> tuple[str, str]:
    """(site key, why)."""
    if override:
        return site_key(override, cfg), "--site"
    if p["site"]:
        return site_key(p["site"], cfg), "blog.md site:"
    if lane in cfg["lane_site"]:
        return cfg["lane_site"][lane], f"{lane} lane"
    return topic_site(p, cfg), "topic"


def lane_category(p: dict, lane: str, key: str, cfg: dict) -> dict:
    """The post with its lane's pinned category when it lands on that lane's own site.
    Training posts on examplerealty are "Agent Training", which feeds the training pages.
    pick_category still falls back to the site default until the site has that category."""
    want = cfg.get("lane_category", {}).get(lane)
    if want and cfg["lane_site"].get(lane) == key:
        return {**p, "category": want}
    return p


# ---- running things in the clone -------------------------------------------------------------------

def _env() -> dict:
    """fv.py may run from a shell without Homebrew on PATH (node, pnpm, npm live there)."""
    path = os.environ.get("PATH", "")
    extra = [p for p in TOOL_PATHS if p not in path.split(os.pathsep)]
    return {**os.environ, "PATH": os.pathsep.join([*extra, path])}


def run(cmd: list[str], cwd: Path, timeout: int = 900, strip: bool = True) -> str:
    try:
        done = subprocess.run(cmd, cwd=cwd, env=_env(), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise RuntimeError(f"{' '.join(cmd)} failed in {cwd}: {err}") from err
    if done.returncode:
        tail = "\n".join((done.stdout + done.stderr).strip().split("\n")[-LOG_TAIL:])
        raise RuntimeError(f"{' '.join(cmd)} failed in {cwd} (exit {done.returncode}):\n{tail}")
    return done.stdout.strip() if strip else done.stdout


def git(clone: Path, *args: str) -> str:
    return run(["git", *args], clone, timeout=300)


def clone_dir(repo: str, cfg: dict) -> Path:
    return Path(cfg["clones"]).expanduser() / repo


def ensure_clone(repo: str, cfg: dict) -> Path:
    path = clone_dir(repo, cfg)
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "-q", cfg["repos"][repo]["remote"], str(path)], path.parent, timeout=600)
    git(path, "config", "user.name", cfg["git_user"]["name"])
    git(path, "config", "user.email", cfg["git_user"]["email"])
    return path


def sync(clone: Path) -> None:
    """The clone at a fresh origin/main, or a clear refusal."""
    git(clone, "fetch", "-q", "origin", "main")
    if git(clone, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError(f"{clone} has uncommitted changes: look at them, then "
                           f"git -C {clone} reset --hard origin/main")
    if git(clone, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        git(clone, "checkout", "-q", "main")
    ahead = git(clone, "rev-list", "--count", "origin/main..HEAD")
    if ahead != "0":
        raise RuntimeError(f"{clone} has {ahead} unpushed commit(s): push or drop them by hand first")
    git(clone, "merge", "-q", "--ff-only", "origin/main")


def install(clone: Path, repo: str, cfg: dict) -> None:
    """Dependencies, only when node_modules is missing or the lockfile changed."""
    spec = cfg["repos"][repo]
    if not spec.get("install"):
        return
    lock = hashlib.sha256((clone / spec["lockfile"]).read_bytes()).hexdigest()
    marker = clone.parent / f".{repo}.installed"
    if (clone / "node_modules").exists() and marker.exists() and marker.read_text().strip() == lock:
        return
    print(f"[publish] blog: installing {repo} dependencies")
    run(spec["install"], clone, timeout=BUILD_TIMEOUT_S)
    marker.write_text(lock + "\n")


# ---- what the publish changes ------------------------------------------------------------------------

def _site_for(jdir: Path, site: dict) -> dict:
    """The featured image only when the job has a thumbnail to copy."""
    if site.get("image_url") and not (Path(jdir) / "out" / "thumbnail.jpg").exists():
        return {k: v for k, v in site.items() if k != "image_url"}
    return site


def prepared(jdir: Path, p: dict, key: str, cfg: dict, read: Callable[[str], str], video_id: str,
             links: dict, day: date) -> dict:
    """Every file text the publish would write, the action and the library outcome."""
    site = _site_for(jdir, cfg["sites"][key])
    repo = cfg["repos"][site["repo"]]
    url = site["url"].format(slug=p["slug"])
    change = blog_entry.change(read(site["posts"]), p, site, video_id or kit_links.ID_PENDING, day)
    files = {site["posts"]: change["text"]} if change["action"] != "live" else {}
    library, obj = "no video library on this site", None
    entry_txt = Path(jdir) / "out" / "video_library_entry.txt"
    if repo.get("library") and change["action"] != "live":
        if not entry_txt.exists():
            library = "skips the video library entry: no out/video_library_entry.txt"
        else:
            obj, why = blog_entry.library_entry(entry_txt.read_text(), {
                **links, "youtube_id": video_id, "blog_url": url})     # uploadDate only from links.json
            if obj:
                text, why = blog_entry.add_library(read(repo["library"]), obj, video_id)
                if why is None:
                    files[repo["library"]] = text
            library = f"skips the video library entry: {why}" if why else "adds the video library entry"
    image = None
    if change["action"] == "add" and site.get("image_url"):
        image = (Path(jdir) / "out" / "thumbnail.jpg", f"{site['image_dir']}/{p['slug']}.jpg")
    return {"site": key, "url": url, "action": change["action"], "category": change["category"],
            "note": change["note"], "entry": change["entry"], "video": change["video"], "library_entry": obj if "adds" in library else None,
            "library": library, "files": files, "image": image}


def entry_sha(prep: dict) -> str:
    """What Tony approves of the post: site, action, the entry and the library entry. The
    date line is left out (it is the day of Go), so a table one day and Go the next match."""
    entry = re.sub(r'^\s+date: "[^"]*",\n', "", prep["entry"], flags=re.M)
    data = [prep["site"], prep["action"], prep["category"], entry, prep["library_entry"] or prep["library"]]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:16]


def plan_row(jdir: Path, lane: str, override: str | None, video_id: str | None, links: dict,
             day: date) -> dict | None:
    """Row B for the Go table, None when the job has no blog.md. Problems are reported on
    the row, not raised, so the table still prints (Go refuses them, --drop B skips the blog)."""
    path = Path(jdir) / "out" / "blog.md"
    if not path.exists():
        return None
    p = blog_md.post(path.read_text())
    row = {"id": "B", "kind": "blog", "file": "blog.md", "title": p["title"], "seconds": 0, "slug": p["slug"],
           "site": None, "url": None, "problems": blog_md.problems(p)}
    if row["problems"]:
        return row
    try:
        cfg = config()
        key, why = choose_site(p, lane, override, cfg)
        clone = ensure_clone(cfg["sites"][key]["repo"], cfg)
        try:
            git(clone, "fetch", "-q", "origin", "main")
        except RuntimeError as err:
            print(f"[publish] blog: could not fetch {cfg['sites'][key]['repo']}, planning from the last copy ({err})")

        def read(rel: str) -> str:
            return run(["git", "show", f"origin/main:{rel}"], clone, strip=False)

        found = next((k for k, s in cfg["sites"].items() if s["repo"] == cfg["sites"][key]["repo"]
                      and blog_entry.find_post(read(s["posts"]), p["slug"])), key)
        if found != key:
            why = f"the post is already on {cfg['sites'][found]['label']}"
        p = lane_category(p, lane, found, cfg)
        prep = prepared(jdir, p, found, cfg, read, video_id, links, day)
    except (ValueError, RuntimeError, OSError) as err:
        return {**row, "problems": [str(err)]}
    if prep["action"] == "live" and video_id and prep["video"] != video_id:
        row = {**row, "problems": [_other_video(prep, video_id)]}
    return {**row, "site": found, "site_why": why, "url": prep["url"], "action": prep["action"],
            "category": prep["category"], "want_category": p["category"], "note": prep["note"],
            "library": prep["library"], "entry": prep["entry"], "entry_sha": entry_sha(prep)}


# ---- Go ---------------------------------------------------------------------------------------------------

def _other_video(prep: dict, video_id: str) -> str:
    return (f"{prep['url']} already embeds video {prep['video']}, not this job's {video_id}: "
            "give blog.md its own slug, or --drop B")


def _approved(prep: dict, row: dict, video_id: str) -> None:
    """Go publishes only what the table showed. A post that is already live with this
    job's video is fine whatever was planned (an earlier Go that crashed after the push)."""
    if prep["action"] == "live":
        if prep["video"] != video_id:
            raise RuntimeError(_other_video(prep, video_id))
        return
    if prep["action"] != row.get("action") or entry_sha(prep) != row.get("entry_sha"):
        raise RuntimeError("row B changed since the table you saw (another post landed on the site, or the "
                           "table read a stale copy): run fv.py publish JOB, review row B, then --go again")


def _apps(clone: Path, cfg: dict, key: str, repo: dict) -> list[str]:
    """The site's app, plus the app behind any generated file the write changed (the
    network feed belongs to examplerealty), so the gate builds everything the commit feeds."""
    changed = set(git(clone, "diff", "--name-only", "HEAD").split("\n"))
    apps = [cfg["sites"][key]["app"], *[app for rel, app in repo.get("generated", {}).items() if rel in changed]]
    return list(dict.fromkeys(apps))


def _build_cmd(template: list[str], apps: list[str]) -> list[str]:
    """The build command with its {app} part once per app (turbo takes several --filter)."""
    return [out for part in template for out in ([part.format(app=a) for a in apps] if "{app}" in part else [part])]


def _write(clone: Path, prep: dict) -> list[str]:
    created = []
    for rel, text in prep["files"].items():
        (clone / rel).write_text(text)
    if prep["image"]:
        src, rel = prep["image"]
        if not (clone / rel).exists():
            (clone / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, clone / rel)
            created.append(rel)
    return created


def _restore(clone: Path, created: list[str]) -> None:
    """Back to origin/main: drops our edits and any local commit that never reached origin
    (a push that timed out may have landed; the next run finds that post live)."""
    git(clone, "reset", "-q", "--hard", "origin/main")
    for rel in created:
        (clone / rel).unlink(missing_ok=True)


def _message(prep: dict, p: dict, video_id: str, job: str) -> str:
    key = prep["site"]
    if prep["action"] == "add":
        subject = f"feat: publish {p['title']}" if key == "techtony" else f"feat({key}): add news post: {p['title']}"
    else:
        subject = f"feat({key}): embed {p['slug']} video ({video_id})"
    extra = "\nAdds its video library entry." if prep["library_entry"] else ""
    return f"{subject}\n\nPublished by fv.py publish, faceless-video job {job}.{extra}\n"


def _commit(clone: Path, prep: dict, created: list[str], repo: dict, p: dict, video_id: str, job: str) -> str:
    """Commit the expected files only. Anything else the build touched is put back."""
    expected = {*prep["files"], *created, *repo.get("generated", [])}
    for rel in git(clone, "diff", "--name-only", "HEAD").split("\n"):
        if rel and rel not in expected:
            print(f"[publish] blog: the build changed {rel}; put back, not committed")
            git(clone, "checkout", "-q", "--", rel)
    changed = [rel for rel in sorted(expected) if (clone / rel).exists()]
    git(clone, "add", "--", *changed)
    git(clone, "commit", "-q", "-m", _message(prep, p, video_id, job))
    return git(clone, "rev-parse", "--short", "HEAD")


def _push(clone: Path) -> bool:
    """True when pushed, False when origin moved first. Anything else raises."""
    try:
        done = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=clone, env=_env(),
                              capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise RuntimeError(f"git push did not finish in {clone}: {err}") from err
    if done.returncode == 0:
        return True
    if any(mark in done.stderr for mark in REJECTED):
        return False
    raise RuntimeError(f"git push failed in {clone}:\n{done.stderr.strip()}")


def wait_live(url: str, video_id: str, log: Callable[[str], None] = print) -> bool:
    """The page is up and carries the video (Vercel deploys in a minute or two)."""
    deadline = time.time() + LIVE_MAX_S
    log(f"[publish] blog: waiting for {url} to go live")
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fv.py publish"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200 and video_id in resp.read().decode("utf-8", "replace"):
                    return True
        except (OSError, ValueError, http.client.HTTPException):
            pass
        time.sleep(LIVE_POLL_S)
    return False


def publish(jdir: Path, row: dict, video_id: str, links: dict, at: datetime,
            log: Callable[[str], None] = print) -> dict:
    """Publish row B. Returns what to save on the row."""
    cfg = config()
    key = row["site"]
    repo_key = cfg["sites"][key]["repo"]
    repo = cfg["repos"][repo_key]
    clone = ensure_clone(repo_key, cfg)
    p = blog_md.post((Path(jdir) / "out" / "blog.md").read_text())
    if row.get("want_category"):                     # the lane's pin, as the table planned it
        p = {**p, "category": row["want_category"]}
    day = at.astimezone(pp.TZ).date()
    for attempt in range(1, ATTEMPTS + 1):
        sync(clone)
        prep = prepared(jdir, p, key, cfg, lambda rel: (clone / rel).read_text(), video_id, links, day)
        _approved(prep, row, video_id)
        if prep["action"] == "live":
            log(f"[publish] blog: {prep['url']} already has its video, nothing to change")
            return {"status": "published", "action": "live", "url": prep["url"], "commit": None,
                    "at": at.isoformat(), "live": wait_live(prep["url"], video_id, log)}
        created: list[str] = []
        try:
            created = _write(clone, prep)
            install(clone, repo_key, cfg)
            for cmd in repo.get("after_write", []):
                run(cmd, clone)
            apps = _apps(clone, cfg, key, repo)
            log(f"[publish] blog: building {', '.join(apps)} (the gate before any push)")
            run(_build_cmd(repo["build"], apps), clone, BUILD_TIMEOUT_S)
            commit = _commit(clone, prep, created, repo, p, video_id, Path(jdir).name)
            pushed = _push(clone)
        except BaseException:
            _restore(clone, created)
            raise
        if pushed:
            break
        log(f"[publish] blog: origin moved before the push (try {attempt} of {ATTEMPTS}), redoing it")
        _restore(clone, created)
    else:
        raise RuntimeError(f"could not push to {repo_key} after {ATTEMPTS} tries: origin keeps moving")
    log(f"[publish] blog: pushed {commit} to {repo_key} ({ACTIONS[prep['action']]}, {prep['library']})")
    live = wait_live(prep["url"], video_id, log)
    log(f"[publish] blog: {'live' if live else 'NOT live yet (check the Vercel deploy)'}: {prep['url']}")
    try:
        run([part.format(url=prep["url"]) for part in repo["indexnow"]], clone, timeout=60)
    except RuntimeError as err:
        log(f"[publish] blog: IndexNow ping failed, harmless: {err}")
    hub = cfg["sites"][key].get("hub")
    if hub and prep["action"] == "add" and prep["category"] == hub["category"]:
        log(f"[publish] blog: a {hub['category']} post: add it to the city hub by hand, {hub['url']}")
    return {"status": "published", "action": prep["action"], "url": prep["url"], "commit": commit,
            "at": at.isoformat(), "live": live, "library": prep["library"]}
