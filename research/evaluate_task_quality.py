"""Repeated source-oracle task checks with paid-in-compute real fallback calls."""

import argparse
import hashlib
import inspect
import json
import random
import time
from dataclasses import asdict, replace
from pathlib import Path

from runtime_info import local_runtime

import multilingual_prompt_optimizer.validation as validation_module
from multilingual_prompt_optimizer import OllamaModel, Request, TiktokenCounter, optimize
from multilingual_prompt_optimizer.automatic import _generate_phrase_options, _review_candidates
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM
from multilingual_prompt_optimizer.validation import answer_schema, execute_checked, validate_answer

TARGET_SYSTEM = "Perform the task in user_prompt. Return the answer in the supplied JSON transport schema. Put requested Python code in code; otherwise put the requested result in answer. Do not add commentary."


def count_usage(calls):
    return {
        "calls": len(calls),
        "input_tokens": sum(c.get("prompt_eval_count", 0) for c in calls),
        "output_tokens": sum(c.get("eval_count", 0) for c in calls),
        "elapsed_ms": sum(c.get("elapsed_ms", 0) for c in calls),
    }


def target_attempt(model, prompt, case):
    before = len(model.calls)
    start = time.perf_counter()
    answer = None
    error = None
    try:
        answer = model.generate(TARGET_SYSTEM, {"user_prompt": prompt}, answer_schema(case["kind"]))
        check = asdict(validate_answer(case, answer))
    except (RuntimeError, ValueError, OSError) as exc:
        error = str(exc)
        check = {"passed": False, "reason": "execution_error"}
    return {
        "answer": answer,
        "validation": check,
        "error": error,
        "calls": model.calls[before:],
        "elapsed_ms": (time.perf_counter() - start) * 1000,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/task-quality-development.json"))
    parser.add_argument("--output", type=Path, default=Path("results/local/task-quality.json"))
    args = parser.parse_args()
    raw = args.input.read_bytes()
    corpus = json.loads(raw)
    config = corpus["protocol"]
    generator = OllamaModel(config["generator"], timeout=180)
    reviewer = OllamaModel(config["reviewer"], timeout=180)
    target = OllamaModel(config["target"], timeout=180)
    counter = TiktokenCounter()
    rng = random.Random(20261104)
    report = {
        "complete": False,
        "validator_source_sha256": hashlib.sha256(
            inspect.getsource(validation_module).encode()
        ).hexdigest(),
        "runtime": local_runtime(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_canonical_sha256": hashlib.sha256(
            json.dumps(corpus, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "protocol": config,
        "target_system": TARGET_SYSTEM,
        "transport_schemas": {
            k: answer_schema(k) for k in ("extraction", "filtering", "arithmetic", "code")
        },
        "generator_protocol_sha256": hashlib.sha256(
            inspect.getsource(_generate_phrase_options).encode()
        ).hexdigest(),
        "review_protocol_sha256": hashlib.sha256(
            (REVIEW_SYSTEM + json.dumps(REVIEW_SCHEMA, sort_keys=True)).encode()
        ).hexdigest(),
        "limitations": [
            "Synthetic development fixtures; five per category, with shared templates. Three repeated outputs per fixture are not independent task samples.",
            "Candidate preparation is reused across target repeats; standalone and reuse-amortized times are both reported.",
            "Structured JSON transport is used for all arms. Schemas specify types, not oracle values, counts or hidden code tests.",
            "The gate has a configured oracle. It is not universal semantic validation. Unsupported Python syntax fails validation; no model code is executed.",
            "Guarded mixed reuses the measured mixed first attempt; any original fallback is a real additional inference, not the original control answer.",
            "Input-content counts use o200k_base. Local inference counts, timings and model sizes are not interchangeable with API bills or energy cost.",
        ],
        "records": [],
    }
    wall = time.perf_counter()
    for case in corpus["items"]:
        request = Request.from_dict(case["request"])
        baseline = optimize(request, counter=counter, rule_modes=())
        gs = len(generator.calls)
        gen_start = time.perf_counter()
        error = None
        try:
            options = _generate_phrase_options(request, generator, ("en", "zh", "ja"), 5, 256)
        except (RuntimeError, ValueError) as exc:
            options = ()
            error = str(exc)
        generation_ms = (time.perf_counter() - gen_start) * 1000
        generation_calls = generator.calls[gs:]
        prepared = {}
        for arm in ("english", "mixed"):
            js = len(reviewer.calls)
            begin = time.perf_counter()
            chosen = baseline
            judgments = []
            arm_error = error
            if options:
                try:
                    selected_options = (
                        options if arm == "mixed" else tuple({"en": o["en"]} for o in options)
                    )
                    pool = optimize(
                        replace(request, phrase_options=selected_options),
                        counter=counter,
                        rule_modes=(),
                    )
                    chosen, judgments = _review_candidates(request, pool, reviewer, 8)
                except (RuntimeError, ValueError) as exc:
                    arm_error = str(exc)
            chosen_dict = chosen.to_dict()
            chosen_dict["candidates"] = [
                {k: v for k, v in c.items() if k != "prompt"} for c in chosen_dict["candidates"]
            ]
            prepared[arm] = {
                "result": chosen_dict,
                "judgments": judgments,
                "error": arm_error,
                "review_calls": reviewer.calls[js:],
                "preparation_ms": generation_ms + (time.perf_counter() - begin) * 1000,
            }
        record = {
            "id": case["id"],
            "kind": case["kind"],
            "generated_phrase_options": list(options),
            "generation_calls": generation_calls,
            "generation_ms": generation_ms,
            "prepared": prepared,
            "trials": [],
        }
        prompts = {
            "original": baseline.prompt,
            "english": prepared["english"]["result"]["prompt"],
            "mixed": prepared["mixed"]["result"]["prompt"],
        }
        for repeat in range(config["repeats"]):
            order = ["original", "english", "mixed"]
            rng.shuffle(order)
            trial = {"repeat": repeat + 1, "order": order, "arms": {}}
            for arm in order:
                attempt = target_attempt(target, prompts[arm], case)
                attempt["content_tokens_attempted"] = counter.count(prompts[arm])
                attempt["passed"] = attempt["validation"]["passed"]
                attempt["fallback_used"] = False
                trial["arms"][arm] = attempt
            # Share the observed mixed attempt only; fallback is always new inference.
            mixed = trial["arms"]["mixed"]
            extra = []
            first = True

            def execute(prompt):
                nonlocal first
                if first:
                    first = False
                    if mixed["error"]:
                        raise RuntimeError(mixed["error"])
                    return mixed["answer"]
                attempt = target_attempt(target, prompt, case)
                extra.append(attempt)
                if attempt["error"]:
                    raise RuntimeError(attempt["error"])
                return attempt["answer"]

            gate_start = time.perf_counter()
            gated = execute_checked(
                prompts["original"], prompts["mixed"], execute, lambda a: validate_answer(case, a)
            )
            gated["passed"] = gated["validated"]
            gated["fallback_used"] = bool(extra)
            gated["calls"] = mixed["calls"] + [c for attempt in extra for c in attempt["calls"]]
            gated["elapsed_ms"] = mixed["elapsed_ms"] + (time.perf_counter() - gate_start) * 1000
            gated["content_tokens_attempted"] = mixed["content_tokens_attempted"] + len(
                extra
            ) * counter.count(prompts["original"])
            trial["arms"]["guarded_mixed"] = gated
            record["trials"].append(trial)
        report["records"].append(record)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            case["id"],
            {
                a: sum(t["arms"][a]["passed"] for t in record["trials"])
                for a in ("original", "english", "mixed", "guarded_mixed")
            },
            flush=True,
        )
    summary = {}
    for arm in ("original", "english", "mixed", "guarded_mixed"):
        rows = [t["arms"][arm] for r in report["records"] for t in r["trials"]]
        prep_arm = "mixed" if arm == "guarded_mixed" else arm
        prep_ms = (
            sum(r["prepared"][prep_arm]["preparation_ms"] for r in report["records"])
            if arm != "original"
            else 0
        )
        prep_calls = (
            [
                c
                for r in report["records"]
                for c in r["generation_calls"] + r["prepared"][prep_arm]["review_calls"]
            ]
            if arm != "original"
            else []
        )
        target_calls = [c for row in rows for c in row["calls"]]
        summary[arm] = {
            "passed": sum(r["passed"] for r in rows),
            "trials": len(rows),
            "pass_rate": sum(r["passed"] for r in rows) / len(rows),
            "fallbacks": sum(r["fallback_used"] for r in rows),
            "content_tokens_attempted": sum(r["content_tokens_attempted"] for r in rows),
            "target_usage": count_usage(target_calls),
            "preparation_usage_once_per_fixture": count_usage(prep_calls),
            "standalone_ms_per_request": (
                sum(r["elapsed_ms"] for r in rows) + prep_ms * config["repeats"]
            )
            / len(rows),
            "reuse_amortized_ms_per_request": (sum(r["elapsed_ms"] for r in rows) + prep_ms)
            / len(rows),
            "by_kind": {
                kind: {
                    "passed": sum(
                        t["arms"][arm]["passed"]
                        for r in report["records"]
                        if r["kind"] == kind
                        for t in r["trials"]
                    ),
                    "trials": sum(len(r["trials"]) for r in report["records"] if r["kind"] == kind),
                }
                for kind in ("extraction", "filtering", "arithmetic", "code")
            },
        }
    report.update(
        complete=True,
        summary=summary,
        total_wall_ms=(time.perf_counter() - wall) * 1000,
        actual_experiment_usage={
            "generator": count_usage(generator.calls),
            "reviewer": count_usage(reviewer.calls),
            "target": count_usage(target.calls),
        },
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
