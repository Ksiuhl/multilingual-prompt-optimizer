import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from multilingual_prompt_optimizer.cli import main
from multilingual_prompt_optimizer.validation import (
    AnswerCheck,
    check_code,
    execute_checked,
    validate_answer,
)


class ValidationTests(unittest.TestCase):
    def test_invoice_and_weighted_mean_oracles(self):
        invoice = {
            "kind": "arithmetic",
            "request": {
                "payload": json.dumps(
                    {
                        "lines": [
                            {"quantity": 3, "unit_price": "19.95"},
                            {"quantity": 2, "unit_price": "4.50"},
                        ],
                        "discount": "5.00",
                        "shipping": "3.25",
                    }
                )
            },
            "oracle": {"operation": "invoice"},
        }
        self.assertTrue(validate_answer(invoice, {"answer": 67.10}).passed)
        weighted = {
            "kind": "arithmetic",
            "request": {
                "payload": json.dumps(
                    {
                        "values": [
                            {"value": 80, "weight": 2},
                            {"value": 60, "weight": 1},
                            {"value": 95, "weight": 3},
                        ]
                    }
                )
            },
            "oracle": {"operation": "weighted_mean"},
        }
        self.assertTrue(validate_answer(weighted, {"answer": 84.17}).passed)

    def extraction(self):
        return {
            "kind": "extraction",
            "request": {"payload": '{"person":{"name":"王芳"}}'},
            "oracle": {"fields": {"name": ["person", "name"], "due": ["due"]}},
        }

    def test_extraction_missing_null_unicode_and_exact_keys(self):
        case = self.extraction()
        self.assertTrue(validate_answer(case, {"answer": {"name": "王芳", "due": None}}).passed)
        for wrong in (
            {"name": "Wang Fang", "due": None},
            {"name": "王芳"},
            {"name": "王芳", "due": ""},
        ):
            self.assertFalse(validate_answer(case, {"answer": wrong}).passed)

    def test_numeric_boolean_is_not_a_numeric_answer(self):
        case = {
            "kind": "arithmetic",
            "request": {"payload": '{"values":[1,1]}'},
            "oracle": {"operation": "mean"},
        }
        self.assertTrue(validate_answer(case, {"answer": 1}).passed)
        self.assertFalse(validate_answer(case, {"answer": True}).passed)
        self.assertFalse(validate_answer(case, {"answer": "1"}).passed)

    def test_decimal_half_up_and_negative_percentage(self):
        case = {
            "kind": "arithmetic",
            "request": {"payload": '{"price":"1.05","percent":"10"}'},
            "oracle": {"operation": "discount"},
        }
        self.assertTrue(validate_answer(case, {"answer": 0.95}).passed)
        self.assertFalse(validate_answer(case, {"answer": 0.94}).passed)
        case = {
            "kind": "arithmetic",
            "request": {"payload": '{"old":80,"new":68}'},
            "oracle": {"operation": "percent_change"},
        }
        self.assertTrue(validate_answer(case, {"answer": -15}).passed)
        self.assertFalse(validate_answer(case, {"answer": 15}).passed)

    def test_filter_boundary_order_and_empty_set(self):
        case = {
            "kind": "filtering",
            "request": {"payload": '[{"id":"B","amount":100},{"id":"A","amount":101}]'},
            "oracle": {
                "conditions": [{"field": "amount", "op": "ge", "value": 100}],
                "output_field": "id",
                "order": "ascending",
            },
        }
        self.assertTrue(validate_answer(case, {"answer": ["A", "B"]}).passed)
        self.assertFalse(validate_answer(case, {"answer": ["B", "A"]}).passed)
        case["oracle"]["conditions"][0]["value"] = 1000
        self.assertTrue(validate_answer(case, {"answer": []}).passed)

    def test_filter_and_or_are_distinct(self):
        case = {
            "kind": "filtering",
            "request": {
                "payload": '[{"id":"A","high":true,"owner":"X"},{"id":"B","high":false,"owner":null}]'
            },
            "oracle": {
                "conditions": [
                    {"field": "high", "op": "eq", "value": True},
                    {"field": "owner", "op": "missing"},
                ],
                "output_field": "id",
            },
        }
        self.assertTrue(validate_answer(case, {"answer": []}).passed)
        case["oracle"]["combine"] = "any"
        self.assertTrue(validate_answer(case, {"answer": ["A", "B"]}).passed)

    def spec(self):
        return {
            "function": "average",
            "parameters": ["xs"],
            "tests": [{"args": [[]], "expected": None}, {"args": [[2, 4]], "expected": 3}],
        }

    def test_code_correct_behavior_and_empty_input_regression(self):
        self.assertTrue(
            check_code(
                "def average(xs):\n    return sum(xs)/len(xs) if xs else None", self.spec()
            ).passed
        )
        self.assertFalse(
            check_code(
                "def average(xs):\n    return sum(xs)/len(xs) if xs else 0", self.spec()
            ).passed
        )

    def test_code_import_attribute_and_side_effect_calls_are_never_executed(self):
        for code in (
            "import os\ndef average(xs):\n return None",
            'def average(xs):\n return __import__("os").system("echo bad")',
            "def average(xs):\n return xs.pop()",
            'def average(xs):\n if False:\n  open("file","w")\n return None',
        ):
            with self.subTest(code=code):
                self.assertFalse(check_code(code, self.spec()).passed)

    def test_code_loops_powers_and_recursion_are_unsupported(self):
        for code in (
            "def average(xs):\n while True:\n  pass",
            "def average(xs):\n return 10 ** 1000000",
            "def average(xs):\n return average(xs)",
        ):
            self.assertFalse(check_code(code, self.spec()).passed)

    def test_code_numeric_bounds_and_signature(self):
        self.assertFalse(check_code("def average(xs):\n return 10000000000000", self.spec()).passed)
        self.assertFalse(check_code("def different(xs):\n return None", self.spec()).passed)

    def test_gate_candidate_pass_uses_one_real_call(self):
        calls = []

        def execute(prompt):
            calls.append(prompt)
            return {"answer": 1}

        result = execute_checked(
            "original", "short", execute, lambda a: AnswerCheck(a["answer"] == 1, "value")
        )
        self.assertTrue(result["validated"])
        self.assertEqual(calls, ["short"])

    def test_gate_failure_executes_original_and_does_not_release_bad_candidate(self):
        calls = []

        def execute(prompt):
            calls.append(prompt)
            return {"answer": 2 if prompt == "short" else 1}

        result = execute_checked(
            "original", "short", execute, lambda a: AnswerCheck(a["answer"] == 1, "value")
        )
        self.assertEqual(calls, ["short", "original"])
        self.assertEqual(result["selected_source"], "original_fallback")
        self.assertEqual(result["answer"], {"answer": 1})

    def test_gate_blocks_answer_when_both_fail(self):
        result = execute_checked(
            "original", "short", lambda p: {"answer": 2}, lambda a: AnswerCheck(False, "wrong")
        )
        self.assertFalse(result["validated"])
        self.assertIsNone(result["answer"])
        self.assertEqual(len(result["attempts"]), 2)

    def test_gate_identical_prompt_does_not_duplicate_inference(self):
        result = execute_checked(
            "same", "same", lambda p: {}, lambda a: AnswerCheck(False, "wrong")
        )
        self.assertEqual(len(result["attempts"]), 1)

    def test_gate_connection_error_still_checks_fallback(self):
        def execute(prompt):
            if prompt == "short":
                raise RuntimeError("offline candidate")
            return {"ok": True}

        result = execute_checked("original", "short", execute, lambda a: AnswerCheck(a["ok"], "ok"))
        self.assertTrue(result["validated"])
        self.assertIn("error", result["attempts"][0])

    def test_validate_cli_nonzero_for_wrong_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "case.json").write_text(json.dumps(self.extraction()), encoding="utf-8")
            (p / "answer.json").write_text('{"answer":{}}', encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "validate",
                            "--case",
                            str(p / "case.json"),
                            "--answer",
                            str(p / "answer.json"),
                        ]
                    ),
                    1,
                )


if __name__ == "__main__":
    unittest.main()
