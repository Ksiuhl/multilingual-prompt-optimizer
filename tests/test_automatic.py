import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from multilingual_prompt_optimizer import OllamaModel, Request, auto_optimize
from multilingual_prompt_optimizer.cli import main


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class FakeModel:
    model = "test-model"

    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []
        self.inputs = []

    def generate(self, system, data, schema):
        self.inputs.append(data)
        self.calls.append({"model": self.model, "status": "test_double"})
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


OPTIONS = {"clauses": [{"en": "Summarize.", "zh": "总结。"}]}


class AutomaticTests(unittest.TestCase):
    def run_auto(self, model, request=None, **kwargs):
        return auto_optimize(
            request or Request("Please summarize the supplied text."),
            generator=model,
            counter=Characters(),
            languages=("en", "zh"),
            **kwargs,
        )

    def test_approved_shortest_candidate_keeps_payload_and_output(self):
        model = FakeModel([OPTIONS, {"equivalent": True, "reason": "Same requirements."}])
        req = Request("Please summarize the supplied text.", payload="    secret source\n")
        result = self.run_auto(model, req)
        self.assertEqual(result.selected_label, "phrases:zh")
        self.assertIn("\n\n    secret source\n\n\nRespond in English.", result.prompt)
        self.assertEqual(result.automation["status"], "judge_approved")
        self.assertFalse(result.semantic_equivalence_verified)
        self.assertNotIn("secret source", json.dumps(model.inputs))
        self.assertEqual(len(result.automation["model_calls"]), 2)

    def test_reject_shortest_then_choose_next_approved(self):
        model = FakeModel(
            [
                OPTIONS,
                {"equivalent": False, "reason": "Unclear wording."},
                {"equivalent": True, "reason": "Same meaning."},
            ]
        )
        result = self.run_auto(model)
        self.assertEqual(result.selected_label, "phrases:en")
        self.assertFalse(next(c for c in result.candidates if c.label == "phrases:zh").accepted)

    def test_negation_loss_rejected_by_judge(self):
        model = FakeModel([OPTIONS, {"equivalent": False, "reason": "Lost negation."}])
        result = self.run_auto(model, Request("Do not summarize the text."), verification_budget=1)
        self.assertEqual(result.selected_label, "original")
        self.assertEqual(result.automation["status"], "original_retained")

    def test_budget_does_not_select_unchecked_candidate(self):
        model = FakeModel([OPTIONS, {"equivalent": False, "reason": "Ambiguous."}])
        result = self.run_auto(model, verification_budget=1)
        self.assertEqual(result.saved_tokens, 0)
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(
            any("not_semantically_approved" in c.rejection_reasons for c in result.candidates)
        )

    def test_numeric_loss_never_reaches_judge(self):
        model = FakeModel([OPTIONS])
        result = self.run_auto(model, Request("Summarize in exactly 3 bullets."))
        self.assertEqual(result.selected_label, "original")
        self.assertEqual(len(model.calls), 1)

    def test_generation_error_returns_original(self):
        result = self.run_auto(FakeModel([RuntimeError("offline")]))
        self.assertEqual(result.automation["status"], "error_original_retained")
        self.assertEqual(result.selected_label, "original")

    def test_invalid_judge_boolean_fails_closed(self):
        result = self.run_auto(FakeModel([OPTIONS, {"equivalent": "true", "reason": "ok"}]))
        self.assertEqual(result.automation["status"], "error_original_retained")
        self.assertEqual(result.saved_tokens, 0)

    def test_bad_or_incomplete_generated_languages_fail_closed(self):
        for answer in (
            {"clauses": []},
            {"clauses": [{"en": "Only one."}]},
            {"clauses": [{"en": "A", "zh": ""}]},
            {"other": []},
        ):
            with self.subTest(answer=answer):
                result = self.run_auto(FakeModel([answer]))
                self.assertEqual(result.automation["status"], "error_original_retained")

    def test_separate_verifier_is_used(self):
        generator = FakeModel([OPTIONS])
        judge = FakeModel([{"equivalent": True, "reason": "Matches."}])
        judge.model = "separate-test-model"
        result = self.run_auto(generator, verifier=judge)
        self.assertTrue(result.automation["different_model_names"])
        self.assertEqual(len(generator.calls), 1)
        self.assertEqual(len(judge.calls), 1)

    def test_invalid_budgets_rejected_before_call(self):
        for kwargs in (
            {"verification_budget": 0},
            {"max_combinations": 1},
            {"max_clauses": 9},
            {"languages": ("en", "xx")},
        ):
            model = FakeModel([])
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                auto_optimize(Request("Summarize."), generator=model, **kwargs)
            self.assertEqual(model.calls, [])

    def test_endpoints_and_cloud_models_are_rejected(self):
        for url in (
            "https://ollama.com",
            "http://example.com",
            "http://localhost.evil.test",
            "http://localhost/path",
            "http://user@localhost:11434",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OllamaModel("local", url)
        with self.assertRaises(ValueError):
            OllamaModel("model:cloud")

    def test_actual_http_protocol_and_usage_record(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                payload = json.dumps(
                    {
                        "done": True,
                        "model": "local",
                        "prompt_eval_count": 20,
                        "eval_count": 10,
                        "total_duration": 100000,
                        "response": json.dumps(OPTIONS),
                    }
                ).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                model = OllamaModel("local", f"http://127.0.0.1:{server.server_port}")
                self.assertEqual(model.generate("system", {"instruction": "test"}, {}), OPTIONS)
                self.assertFalse(received[0]["stream"])
                self.assertFalse(received[0]["think"])
                self.assertEqual(model.calls[0]["prompt_eval_count"], 20)
            finally:
                server.shutdown()
                thread.join()

    def test_cli_offline_writes_original_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / "input.json", Path(folder) / "output.json"
            source.write_text('{"instruction":"Please summarize."}', encoding="utf-8")
            with patch.object(OllamaModel, "generate", side_effect=RuntimeError("offline")):
                with redirect_stderr(StringIO()):
                    code = main(
                        ["auto", "--input", str(source), "--output", str(dest), "--model", "local"]
                    )
            self.assertEqual(code, 2)
            result = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(result["selected_label"], "original")
            self.assertEqual(result["automation"]["status"], "error_original_retained")


if __name__ == "__main__":
    unittest.main()
