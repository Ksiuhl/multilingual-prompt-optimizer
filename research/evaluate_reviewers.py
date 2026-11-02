"""Compare the unchanged production review protocol on synthetic labeled pairs."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from runtime_info import local_runtime

from multilingual_prompt_optimizer import OllamaModel
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM, judge_instruction


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/reviewer-development.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("results/local/reviewer-comparison.json")
    )
    parser.add_argument("--models", nargs="+", default=["qwen3:4b", "qwen3:8b"])
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = json.loads(raw)
    report = {
        "complete": False,
        "runtime": local_runtime(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "review_protocol_sha256": hashlib.sha256(
            (REVIEW_SYSTEM + json.dumps(REVIEW_SCHEMA, sort_keys=True)).encode()
        ).hexdigest(),
        "scope": "Synthetic development comparison, one trial per pair/model, assistant-authored labels.",
        "selection_rule": "Among models with zero false accepts and zero errors, maximize true accepts; ties favor the first model. Otherwise retain the first model with a warning.",
        "models": [],
    }
    for name in args.models:
        model = OllamaModel(name, timeout=180)
        rows = []
        start = time.perf_counter()
        for item in data["items"]:
            row = {"id": item["id"], "expected": item["expected_equivalent"]}
            try:
                decision = judge_instruction(
                    model, item["original"], item["candidate"], item["output_instruction"]
                )
                row.update(decision)
                row["correct"] = decision["equivalent"] == row["expected"]
            except (RuntimeError, ValueError) as exc:
                row.update(error=str(exc), correct=False)
            row["call"] = model.calls[-1]
            rows.append(row)
            print(name, item["id"], "correct" if row["correct"] else "incorrect", flush=True)
        positives = sum(i["expected_equivalent"] for i in data["items"])
        metrics = {
            "true_accepts": sum(r.get("equivalent") is True and r["expected"] for r in rows),
            "false_accepts": sum(r.get("equivalent") is True and not r["expected"] for r in rows),
            "true_rejects": sum(r.get("equivalent") is False and not r["expected"] for r in rows),
            "false_rejects": sum(r.get("equivalent") is False and r["expected"] for r in rows),
            "errors": sum("error" in r for r in rows),
            "positives": positives,
            "negatives": len(rows) - positives,
            "accuracy": sum(r["correct"] for r in rows) / len(rows),
            "elapsed_ms": (time.perf_counter() - start) * 1000,
            "input_tokens": sum(c.get("prompt_eval_count", 0) for c in model.calls),
            "output_tokens": sum(c.get("eval_count", 0) for c in model.calls),
        }
        report["models"].append({"model": name, "metrics": metrics, "records": rows})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    eligible = [
        m
        for m in report["models"]
        if not m["metrics"]["false_accepts"] and not m["metrics"]["errors"]
    ]
    selected = (
        max(eligible, key=lambda m: m["metrics"]["true_accepts"])
        if eligible
        else report["models"][0]
    )
    report.update(
        complete=True,
        selected_model=selected["model"],
        selection_warning=None
        if eligible
        else "No model met the zero-false-accept/no-error development rule.",
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "selected": report["selected_model"],
                "metrics": [{m["model"]: m["metrics"]} for m in report["models"]],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
