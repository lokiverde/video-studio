"""Slot planning for fv.py publish. Pure: the clock and the other jobs' bookings come in as
arguments, rows go out as new dicts (inputs are never mutated).

Each lane posts at 09:00 and 12:00 Pacific (15:00 too for an --urgent job). Shorts take the
next free slots in kit order. Tony LI posts at most once a day, only on a 9:00 Short, on its
lane's own day (odd ordinal days tech, even real estate) unless the other lane has no 9:00
Short that day. A dropped Short frees its slot and later ones slide up; a pinned Short keeps
its time and nothing slides into it; a scheduled row never moves. The blog row (B) posts at
Go and takes no slot.

Stagger: the slot is the row's anchor; each channel posts at its own clock time inside it
(channels.json lanes.<lane>.stagger, keyed by the slot's HH:MM), so one Short fills the day
instead of landing on four channels at the same minute. A channel time already under ten
minutes away, or a pin outside the table, posts at the anchor. The full LinkedIn video goes
at Go only between 7:00 and 21:00; a night Go holds it for the next 9:00 row's Tony LI time.
Spec: docs/briefs/2026-10-29-auto-poster.md, decisions 5, 13, 16 and 22."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
SLOTS = (time(9, 0), time(12, 0))
URGENT_SLOT = time(15, 0)
LI_SLOT = time(9, 0)
GO_HOURS = (time(7, 0), time(21, 0))          # the full LinkedIn video goes at Go only inside these
MIN_LEAD = timedelta(minutes=10)
HORIZON_DAYS = 366
LI_KEY = "me_linkedin"
SENT = ("scheduled", "partial", "cancelled", "published")   # rows already out (Blotato, the blog): never move
MAX_SECONDS = {"twitter": 140}
SUFFIX_PLATFORM = {"x": "twitter", "twitter": "twitter", "tiktok": "tiktok", "youtube": "youtube",
                   "linkedin": "linkedin", "instagram": "instagram", "facebook": "facebook"}


# ---- time -------------------------------------------------------------------------------

def li_owner(day: date) -> str:
    """Whose day Tony LI is: odd ordinal days tech, even real estate."""
    return "tech" if day.toordinal() % 2 else "realestate"


def slot_times(start: datetime, urgent: bool = False) -> Iterator[datetime]:
    """Every lane slot from start on, in order, for HORIZON_DAYS days."""
    times = SLOTS + ((URGENT_SLOT,) if urgent else ())
    day = start.astimezone(TZ).date()
    for offset in range(HORIZON_DAYS):
        for t in times:
            yield datetime.combine(day + timedelta(days=offset), t, tzinfo=TZ)


def channel_times(anchor: datetime, keys: Iterable[str], stagger: dict | None,
                  earliest: datetime | None = None) -> dict[str, str]:
    """Each channel's own posting time (ISO) for a row anchored at a slot. The table is keyed
    by the anchor's Pacific HH:MM; a channel or a clock time not in it, or a staggered time
    before earliest, posts at the anchor."""
    local = anchor.astimezone(TZ)
    table = (stagger or {}).get(local.strftime("%H:%M")) or {}
    out = {}
    for key in keys:
        when = local
        if key in table:
            when = datetime.combine(local.date(), time.fromisoformat(table[key]), tzinfo=TZ)
            if earliest is not None and when < earliest:
                when = local
        out[key] = when.isoformat()
    return out


def full_li_anchor(now: datetime, stagger: dict | None, li_days: set[date] | None = None) -> datetime | None:
    """None when a Go now may post the full LinkedIn video at once; at night, the next 9:00
    row whose Tony LI time is still ahead, on a day Tony LI has no post yet."""
    local = now.astimezone(TZ)
    if GO_HOURS[0] <= local.time() < GO_HOURS[1]:
        return None
    for offset in range(HORIZON_DAYS):
        day = local.date() + timedelta(days=offset)
        anchor = datetime.combine(day, LI_SLOT, tzinfo=TZ)
        if day not in (li_days or ()) and \
                datetime.fromisoformat(channel_times(anchor, [LI_KEY], stagger)[LI_KEY]) >= now + MIN_LEAD:
            return anchor
    raise ValueError(f"no free Tony LI morning in the next {HORIZON_DAYS} days")


def minute(at: str | datetime) -> datetime:
    """One instant per clock minute, for (channel, minute) collision checks."""
    value = datetime.fromisoformat(at) if isinstance(at, str) else at
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def row_minutes(row: dict) -> set[tuple[str, datetime]]:
    """(channel, minute) of every live post a row holds in Blotato, or plans to. A post's
    own "at" is the truth once it is sent; a plan uses its times, then its anchor."""
    out = set()
    if row.get("dropped") or row.get("at") in (None, "go"):
        return out
    posts = row.get("posts") or {}
    times = row.get("times") or {}
    for key in row.get("channels") or []:
        post = posts.get(key) or {}
        if post.get("cancelled"):
            continue
        at = post.get("at") if post.get("submission_id") else None
        at = at or times.get(key) or row["at"]
        if at != "go":
            out.add((key, minute(at)))
    return out


def clashes(times: dict[str, str], busy: set[tuple[str, datetime]],
            accounts: dict[str, str] | None = None) -> list[str]:
    """Channels whose time is already taken (the Blotato lookup matches by account and
    minute, so two posts there would be ambiguous). With accounts (channel key to account
    id), two channels on one login count as one: Tony LI and the HM page share 90003."""
    def owner(key: str) -> str:
        return (accounts or {}).get(key, key)

    taken = {(owner(key), at) for key, at in busy}
    return [key for key, at in times.items() if (owner(key), minute(at)) in taken]


def when_label(at: str | None) -> str:
    """'Fri 10-30 09:00' in Pacific time, or 'at Go' for a row that posts when Tony says Go."""
    if at in (None, "go"):
        return "at Go"
    return datetime.fromisoformat(at).astimezone(TZ).strftime("%a %m-%d %H:%M")


def parse_when(value: str) -> datetime:
    """'2026-10-31T15:00', '2026-10-31 15:00', '2026-10-31 3pm' or '2026-10-31 9:30am',
    read as Pacific time."""
    text = (value or "").strip().lower()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[t ](\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        raise ValueError(f"not a date and time: {value!r} (use 2026-10-31T15:00 or 2026-10-31 3pm)")
    day, hour, minute, half = m.group(1), int(m.group(2)), int(m.group(3) or 0), m.group(4)
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    return datetime.combine(date.fromisoformat(day), time(hour, minute), tzinfo=TZ)


# ---- edits (each returns new rows) ------------------------------------------------------------

def _find(rows: list[dict], row_id: str) -> int:
    for i, row in enumerate(rows):
        if row["id"] == row_id:
            return i
    raise ValueError(f"no row {row_id!r} (rows: {', '.join(r['id'] for r in rows)})")


def _replace(rows: list[dict], i: int, row: dict) -> list[dict]:
    return [*rows[:i], row, *rows[i + 1:]]


def drop(rows: list[dict], target: str, channels: Iterable[str] | None = None) -> list[dict]:
    """'2' drops row 2 everywhere; '2:me_x' drops it from one channel."""
    row_id, _, key = target.partition(":")
    i = _find(rows, row_id)
    row = rows[i]
    if not key:
        return _replace(rows, i, {**row, "dropped": True})
    if channels is not None and key not in channels:
        raise ValueError(f"row {row_id} does not post to {key!r} (channels: {', '.join(channels)})")
    return _replace(rows, i, {**row, "drop_channels": sorted({*row.get("drop_channels", []), key})})


def add(rows: list[dict], target: str, optional: Iterable[str]) -> list[dict]:
    """'1:partner_linkedin' puts one of the lane's optional channels on row 1 only."""
    row_id, _, key = target.partition(":")
    optional = list(optional)
    if not key:
        raise ValueError(f"--add needs a row and a channel, like 1:{optional[0] if optional else 'KEY'}")
    if key not in optional:
        offered = ", ".join(optional) or "none"
        raise ValueError(f"this lane cannot add {key!r} (optional channels: {offered})")
    i = _find(rows, row_id)
    row = rows[i]
    return _replace(rows, i, {**row, "add_channels": sorted({*row.get("add_channels", []), key})})


