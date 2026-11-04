import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multilingual_prompt_optimizer import JsonExtractionTemplate
from multilingual_prompt_optimizer.cli import main


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class ValidatedTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = JsonExtractionTemplate(
            "Please carefully extract the specified scalar from the supplied source.",
            "Extract.",
            (("value", ("a", "value")),),
            "fixture-model-v1-options",
            "characters",
        )
        self.evidence = {
            "template_fingerprint": self.template.fingerprint,
            "trials": [],
            "charges": [],
            "preparation_quota": 0,
            "counter_delta_quota": 0,
        }
        for split, values in [("development", range(10)), ("holdout", range(100, 120))]:
            for i in values:
                payload = json.dumps({"a": {"value": i}, "distractor": -i})
                for arm, instruction, cost in [
                    ("original", self.template.original_instruction, 10),
                    ("compressed", self.template.compressed_instruction, 6),
                ]:
                    rid = f"{split}-{i}-{arm}"
                    prompt = self.template.request(payload).compose(instruction)
                    self.evidence["trials"].append(
                        {
                            "split": split,
                            "case_id": str(i),
                            "arm": arm,
                            "payload": payload,
                            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                            "response_text": json.dumps({"answer": {"value": i}}),
                            "request_id": rid,
                        }
                    )
                    self.evidence["charges"].append({"request_id": rid, "quota": cost})
        self.reconcile(self.evidence)

    def reconcile(self, evidence):
        evidence["counter_delta_quota"] = sum(r["quota"] for r in evidence["charges"])

    def select(self, **kwargs):
        return self.template.select(
            '{"a":{"value":999}}',
            counter=Characters(),
            target=self.template.target,
            evidence=self.evidence,
            **kwargs,
        )

    def test_disjoint_paired_evidence_admits_only_explicitly(self):
        self.assertTrue(self.template.assess(self.evidence)["admitted"])
        self.assertEqual(self.select()["result"]["selected_label"], "original")
        self.assertEqual(
            self.select(allow_compression=True)["result"]["selected_label"], "supplied:template"
        )

    def test_one_holdout_error_blocks_admission(self):
        self.evidence["trials"][-1]["response_text"] = '{"answer":{"value":false}}'
        result = self.template.assess(self.evidence)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "task_accuracy_gate_failed")

    def test_equal_cost_or_preparation_erasing_savings_blocks_admission(self):
        for split in ["development", "holdout"]:
            e = copy.deepcopy(self.evidence)
            for row in e["charges"]:
                if row["request_id"].startswith(split) and row["request_id"].endswith("compressed"):
                    row["quota"] = 10
            self.reconcile(e)
            self.assertFalse(self.template.assess(e)["admitted"])
        self.evidence["preparation_quota"] = 40
        self.assertFalse(self.template.assess(self.evidence)["admitted"])

    def test_missing_ambiguous_or_unreconciled_cost_is_not_approval(self):
        variants = []
        for field, value in [("preparation_quota", None), ("counter_delta_quota", 9999)]:
            e = copy.deepcopy(self.evidence)
            e[field] = value
            variants.append(e)
        e = copy.deepcopy(self.evidence)
        e["charges"].pop()
        variants.append(e)
        e = copy.deepcopy(self.evidence)
        e["charges"].append(e["charges"][0].copy())
        variants.append(e)
        e = copy.deepcopy(self.evidence)
        e["trials"][-1]["request_id"] = e["trials"][0]["request_id"]
        variants.append(e)
        for e in variants:
            self.assertFalse(self.template.assess(e)["admitted"])

    def test_changed_prompt_or_template_identity_is_rejected(self):
        e = copy.deepcopy(self.evidence)
        e["trials"][0]["prompt_sha256"] = "changed"
        self.assertFalse(self.template.assess(e)["admitted"])
        e = copy.deepcopy(self.evidence)
        e["template_fingerprint"] = "changed"
        self.assertFalse(self.template.assess(e)["admitted"])
        for target, counter in [
            ("different-model", Characters()),
            (
                self.template.target,
                type("Other", (), {"name": "other", "count": lambda self, t: len(t)})(),
            ),
        ]:
            result = self.template.select(
                '{"a":{"value":9}}',
                counter=counter,
                target=target,
                evidence=self.evidence,
                allow_compression=True,
            )
            self.assertEqual(result["result"]["selected_label"], "original")

    def test_development_holdout_leakage_and_insufficient_inputs_are_rejected(self):
        e = copy.deepcopy(self.evidence)
        first = next(r for r in e["trials"] if r["split"] == "development")
        for row in e["trials"]:
            if row["split"] == "holdout" and row["case_id"] == "100":
                row["payload"] = first["payload"]
        self.assertFalse(self.template.assess(e)["admitted"])
        e = copy.deepcopy(self.evidence)
        removed = {
            r["request_id"]
            for r in e["trials"]
            if r["split"] == "development" and r["case_id"] == "0"
        }
        e["trials"] = [r for r in e["trials"] if r["request_id"] not in removed]
        e["charges"] = [r for r in e["charges"] if r["request_id"] not in removed]
        self.reconcile(e)
        self.assertEqual(self.template.assess(e)["reason"], "insufficient_development_inputs")

    def test_wrong_candidate_answer_retries_original_and_releases_only_valid_answer(self):
        answers = iter(['{"answer":{"value":0}}', '{"answer":{"value":999}}'])
        prompts = []

        def execute(prompt):
            prompts.append(prompt)
            return next(answers)

        result = self.template.execute(
            '{"a":{"value":999}}',
            execute=execute,
            counter=Characters(),
            target=self.template.target,
            evidence=self.evidence,
            allow_compression=True,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(result["selected_source"], "original_fallback")
        self.assertEqual(len(prompts), 2)
        self.assertNotEqual(prompts[0], prompts[1])

    def test_no_invalid_answer_is_released_when_both_attempts_fail(self):
        result = self.template.execute(
            '{"a":{"value":999}}',
            execute=lambda _: '{"answer":{"value":"999"}}',
            counter=Characters(),
            target=self.template.target,
            evidence=self.evidence,
            allow_compression=True,
        )
        self.assertFalse(result["validated"])
        self.assertIsNone(result["answer"])

    def test_default_original_can_still_be_runtime_validated(self):
        calls = []
        result = self.template.execute(
            '{"a":{"value":999}}',
            execute=lambda p: calls.append(p) or '{"answer":{"value":999}}',
            counter=Characters(),
            target=self.template.target,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(result["selected_source"], "original")
        self.assertEqual(len(calls), 1)

    def test_source_scope_failure_never_executes_or_releases(self):
        for payload in [
            "[]",
            '{"a":{"value":[]}}',
            '{"a":1}',
            '{"a":{},"a":{}}',
            '{"a":{"value":NaN}}',
        ]:

            def forbidden(_):
                raise AssertionError("No call for unsupported source")

            result = self.template.execute(
                payload,
                execute=forbidden,
                counter=Characters(),
                target=self.template.target,
                evidence=self.evidence,
                allow_compression=True,
            )
            self.assertFalse(result["validated"])
            self.assertEqual(result["attempts"], [])

    def test_scalar_types_unicode_and_duplicate_response_keys_are_checked(self):
        cases = [
            ('{"a":{"value":false}}', '{"answer":{"value":0}}'),
            ('{"a":{"value":"007"}}', '{"answer":{"value":7}}'),
            ('{"a":{"value":" 王芳 "}}', '{"answer":{"value":"王芳"}}'),
            ("{}", '{"answer":{"value":"null"}}'),
        ]
        for payload, wrong in cases:
            self.assertFalse(self.template.check(payload, wrong).passed)
        self.assertTrue(self.template.check("{}", '{"answer":{"value":null}}').passed)
        self.assertFalse(self.template.check("{}", '{"answer":{"value":1,"value":null}}').passed)

    def test_template_roundtrip_and_invalid_path(self):
        self.assertEqual(
            JsonExtractionTemplate.from_dict(self.template.to_dict()).fingerprint,
            self.template.fingerprint,
        )
        data = self.template.to_dict()
        data["fields"] = [["value", "not-an-array"]]
        with self.assertRaises(ValueError):
            JsonExtractionTemplate.from_dict(data)

    def test_multiple_paths_match_an_independently_written_expected_answer(self):
        t = JsonExtractionTemplate(
            "Extract fields.",
            "Extract.",
            (
                ("name", ("customer", "name")),
                ("id", ("order", "id")),
                ("amount", ("payment", "amount")),
            ),
            "fixture",
            "characters",
        )
        payload = '{"customer":{"name":" 王芳 "},"order":{},"payment":{"amount":"007.50"},"archived":{"name":"WRONG"}}'
        self.assertEqual(
            t.expected(payload), {"answer": {"name": " 王芳 ", "id": None, "amount": "007.50"}}
        )

    def test_repeated_payloads_cannot_inflate_holdout_input_count(self):
        e = copy.deepcopy(self.evidence)
        for row in e["trials"]:
            if row["split"] == "holdout" and row["case_id"] == "119":
                row["payload"] = json.dumps({"a": {"value": 118}, "distractor": -118})
                instruction = (
                    self.template.original_instruction
                    if row["arm"] == "original"
                    else self.template.compressed_instruction
                )
                row["prompt_sha256"] = hashlib.sha256(
                    self.template.request(row["payload"]).compose(instruction).encode()
                ).hexdigest()
                row["response_text"] = '{"answer":{"value":118}}'
        self.assertEqual(self.template.assess(e)["reason"], "insufficient_holdout_inputs")

    def test_cli_uses_evidence_only_after_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in [
                ("template", self.template.to_dict()),
                ("evidence", self.evidence),
                ("source", {"a": {"value": 999}}),
            ]:
                (root / (name + ".json")).write_text(json.dumps(value), encoding="utf8")
            args = [
                "validated-extract",
                "--template",
                str(root / "template.json"),
                "--input",
                str(root / "source.json"),
                "--evidence",
                str(root / "evidence.json"),
                "--target",
                self.template.target,
                "--output",
                str(root / "out.json"),
            ]
            with patch("multilingual_prompt_optimizer.cli._counter", return_value=Characters()):
                self.assertEqual(main(args), 0)
                self.assertEqual(
                    json.loads((root / "out.json").read_text())["result"]["selected_label"],
                    "original",
                )
                self.assertEqual(main(args + ["--enable-compression"]), 0)
                self.assertEqual(
                    json.loads((root / "out.json").read_text())["result"]["selected_label"],
                    "supplied:template",
                )


if __name__ == "__main__":
    unittest.main()
