"""Unit tests for the publish kit's pure functions. Run: python3 -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import publish_kit as kit  # noqa: E402


def scenes(*pairs):
    return {"title": "T", "scenes": [{"id": i, "caption": c, "narration": n}
                                     for i, (c, n) in enumerate(pairs, 1)]}


class Clocks(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(kit.clock(0), "0:00")
        self.assertEqual(kit.clock(75.9), "1:15")
        self.assertEqual(kit.clock(3671), "1:01:11")

    def test_srt_clock(self):
        self.assertEqual(kit.srt_clock(61.5), "00:01:01,500")


class Clean(unittest.TestCase):
    def test_dashes_removed(self):
        self.assertEqual(kit.clean("rates rose — fast"), "rates rose, fast")
        self.assertNotIn("–", kit.clean("2020–2026"))

    def test_license_numbers_lose_the_pound_sign(self):
        # Instagram and YouTube read "#00000001" as a hashtag (Tony, 2026-10-20)
        self.assertEqual(kit.clean("CA DRE #00000001 | Corp DRE # 00000003"),
                         "CA DRE 00000001 | Corp DRE 00000003")

    def test_real_hashtags_survive(self):
        self.assertEqual(kit.clean("#RentControl #Springfield #2026"), "#RentControl #Springfield #2026")


class Chapters(unittest.TestCase):
    def test_first_chapter_is_zero_and_short_scenes_fold(self):
        data = scenes(("A", "a."), ("B", "b."), ("C", "c."), ("D", "d."))
        got = kit.chapters(data, [12.0, 4.0, 11.0, 12.0])
        self.assertEqual(got[0], (0.0, "A"))
        self.assertEqual([label for _, label in got], ["A", "B", "D"])
        starts = [s for s, _ in got] + [39.0]
        self.assertTrue(all(b - a >= kit.MIN_CHAPTER_S for a, b in zip(starts, starts[1:])))

    def test_short_tail_folds_into_previous(self):
        got = kit.chapters(scenes(("A", "a."), ("B", "b."), ("C", "c.")), [12.0, 12.0, 5.0])
        self.assertEqual([label for _, label in got], ["A", "B"])


class Srt(unittest.TestCase):
    def test_cues_stay_inside_their_scene_and_are_ordered(self):
        data = scenes(("A", "One sentence here. And a second one."), ("B", "Third."))
        srt = kit.transcript_srt(data, [6.0, 3.0])
        self.assertIn("1\n00:00:00,000 -->", srt)
        self.assertIn("3\n00:00:06,000 -->", srt)  # scene 2 starts exactly at 6.0s
        self.assertEqual(srt.count("-->"), 3)

    def test_long_sentence_is_split(self):
        long = "word " * 40
        self.assertTrue(all(len(c) <= kit.SRT_MAX_CHARS for c in kit.caption_chunks(long)))


class Tags(unittest.TestCase):
    def test_tag_budget_and_dedupe(self):
        tags = kit.fit_tags(["a" * 30] * 3 + [f"tag number {i:03d} padding padding" for i in range(40)])
        self.assertEqual(tags.count("a" * 30), 1)
        self.assertLessEqual(len(", ".join(tags)), kit.TAGS_MAX_CHARS)

    def test_authored_block_wins_without_calling_tim(self):
        data = {**scenes(("A", "Hello there.")),
                "youtube": {"title": "Mine", "description": "Desc", "tags": ["X", "y"]}}
        meta = kit.youtube_meta(data, {"TIM_LLM_URL": "http://127.0.0.1:1"})
        self.assertEqual((meta["title"], meta["source"], meta["tags"]), ("Mine", "scenes.json", ["x", "y"]))


if __name__ == "__main__":
    unittest.main()
