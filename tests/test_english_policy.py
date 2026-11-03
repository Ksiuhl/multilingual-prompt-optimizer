import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multilingual_prompt_optimizer import Request, auto_optimize, optimize
from multilingual_prompt_optimizer.cli import main


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class Generator:
    model = "test-model"

    def __init__(self):
        self.calls = []
        self.inputs = []

    def generate(self, system, data, schema):
        self.calls.append({"model": self.model})
        self.inputs.append(data)
        if "languages" in data:
            return {"clauses": [{lang: "Summarize." for lang in data["languages"]}]}
        return {"equivalent": True, "reason": "Same task."}


class EnglishPolicyTests(unittest.TestCase):
    def test_single_language_accepts_a_one_combination_budget(self):
        model = Generator()
        result = auto_optimize(
            Request("Please summarize the supplied document."),
            generator=model,
            counter=Characters(),
            max_combinations=1,
        )
        self.assertEqual(model.inputs[0]["languages"], ["en"])
        self.assertNotEqual(result.automation["status"], "error_original_retained")

    def test_default_auto_rewrites_only_in_english_and_preserves_payload(self):
        generator = Generator()
        result = auto_optimize(
            Request("Please summarize the supplied document.", payload="KEEP: 王芳\n"),
            generator=generator,
            counter=Characters(),
        )
        self.assertEqual(generator.inputs[0]["languages"], ["en"])
        self.assertEqual(result.automation["policy"], "concise_english")
        self.assertNotIn("KEEP", json.dumps(generator.inputs))
        self.assertIn("KEEP: 王芳\n", result.prompt)
        self.assertLess(result.selected_tokens, result.original_tokens)

    def test_explicit_languages_keep_experimental_search_available(self):
        result = auto_optimize(
            Request("Please summarize the supplied document."),
            generator=Generator(),
            counter=Characters(),
            languages=("en", "zh"),
        )
        self.assertEqual(result.automation["policy"], "experimental_multilingual")
        self.assertEqual(result.automation["languages"], ["en", "zh"])

    def test_default_rules_omit_translation_and_explicit_mode_restores_it(self):
        request = Request("Please explain the artificial intelligence algorithm.")
        default = optimize(request, counter=Characters())
        experimental = optimize(request, counter=Characters(), rule_modes=("lite", "translate"))
        self.assertFalse(any(c.label == "promptmin:translate" for c in default.candidates))
        self.assertTrue(any(c.label == "promptmin:translate" for c in experimental.candidates))

    def test_cli_translation_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text(
                json.dumps({"instruction": "Please explain artificial intelligence."})
            )
            for flags, expected in [((), False), (("--experimental-multilingual",), True)]:
                output = Path(folder) / ("experimental.json" if expected else "default.json")
                with patch("multilingual_prompt_optimizer.cli._counter", return_value=Characters()):
                    status = main(
                        ["optimize", "--input", str(source), "--output", str(output), *flags]
                    )
                self.assertEqual(status, 0)
                result = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(
                    any(c["label"] == "promptmin:translate" for c in result["candidates"]), expected
                )

    def test_cli_auto_defaults_and_explicit_language_override(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text(json.dumps({"instruction": "Please summarize the supplied text."}))
            variants = [
                ([], ["en"]),
                (["--experimental-multilingual"], ["en", "zh", "ja"]),
                (["--experimental-multilingual", "--languages", "en"], ["en"]),
            ]
            for index, (flags, languages) in enumerate(variants):
                model = Generator()
                output = Path(folder) / f"auto-{index}.json"
                with (
                    patch("multilingual_prompt_optimizer.cli._counter", return_value=Characters()),
                    patch(
                        "multilingual_prompt_optimizer.automatic.OllamaModel", return_value=model
                    ),
                ):
                    status = main(
                        [
                            "auto",
                            "--input",
                            str(source),
                            "--output",
                            str(output),
                            "--model",
                            "local",
                            *flags,
                        ]
                    )
                self.assertEqual(status, 0)
                self.assertEqual(model.inputs[0]["languages"], languages)


if __name__ == "__main__":
    unittest.main()
