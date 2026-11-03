import json
import unittest
from dataclasses import replace

from multilingual_prompt_optimizer import (
    Request,
    freeze_english,
    rank_translations,
    translation_job,
)


class Chars:
    name = "test-characters"

    def count(self, text):
        return len(text)


class TwoStageTests(unittest.TestCase):
    def setUp(self):
        self.segments = ("Return 3 identifiers in input order.", "Preserve empty strings exactly.")
        self.request = Request(
            " ".join(self.segments),
            payload="PRIVATE_SOURCE_NOT_FOR_TRANSLATION",
            output_instruction="JSON only.",
        )
        self.frozen = freeze_english(self.request, self.segments)

    def test_translator_only_receives_frozen_english(self):
        job = translation_job(self.frozen)
        self.assertEqual(job["data"]["english_segments"], list(self.segments))
        self.assertNotIn(self.request.payload, json.dumps(job))
        self.assertEqual(
            set(job["data"]), {"frozen_english_sha256", "english_segments", "target_languages"}
        )
        self.assertNotIn("en", job["schema"]["properties"]["translations"]["items"]["properties"])

    def test_exact_partition_and_identity_are_required(self):
        with self.assertRaises(ValueError):
            freeze_english(self.request, ["Return 3 identifiers.", self.segments[1]])
        with self.assertRaises(ValueError):
            translation_job(replace(self.frozen, sha256="wrong"))

    def test_translator_cannot_rewrite_english_or_drop_segments(self):
        bad = {"translations": [{"en": "CHANGED", "zh": "甲", "ja": "乙"}] * 2}
        with self.assertRaises(ValueError):
            rank_translations(self.frozen, bad, counter=Chars())
        with self.assertRaises(ValueError):
            rank_translations(self.frozen, {"translations": []}, counter=Chars())

    def test_english_fallback_when_translations_grow(self):
        response = {"translations": [{"zh": s * 4, "ja": s * 5} for s in self.segments]}
        out = rank_translations(self.frozen, response, counter=Chars())
        self.assertEqual(out["pool"]["selected_label"], "original")
        self.assertEqual(out["pool"]["prompt"], self.request.compose(self.request.instruction))
        self.assertIsNotNone(out["shortest_genuine"])
        self.assertFalse(out["shortest_genuine"]["strictly_shorter_than_english"])

    def test_shorter_genuine_composition_keeps_source_and_english_segments(self):
        response = {
            "translations": [
                {"zh": "依序取3个id。", "ja": "順に3個。"},
                {"zh": "保留空串。", "ja": "空文字維持。"},
            ]
        }
        out = rank_translations(self.frozen, response, counter=Chars())
        self.assertNotEqual(out["pool"]["selected_label"], "original")
        self.assertIn(self.request.payload, out["pool"]["prompt"])
        self.assertTrue(out["pool"]["prompt"].endswith(self.request.output_instruction))
        self.assertIn("en", out["shortest_genuine"]["languages"])
        self.assertFalse(out["semantics_certified"])

    def test_numeric_loss_is_not_a_diagnostic_candidate(self):
        response = {
            "translations": [{"zh": "取id。", "ja": "id取得。"}, {"zh": "空串。", "ja": "空文字。"}]
        }
        out = rank_translations(self.frozen, response, counter=Chars())
        for candidate in out["pool"]["candidates"]:
            if candidate["label"].startswith("supplied:stage2:") and not candidate["instruction"].startswith(
                self.segments[0]
            ):
                self.assertIn("instruction_number_changed", candidate["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