def restore(rows: list[dict], row_id: str) -> list[dict]:
    i = _find(rows, row_id)
    row = {k: v for k, v in rows[i].items() if k not in ("dropped", "drop_channels")}
    return _replace(rows, i, row)


def pin(rows: list[dict], row_id: str, when: datetime) -> list[dict]:
    i = _find(rows, row_id)
    return _replace(rows, i, {**rows[i], "pinned_at": when.astimezone(TZ).isoformat()})


# ---- assignment ----------------------------------------------------------------------------------

def platform_of(key: str, platforms: dict[str, str] | None = None) -> str:
    """The platform behind a channel key: from channels.json when given, else its suffix."""
    return (platforms or {}).get(key) or SUFFIX_PLATFORM.get(key.rsplit("_", 1)[-1], key)


def _channels_for(row: dict, when: datetime | None, lane: str, lane_channels: list[str],
                  li_days: set[date], other_nine: set[date] | None,
                  platforms: dict[str, str] | None) -> tuple[list[str], dict]:
    chosen, skipped = [], {}
    added = [k for k in row.get("add_channels", []) if k not in lane_channels]
    for key in [*lane_channels, *added]:
        limit = MAX_SECONDS.get(platform_of(key, platforms))
        li_block = li_reason(when, lane, li_days, other_nine) if key == LI_KEY else None
        if key in row.get("drop_channels", []):
            skipped[key] = "dropped"
        elif limit and float(row.get("seconds") or 0) > limit:
            skipped[key] = f"over {limit} s"
        elif li_block:
            skipped[key] = li_block
        else:
            chosen.append(key)
    return chosen, skipped


