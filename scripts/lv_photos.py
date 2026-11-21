"""Listing photo folder to an ordered inventory, and validation of Claude's picks.

Photo Batch (../photo-batch) names every processed photo `<n> <room> <original>.jpg`
with n 0-8, so a plain sort already reads as a tour: exteriors first, then living,
dining, kitchen, halls, stairs, bedrooms, baths, other. Untagged photos sort into
"other" so nothing silently drops out of the inventory.
"""
import json
import re
from pathlib import Path

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
TAG = re.compile(r"^(\d)\s+([a-z ]+?)\s+(\S.*)$", re.I)

# Photo Batch tag -> the label shown on screen (photo_batch_gui.py ROOMS).
ROOM_LABELS = {
    0: "Exterior", 1: "Living Room", 2: "Dining", 3: "Kitchen", 4: "Hallway",
    5: "Stairs", 6: "Bedroom", 7: "Bathroom", 8: "",
}
OTHER = 8
CUTS = ("landscape", "portrait")

# Photographers name files by room ("Self - 20200 Example_Master Bath2.jpg"). When there is
# no Photo Batch prefix, read the room from the name: (pattern, tour code, on-screen label).
# Order matters, first match wins ("Master Bath" before "Bath", "Family room-Kitchen" is family).
KEYWORDS = [
    (r"front|exterior|curb|facade", 0, "Exterior"),
    (r"living", 1, "Living Room"), (r"family", 1, "Family Room"),
    (r"dining", 2, "Dining"), (r"kitchen", 3, "Kitchen"),
    (r"game|bonus|media|office|den\b", 4, "Bonus Room"), (r"gym", 4, "Home Gym"),
    (r"hall|entry|foyer", 4, "Entry"), (r"stair", 5, "Stairs"),
    (r"master bed|primary bed", 6, "Primary Suite"), (r"bed", 6, "Bedroom"),
    (r"master bath|primary bath", 7, "Primary Bath"), (r"bath", 7, "Bathroom"),
    (r"laundry", 8, "Laundry"), (r"garage", 8, "Garage"),
    (r"yard|patio|pool|garden|pond|deck", 8, "Backyard"),
]


def classify(name: str) -> tuple[int, str, str]:
    """(room code, room word, label) from a Photo Batch name, else from room words in the name."""
    match = TAG.match(Path(name).stem)
    if match:
        code = int(match.group(1))
        return code, match.group(2).strip().lower(), ROOM_LABELS.get(code, "")
    stem = Path(name).stem.lower()
    for pattern, code, label in KEYWORDS:
        if re.search(pattern, stem):
            return code, label.lower(), label
    return OTHER, "other", ""


def scan(folder: Path) -> list[dict]:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise RuntimeError(f"photo folder not found: {folder}")
    files = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in PHOTO_EXT and not p.name.startswith(".")]
    photos = []
    for path in files:
        code, room, label = classify(path.name)
        photos.append({"name": path.name, "path": str(path), "room_code": code, "room": room, "label": label})
    photos.sort(key=lambda p: (p["room_code"], p["name"]))
    return [{**p, "n": i + 1} for i, p in enumerate(photos)]


def by_name(photos: list[dict]) -> dict:
    return {p["name"]: p for p in photos}


def normalize_pick(pick) -> dict:
    return {"photo": pick} if isinstance(pick, str) else dict(pick)


def validate_picks(picks: dict, photos: list[dict]) -> list[str]:
    """Problems with picks.json, empty when it is renderable."""
    problems = []
    known = by_name(photos)
    for cut in CUTS:
        entries = picks.get(cut)
        if not isinstance(entries, list) or len(entries) < 3:
            problems.append(f"{cut}: needs a list of at least 3 photos")
            continue
        for i, raw in enumerate(entries):
            pick = normalize_pick(raw)
            if pick.get("photo") not in known:
                problems.append(f"{cut}[{i}]: unknown photo {pick.get('photo')!r}")
            focus = pick.get("focus")
            if focus is not None and not (isinstance(focus, (int, float)) and 0 <= focus <= 1):
                problems.append(f"{cut}[{i}]: focus must be a number 0 to 1")
            callout = pick.get("callout") or ""
            if len(callout) > 38:
                problems.append(f"{cut}[{i}]: callout over 38 characters: {callout!r}")
    return problems


def resolve(picks: dict, photos: list[dict], cut: str) -> list[dict]:
    """Picks for one cut with the source path and the on-screen label filled in.
    The first photo of each room gets its room label unless the pick sets `label`
    (an empty string suppresses it). The opening photo never carries a label, the
    facts card is on it."""
    known = by_name(photos)
    out, last_room = [], None
    for i, raw in enumerate(picks[cut]):
        pick = normalize_pick(raw)
        photo = known[pick["photo"]]
        room_label = photo.get("label", ROOM_LABELS.get(photo["room_code"], ""))
        auto = room_label if photo["room"] != last_room else ""
        label = pick.get("label", auto) if i > 0 else ""
        out.append({**pick, "path": photo["path"], "room": photo["room"], "label": label,
                    "callout": pick.get("callout", "") if i > 0 else ""})
        last_room = photo["room"]
    return out


def load_picks(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"{path.name} not written yet: pick the photos first")
    return json.loads(path.read_text())
