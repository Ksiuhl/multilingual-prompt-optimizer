"""One paired summary check; omissions are reported, not silently discarded."""

import argparse
import json
from pathlib import Path

from multilingual_prompt_optimizer import OllamaModel, Request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("examples/automatic.json"))
    parser.add_argument(
        "--optimized", type=Path, default=Path("results/live-summary-8b-review.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("results/local/summary-task-check.json")
    )
    parser.add_argument("--model", default="qwen3:4b")
    args = parser.parse_args()
    request = Request.from_dict(json.loads(args.input.read_text(encoding="utf-8")))
    optimized = json.loads(args.optimized.read_text(encoding="utf-8"))
    model = OllamaModel(args.model, timeout=120)
    schema = {
        "type": "object",
        "required": ["bullets"],
        "additionalProperties": False,
        "properties": {
            "bullets": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}}
        },
    }
    results = {}
    for name, prompt in [
        ("original", request.compose(request.instruction)),
        ("optimized", optimized["prompt"]),
    ]:
        answer = model.generate(
            "Perform the user task. Return three English summary bullets in the JSON schema.",
            {"user_prompt": prompt},
            schema,
        )
        text = " ".join(answer.get("bullets", []))
        results[name] = {
            "response": answer,
            "model_usage": model.calls[-1],
            "checks": {
                "three_bullets": len(answer.get("bullets", [])) == 3,
                "user_count_120": "120" in text,
                "onboarded_96": "96" in text,
                "launch_date": any(
                    d in text for d in ("2 November 2026", "November 2, 2026", "2026-11-02")
                ),
                "review_date": any(
                    d in text for d in ("9 November 2026", "November 9, 2026", "2026-11-09")
                ),
                "two_payment_bugs": any(
                    d in text.lower() for d in ("two payment bugs", "2 payment bugs")
                ),
            },
        }
    results["limitations"] = [
        "One development summary task, one run per condition, not independent accuracy validation.",
        "Matched structured-output wrapping was used for both calls. Exact date-format checks have limited coverage.",
        "Inference can vary even at temperature zero. A difference in one pair does not establish causality.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    passed = all(all(r["checks"].values()) for name, r in results.items() if name != "limitations")
    print(json.dumps({"all_checks_passed": passed, "output": str(args.output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
