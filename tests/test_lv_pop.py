import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lv_cards  # noqa: E402
import lv_depth  # noqa: E402
import lv_map  # noqa: E402
import lv_pop  # noqa: E402
import lv_type  # noqa: E402

BRAND = lv_cards.load_brand("examplerealty")


def test_miles_round_up_never_down():
    assert lv_map.miles_up(0.31 * lv_map.M_PER_MILE) == 0.4
    assert lv_map.miles_up(0.3 * lv_map.M_PER_MILE) == 0.3
    assert lv_map.miles_up(5) == 0.1


def test_haversine_known_distance():
    pier, home = (33.8397279, -118.392663), (33.8305425, -118.3849595)
    assert lv_map.haversine_m(home, pier) == pytest.approx(1240, rel=0.03)


def test_geocode_strips_unit(monkeypatch):
    seen = {}

    def fake_get(url, timeout=60):
        seen["url"] = url
        return b'[{"lat": "33.83", "lon": "-118.38"}]'

    monkeypatch.setattr(lv_map.common, "http_get", fake_get)
    assert lv_map.geocode("123 S Pacific Coast Hwy #E", "Redondo Beach", "90277") == (33.83, -118.38)
    assert "%23E" not in seen["url"] and "Pacific" in seen["url"]


def test_distance_tags_from_city_manifest():
    city = {"pois": [{"name": "Pier", "lat": 33.84, "lon": -118.39}],
            "distance_tags": [{"kind": "coastline", "label": "The beach"},
                              {"kind": "road", "name": "Esplanade", "label": "The Esplanade"},
                              {"kind": "poi", "name": "Pier", "label": "The Pier"},
                              {"kind": "poi", "name": "Missing", "label": "Nope"}]}
    ways = [{"tags": {"natural": "coastline"}, "pts": [[33.8305, -118.3920]]},
            {"tags": {"highway": "secondary", "name": "Esplanade"}, "pts": [[33.8305, -118.3900]]}]
    tags = lv_map.distance_tags(city, (33.8305, -118.3850), ways)
    assert [t["label"] for t in tags] == ["The beach", "The Esplanade", "The Pier"]
    assert tags[0]["at"] is None and tags[2]["at"] == (33.84, -118.39)


@pytest.mark.skipif(not (lv_map.CITIES_DIR / "redondo-beach" / "cache" / "osm.json").exists(),
                    reason="Redondo map cache not present on this machine")
def test_portrait_map_keeps_tags_above_instagram_ui():
    city = lv_map.load_city("redondo-beach")
    scene = lv_map.MapScene(city, (33.8305425, -118.3849595), "123 S PCH #E", BRAND)
    wide, close = scene.views((1080, 1920))
    for tag in [t for t in scene.tags if t["at"]]:
        _, y = scene._px(*tag["at"], close, (1080, 1920))
        assert 0.08 * 1920 < y < 0.74 * 1920


def test_speed_ramp_is_monotonic_and_front_loaded():
    vals = [lv_depth.speed_ramp(p / 10, 2.2) for p in range(11)]
    assert vals == sorted(vals) and vals[0] == 0 and vals[-1] == 1
    assert vals[5] > 0.5


@pytest.mark.skipif(not lv_depth.MODEL.exists(), reason="depth model not downloaded")
@pytest.mark.parametrize("move,size", [("dolly", (320, 180)), ("pan_r", (180, 320)), ("orbit_l", (320, 180))])
def test_parallax_frames_have_the_output_size(move, size):
    rgb = (np.random.default_rng(1).random((300, 400, 3)) * 255).astype(np.uint8)
    px = lv_depth.Parallax(rgb, size, lv_depth.MOVES[move])
    for p in (0, 0.5, 1):
        assert px.frame(p).shape == (size[1], size[0], 3)


def test_kinetic_type_draws_and_respects_its_window():
    frame = np.zeros((360, 640, 3), np.uint8)
    block = lv_type.Block([lv_type.Line("Hello there", "bold", 40)], 0.0, 2.0, x=20, bottom=300, width=640)
    lv_type.draw(frame, block, 5.0, BRAND)
    assert frame.max() == 0
    lv_type.draw(frame, block, 1.0, BRAND)
    assert frame.max() > 200


