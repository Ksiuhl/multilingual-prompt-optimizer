import importlib.util
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from multilingual_prompt_optimizer import (
    Candidate,
    JsonTokenizerCounter,
    Request,
    TiktokenCounter,
    optimize,
)
from multilingual_prompt_optimizer.cli import main


class CharacterCounter:
    name = "characters-for-test"

    def count(self, text):
        return len(text)


class OptimizerTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("tokenizers"), "optional hf dependency not installed"
    )
    def test_local_json_tokenizer_needs_no_model_download(self):
        from tokenizers import Tokenizer, models, pre_tokenizers

        tokenizer = Tokenizer(
            models.WordLevel({"[UNK]": 0, "hello": 1, "world": 2}, unk_token="[UNK]")
        )
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "tokenizer.json"
            tokenizer.save(str(source))
            counter = JsonTokenizerCounter(source)
            self.assertEqual(counter.count("hello world"), 2)
            self.assertTrue(counter.name.startswith("tokenizer-json:sha256:"))
            self.assertEqual(len(counter.name.split(":")[-1]), 64)

    def test_payload_and_output_are_immutable(self):
        code = "def average(xs):\n    return sum(xs) / len(xs)\n"
        req = Request(
            "Please fix this Python function.", payload=code, output_instruction="Code only."
        )
        result = optimize(req)
        for candidate in result.candidates:
            self.assertIn("\n\n" + code + "\n\nCode only.", candidate.prompt)

    def test_final_token_growth_falls_back(self):
        original = "Please summarize the update below in exactly three bullet points. Keep the dates and numbers unchanged, and do not add information."
        result = optimize(Request(original))
        self.assertLessEqual(result.selected_tokens, result.original_tokens)
        self.assertTrue(
            any("full_prompt_token_increase" in c.rejection_reasons for c in result.candidates)
        )

    def test_supplied_candidate_selected_by_complete_prompt(self):
        req = Request(
            "A long instruction for the same task.",
            payload="data",
            candidates=(Candidate("short", "Do task."),),
        )
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertEqual(result.selected_label, "supplied:short")
        self.assertEqual(result.selected_tokens, len("Do task.\n\ndata\n\nRespond in English."))

    def test_larger_candidate_rejected(self):
        req = Request("Go.", candidates=(Candidate("long", "Please do a much longer thing."),))
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertEqual(result.selected_label, "original")
        self.assertFalse(result.candidates[1].accepted)

    def test_tie_keeps_original(self):
        req = Request("Go.", candidates=(Candidate("equal", "Do."),))
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertEqual(result.selected_label, "original")

    def test_missing_number_rejected(self):
        req = Request("Return 3 items.", candidates=(Candidate("wrong", "Return 2."),))
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertIn("instruction_number_changed", result.candidates[1].rejection_reasons)

    def test_number_in_payload_does_not_mask_removed_instruction_number(self):
        req = Request(
            "Return 3 items.", payload="3", candidates=(Candidate("wrong", "Return items."),)
        )
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertFalse(result.candidates[1].accepted)

    def test_repeated_numbers_preserved(self):
        req = Request("Use 3 rows and 3 columns.", candidates=(Candidate("lost", "Use 3 cells."),))
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertFalse(result.candidates[1].accepted)

    def test_exact_literal_is_not_removed(self):
        req = Request("Return exactly this string: please", protected_literals=("please",))
        result = optimize(req)
        self.assertIn("please", result.prompt)
        self.assertTrue(
            any(
                "protected_literal_changed:please" in c.rejection_reasons for c in result.candidates
            )
        )

    def test_literal_only_in_payload_stays_unchanged(self):
        req = Request("Please copy the text.", payload="TOKEN", protected_literals=("TOKEN",))
        result = optimize(req)
        self.assertIn("\n\nTOKEN\n\n", result.prompt)

    def test_full_phrase_combinations_including_monolingual_are_considered(self):
        req = Request(
            "Long original request.",
            output_instruction="",
            phrase_options=(
                {"en": "AAAA", "zh": "甲"},
                {"en": "B", "zh": "乙乙乙"},
            ),
        )
        result = optimize(req, counter=CharacterCounter(), rule_modes=())
        self.assertEqual(result.prompt, "甲 B")
        self.assertEqual(sum(c.source == "phrase_search" for c in result.candidates), 4)

    def test_search_is_bounded_before_generation(self):
        req = Request(
            "Long original.", phrase_options=tuple({"en": "a", "zh": "b"} for _ in range(10))
        )
        with self.assertRaisesRegex(ValueError, "1024 combinations"):
            optimize(req, max_combinations=256)

    def test_semantics_not_claimed_verified(self):
        result = optimize(Request("Summarize."), rule_modes=())
        self.assertFalse(result.semantic_equivalence_verified)

    def test_special_token_like_text_is_plain_content(self):
        count = TiktokenCounter().count("<|endoftext|>")
        self.assertGreater(count, 0)

    def test_rule_counter_registration_is_isolated_between_threads(self):
        class AlwaysOne:
            name = "one-for-test"

            def count(self, text):
                return 1

        req = Request("Please write the documentation for this application.")

        def task(index):
            counter = AlwaysOne() if index % 2 else CharacterCounter()
            result = optimize(req, counter=counter)
            return all(c.tokens == counter.count(c.prompt) for c in result.candidates)

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(task, range(12))))

    def test_negative_counter_is_rejected(self):
        class Invalid:
            name = "bad"

            def count(self, text):
                return -1

        with self.assertRaisesRegex(ValueError, "nonnegative"):
            optimize(Request("Go."), counter=Invalid(), rule_modes=())

    def test_request_rejects_unknown_fields(self):
        with self.assertRaisesRegex(ValueError, "unknown request fields"):
            Request.from_dict({"instruction": "Go.", "paylod": "typo"})

    def test_request_rejects_bad_phrase_options(self):
        with self.assertRaises(ValueError):
            Request.from_dict({"instruction": "Go.", "phrase_options": [{}]})

    def test_request_rejects_bad_candidate(self):
        with self.assertRaises(ValueError):
            Request.from_dict({"instruction": "Go.", "candidates": [{"label": "a"}]})

    def test_request_rejects_absent_protected_literal(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            Request("Go.", protected_literals=("not present",))

    def test_request_rejects_duplicate_candidate_labels(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            Request("Go.", candidates=(Candidate("x", "One."), Candidate("x", "Two.")))

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            output = Path(folder) / "result.json"
            request.write_text(json.dumps({"instruction": "Please summarize."}), encoding="utf-8")
            self.assertEqual(
                main(["optimize", "--input", str(request), "--output", str(output)]), 0
            )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertLessEqual(result["selected_tokens"], result["original_tokens"])

    def test_cli_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            request.write_text('{"instruction":"Go.","output_instruction":""}', encoding="utf-8")
            stream = StringIO()
            with redirect_stdout(stream):
                status = main(["optimize", "--input", str(request), "--no-rules", "--text"])
            self.assertEqual(status, 0)
            self.assertEqual(stream.getvalue(), "Go.\n")

    def test_cli_error_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "bad.json", Path(folder) / "out.json"
            source.write_text('{"instruction":false}', encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(
                    main(["optimize", "--input", str(source), "--output", str(output)]), 2
                )
            self.assertFalse(output.exists())

    def test_benchmark_has_same_original_totals_and_no_increase(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "corpus.json", Path(folder) / "out.json"
            source.write_text(
                json.dumps({"items": [{"id": "a", "instruction": "Please summarize."}]}),
                encoding="utf-8",
            )
            self.assertEqual(
                main(["benchmark", "--input", str(source), "--output", str(output)]), 0
            )
            results = json.loads(output.read_text(encoding="utf-8"))
            for method in ["automatic_rules", "supplied_search", "hybrid"]:
                self.assertLessEqual(results["totals"][method], results["totals"]["original"])


if __name__ == "__main__":
    unittest.main()
