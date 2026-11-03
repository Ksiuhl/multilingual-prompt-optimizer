import json
import unittest

from multilingual_prompt_optimizer import Candidate, Request, json_object_contract, optimize
from multilingual_prompt_optimizer.validation import validate_answer


class Characters:
    name = "characters"

    def count(self, text):
        return len(text)


class OutputContractTests(unittest.TestCase):
    def test_contract_is_immutable_and_counted_in_every_complete_prompt(self):
        contract = json_object_contract(("launch", "progress", "next"))
        request = Request(
            "Please summarize this supplied project note.",
            payload="KEEP SOURCE: 王芳\n",
            output_instruction=contract,
            candidates=(Candidate("short", "Summarize the project note."),),
        )
        result = optimize(request, counter=Characters(), rule_modes=())
        for candidate in result.candidates:
            self.assertTrue(candidate.prompt.endswith(contract))
            self.assertIn("KEEP SOURCE: 王芳\n", candidate.prompt)
            self.assertEqual(candidate.tokens, len(candidate.prompt))
        self.assertEqual(result.selected_label, "supplied:short")

    def test_field_names_are_json_encoded_in_shape(self):
        names = ['quoted"key', "城市"]
        contract = json_object_contract(names)
        shape = contract.split("replace every placeholder: ", 1)[1].split(". No extra keys", 1)[0]
        self.assertEqual(set(json.loads(shape)["answer"]), set(names))
        self.assertIn('ONLY top-level key must be "answer"', contract)

    def test_invalid_field_sets_fail_before_model_use(self):
        for fields in ("launch", [], ["x", "x"], [""], [None], list(map(str, range(65)))):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                json_object_contract(fields)

    def test_missing_wrapper_still_fails_validation(self):
        case = {
            "kind": "extraction",
            "request": {"payload": '{"launch":"2027-02-03"}'},
            "oracle": {"fields": {"launch": ["launch"]}},
        }
        self.assertFalse(validate_answer(case, {"launch": "2027-02-03"}).passed)
        self.assertTrue(validate_answer(case, {"answer": {"launch": "2027-02-03"}}).passed)


if __name__ == "__main__":
    unittest.main()
