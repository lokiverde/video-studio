"""MLS "Agent Full" PDF to the facts a listing video shows.

Reads the text layer with `pdftotext -layout` (poppler, installed on the Mac) and
pulls label: value pairs out of it. The layout is the CRMLS Matrix Agent Full
report. Anything the parser cannot find is left None rather than guessed, and
places where the report disagrees with itself (the square-footage field against
the number in the description) are listed under `conflicts` so Tony confirms them
before a render puts a wrong number on screen.
"""
import re
import subprocess
from pathlib import Path

# MLS sub-type codes and long names to the word a buyer uses.
PROPERTY_TYPES = {
    "TWNHS": "Townhome", "TOWNHOUSE": "Townhome",
    "CONDO": "Condo", "CONDOMINIUM": "Condo",
    "SFR": "Single Family Home", "SINGLE FAMILY RESIDENCE": "Single Family Home",
    "DPLX": "Duplex", "DUPLEX": "Duplex", "TRPLX": "Triplex", "TRIPLEX": "Triplex",
    "QUADRUPLEX": "Fourplex", "LOFT": "Loft", "MANUFACTURED": "Manufactured Home",
    "CABIN": "Cabin", "STCKCP": "Co-op", "STOCK COOPERATIVE": "Co-op",
}

LABEL_END = r"(?=\s{2,}|\n|$)"


def pdf_text(pdf_path: Path) -> str:
    try:
        out = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                             capture_output=True, text=True, check=True)
    except FileNotFoundError as err:
        raise RuntimeError("pdftotext not found (brew install poppler)") from err
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"pdftotext could not read {pdf_path}: {err.stderr.strip()}") from err
    return out.stdout


def field(text: str, label: str) -> str | None:
    """Value after `LABEL:` up to the next column gap or line end."""
    match = re.search(rf"(?<![A-Za-z.]){re.escape(label)}:[ \t]*(.*?){LABEL_END}", text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def money(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d.]", "", value)
    return round(float(digits)) if digits else None


def number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"[\d,]+", value)
    return int(match.group(0).replace(",", "")) if match else None


def baths(value: str | None) -> float | None:
    """`3/2,0,1,0` is beds / full, three-quarter, half, quarter. A three-quarter
    bath counts as full on a flyer, a half or quarter bath as half."""
    if not value or "/" not in value:
        return None
    parts = [int(p) for p in re.findall(r"\d+", value.split("/", 1)[1])]
    parts += [0] * (4 - len(parts))
    full, three_quarter, half, quarter = parts[:4]
    return full + three_quarter + 0.5 * (half + quarter)


def beds(value: str | None) -> int | None:
    if not value or "/" not in value:
        return None
    return number(value.split("/", 1)[0].strip())


def property_type(text: str) -> str | None:
    candidates = re.findall(r"PROP SUB TYPE:[ \t]*(.*?)" + LABEL_END, text)
    for raw in reversed(candidates):  # the long name comes second in the report
        key = raw.strip().upper()
        for code, name in PROPERTY_TYPES.items():
            if key.startswith(code):
                return name
    return candidates[0].strip() if candidates else None


def header(text: str) -> dict:
    """First line: `123 S Pacific Coast, Redondo Beach 90277   STATUS: Active   LIST PRICE: $1,000,000`."""
    first = next((line for line in text.splitlines() if "STATUS:" in line), "")
    match = re.match(r"\s*(.+?),\s*(.+?)\s+(\d{5})\s+STATUS:", first)
    if not match:
        return {"street": None, "city": None, "zip": None}
    return {"street": match.group(1).strip(), "city": match.group(2).strip(), "zip": match.group(3)}


def description(text: str) -> str:
    match = re.search(r"DESCRIPTION\s*\n(.*?)\n\s*\n", text, re.S)
    return " ".join(match.group(1).split()) if match else ""


