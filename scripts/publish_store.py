"""The publish.json sidecar: a job's lane, route, YouTube id, Go plan and Blotato ids.
Like links.json it sits outside every approval hash, so writing it never sends Tony back
through a preview gate. Also reads every job's sidecar to see which slots are booked.
Spec: docs/briefs/2026-10-29-auto-poster.md."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import publish_plan as pp

SIDECAR = "publish.json"


def load(jdir: Path) -> dict:
    """publish.json as a dict, empty when the job has none. A sidecar that exists but does not
    parse is an error: treating it as empty would post everything a second time."""
    path = Path(jdir) / SIDECAR
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError as err:
        raise ValueError(f"{path} is not valid JSON ({err}): fix it by hand before publishing") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object: fix it by hand before publishing")
    return data


def save(jdir: Path, updates: dict) -> dict:
    """New record with the updates merged in, written atomically. Returns the record."""
    record = {**load(jdir), **updates}
    path = Path(jdir) / SIDECAR
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)          # replace, not rename: Windows refuses to rename over a file
    return record


def bookings(jobs_dir: Path, now: datetime, skip: str | None = None,
             li_key: str = "me_linkedin") -> dict:
    """What other jobs already have in Blotato: taken[lane] = Short slot anchors from now on,
    nine[lane] = dates with a 9:00 Short, li_days = Pacific dates Tony LI posts (by the LI
    post's own time), counted from today even when today's post already went out, and
    busy = (channel, minute) of every live post from now on. The full LinkedIn video books
    only its Tony LI day and minute, never a lane slot. Only rows that went out at Go count;
    a plan nobody approved books nothing."""
    taken: dict[str, set[datetime]] = {}
    nine: dict[str, set[date]] = {}
    li_days: set[date] = set()
    busy: set[tuple[str, datetime]] = set()
    cutoff = pp.minute(now)
    for path in sorted(Path(jobs_dir).glob(f"*/{SIDECAR}")):
        if path.parent.name == skip:
            continue
        record = load(path.parent)
        lane = record.get("lane")
        for row in record.get("rows") or []:
            if row.get("status") not in ("scheduled", "partial") or row.get("at") in (None, "go"):
                continue
            minutes = pp.row_minutes(row)
            busy |= {m for m in minutes if m[1] >= cutoff}
            for key, at in minutes:
                local = at.astimezone(now.tzinfo).date()
                if key == li_key and local >= now.date():
                    li_days.add(local)
            when = datetime.fromisoformat(row["at"]).astimezone(now.tzinfo)
            if row.get("kind") == "linkedin_full" or when <= now:
                continue
            taken.setdefault(lane, set()).add(when)
            if when.hour == 9 and when.minute == 0:
                nine.setdefault(lane, set()).add(when.date())
    return {"taken": taken, "nine": nine, "li_days": li_days, "busy": busy}
