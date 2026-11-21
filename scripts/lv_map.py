"""Animated location map for the listing video: wide coastline, zoom to the property,
pin drop, and distance tags to the places buyers care about.

Drawn from cached OpenStreetMap vectors (assets/cities/<slug>/cache/osm.json) with
OpenCV anti-aliased polylines, so it is crisp at every zoom level and costs nothing
per render. ODbL requires attribution; it is printed small in the corner.

Distances are straight-line ("as the crow flies") and rounded UP to the next tenth of
a mile so the video never promises something closer than it is.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

import common
import lv_cards

CITIES_DIR = common.ROOT / "assets" / "cities"
M_PER_DEG_LAT = 110_540.0
M_PER_MILE = 1609.34

# Road classes: (colour key, width in px at close zoom, min zoom width in m to draw)
ROAD_STYLE = {
    "motorway": ("major", 5), "trunk": ("major", 5), "primary": ("major", 4),
    "secondary": ("mid", 3), "tertiary": ("mid", 2.5), "unclassified": ("minor", 1.5),
    "residential": ("minor", 1.5), "pedestrian": ("walk", 2), "cycleway": ("walk", 1.5),
}
PALETTE = {  # RGB
    "ocean": (6, 44, 72), "land": (4, 22, 38), "minor": (28, 58, 86), "mid": (48, 88, 122),
    "major": (132, 170, 200), "walk": (0, 120, 170), "beach": (58, 62, 52), "park": (12, 48, 40),
    "coast": (41, 168, 214), "pier": (230, 240, 248),
}


def load_city(slug: str) -> dict:
    path = CITIES_DIR / slug / "city.json"
    if not path.exists():
        raise RuntimeError(f"no city library {path}")
    return {**json.loads(path.read_text()), "dir": str(path.parent)}


def media_file(city: dict, rel: str) -> Path:
    """A city clip or still: the local copy in media/ if present, else the Drive library
    (`library` in city.json, Tony's Google Drive), so a fresh machine needs no re-upload."""
    local = Path(city["dir"]) / rel
    if local.exists() or not city.get("library"):
        return local
    remote = Path(city["library"]) / Path(rel).relative_to("media")
    if not remote.exists():
        raise RuntimeError(f"city media missing: {local} and {remote}")
    return remote


def geocode(address: str, city: str | None, zip_code: str | None) -> tuple[float, float] | None:
    """Nominatim (OpenStreetMap) lookup of the listing. One request, polite user agent."""
    import re
    import urllib.parse
    # Nominatim finds no match with a unit on the end ("#E", "Unit 4", "Apt 2"): drop it.
    street = re.sub(r"\s*(#|\bunit\b|\bapt\.?\b|\bsuite\b|\bste\.?\b)\s*\w+\s*$", "", address, flags=re.I)
    query = ", ".join(x for x in (street, city, "CA", zip_code) if x)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
    try:
        hits = json.loads(common.http_get(url, timeout=30))
    except (RuntimeError, ValueError):
        return None
    return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None


def haversine_m(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def miles_up(meters: float) -> float:
    return max(0.1, math.ceil(meters / M_PER_MILE * 10 - 1e-9) / 10)


def load_osm(city: dict) -> list[dict]:
    path = Path(city["dir"]) / city["map"]["osm"]
    if not path.exists():
        raise RuntimeError(f"map data missing: {path} (fetch it with Overpass, see docs/listing-video.md)")
    return json.loads(path.read_text())["ways"]


def nearest(home, ways, pred) -> tuple[float, tuple] | None:
    """(metres, (lat, lon)) of the closest vertex of any matching way."""
    best = None
    for w in ways:
        if pred(w["tags"]):
            for pt in w["pts"]:
                d = haversine_m(home, pt)
                if best is None or d < best[0]:
                    best = (d, (pt[0], pt[1]))
    return best


def nearest_m(home, ways, pred) -> float | None:
    hit = nearest(home, ways, pred)
    return hit[0] if hit else None


def distance_tags(city: dict, home: tuple, ways: list[dict]) -> list[dict]:
    """[{label, miles, at, point}] from city.json distance_tags. `at` is set for named places
    (shown as pins on the overview map); `point` is where the distance was measured to, for
    every tag (the map tour flies there)."""
    pois = {p["name"]: p for p in city["pois"]}
    tags = []
    for spec in city.get("distance_tags", []):
        at, hit = None, None
        if spec["kind"] == "coastline":
            hit = nearest(home, ways, lambda t: t.get("natural") in ("coastline", "beach"))
        elif spec["kind"] == "road":
            hit = nearest(home, ways, lambda t, n=spec["name"]: t.get("name") == n)
        elif spec["kind"] == "road_ref":
            hit = nearest(home, ways, lambda t, r=spec["ref"]: r in (t.get("ref") or "").split(";")
                          and t.get("highway") == "motorway")
        elif spec["kind"] == "poi" and spec["name"] in pois:
            poi = pois[spec["name"]]
            at = (poi["lat"], poi["lon"])
            hit = (haversine_m(home, at), at)
        if hit is not None:
            tags.append({"label": spec["label"], "miles": miles_up(hit[0]), "at": at, "point": hit[1],
                         "overview": spec.get("overview", at is not None)})
    return tags


@dataclass(frozen=True)
class View:
    cx: float  # metres east of origin
    cy: float  # metres south of origin
    width_m: float


class MapScene:
    """Projected geometry around one home. frame(p, size) draws progress p in 0..1."""

    def __init__(self, city: dict, home: tuple, label: str, brand: dict):
        self.city, self.home, self.label, self.brand = city, home, label, brand
        self.lat0, self.lon0 = home
        self.kx = M_PER_DEG_LAT * math.cos(math.radians(self.lat0))
        ways = load_osm(city)
        self.tags = distance_tags(city, home, ways)
        self.layers = self._project(ways)
        self.ocean = self._ocean([w for w in ways if w["tags"].get("natural") == "coastline"])

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (self.lat0 - lat) * M_PER_DEG_LAT

    def _project(self, ways):
        layers = {k: [] for k in ("park", "beach", "minor", "walk", "mid", "major", "pier")}
        for w in ways:
            t = w["tags"]
            pts = np.array([self.xy(*p) for p in w["pts"]], dtype=np.float64)
            if t.get("leisure") in ("park", "marina"):
                layers["park"].append(pts)
            elif t.get("natural") == "beach":
                layers["beach"].append(pts)
            elif t.get("man_made") == "pier":
                layers["pier"].append(pts)
            elif t.get("highway") in ROAD_STYLE:
                layers[ROAD_STYLE[t["highway"]][0]].append(pts)
        return layers

    def _ocean(self, coast_ways) -> np.ndarray | None:
        """Chain the coastline pieces and close the polygon far out to sea (west)."""
        pieces = [[tuple(p) for p in w["pts"]] for w in coast_ways]
        if not pieces:
            return None
        chains = []
        while pieces:
            chain = pieces.pop(0)
            grown = True
            while grown:
                grown = False
                for i, pc in enumerate(pieces):
                    if pc[0] == chain[-1]:
                        chain += pc[1:]
                    elif pc[-1] == chain[0]:
                        chain = pc[:-1] + chain
                    else:
                        continue
                    pieces.pop(i)
                    grown = True
                    break
            chains.append(chain)
        main = max(chains, key=len)
        pts = [self.xy(*p) for p in main]
        # OSM coastline keeps land on the left: walk it, then swing out west to close.
        far = min(p[0] for p in pts) - 60_000
        ring = pts + [(far, pts[-1][1]), (far, pts[0][1])]
        return np.array(ring, dtype=np.float64)

    # ---------- camera ----------

    def views(self, size) -> tuple[View, View]:
        w, h = size
        aspect = h / w
        wide = View(0, 0, self.city["map"]["wide_width_m"] * (0.62 if aspect > 1 else 1.0))
        pts = [(0.0, 0.0)] + [self.xy(*t["at"]) for t in self.overview_tags()]
        return wide, self.fit(pts, size, self.city["map"]["close_width_m"])

    def overview_tags(self) -> list[dict]:
        return [t for t in self.tags if t["at"] and t.get("overview", True)]

    def fit(self, pts, size, min_width: float) -> View:
        """Smallest view holding every point with room for labels. Portrait keeps content in
        the band a phone shows clearly (above Instagram's caption area), centred at 40%."""
        w, h = size
        aspect = h / w
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        span_w = (max(xs) - min(xs)) * 1.5 + 600
        span_h = (max(ys) - min(ys)) * 1.2 + 600
        usable, centre = (0.60, 0.40) if aspect > 1 else (0.82, 0.5)
        width = max(span_w, span_h / (aspect * usable), min_width)
        cy = (max(ys) + min(ys)) / 2 + (0.5 - centre) * width * aspect
        return View((max(xs) + min(xs)) / 2, cy, width)

    @staticmethod
    def blend(a: View, b: View, q: float) -> View:
        """Zoom in log space so the move feels like a constant-speed descent."""
        width = math.exp(math.log(a.width_m) + (math.log(b.width_m) - math.log(a.width_m)) * q)
        span = a.width_m - b.width_m
        k = q if abs(span) < 1e-6 else (a.width_m - width) / span  # works zooming in or out
        return View(a.cx + (b.cx - a.cx) * k, a.cy + (b.cy - a.cy) * k, width)

    # ---------- drawing ----------

    def _to_px(self, pts: np.ndarray, view: View, size) -> np.ndarray:
        w, h = size
        s = w / view.width_m
        out = (pts - (view.cx, view.cy)) * s + (w / 2, h / 2)
        return np.round(out * 4).astype(np.int32)  # shift=2: quarter-pixel precision

    def draw_base(self, view: View, size, coast_reveal: float = 1.0) -> np.ndarray:
        w, h = size
        img = np.empty((h, w, 3), np.uint8)
        img[:] = PALETTE["land"]
        if self.ocean is not None:
            cv2.fillPoly(img, [self._to_px(self.ocean, view, size)], PALETTE["ocean"], cv2.LINE_AA, 2)
        s = w / view.width_m
        for key in ("park", "beach"):
            polys = [self._to_px(p, view, size) for p in self.layers[key] if len(p) > 2]
            if polys:
                cv2.fillPoly(img, polys, PALETTE[key], cv2.LINE_AA, 2)
        widths = {"minor": 1.4, "walk": 1.6, "mid": 2.4, "major": 3.6, "pier": 3.0}
        zoom_k = min(1.6, max(0.55, (2500 / view.width_m) ** 0.35))
        for key in ("minor", "walk", "mid", "major", "pier"):
            if key == "minor" and view.width_m > 9000:
                continue  # at the widest shot residential streets are just noise
            lines = [self._to_px(p, view, size) for p in self.layers[key]]
            if lines:
                cv2.polylines(img, lines, False, PALETTE[key], max(1, round(widths[key] * zoom_k)), cv2.LINE_AA, 2)
        if self.ocean is not None and coast_reveal > 0:
            coast = self._to_px(self.ocean[:-2], view, size)
            n = max(2, int(len(coast) * coast_reveal))
            glow = np.zeros_like(img)
            cv2.polylines(glow, [coast[:n]], False, PALETTE["coast"], 10, cv2.LINE_AA, 2)
            glow = cv2.GaussianBlur(glow, (0, 0), 9)
            img = cv2.add(img, (glow * 0.8).astype(np.uint8))
            cv2.polylines(img, [coast[:n]], False, PALETTE["coast"], 3, cv2.LINE_AA, 2)
        del s
        return img

    def frame(self, p: float, size) -> np.ndarray:
        """p 0..1 over the whole map shot."""
        wide, close = self.views(size)
        q = smoothstep(0.12, 0.72, p)
        view = self.blend(wide, close, q)
        img = self.draw_base(view, size, coast_reveal=min(1.0, 0.15 + p / 0.35))
        pil = Image.fromarray(img).convert("RGBA")
        self._draw_pins(pil, view, size, p)
        return np.asarray(pil.convert("RGB"))

    def _px(self, lat, lon, view, size):
        w, h = size
        x, y = self.xy(lat, lon)
        s = w / view.width_m
        return (x - view.cx) * s + w / 2, (y - view.cy) * s + h / 2

    def _draw_pins(self, pil: Image.Image, view: View, size, p: float) -> None:
        w, h = size
        c = self.brand["colors"]
        d = ImageDraw.Draw(pil, "RGBA")
        small = lv_cards.font(self.brand, "semibold", 30 if w > h else 34)
        # POI dots and tags
        for k, tag in enumerate(self.overview_tags()):
            a = smoothstep(0.66 + 0.06 * k, 0.74 + 0.06 * k, p)
            if a <= 0:
                continue
            x, y = self._px(*tag["at"], view, size)
            r = 9
            d.ellipse([x - r, y - r, x + r, y + r], fill=lv_cards.rgba(c["white"], a), outline=lv_cards.rgba(c["cyan"], a), width=4)
            text = f"{tag['label']}  {tag['miles']:g} mi"
            tw = d.textlength(text, font=small)
            bx = x + 22 if x + 22 + tw + 30 < w else x - 22 - tw - 30
            d.rounded_rectangle([bx, y - 26, bx + tw + 30, y + 26], radius=26, fill=lv_cards.rgba(c["navy"], 0.88 * a))
            d.text((bx + 15, y - 19), text, font=small, fill=lv_cards.rgba(c["white"], a))
        # Home pin: drops in with a small overshoot, then a ripple ring
        drop = smoothstep(0.55, 0.66, p)
        if drop > 0:
            x, y = self._px(self.lat0, self.lon0, view, size)
            bounce = 1 + 0.25 * math.sin(math.pi * min(1.0, drop * 1.3)) * (1 - drop)
            y_off = (1 - drop) * -120
            ring = (p - 0.62) / 0.3
            if 0 < ring < 1:
                rr = 20 + 90 * ring
                d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=lv_cards.rgba(c["cyan"], 1 - ring), width=5)
            r = 22 * bounce
            d.ellipse([x - r, y + y_off - r, x + r, y + y_off + r], fill=lv_cards.rgba(c["cyan"]), outline=lv_cards.rgba(c["white"]), width=6)
            if drop >= 1:
                label = self.label
                f = lv_cards.font(self.brand, "bold", 34 if w > h else 38)
                tw = d.textlength(label, font=f)
                a = smoothstep(0.64, 0.72, p)
                bx = x - tw / 2 - 18
                d.rounded_rectangle([bx, y + 36, bx + tw + 36, y + 94], radius=12, fill=lv_cards.rgba(c["white"], a))
                d.text((bx + 18, y + 44), label, font=f, fill=lv_cards.rgba(c["navy"], a))
        # Attribution (ODbL)
        f = lv_cards.font(self.brand, "regular", 18)
        text = self.city["map"]["attribution"]
        tw = d.textlength(text, font=f)
        d.text((w - tw - 20, h - 34 if w > h else h * 0.785), text, font=f, fill=(255, 255, 255, 110))


def smoothstep(a: float, b: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


class MapTour:
    """After the pin drop: the camera flies from the home to each nearby place in turn,
    drawing a dashed straight line (the distance quoted is straight-line too) and
    pulsing a marker there. Used when a city has no footage of its own."""

    def __init__(self, scene: MapScene, stops: list[str], size):
        self.scene, self.size = scene, size
        by_label = {t["label"]: t for t in scene.tags}
        self.stops = [by_label[s] for s in stops if s in by_label]
        if not self.stops:
            raise RuntimeError("map tour has no stops that match distance_tags labels")
        _, self.start_view = scene.views(size)
        self.views = [scene.fit([(0.0, 0.0), scene.xy(*t["point"])], size, 1400) for t in self.stops]

    def frame(self, k: int, p: float) -> np.ndarray:
        """Stop k at progress p (0..1 over that stop's shot)."""
        sc, size = self.scene, self.size
        prev = self.start_view if k == 0 else self.views[k - 1]
        glide = smoothstep(0.0, 0.45, p)
        view = MapScene.blend(prev, self.views[k], glide) if prev.width_m != self.views[k].width_m else View(
            prev.cx + (self.views[k].cx - prev.cx) * glide, prev.cy + (self.views[k].cy - prev.cy) * glide, prev.width_m)
        img = sc.draw_base(view, size)
        tag = self.stops[k]
        hx, hy = sc._px(sc.lat0, sc.lon0, view, size)
        px, py = sc._px(*tag["point"], view, size)
        reveal = smoothstep(0.15, 0.6, p)
        ex, ey = hx + (px - hx) * reveal, hy + (py - hy) * reveal
        dash = np.hypot(ex - hx, ey - hy)
        n = max(1, int(dash / 26))
        for i in range(n):
            if i % 2 == 0:
                a0, a1 = i / n, min(1.0, (i + 1) / n)
                cv2.line(img, (int(hx + (ex - hx) * a0), int(hy + (ey - hy) * a0)),
                         (int(hx + (ex - hx) * a1), int(hy + (ey - hy) * a1)), (255, 255, 255), 4, cv2.LINE_AA)
        pil = Image.fromarray(img).convert("RGBA")
        d = ImageDraw.Draw(pil, "RGBA")
        c = sc.brand["colors"]
        # home pin
        d.ellipse([hx - 16, hy - 16, hx + 16, hy + 16], fill=lv_cards.rgba(c["cyan"]), outline=lv_cards.rgba(c["white"]), width=5)
        # destination marker pulses in once the line arrives
        arrive = smoothstep(0.5, 0.7, p)
        if arrive > 0:
            ring = (p - 0.55) / 0.4
            if 0 < ring < 1:
                rr = 16 + 70 * ring
                d.ellipse([px - rr, py - rr, px + rr, py + rr], outline=lv_cards.rgba(c["cyan"], 1 - ring), width=5)
            r = 14 * arrive
            d.ellipse([px - r, py - r, px + r, py + r], fill=lv_cards.rgba(c["white"]), outline=lv_cards.rgba(c["cyan"]), width=5)
        f = lv_cards.font(sc.brand, "regular", 18)
        text = sc.city["map"]["attribution"]
        w, h = size
        tw = d.textlength(text, font=f)
        d.text((w - tw - 20, h - 34 if w > h else h * 0.785), text, font=f, fill=(255, 255, 255, 110))
        return np.asarray(pil.convert("RGB"))