def test_count_up_lands_on_the_number():
    frame = np.zeros((200, 800, 3), np.uint8)
    block = lv_type.Block([lv_type.Line("${:,}", "bold", 40, count=1_480_000)], 0.0, 3.0, x=10, bottom=150, width=800)
    lv_type.draw(frame, block, 2.5, BRAND)  # after the 0.9s count, the full price is drawn
    assert frame.max() > 200


def test_scrim_is_strongest_bottom_left():
    a = lv_pop.scrim((320, 180), False)
    assert a.shape == (180, 320, 1)
    assert a[170, 5, 0] > a[170, 315, 0] > a[20, 5, 0]


def test_whip_mix_slides_between_frames():
    cut = object.__new__(lv_pop.PopCut)
    a = np.full((10, 100, 3), 10, np.uint8)
    b = np.full((10, 100, 3), 200, np.uint8)
    assert (cut._mix(a, b, 0.0, "whip") == 10).all()
    assert (cut._mix(a, b, 1.0, "whip") == 200).all()
    mid = cut._mix(a, b, 0.5, "fade")
    assert 100 <= mid.mean() <= 110


def test_short_address():
    assert lv_pop.short_address("123 S Pacific Coast Hwy #E") == "123 S PCH #E"


def test_blend_zoom_out_stays_between_views():
    a = lv_map.View(-278.0, 223.0, 2464.0)
    b = lv_map.View(-272.0, -897.0, 5971.0)
    for q in (0.0, 0.3, 0.5, 1.0):
        v = lv_map.MapScene.blend(a, b, q)
        assert min(a.cy, b.cy) - 1 <= v.cy <= max(a.cy, b.cy) + 1
        assert min(a.width_m, b.width_m) - 1 <= v.width_m <= max(a.width_m, b.width_m) + 1


def test_blend_same_width_moves_linearly():
    a, b = lv_map.View(0.0, 0.0, 1000.0), lv_map.View(100.0, 0.0, 1000.0)
    assert lv_map.MapScene.blend(a, b, 0.5).cx == pytest.approx(50.0)


def test_kicker_new_price_when_reduced():
    assert lv_cards.kicker_text({"price": 950000, "previous_price": 999900}) == "NEW PRICE"
    assert lv_cards.kicker_text({"price": 950000, "previous_price": None}) == "FOR SALE"
    assert lv_cards.kicker_text({"price": 999900, "previous_price": 950000}) == "FOR SALE"


def test_strike_sprite_draws_a_line():
    lv_type.register_brand(BRAND)
    plain = lv_type.word_sprite("$999,900", "regular", 44, (255, 255, 255, 255), 0.0, BRAND.get("name", "brand"))
    struck = lv_type.word_sprite("$999,900", "regular", 44, (255, 255, 255, 255), 0.0, BRAND.get("name", "brand"), True)
    assert struck[1].sum() > plain[1].sum()


def test_carson_map_tour_renders_every_stop():
    city = lv_map.load_city("carson")
    if not (lv_map.CITIES_DIR / "carson" / "cache" / "osm.json").exists():
        pytest.skip("no OSM cache")
    scene = lv_map.MapScene(city, (33.8479994, -118.2551379), "20200 Example Ave", BRAND)
    stops = city["map_tour"]["landscape"]
    tour = lv_map.MapTour(scene, stops, (480, 270))
    for k in range(len(stops)):
        for p in (0.0, 0.3, 0.7, 1.0):
            img = tour.frame(k, p)
            assert img.shape == (270, 480, 3)


def test_media_file_falls_back_to_drive_library(tmp_path):
    local, drive = tmp_path / "city", tmp_path / "drive"
    (local / "media").mkdir(parents=True)
    (drive / "originals").mkdir(parents=True)
    (drive / "originals" / "a.mp4").write_bytes(b"x")
    city = {"dir": str(local), "library": str(drive)}
    assert lv_map.media_file(city, "media/originals/a.mp4") == drive / "originals" / "a.mp4"
    (local / "media" / "originals").mkdir()
    (local / "media" / "originals" / "a.mp4").write_bytes(b"x")
    assert lv_map.media_file(city, "media/originals/a.mp4") == local / "media" / "originals" / "a.mp4"
    with pytest.raises(RuntimeError):
        lv_map.media_file(city, "media/originals/missing.mp4")
