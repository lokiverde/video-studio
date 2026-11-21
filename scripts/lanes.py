"""Lanes: which brand a job posts under, the channels that lane posts to, and the footer its
captions end with. Tech (TechTony) never carries the DRE line; real estate (Example Realty) and
training (Example Realty Training, training videos) always do. Channels and ids
live in assets/publish/channels.json. A signer (Tony by default, or Partner) decides whose
license line a DRE lane carries and which personal LinkedIn the job may use.
Spec: docs/briefs/2026-10-29-auto-poster.md, decisions 4, 6, 9 and 12, and its training lane
section (2026-11-12)."""
from __future__ import annotations

import json
from pathlib import Path

import common
import publish_store

CHANNELS_FILE = common.ROOT / "assets" / "publish" / "channels.json"
LANES = ("tech", "realestate", "training", "none")
DEFAULT_SIGNER = "tony"


def spec() -> dict:
    return json.loads(CHANNELS_FILE.read_text())


def lane_channels(lane: str) -> list[str]:
    lanes = spec()["lanes"]
    if lane not in lanes:
        raise ValueError(f"lane {lane!r} posts nowhere (lanes: {', '.join(lanes)})")
    return list(lanes[lane]["channels"])


def _lane_spec(lane: str | None) -> dict:
    return spec()["lanes"].get(lane or "", {})


def optional_channels(lane: str) -> list[str]:
    """Channels a lane posts to only on a row Tony adds them to (--add ROW:KEY)."""
    return list(_lane_spec(lane).get("optional") or [])


def carries_dre(lane: str | None) -> bool:
    """Whether every caption in the lane must carry the DRE line (an unknown lane does)."""
    return bool(_lane_spec(lane).get("dre", True))


def full_linkedin(lane: str) -> bool:
    """Whether the lane posts the full 9:16 video to Tony LI (row L)."""
    return bool(_lane_spec(lane).get("full_linkedin", True))


def scoreboard_name(lane: str) -> str:
    """The channel name the 90-day scoreboard logs the lane's Shorts under."""
    return _lane_spec(lane).get("scoreboard") or "ExampleRealty"


def accounts() -> dict[str, str]:
    """Channel key to Blotato account id. Two channels on one login (Tony LI and the HM page)
    share an id, which is what the planner's shared-minute check compares."""
    return {key: str(ch["accountId"]) for key, ch in spec()["channels"].items()}


def stagger(lane: str) -> dict:
    """The lane's per-channel clock times inside each slot (empty: every channel at the slot)."""
    return dict(spec()["lanes"].get(lane, {}).get("stagger") or {})


def channel(key: str) -> dict:
    channels = spec()["channels"]
    if key not in channels:
        raise ValueError(f"no channel {key!r} in {CHANNELS_FILE.name}")
    return {"key": key, **channels[key]}


def labels(keys) -> str:
    """'Tony TikTok, Tony X' for a list of channel keys."""
    return ", ".join(channel(k)["label"] for k in keys)


def default_lane(job: dict) -> str | None:
    """The lane the thumbnail mark implies, or None when the job has no known mark."""
    mark = str((job.get("thumbnail") or {}).get("mark") or "").strip().upper()
    return spec()["marks"].get(mark)


def _job_json(jdir: Path) -> dict:
    for name in ("job.json", "scenes.json"):
        try:
            return json.loads((Path(jdir) / name).read_text())
        except (OSError, ValueError):
            continue
    return {}


def job_lane(jdir: Path, job: dict | None = None) -> str | None:
    """The sidecar's lane when Tony set one, else the thumbnail mark's."""
    chosen = publish_store.load(jdir).get("lane")
    if chosen:
        return chosen
    return default_lane(job if job is not None else _job_json(jdir))


def signers() -> list[str]:
    """Every signer key in channels.json (tony, partner)."""
    return [k for k in spec().get("signers", {}) if not k.startswith("_")]


def _signer_spec(signer: str | None) -> dict:
    key = signer or DEFAULT_SIGNER
    table = spec().get("signers", {})
    if key.startswith("_") or key not in table:
        raise ValueError(f"no signer {key!r} in {CHANNELS_FILE.name} (signers: {', '.join(signers())})")
    return table[key]


def signer_label(signer: str | None) -> str:
    return _signer_spec(signer).get("label") or (signer or DEFAULT_SIGNER)


def signer_footer(signer: str | None, cfg: dict) -> str:
    """The signer's license line: config.env's footer_key, else the default in channels.json."""
    sig = _signer_spec(signer)
    return cfg.get(sig["footer_key"]) or sig.get("footer_default") or ""


def signer_dre(signer: str | None) -> str | None:
    """The signer's own license number, which every DRE caption on their job must carry."""
    return _signer_spec(signer).get("dre")


def signer_linkedin(signer: str | None) -> str | None:
    """The signer's own LinkedIn channel, put on Short 1 of their job (None for Tony, whose LI
    the lanes already post to)."""
    return _signer_spec(signer).get("linkedin")


def signer_never(signer: str | None) -> list[str]:
    """Channels a job with this signer never posts to (Partner: Tony LI)."""
    return list(_signer_spec(signer).get("never") or [])


def signer_voice_never(signer: str | None) -> list[str]:
    """TTS voices Go refuses on this signer's job (Partner: Tony's cloned voice)."""
    return list(_signer_spec(signer).get("voice_never") or [])


def signer_channels(lane: str, signer: str | None) -> list[str]:
    """The lane's channels for a job with this signer: Tony LI comes off Partner's."""
    never = set(signer_never(signer))
    return [k for k in lane_channels(lane) if k not in never]


def job_signer(jdir: Path, job: dict | None = None) -> str:
    """The sidecar's signer when Tony set one with --signer, else job.json's, else Tony."""
    chosen = publish_store.load(jdir).get("signer") \
        or (job if job is not None else _job_json(jdir)).get("signer") or DEFAULT_SIGNER
    _signer_spec(chosen)
    return chosen


def footer_for(lane: str | None, cfg: dict, job: dict | None = None, signer: str | None = None) -> str:
    """A footer authored in the job wins; then the lane's footer from config; tech falls back
    to the TechTony tagline and everything else to the signer's license line (YOUTUBE_FOOTER
    for Tony, PARTNER_FOOTER for Partner). A DRE lane with its own footer line (training)
    puts the license line on the line after it. signer: over job.json's "signer"."""
    authored = ((job or {}).get("youtube") or {}).get("footer")
    if authored is None:
        lane_spec = spec()["lanes"].get(lane or "", spec()["lanes"]["realestate"])
        dre = signer_footer(signer or (job or {}).get("signer"), cfg)
        if lane_spec["footer_key"] == "YOUTUBE_FOOTER":
            authored = dre or lane_spec["footer_default"]
        else:
            authored = cfg.get(lane_spec["footer_key"]) or lane_spec["footer_default"]
            if lane_spec.get("dre") and dre and dre not in authored:
                authored = f"{authored}\n{dre}" if authored else dre
    return authored.replace("\\n", "\n")


def ai_footage(jdir: Path) -> bool:
    """Realistic AI footage: a realistic-footage folder, or any clip scene in scenes.json
    (the same test publish_kit.ai_disclosure uses for the YouTube description)."""
    jdir = Path(jdir)
    if (jdir / "rf").is_dir():
        return True
    try:
        scenes = json.loads((jdir / "scenes.json").read_text()).get("scenes") or []
    except (OSError, ValueError):
        return False
    return any(scene.get("clip") for scene in scenes)
