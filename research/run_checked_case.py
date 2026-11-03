"""Run automatic optimization plus a configured task-answer gate on one fixture."""

import argparse
import json
from pathlib import Path

from multilingual_prompt_optimizer import (
    OllamaModel,
    Request,
    auto_optimize,
    execute_checked,
    validate_answer,
)
from multilingual_prompt_optimizer.validation import answer_schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-compression", action="store_true")
    parser.add_argument("--input", type=Path, default=Path("data/task-quality-development.json"))
    parser.add_argument("--id", default="F03")
    parser.add_argument("--output", type=Path, default=Path("results/local/checked-demo.json"))
    args = parser.parse_args()
    cases = json.loads(args.input.read_text(encoding="utf-8"))["items"]
    matches = [c for c in cases if c["id"] == args.id]
    if len(matches) != 1:
        raise ValueError("Unknown case ID")
    case = matches[0]
    request = Request.from_dict(case["request"])
    optimized = auto_optimize(
        request,
        generator=OllamaModel("qwen3:4b") if args.enable_compression else None,
        verifier=OllamaModel("qwen3:8b") if args.enable_compression else None,
        allow_compression=args.enable_compression,
    )
    target = OllamaModel("qwen3:4b")

    def execute(prompt):
        return target.generate(
            "Perform the task in user_prompt. Return the answer in the supplied JSON transport schema. Put requested Python code in code; otherwise put the requested result in answer. Do not add commentary.",
            {"user_prompt": prompt},
            answer_schema(case["kind"]),
        )

    result = execute_checked(
        request.compose(request.instruction),
        optimized.prompt,
        execute,
        lambda a: validate_answer(case, a),
    )
    report = {
        "id": case["id"],
        "kind": case["kind"],
        "configured_oracle_required": True,
        "optimization": optimized.to_dict(),
        "execution": result,
        "target_calls": target.calls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "validated": result["validated"],
                "selected_source": result["selected_source"],
                "answer": result["answer"],
                "target_calls": len(target.calls),
                "result_file": str(args.output),
            },
            ensure_ascii=True,
        )
    )
    return 0 if result["validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
