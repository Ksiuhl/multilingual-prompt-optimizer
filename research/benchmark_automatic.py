"""Matched generated-pool search comparison; does not measure target task accuracy."""

import argparse
import hashlib
import inspect
import json
import time
from dataclasses import replace
from pathlib import Path

from runtime_info import local_runtime

from multilingual_prompt_optimizer import Candidate, OllamaModel, Request, TiktokenCounter, optimize
from multilingual_prompt_optimizer.automatic import _generate_phrase_options, _review_candidates
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM


def usage(calls):
    return {
        "calls": len(calls),
        "input_tokens": sum(c.get("prompt_eval_count", 0) for c in calls),
        "output_tokens": sum(c.get("eval_count", 0) for c in calls),
        "call_elapsed_ms": sum(c["elapsed_ms"] for c in calls),
    }


def compact(result):
    record = result.to_dict()
    record["candidates"] = [
        {k: v for k, v in c.items() if k != "prompt"} for c in record["candidates"]
    ]
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/development.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("results/local/automatic-benchmark.json")
    )
    parser.add_argument(
        "--reviewer-results", type=Path, default=Path("results/reviewer-comparison.json")
    )
    parser.add_argument("--generator", default="qwen3:4b")
    args = parser.parse_args()
    selection = json.loads(args.reviewer_results.read_text(encoding="utf-8"))
    if not selection.get("complete"):
        raise ValueError("Reviewer comparison is incomplete")
    judge_name = selection["selected_model"]
    generator = OllamaModel(args.generator, timeout=180)
    verifier = OllamaModel(judge_name, timeout=180)
    counter = TiktokenCounter()
    raw = args.input.read_bytes()
    corpus = json.loads(raw)
    report = {
        "complete": False,
        "runtime": local_runtime(),
        "scope": "30 synthetic development tasks, generated candidates only; no target-model task accuracy or API billing measured.",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "generator_protocol_sha256": hashlib.sha256(
            inspect.getsource(_generate_phrase_options).encode()
        ).hexdigest(),
        "review_protocol_sha256": hashlib.sha256(
            (REVIEW_SYSTEM + json.dumps(REVIEW_SCHEMA, sort_keys=True)).encode()
        ).hexdigest(),
        "generator": args.generator,
        "reviewer": judge_name,
        "tokenizer": counter.name,
        "languages": ["en", "zh", "ja"],
        "verification_budget_per_arm": 8,
        "max_combinations": 256,
        "method": "Generate one shared multilingual phrase pool per task. Compare its English-only member, best monolingual member and mixed combinations; each arm gets a fresh review budget. No authored alternatives or PromptMin rules are used. Generation cost is recorded once, and also charged once per standalone arm in summaries.",
        "limitations": [
            "English-only is drawn from shared multilingual generation, not an independently optimized English generator.",
            "Local generator/reviewer counts use their own tokenizers, not o200k_base.",
            "Judge approval is not independent task accuracy. Data and reviewer selection are development-only.",
            "One run per task/arm, fixed arm order, caching and model load can affect timings.",
        ],
        "records": [],
    }
    start = time.perf_counter()
    for item in corpus["items"]:
        request = Request.from_dict(
            {k: v for k, v in item.items() if k not in {"id", "candidates", "phrase_options"}}
        )
        baseline = optimize(request, counter=counter, rule_modes=(), allow_compression=True)
        gs = len(generator.calls)
        generation_error = None
        try:
            options = _generate_phrase_options(request, generator, ("en", "zh", "ja"), 5, 256)
        except (RuntimeError, ValueError) as exc:
            options = ()
            generation_error = str(exc)
        generation_calls = generator.calls[gs:]
        record = {
            "id": item["id"],
            "original_tokens": baseline.original_tokens,
            "generated_phrase_options": list(options),
            "generation_error": generation_error,
            "generation_calls": generation_calls,
            "generation_usage": usage(generation_calls),
            "arms": {},
        }
        for arm in ("english", "single_language", "mixed"):
            arm_start = time.perf_counter()
            js = len(verifier.calls)
            judgments = []
            error = generation_error
            result = baseline
            if options:
                if arm == "english":
                    req = replace(request, phrase_options=tuple({"en": o["en"]} for o in options))
                elif arm == "single_language":
                    req = replace(
                        request,
                        candidates=tuple(
                            Candidate("single:" + lang, " ".join(o[lang] for o in options))
                            for lang in ("en", "zh", "ja")
                        ),
                    )
                else:
                    req = replace(request, phrase_options=options)
                try:
                    pool = optimize(
                        req,
                        counter=counter,
                        rule_modes=(),
                        max_combinations=256,
                        allow_compression=True,
                    )
                    result, judgments = _review_candidates(request, pool, verifier, 8)
                except (RuntimeError, ValueError) as exc:
                    error = str(exc)
            calls = verifier.calls[js:]
            record["arms"][arm] = {
                "result": compact(result),
                "judgments": judgments,
                "error": error,
                "review_calls": calls,
                "review_usage": usage(calls),
                "elapsed_ms": (time.perf_counter() - arm_start) * 1000,
            }
        report["records"].append(record)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            item["id"],
            baseline.original_tokens,
            {a: record["arms"][a]["result"]["selected_tokens"] for a in record["arms"]},
            flush=True,
        )
    original = sum(r["original_tokens"] for r in report["records"])
    gen_input = sum(r["generation_usage"]["input_tokens"] for r in report["records"])
    gen_output = sum(r["generation_usage"]["output_tokens"] for r in report["records"])
    gen_ms = sum(r["generation_usage"]["call_elapsed_ms"] for r in report["records"])
    totals = {}
    for arm in ("english", "single_language", "mixed"):
        rows = [r["arms"][arm] for r in report["records"]]
        selected = sum(r["result"]["selected_tokens"] for r in rows)
        totals[arm] = {
            "original_tokens": original,
            "selected_tokens": selected,
            "saved_tokens": original - selected,
            "reduction": (original - selected) / original,
            "improved_tasks": sum(r["result"]["saved_tokens"] > 0 for r in rows),
            "errors": sum(bool(r["error"]) for r in rows),
            "review_calls": sum(r["review_usage"]["calls"] for r in rows),
            "local_model_input_tokens_including_shared_generation": gen_input
            + sum(r["review_usage"]["input_tokens"] for r in rows),
            "local_model_output_tokens_including_shared_generation": gen_output
            + sum(r["review_usage"]["output_tokens"] for r in rows),
            "elapsed_ms_including_shared_generation": gen_ms + sum(r["elapsed_ms"] for r in rows),
        }
    report.update(
        complete=True,
        totals=totals,
        total_experiment_elapsed_ms=(time.perf_counter() - start) * 1000,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    main()