def li_reason(when: datetime | None, lane: str, li_days: set[date], other_nine: set[date] | None) -> str | None:
    """Why Tony LI skips this slot, or None when it may post."""
    if when is None or when.timetz().replace(tzinfo=None) != LI_SLOT:
        return "Tony LI only takes the 9:00 Short"
    day = when.date()
    if day in li_days:
        return "Tony LI already has its post that day"
    if li_owner(day) != lane and (other_nine is None or day in other_nine):
        return "the other lane's Tony LI day"
    return None


def assign(rows: list[dict], *, lane: str, lane_channels: list[str], now: datetime,
           taken: set[datetime] | None = None, li_days: set[date] | None = None,
           other_nine: set[date] | None = None, start: date | None = None,
           urgent: bool = False, platforms: dict[str, str] | None = None,
           stagger: dict | None = None, busy: set[tuple[str, datetime]] | None = None,
           accounts: dict[str, str] | None = None) -> list[dict]:
    """New rows with "at" (ISO anchor, or "go"), "channels" and each channel's own "times"
    filled, plus "skipped" reasons.
    other_nine: dates the other lane has a 9:00 Short (None: assume every date, no borrowing).
    stagger: the lane's per-channel times by slot (channels.json); None posts every channel
    at the slot.
    busy: (channel, minute) pairs other jobs hold; a slot that would put a channel on one is
    skipped, and a pin that would is refused.
    accounts: channel key to Blotato account id, so two channels on one login (Tony LI and
    the HM page) never share a minute."""
    taken = set(taken or ())
    li_days = set(li_days or ())
    busy = set(busy or ()) | {m for r in rows if r.get("status") in SENT for m in row_minutes(r)}
    lead = now + MIN_LEAD
    earliest = lead
    if start is not None:
        earliest = max(earliest, datetime.combine(start, time(0), tzinfo=TZ))
    for row in rows:
        if row.get("pinned_at") and row.get("status") not in SENT and not row.get("dropped") \
                and datetime.fromisoformat(row["pinned_at"]) < now + MIN_LEAD:
            raise ValueError(f"row {row['id']} is pinned to {row['pinned_at']}, which is past or under "
                             f"{int(MIN_LEAD.total_seconds() // 60)} minutes away: pin a later time")
    fixed = {r["id"]: datetime.fromisoformat(r.get("pinned_at") or r["at"]) for r in rows
             if not r.get("dropped") and r["kind"] == "short"
             and (r.get("status") in SENT or r.get("pinned_at"))}
    taken |= set(fixed.values())

    def keys_at(row: dict, when: datetime) -> list[str]:
        """The channels the row would post to at that time, for collision checks."""
        if row["kind"] == "linkedin_full":
            return [k for k in [LI_KEY] if k not in row.get("drop_channels", [])]
        return _channels_for(row, when, lane, lane_channels, li_days, other_nine, platforms)[0]

    def next_slot(row: dict, reserved: set) -> datetime | None:
        for slot in slot_times(earliest, urgent):
            if slot < earliest or slot in taken:
                continue
            if not clashes(channel_times(slot, keys_at(row, slot), stagger, lead), busy | reserved, accounts):
                return slot
        return None

    full_li: dict[str, str | None] = {}    # the full LinkedIn video is its day's one Tony LI post
    full_when: dict[str, datetime | None] = {}
    for row in rows:
        if row["kind"] == "linkedin_full" and not row.get("dropped") and row.get("status") not in SENT:
            when = datetime.fromisoformat(row["pinned_at"]) if row.get("pinned_at") \
                else full_li_anchor(now, stagger, li_days)
            full_when[row["id"]] = when
            day = (when or now).astimezone(TZ).date()
            full_li[row["id"]] = ("Tony LI already has its post that day: pin it to another day "
                                  f"with --at {row['id']}=YYYY-MM-DDTHH:MM") if day in li_days else None
            li_days.add(day)
    reserved: set[tuple[str, datetime]] = set()      # pinned rows keep their minutes
    for row in rows:
        if row.get("pinned_at") and row.get("status") not in SENT and not row.get("dropped") \
                and row["kind"] in ("short", "linkedin_full"):
            pinned = datetime.fromisoformat(row["pinned_at"])
            planned = channel_times(pinned, keys_at(row, pinned), stagger, lead)
            hit = clashes(planned, busy, accounts)
            if hit:
                raise ValueError(f"row {row['id']} pinned to {when_label(row['pinned_at'])} puts {', '.join(hit)} "
                                 "on a minute another post already has: pin another time")
            reserved |= {(k, minute(v)) for k, v in planned.items()}
    out = []
    for row in rows:
        base = {k: v for k, v in row.items() if k not in ("at", "skipped", "times")} \
            if row.get("status") not in SENT else dict(row)
        if row.get("dropped"):
            out.append({k: v for k, v in base.items() if k != "channels"})
            continue
        if row.get("status") in SENT:
            out.append(base)
            continue
        if row["kind"] == "blog":                     # the blog goes first at Go, no Blotato channel
            out.append({**base, "at": "go", "channels": [], "skipped": {}})
            continue
        if row["kind"] == "linkedin_full":
            when = full_when.get(row["id"])
            reason = full_li.get(row["id"]) or ("dropped" if LI_KEY in row.get("drop_channels", []) else None)
            channels = [] if reason else [LI_KEY]
            timed = {"times": channel_times(when, channels, stagger, lead)} if when else {}
            busy |= {(k, minute(v)) for k, v in timed.get("times", {}).items()}
            out.append({**base, "at": when.isoformat() if when else "go", "channels": channels,
                        "skipped": {LI_KEY: reason} if reason else {}, **timed})
            continue
        when = fixed.get(row["id"])
        if when is None:
            when = next_slot(row, reserved)
            if when is None:
                raise ValueError(f"no free slot in the next {HORIZON_DAYS} days for row {row['id']}")
            taken.add(when)
        channels, skipped = _channels_for(row, when, lane, lane_channels, li_days, other_nine, platforms)
        if LI_KEY in channels:
            li_days.add(when.astimezone(TZ).date())
        times = channel_times(when, channels, stagger, lead)
        busy |= {(k, minute(v)) for k, v in times.items()}
        out.append({**base, "at": when.isoformat(), "channels": channels, "skipped": skipped, "times": times})
    return out
