"""The real-footage library: camera styles and camera behaviors, one Markdown file each
under assets/real-footage/ (format in its README). A shot's "style" names a file in
styles/, a clip's "technique" names a file in behaviors/. Spec:
docs/briefs/2026-10-24-realistic-footage.md, sections 6.4 and 6.5.
"""
import common

LIBRARY = common.ROOT / "assets" / "real-footage"
FOLDERS = {"style": "styles", "technique": "behaviors"}


def names(field):
    """Every name a shot's `field` ("style" or "technique") can take, sorted."""
    return sorted(p.stem for p in (LIBRARY / FOLDERS[field]).glob("*.md"))


def require(field, name, where=""):
    """Stop with the real names when `name` is not in the library."""
    known = names(field)
    if name not in known:
        common.die(f"{where}{field} '{name}' is not in assets/real-footage/{FOLDERS[field]}/ "
                   f"(have: {', '.join(known) or 'nothing, the folder is missing'})")


def require_names(style, technique, where=""):
    """Stop when a style or technique is named but the library does not have it."""
    if style:
        require("style", style, where)
    if technique:
        require("technique", technique, where)


def front_matter(field, name):
    """A library file's front matter as a dict, lists as Python lists (format in the
    library README: one key per line, [a, b] lists, quoted text that holds a colon)."""
    path = LIBRARY / FOLDERS[field] / f"{name}.md"
    parts = path.read_text().split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        common.die(f"{path} has no front matter between two --- lines (see assets/real-footage/README.md)")
    entry = {}
    for line in parts[1].strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            entry[key.strip()] = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        else:
            entry[key.strip()] = value.strip('"')
    return entry
