import unittest

from multilingual_prompt_optimizer.semantic import judge_instruction


class Stub:
    def __init__(self, result):
        self.result = result
        self.data = None

    def generate(self, system, data, schema):
        self.data = data
        return self.result


class SemanticTests(unittest.TestCase):
    def test_review_input_does_not_contain_expected_labels(self):
        model = Stub({"equivalent": True, "reason": "Same task."})
        result = judge_instruction(model, "Please summarize.", "Summarize.", "English only.")
        self.assertTrue(result["equivalent"])
        self.assertEqual(set(model.data), {"original", "candidate", "unchanged_output_instruction"})

    def test_overlong_reason_is_rejected_even_if_model_ignores_schema(self):
        with self.assertRaisesRegex(ValueError, "invalid semantic"):
            judge_instruction(Stub({"equivalent": True, "reason": "a" * 241}), "a", "b", "")

    def test_non_boolean_equivalence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid semantic"):
            judge_instruction(Stub({"equivalent": "true", "reason": "same"}), "a", "b", "")


if __name__ == "__main__":
    unittest.main()
