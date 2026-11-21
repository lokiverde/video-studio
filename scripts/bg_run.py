"""Run a long render detached from the Claude session that started it.

  python3 scripts/bg_run.py --name <label> -- <command> [args...]

Returns at once and prints where the log and status live. The command runs in its own
session at low priority (nice 10, so background bots stay responsive) and keeps going if
the Claude session, SSH link or laptop goes away. When it ends, jobs/_bg/<label>.status.json
says done or failed, and Telegram gets a ping if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are
set in config.env (the Mac mini has them; the MacBook stays quiet).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import common
import platform_util

BG_DIR = common.JOBS_DIR / "_bg"
NICE = 10
TAIL_LINES = 12
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def fmt_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


def build_message(label, rc, seconds, tail):
    took = fmt_duration(seconds)
    if rc == 0:
        return f"{label} done in {took}."
    lines = "\n".join(tail[-TAIL_LINES:])
    return f"{label} FAILED (exit {rc}) after {took}.\n\n{lines}"


def check_label(label):
    if not LABEL_RE.match(label or "") or ".." in label:
        common.die(f"--name {label!r}: use letters, digits, dot, dash or underscore")
    return label


def send_telegram(text, cfg, opener=urllib.request.urlopen):
    token, chat = cfg.get("TELEGRAM_BOT_TOKEN"), cfg.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with opener(req, timeout=20) as reply:
            return reply.status == 200
    except OSError as exc:
        print(f"telegram ping failed: {exc}", file=sys.stderr)
        return False


def _write_status(bg_dir, label, **fields):
    path = Path(bg_dir) / f"{label}.status.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"label": label, **fields}, indent=2))
    tmp.replace(path)


def _tail(log, n=TAIL_LINES):
    try:
        return log.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def run_child(label, cmd, bg_dir, cfg, notify=send_telegram):
    """Run cmd to completion with output in a timestamped log, then record and ping."""
    bg_dir = Path(bg_dir)
    bg_dir.mkdir(parents=True, exist_ok=True)
    log = bg_dir / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    started = time.time()
    base = {"cmd": cmd, "log": str(log), "pid": os.getpid(), "started": started}
    _write_status(bg_dir, label, state="running", **base)
    with open(log, "w") as out:
        try:
            rc = subprocess.call(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
        except OSError as exc:
            out.write(f"could not start {cmd[0]}: {exc}\n")
            rc = 127
    seconds = time.time() - started
    _write_status(bg_dir, label, state="done" if rc == 0 else "failed", rc=rc,
                  ended=time.time(), seconds=round(seconds, 1), **base)
    if notify:
        notify(build_message(label, rc, seconds, _tail(log)), cfg)
    return rc


def launch(label, cmd, bg_dir=BG_DIR, ping=True):
    """Start the child in its own session at low priority; return (pid, bg_dir) at once."""
    bg_dir = Path(bg_dir)
    bg_dir.mkdir(parents=True, exist_ok=True)
    child = [sys.executable, str(Path(__file__).resolve()), "--child", "--name", label,
             "--bg-dir", str(bg_dir)] + ([] if ping else ["--no-ping"]) + ["--"] + list(cmd)
    with open(bg_dir / f"{label}.runner.log", "a") as runner_log:
        proc = subprocess.Popen(child, stdin=subprocess.DEVNULL, stdout=runner_log,
                                stderr=subprocess.STDOUT, cwd=common.ROOT,
                                **platform_util.detached_low_priority(NICE))
    return proc.pid, bg_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True, help="label for the log, status file and ping")
    ap.add_argument("--bg-dir", default=str(BG_DIR), help=argparse.SUPPRESS)
    ap.add_argument("--no-ping", action="store_true", help="skip the Telegram ping")
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- then the command to run")
    a = ap.parse_args()
    label = check_label(a.name)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        common.die("nothing to run: put the command after --")
    if a.child:
        notify = None if a.no_ping else send_telegram
        sys.exit(run_child(label, cmd, a.bg_dir, common.load_config(), notify=notify))
    pid, bg_dir = launch(label, cmd, a.bg_dir, ping=not a.no_ping)
    print(f"started {label} (pid {pid}), detached at nice {NICE}")
    print(f"status: {bg_dir / (label + '.status.json')}")
    print(f"logs:   {bg_dir}/{label}-*.log")


if __name__ == "__main__":
    main()
