import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from multilingual_prompt_optimizer import (
    Candidate,
    Request,
    TemplateCache,
    auto_optimize,
    cache_context,
    optimize,
)
from multilingual_prompt_optimizer.cli import main


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class UntouchableModel:
    def __getattribute__(self, name):
        raise AssertionError("Disabled compression must not touch a model")


class OriginalPolicyTests(unittest.TestCase):
    def request(self):
        return Request(
            "Please summarize this text carefully.",
            payload=" 王芳\n    preserve indentation  \n",
            output_instruction="Return JSON only.  ",
            candidates=(Candidate("short", "Summarize."),),
            phrase_options=tuple({"en": "a", "zh": "甲"} for _ in range(10)),
        )

    def test_default_ignores_all_candidate_sources_and_unused_search_budget(self):
        req = self.request()
        with patch(
            "multilingual_prompt_optimizer.rules.generate",
            side_effect=AssertionError("No rule generation"),
        ):
            result = optimize(
                req, counter=Characters(), rule_modes=("lite", "translate", "aggressive")
            )
        self.assertEqual(result.prompt, req.compose(req.instruction))
        self.assertEqual(result.saved_tokens, 0)
        self.assertEqual(result.selected_label, "original")
        self.assertEqual(len(result.candidates), 1)
        self.assertFalse(result.compression_enabled)

    def test_opt_in_runs_search_without_claiming_task_validation(self):
        req = Request(
            "Please summarize this text carefully.", candidates=(Candidate("short", "Summarize."),)
        )
        result = optimize(req, counter=Characters(), rule_modes=(), allow_compression=True)
        self.assertLess(result.selected_tokens, result.original_tokens)
        self.assertTrue(result.compression_enabled)
        self.assertFalse(result.semantic_equivalence_verified)

    def test_auto_default_never_touches_generator_or_verifier(self):
        req = self.request()
        result = auto_optimize(
            req, generator=UntouchableModel(), verifier=UntouchableModel(), counter=Characters()
        )
        self.assertEqual(result.prompt, req.compose(req.instruction))
        self.assertEqual(result.automation["status"], "compression_disabled")
        self.assertEqual(result.automation["model_calls"], [])
        self.assertEqual(auto_optimize(req, counter=Characters()).prompt, result.prompt)

    def test_even_calibrated_cache_requires_opt_in(self):
        req = Request("Please summarize this text carefully.", output_instruction="JSON.")
        context = cache_context(
            req,
            tokenizer="characters",
            generator={},
            reviewer={},
            protocol={},
            validator="fixture",
            mode="english",
        )
        with tempfile.TemporaryDirectory() as folder:
            cache = TemplateCache(folder)
            cache.save(context, "Summarize.", [True, True])
            with patch.object(
                cache, "load", side_effect=AssertionError("Do not read cached rewrites")
            ):
                result = cache.apply(context, " 王芳  ", Characters())
            self.assertEqual(
                result["prompt"],
                Request(req.instruction, payload=" 王芳  ", output_instruction="JSON.").compose(
                    req.instruction
                ),
            )
            self.assertEqual(result["reason"], "compression_disabled")
            self.assertGreater(
                cache.apply(context, " 王芳  ", Characters(), allow_compression=True)[
                    "saved_tokens"
                ],
                0,
            )

    def test_truthy_values_are_not_permission(self):
        for value in [1, "true", None]:
            with self.subTest(value=value):
                for call in [
                    lambda: optimize(self.request(), allow_compression=value),
                    lambda: auto_optimize(self.request(), allow_compression=value),
                    lambda: TemplateCache("unused").apply(
                        {}, "", Characters(), allow_compression=value
                    ),
                ]:
                    with self.assertRaisesRegex(ValueError, "Boolean"):
                        call()

    def run_cli(self, command, raw, flags=()):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            output = Path(folder) / "output.json"
            source.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf8")
            with patch("multilingual_prompt_optimizer.cli._counter", return_value=Characters()):
                status = main([command, "--input", str(source), "--output", str(output), *flags])
            return status, json.loads(
                output.read_text(encoding="utf8")
            ) if output.exists() else None

    def test_cli_default_preserves_supplied_short_alternative(self):
        raw = {
            "instruction": "Please summarize this text carefully.",
            "payload": " 王芳\n  ",
            "candidates": [{"label": "short", "instruction": "Summarize."}],
        }
        status, result = self.run_cli("optimize", raw)
        self.assertEqual(status, 0)
        self.assertEqual(result["prompt"], Request.from_dict(raw).compose(raw["instruction"]))
        self.assertFalse(result["compression_enabled"])
        status, enabled = self.run_cli("optimize", raw, ["--enable-compression", "--no-rules"])
        self.assertEqual(status, 0)
        self.assertTrue(enabled["compression_enabled"])
        self.assertGreater(enabled["saved_tokens"], 0)

    def test_cli_auto_default_needs_no_model_or_ollama(self):
        for flags in [[], ["--model", "missing-model", "--verifier-model", "missing-verifier"]]:
            with (
                self.subTest(flags=flags),
                patch(
                    "multilingual_prompt_optimizer.automatic.OllamaModel",
                    side_effect=AssertionError("No model construction"),
                ),
            ):
                status, result = self.run_cli("auto", {"instruction": "Please summarize."}, flags)
            self.assertEqual(status, 0)
            self.assertEqual(result["automation"]["status"], "compression_disabled")

    def test_benchmark_does_not_bypass_default_policy(self):
        raw = {
            "items": [
                {
                    "id": "one",
                    "instruction": "Please summarize this text carefully.",
                    "candidates": [{"label": "short", "instruction": "Summarize."}],
                }
            ]
        }
        status, result = self.run_cli("benchmark", raw)
        self.assertEqual(status, 0)
        self.assertEqual(len(set(result["totals"].values())), 1)
        status, enabled = self.run_cli("benchmark", raw, ["--enable-compression"])
        self.assertEqual(status, 0)
        self.assertLess(enabled["totals"]["hybrid"], enabled["totals"]["original"])

    def test_rewrite_modifiers_alone_cannot_enable_compression(self):
        for command, flags in [
            ("optimize", ["--aggressive"]),
            ("optimize", ["--experimental-multilingual"]),
            ("optimize", ["--no-rules"]),
            ("auto", ["--languages", "en,zh"]),
        ]:
            with self.subTest(flags=flags), redirect_stderr(StringIO()):
                status, result = self.run_cli(command, {"instruction": "Summarize."}, flags)
            self.assertEqual(status, 2)
            self.assertIsNone(result)

    def test_enabled_auto_requires_model(self):
        with redirect_stderr(StringIO()):
            status, result = self.run_cli(
                "auto", {"instruction": "Summarize."}, ["--enable-compression"]
            )
        self.assertEqual(status, 2)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
