"""The "pop" listing video: location map -> city montage -> hero reveal -> beat-cut
parallax tour -> end card. Same interface as lv_render.Cut (size, duration,
frame_at, preview_times), so lv_render.encode renders it unchanged.

Shot list per cut (all lengths are whole beats of the bed, so every cut lands on
the music):
  map      zoom from the whole coast to the home, pin drop, distance tags
  montage  Tony's own city footage, one distance line per clip
  hero     best exterior, depth dolly, address/price/stats typed on
  tour     parallax photos, room labels, hard cuts; `transition: whip` between floors
  card     Your Team placard, or the MLS card with no contact info
"""
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

import lv_beats
import lv_cards
import lv_clips
import lv_depth
import lv_map
import lv_mls
import lv_render
import lv_type
from lv_type import Block, Line

WHIP = 0.30   # seconds, centred on the cut
FADE = 0.50
LANDSCAPE_MOVES = ("orbit_r", "dolly", "orbit_l", "rise")
PORTRAIT_MOVES = ("pan_r", "pan_l")
ABBREV = {"Pacific Coast Hwy": "PCH", "Boulevard": "Blvd", "Avenue": "Ave", "Street": "St"}


@dataclass
class Shot:
    kind: str
    start: float
    dur: float
    transition: str               # how this shot comes in: cut, whip, fade
    render: Callable              # (t_local, p) -> RGB uint8 array
    blocks: list = field(default_factory=list)
    scrim: bool = False           # darken the bottom for type legibility

    @property
    def end(self) -> float:
        return self.start + self.dur


def short_address(address: str) -> str:
    for long, short in ABBREV.items():
        address = address.replace(long, short)
    return address


def scrim(size, portrait: bool) -> np.ndarray:
    """Bottom darkening alpha (HxWx1), stronger behind where type sits."""
    w, h = size
    y = np.linspace(0, 1, h, dtype=np.float32)
    x = np.linspace(0, 1, w, dtype=np.float32)
    # Ramp to full strength by the top of the type block (about 40% down in portrait,
    # 45% in landscape), weighted to the left where the type sits.
    top, ramp = (0.28, 0.20) if portrait else (0.30, 0.25)
    t = np.clip((y - top) / ramp, 0, 1)
    a = t * t * (3 - 2 * t) * 0.70
    if portrait:  # ease off under Instagram's caption area, nothing to read there
        a *= np.clip((0.97 - y) / 0.2, 0.45, 1)
    fx = 1 - (0.55 if not portrait else 0.30) * x ** 1.3
    return (a[:, None] * fx[None, :])[:, :, None]


def apply_scrim(frame: np.ndarray, alpha: np.ndarray, color) -> np.ndarray:
    tint = np.array(color[:3], np.float32)
    return (frame.astype(np.float32) * (1 - alpha) + tint * alpha).astype(np.uint8)


