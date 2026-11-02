import json
import tempfile
import unittest
from pathlib import Path

from multilingual_prompt_optimizer import OllamaModel, Request
from multilingual_prompt_optimizer.template_cache import TemplateCache, cache_context


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class CacheTests(unittest.TestCase):
    def context(self, **changes):
        args = {
            "tokenizer": "characters",
            "generator": {"digest": "g1"},
            "reviewer": {"digest": "r1"},
            "protocol": "p1",
            "validator": "v1",
            "mode": "english",
        }
        args.update(changes)
        return cache_context(Request("Please summarize the text."), **args)

    def test_cache_applies_to_new_payload_without_storing_private_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            c = TemplateCache(directory)
            context = self.context()
            c.save(context, "Summarize.", [True, True])
            result = c.apply(context, "PRIVATE NEW INPUT", Characters())
            self.assertTrue(result["cache_hit"])
            self.assertIn("PRIVATE NEW INPUT", result["prompt"])
            self.assertNotIn("PRIVATE NEW INPUT", next(Path(directory).glob("*.json")).read_text())
            self.assertEqual(result["reason"], "cache_applied")

    def test_miss_returns_original_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            r = TemplateCache(directory).apply(self.context(), "new", Characters())
            self.assertFalse(r["cache_hit"])
            self.assertEqual(r["saved_tokens"], 0)

    def test_calibration_failure_is_cached_as_original(self):
        with tempfile.TemporaryDirectory() as directory:
            c = TemplateCache(directory)
            context = self.context()
            item = c.save(context, "Unsafe short text.", [True, False])
            self.assertFalse(item["admitted"])
            self.assertEqual(item["instruction"], context["instruction"])
            self.assertEqual(
                c.apply(context, "new", Characters())["reason"], "calibration_rejected"
            )

    def test_one_calibration_pass_is_insufficient(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(
                TemplateCache(directory).save(self.context(), "Short.", [True])["admitted"]
            )

    def test_context_changes_invalidate(self):
        original = self.context()
        for changes in (
            {"tokenizer": "other"},
            {"generator": {"digest": "g2"}},
            {"reviewer": {"digest": "r2"}},
            {"validator": "v2"},
            {"protocol": "p2"},
            {"mode": "mixed"},
        ):
            self.assertNotEqual(
                TemplateCache.key(original), TemplateCache.key(self.context(**changes))
            )
        changed = dict(original, instruction="Different request.")
        self.assertNotEqual(TemplateCache.key(original), TemplateCache.key(changed))

    def test_corrupt_cache_is_a_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            c = TemplateCache(directory)
            context = self.context()
            c.save(context, "Summarize.", [True, True])
            p = next(Path(directory).glob("*.json"))
            r = json.loads(p.read_text())
            r["instruction"] = "Tampered."
            p.write_text(json.dumps(r))
            self.assertIsNone(c.load(context))

    def test_new_payload_full_prompt_growth_is_rejected(self):
        class BoundaryCounter:
            name = "characters"

            def count(self, text):
                return 100 if text.startswith("Short.") and "new payload" in text else len(text)

        with tempfile.TemporaryDirectory() as directory:
            c = TemplateCache(directory)
            context = self.context()
            c.save(context, "Short.", [True, True])
            result = c.apply(context, "new payload", BoundaryCounter())
            self.assertEqual(result["saved_tokens"], 0)
            self.assertEqual(result["reason"], "original_retained_after_recount")

    def test_cached_numeric_loss_cannot_bypass_structural_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            context = cache_context(
                Request("Return exactly 3 items."),
                tokenizer="characters",
                generator="g",
                reviewer="r",
                protocol="p",
                validator="v",
                mode="mixed",
            )
            c = TemplateCache(directory)
            c.save(context, "Return items.", [True, True])
            self.assertEqual(c.apply(context, "new", Characters())["saved_tokens"], 0)

    def test_mismatched_counter_is_not_silently_used(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "tokenizer"):
                TemplateCache(directory).apply(self.context(tokenizer="other"), "new", Characters())

    def test_model_budgets_are_bounded(self):
        for options in ({"num_predict": True}, {"num_predict": 0}, {"context_length": 100}):
            with self.assertRaises(ValueError):
                OllamaModel("local", **options)
        model = OllamaModel("local", num_predict=4096, context_length=8192)
        self.assertEqual(model.options["num_ctx"], 8192)


if __name__ == "__main__":
    unittest.main()