def full_address(street: str | None, desc: str) -> str | None:
    """The report header truncates the street (`123 S Pacific Coast`). The remarks usually
    spell it out with the unit (`123 S Pacific Coast Hwy #E`), so prefer that when it
    starts the same way."""
    if not street:
        return None
    match = re.search(rf"{re.escape(street)}[^,.;]*", desc)
    return match.group(0).strip() if match else street


def sqft_in_description(desc: str) -> int | None:
    match = re.search(r"([\d,]{3,6})\s*(?:square feet|sq\.? ?ft)", desc, re.I)
    return number(match.group(1)) if match else None


def agents(text: str) -> list[dict]:
    found = []
    for role, lic in (("LA", "LA State License"), ("CoLA", "CoLA State License")):
        name = field(text, role)
        if not name:
            continue
        found.append({"role": role, "name": re.sub(r"^\(\w+\)\s*", "", name),
                      "license": field(text, lic)})
    return found


def price_change(text: str) -> tuple[int | None, int | None]:
    """(previous, current) from the report's `Recent: ... PRC CHG : $999,900->$950,000`."""
    match = re.search(r"PRC CHG\s*:\s*\$([\d,]+)\s*->\s*\$([\d,]+)", text)
    return (money(match.group(1)), money(match.group(2))) if match else (None, None)


def is_lease(text: str) -> bool:
    return bool(re.search(r"AGENT FULL:\s*Residential Lease|Residential Income Lease", text, re.I))


def parse(text: str) -> dict:
    """Every fact the video uses, plus `conflicts` for Tony to confirm."""
    head = header(text)
    desc = description(text)
    bed_bath = field(text, "BED / BATH")
    sqft = number(field(text, "SQFT(src)"))
    lease = is_lease(text)
    facts = {
        "address": full_address(head["street"], desc),
        "city": head["city"],
        "zip": head["zip"],
        "price": money(field(text, "LIST PRICE")),
        "original_price": money(field(text, "LIST $ ORIGINAL")),
        "previous_price": price_change(text)[0],
        "listing_type": "lease" if lease else "sale",
        "beds": beds(bed_bath),
        "baths": baths(bed_bath),
        "sqft": sqft,
        "year_built": number(field(text, "YEAR BUILT(src)")),
        "property_type": property_type(text),
        "garage": field(text, "GARAGE"),
        "listing_id": field(text, "LISTING ID"),
        "status": field(text, "STATUS"),
        "agents": agents(text),
        "description": desc,
    }
    return {**facts, "conflicts": conflicts(facts)}


def conflicts(facts: dict) -> list[str]:
    found = []
    described = sqft_in_description(facts["description"])
    if facts["sqft"] and described and described != facts["sqft"]:
        found.append(f"square feet: MLS field says {facts['sqft']:,}, description says {described:,}")
    for key in ("address", "city", "price", "beds", "baths", "property_type"):
        if facts.get(key) in (None, ""):
            found.append(f"{key} not found in the PDF, set it in listing.json")
    return found


def from_pdf(pdf_path: Path) -> dict:
    return parse(pdf_text(pdf_path))


def fmt_baths(value: float | None) -> str:
    if value is None:
        return "?"
    return str(int(value)) if value == int(value) else f"{value:g}"


def fmt_price(facts: dict) -> str:
    if not facts.get("price"):
        return ""
    text = f"${facts['price']:,}"
    return text + "/mo" if facts.get("listing_type") == "lease" else text


def stat_line(facts: dict) -> str:
    """`3 BD | 2.5 BA | 1,700 SF | Townhome`, skipping anything unknown."""
    parts = []
    if facts.get("beds") is not None:
        parts.append(f"{facts['beds']} BD")
    if facts.get("baths") is not None:
        parts.append(f"{fmt_baths(facts['baths'])} BA")
    if facts.get("sqft"):
        parts.append(f"{facts['sqft']:,} SF")
    if facts.get("property_type"):
        parts.append(facts["property_type"])
    return "  |  ".join(parts)


def price_reduced(facts: dict) -> bool:
    prev, now = facts.get("previous_price"), facts.get("price")
    return bool(prev and now and now < prev)