class PopCut:
    def __init__(self, picks: list[dict], facts: dict, brand: dict, cut: str, bpm: float,
                 mls: bool, city: dict, home: tuple, montage: list[dict], work: Path):
        spec = brand["pop"][cut]
        self.size = tuple(brand["cuts"][cut]["size"])
        w, h = self.size
        self.portrait = h > w
        self.brand, self.facts, self.mls = brand, facts, mls
        self.beat = 60 / bpm
        self.scrim = scrim(self.size, self.portrait)
        # light navy wash under the logo so it reads over sky and foliage
        self.top_scrim = np.clip(1 - np.linspace(0, 1, h, dtype=np.float32) / (0.22 if self.portrait else 0.26), 0, 1)[:, None, None] ** 1.5 * 0.5
        self.navy = lv_cards.rgba(brand["colors"]["navy"])
        self.margin = 70 if self.portrait else 96
        self.text_bottom = int(h * 0.74) if self.portrait else h - 96
        self._cache: dict = {}
        shots: list[Shot] = []
        t = 0.0

        def add(kind, beats, transition, render, blocks=(), use_scrim=False, seconds=None):
            nonlocal t
            dur = seconds if seconds is not None else beats * self.beat
            shots.append(Shot(kind, round(t, 4), round(dur, 4), transition, render, list(blocks), use_scrim))
            t += dur

        # 1. map
        scene = lv_map.MapScene(city, home, short_address(facts.get("address") or ""), brand)
        self.tags = {tg["label"]: tg for tg in scene.tags}
        map_top = int(h * 0.09) if self.portrait else 84
        add("map", spec["map_beats"], "cut", lambda tl, p, s=scene: s.frame(p, self.size),
            [Block([Line("LOCATION", "semibold", 34, "white", 6), Line(city["label"], "bold", 84 if self.portrait else 78)],
                   0.25, spec["map_beats"] * self.beat - 0.05, x=self.margin, top=map_top, width=w)])

        # 2. city beat: Tony's footage when the city has it, otherwise a map tour
        if not montage and city.get("map_tour", {}).get(cut):
            tour_map = lv_map.MapTour(scene, city["map_tour"][cut], self.size)
            beats = spec.get("tour_beats", 3)
            for k, stop in enumerate(tour_map.stops):
                label = stop["label"].upper()
                add("maptour", beats, "cut", lambda tl, p, tm=tour_map, i=k: tm.frame(i, p), [
                    Block([Line(label, "semibold", 34 if len(label) < 22 else 28, "white", 6),
                           Line(f"{stop['miles']:g} mi", "bold", 110 if self.portrait else 104)],
                          0.35, beats * self.beat, x=self.margin, bottom=self.text_bottom, width=w)],
                    use_scrim=True)
        for k, clip in enumerate(montage):
            folder = lv_clips.prepare(lv_map.media_file(city, clip["file"]), clip["start"],
                                      spec["clip_beats"] * self.beat + WHIP, self.size, work / "clips")
            player = lv_clips.Clip(folder)
            tag = self.tags.get(clip.get("tag", ""))
            blocks = []
            if tag:
                blocks = [Block([Line(tag["label"].upper(), "semibold", 36, "white", 6),
                                 Line(f"{tag['miles']:g} mi", "bold", 110 if self.portrait else 104)],
                                0.05, spec["clip_beats"] * self.beat, x=self.margin, bottom=self.text_bottom, width=w)]
            add("clip", spec["clip_beats"], "whip" if k == 0 else "cut",
                lambda tl, p, pl=player: pl.frame(max(0.0, tl + WHIP / 2), p), blocks, use_scrim=bool(tag))

        # 3. hero exterior with the facts
        hero = picks[0]
        hero_dur = spec["open_beats"] * self.beat
        kicker = lv_cards.kicker_text(facts)
        price_fmt = "${:,}" + ("/mo" if facts.get("listing_type") == "lease" else "")
        reduced = lv_mls.price_reduced(facts)
        lift = (150 if self.portrait else 130) + (64 if reduced else 0)  # room for the struck old price
        add("hero", spec["open_beats"], "whip", self._photo_render(0, hero, "dolly"), [
            Block([Line(kicker, "semibold", 34, "white", 7),
                   Line(facts.get("address") or "", "bold", 84 if not self.portrait else 72),
                   Line(lv_cards.city_line(facts), "regular", 44, "soft", gap=26)],
                  0.2, hero_dur - 0.05, x=self.margin, bottom=self.text_bottom - lift, width=w),
            Block(([Line("${:,}".format(facts["previous_price"]), "regular", 44, "soft", strike=True, gap=4)]
                   if reduced else [])
                  + [Line(price_fmt, "bold", 80, count=facts.get("price") or 0),
                   Line(lv_mls.stat_line(facts), "semibold", 42, gap=0)],
                  0.2 + 0.45 * hero_dur, hero_dur - 0.05, x=self.margin, bottom=self.text_bottom, width=w),
        ], use_scrim=True)

        # 4. tour
        tour = picks[1:]
        fixed = sum(s.dur for s in shots) + spec["card_seconds"]
        free = [p for p in tour if not p.get("beats")]
        remaining = spec["target_seconds"] - fixed - sum(p["beats"] * self.beat for p in tour if p.get("beats"))
        per = max(2, min(6, round(remaining / self.beat / max(len(free), 1)))) if free else 4
        moves = PORTRAIT_MOVES if self.portrait else LANDSCAPE_MOVES
        for i, pick in enumerate(tour, start=1):
            beats = pick.get("beats") or per
            dur = beats * self.beat
            move = pick.get("move") or moves[(i - 1) % len(moves)]
            add("photo", beats, pick.get("transition", "cut"), self._photo_render(i, pick, move),
                self._label_blocks(pick, dur), use_scrim=bool(pick.get("label") or pick.get("callout")))

        # 5. end card
        card = (lv_cards.mls_card if mls else lv_cards.placard)(facts, brand, self.size)
        card_rgb = np.asarray(card.convert("RGB"))
        add("card", 0, "fade", lambda tl, p, c=card_rgb: c, seconds=spec["card_seconds"])

        self.shots = shots
        self.duration = t
        self.logo = None if mls else self._logo_sprite()

    # ---------- builders ----------

    def _photo_render(self, index: int, pick: dict, move: str):
        def render(tl, p, i=index, pk=pick, mv=move):
            return self._parallax(i, pk, mv).frame(p)
        return render

    def _parallax(self, i: int, pick: dict, move: str) -> lv_depth.Parallax:
        key = ("px", i)
        if key not in self._cache:
            # keep memory flat during an encode: only the neighbouring photos stay loaded
            self._cache = {k: v for k, v in self._cache.items() if abs(k[1] - i) <= 1}
            rgb = np.asarray(lv_render.load_photo(pick["path"]))
            focus = pick.get("focus", 0.38 if i == 0 else 0.5)
            self._cache[key] = lv_depth.Parallax(rgb, self.size, lv_depth.MOVES[move], focus)
        return self._cache[key]

    def _label_blocks(self, pick: dict, dur: float) -> list:
        label, callout = pick.get("label", ""), pick.get("callout", "")
        w = self.size[0]
        end = min(dur - 0.02, 3.2)
        if callout:
            lines = [Line(label.upper(), "semibold", 32, "white", 6)] if label else []
            lines.append(Line(callout, "bold", 70 if self.portrait else 66, gap=0))
        elif label:
            lines = [Line(label, "bold", 76 if self.portrait else 70, gap=0)]
        else:
            return []
        return [Block(lines, 0.08, end, x=self.margin, bottom=self.text_bottom, width=w)]

    def _logo_sprite(self):
        w, h = self.size
        mark = lv_cards.logo(self.brand, "logo_white", 300 if self.portrait else 250)
        arr = np.asarray(mark).astype(np.float32) / 255.0
        x = (w - mark.width) // 2 if self.portrait else w - mark.width - 64
        y = int(h * 0.08) if self.portrait else 54
        return arr[:, :, :3] * 255.0, arr[:, :, 3], x, y

    # ---------- frames ----------

    def shot_frame(self, k: int, t: float) -> np.ndarray:
        s = self.shots[k]
        tl = t - s.start
        p = min(1.0, max(0.0, (tl + 0.15) / (s.dur + 0.3)))
        frame = np.ascontiguousarray(s.render(tl, p), dtype=np.uint8).copy()
        if s.scrim:
            frame = apply_scrim(frame, self.scrim, self.navy)
        if s.kind == "hero" and self.logo is not None:
            frame = apply_scrim(frame, self.top_scrim, self.navy)
            rgb, alpha, x, y = self.logo
            lv_type.blend(frame, rgb, alpha, x, y, lv_render.envelope(tl, 0.3, s.dur - 0.1, 0.4))
        for block in s.blocks:
            lv_type.draw(frame, block, tl, self.brand)
        return frame

    def frame_at(self, t: float) -> np.ndarray:
        k = next((i for i, s in enumerate(self.shots) if t < s.end), len(self.shots) - 1)
        s = self.shots[k]
        out = None
        nxt = self.shots[k + 1] if k + 1 < len(self.shots) else None
        if nxt and nxt.transition != "cut":
            half = (WHIP if nxt.transition == "whip" else FADE) / 2
            if t > s.end - half:
                x = (t - (s.end - half)) / (2 * half)
                out = self._mix(self.shot_frame(k, t), self.shot_frame(k + 1, t), x, nxt.transition)
        if out is None and k > 0 and s.transition != "cut":
            half = (WHIP if s.transition == "whip" else FADE) / 2
            if t < s.start + half:
                x = 0.5 + (t - s.start) / (2 * half)
                out = self._mix(self.shot_frame(k - 1, t), self.shot_frame(k, t), x, s.transition)
        if out is None:
            out = self.shot_frame(k, t)
        level = min(1.0, t / 0.25, (self.duration - t) / 0.9)
        if level < 1:
            out = (out.astype(np.float32) * max(0.0, level)).astype(np.uint8)
        return out

    def _mix(self, a: np.ndarray, b: np.ndarray, x: float, kind: str) -> np.ndarray:
        x = min(1.0, max(0.0, x))
        if kind == "fade":
            return cv2.addWeighted(a, 1 - x, b, x, 0)
        e = 0.5 - 0.5 * math.cos(math.pi * x)  # ease in-out
        w = a.shape[1]
        off = int(round(e * w))
        out = np.empty_like(a)
        out[:, :w - off] = a[:, off:]
        out[:, w - off:] = b[:, :off]
        blur = int(90 * math.sin(math.pi * x)) | 1
        return cv2.blur(out, (blur, 1)) if blur > 1 else out

    def preview_times(self) -> list[float]:
        times = []
        for s in self.shots:
            if s.kind in ("map", "maptour"):
                times.append(s.start + s.dur * 0.85)
            elif s.kind == "hero":
                times.append(s.start + s.dur * 0.88)
            elif s.kind == "card":
                times.append(s.start + s.dur * 0.6)
            else:
                times.append(s.start + min(1.0, s.dur * 0.6))
        return times


def build(picks: list[dict], facts: dict, brand: dict, cut: str, bpm: float, mls: bool,
          city_slug: str, work: Path) -> PopCut:
    city = lv_map.load_city(city_slug)
    if facts.get("lat") is None:
        raise RuntimeError("listing.json has no lat/lon; run `lv.py geocode --job ...`")
    clips = {c["id"]: c for c in city["clips"]}
    montage = [clips[i] for i in city["montage"][cut]]
    return PopCut(picks, facts, brand, cut, bpm, mls, city, (facts["lat"], facts["lon"]), montage, work)
