"""Calibrate instruction caches, test fresh inputs, then project larger reuse counts."""

import argparse
import hashlib
import inspect
import json
import random
import time
from dataclasses import replace
from pathlib import Path

from evaluate_task_quality import count_usage, target_attempt
from reuse_analysis import break_even_uses
from runtime_info import local_runtime

import multilingual_prompt_optimizer.template_cache as cache_module
import multilingual_prompt_optimizer.validation as validation_module
from multilingual_prompt_optimizer import (
    OllamaModel,
    Request,
    TemplateCache,
    TiktokenCounter,
    cache_context,
    optimize,
)
from multilingual_prompt_optimizer.automatic import _generate_phrase_options, _review_candidates
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM
from multilingual_prompt_optimizer.validation import execute_checked, validate_answer


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/template-reuse-development.json"))
    parser.add_argument("--output", type=Path, default=Path("results/local/template-reuse.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/local/template-cache"))
    parser.add_argument(
        "--refresh", action="store_true", help="Rebuild caches for a new measured preparation run"
    )
    args = parser.parse_args()
    corpus = json.loads(args.input.read_text(encoding="utf-8"))
    config = corpus["protocol"]
    generator = OllamaModel(config["generator"], timeout=240, **config["generator_options"])
    reviewer = OllamaModel(config["reviewer"], timeout=180)
    target = OllamaModel(config["target"], timeout=180)
    runtime = local_runtime()
    revisions = {m["name"]: m["digest"] for m in runtime["models"]}
    counter = TiktokenCounter()
    cache = TemplateCache(args.cache_dir)
    protocol = {
        "generator_source": hashlib.sha256(
            inspect.getsource(_generate_phrase_options).encode()
        ).hexdigest(),
        "review": digest([REVIEW_SYSTEM, REVIEW_SCHEMA]),
        "cache_policy": hashlib.sha256(inspect.getsource(cache_module).encode()).hexdigest(),
        "calibration_required": 2,
        "review_budget": 8,
        "target": {
            "name": target.model,
            "digest": revisions[target.model],
            "options": target.options,
        },
    }
    report = {
        "complete": False,
        "runtime": runtime,
        "protocol": config,
        "dataset_canonical_sha256": digest(corpus),
        "protocol_fingerprints": protocol,
        "measured_uses_per_template": [1, 10],
        "projected_uses_per_template": [100, 1000],
        "limitations": [
            "Four synthetic development templates. Test inputs were frozen before preparation and excluded from calibration; not an independent external test.",
            "One target execution per fresh input/policy. No general accuracy guarantee or accuracy projection for 100/1000 uses.",
            "Cache admission requires two passing calibration answers; every fresh input is still counted and answer-validated.",
            "Preparation was measured once per template, shared generation charged once to each hypothetical standalone candidate policy.",
            "100/1000-use time/content projections assume the ten observed inputs represent future requests. Loading/cache/order effects may change timings.",
            "No API bills, electricity use or monetary costs measured. Content tokens exclude wrappers. Available usage for service failures can be incomplete.",
        ],
        "templates": [],
    }
    rng = random.Random(505)
    overall = time.perf_counter()
    for index, template in enumerate(corpus["templates"]):
        case = template["calibration"][0]
        request = Request.from_dict(case["request"])
        oracle_digest = digest(case["oracle"])
        assert all(
            digest(c["oracle"]) == oracle_digest for c in template["calibration"] + template["test"]
        )
        validator = digest(
            {"source": inspect.getsource(validation_module), "oracle_digest": oracle_digest}
        )
        contexts = {
            arm: cache_context(
                request,
                tokenizer=counter.name,
                generator={
                    "name": generator.model,
                    "digest": revisions[generator.model],
                    "options": generator.options,
                },
                reviewer={
                    "name": reviewer.model,
                    "digest": revisions[reviewer.model],
                    "options": reviewer.options,
                },
                protocol=protocol,
                validator=validator,
                mode=arm,
            )
            for arm in ("english", "mixed")
        }
        if not args.refresh and any(cache.load(c) for c in contexts.values()):
            raise ValueError(
                "Existing measured cache found; use --refresh or a fresh cache directory"
            )
        gs = len(generator.calls)
        start = time.perf_counter()
        gen_error = None
        try:
            options = _generate_phrase_options(request, generator, ("en", "zh", "ja"), 5, 256)
        except (RuntimeError, ValueError) as exc:
            options = ()
            gen_error = str(exc)
        gen_ms = (time.perf_counter() - start) * 1000
        gen_calls = generator.calls[gs:]
        prepared = {}
        for arm in ("english", "mixed"):
            rs = len(reviewer.calls)
            start = time.perf_counter()
            chosen = optimize(request, counter=counter, rule_modes=())
            error = gen_error
            judgments = []
            if options:
                try:
                    subset = options if arm == "mixed" else tuple({"en": o["en"]} for o in options)
                    pool = optimize(
                        replace(request, phrase_options=subset), counter=counter, rule_modes=()
                    )
                    chosen, judgments = _review_candidates(request, pool, reviewer, 8)
                except (RuntimeError, ValueError) as exc:
                    error = str(exc)
            selected = next(
                c.instruction for c in chosen.candidates if c.label == chosen.selected_label
            )
            prepared[arm] = {
                "candidate_instruction": selected,
                "selected_label": chosen.selected_label,
                "original_tokens_on_representative": chosen.original_tokens,
                "selected_tokens_on_representative": chosen.selected_tokens,
                "judgments": judgments,
                "error": error,
                "review_calls": reviewer.calls[rs:],
                "preparation_ms": gen_ms + (time.perf_counter() - start) * 1000,
                "calibration": [],
            }
        # Alternate calibration order to distribute some warm-up/order effects.
        calibration_order = ["english", "mixed"] if index % 2 == 0 else ["mixed", "english"]
        for arm in calibration_order:
            for calibration in template["calibration"]:
                req = Request.from_dict(calibration["request"])
                from multilingual_prompt_optimizer import Candidate

                proposal = optimize(
                    replace(
                        req,
                        candidates=(
                            Candidate("candidate", prepared[arm]["candidate_instruction"]),
                        ),
                    ),
                    counter=counter,
                    rule_modes=(),
                )
                candidate_applied = (
                    proposal.selected_label != "original"
                    or prepared[arm]["candidate_instruction"] == req.instruction
                )
                if candidate_applied and not prepared[arm]["error"]:
                    attempt = target_attempt(target, proposal.prompt, calibration)
                else:
                    attempt = {
                        "answer": None,
                        "validation": {
                            "passed": False,
                            "reason": "candidate_not_applied_or_preparation_error",
                        },
                        "calls": [],
                        "elapsed_ms": 0,
                        "error": None,
                    }
                prepared[arm]["calibration"].append(
                    {"id": calibration["id"], "prompt": proposal.prompt, **attempt}
                )
                prepared[arm]["preparation_ms"] += attempt["elapsed_ms"]
            start = time.perf_counter()
            artifact = cache.save(
                contexts[arm],
                prepared[arm]["candidate_instruction"],
                [a["validation"]["passed"] for a in prepared[arm]["calibration"]],
            )
            prepared[arm]["preparation_ms"] += (time.perf_counter() - start) * 1000
            prepared[arm]["cache_artifact"] = artifact
        controls = []
        for calibration in template["calibration"]:
            req = Request.from_dict(calibration["request"])
            controls.append(
                {
                    "id": calibration["id"],
                    **target_attempt(target, req.compose(req.instruction), calibration),
                }
            )
        row = {
            "id": template["id"],
            "instruction_tokens": counter.count(template["instruction"]),
            "generated_phrase_options": list(options),
            "generation_calls": gen_calls,
            "generation_ms": gen_ms,
            "prepared": prepared,
            "original_calibration_controls": controls,
            "test": [],
        }
        for fresh in template["test"]:
            req = Request.from_dict(fresh["request"])
            original = req.compose(req.instruction)
            order = ["original", "english", "mixed"]
            rng.shuffle(order)
            trial = {"id": fresh["id"], "kind": fresh["kind"], "order": order, "policies": {}}
            for arm in order:
                if arm == "original":
                    attempt = target_attempt(target, original, fresh)
                    trial["policies"][arm] = {
                        "passed": attempt["validation"]["passed"],
                        "candidate_passed": attempt["validation"]["passed"],
                        "fallback_used": False,
                        "attempts": [attempt],
                        "content_tokens_attempted": counter.count(original),
                        "elapsed_ms": attempt["elapsed_ms"],
                        "calls": attempt["calls"],
                    }
                    continue
                call_start = len(target.calls)
                start = time.perf_counter()
                application = cache.apply(contexts[arm], req.payload, counter)
                attempts = []

                def execute(prompt):
                    attempt = target_attempt(target, prompt, fresh)
                    attempt["prompt_tokens"] = counter.count(prompt)
                    attempts.append(attempt)
                    if attempt["error"]:
                        raise RuntimeError(attempt["error"])
                    return attempt["answer"]

                outcome = execute_checked(
                    original, application["prompt"], execute, lambda a: validate_answer(fresh, a)
                )
                trial["policies"][arm] = {
                    "passed": outcome["validated"],
                    "candidate_passed": attempts[0]["validation"]["passed"],
                    "fallback_used": len(attempts) > 1,
                    "cache_application": application,
                    "outcome": outcome,
                    "attempts": attempts,
                    "content_tokens_attempted": sum(a["prompt_tokens"] for a in attempts),
                    "elapsed_ms": (time.perf_counter() - start) * 1000,
                    "calls": target.calls[call_start:],
                }
            row["test"].append(trial)
        report["templates"].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            template["id"],
            {
                "admitted": {a: prepared[a]["cache_artifact"]["admitted"] for a in prepared},
                "passes": {
                    a: sum(t["policies"][a]["passed"] for t in row["test"])
                    for a in ("original", "english", "mixed")
                },
            },
            flush=True,
        )
    summary = {}
    projections = {}
    for arm in ("original", "english", "mixed"):
        data = [t["policies"][arm] for r in report["templates"] for t in r["test"]]
        prep = (
            sum(r["prepared"][arm]["preparation_ms"] for r in report["templates"])
            if arm != "original"
            else 0
        )
        mean_total = sum(
            sum(t["policies"][arm]["elapsed_ms"] for t in r["test"]) / len(r["test"])
            for r in report["templates"]
        )
        summary[arm] = {
            "passed": sum(d["passed"] for d in data),
            "inputs": len(data),
            "candidate_passed": sum(d["candidate_passed"] for d in data),
            "fallbacks": sum(d["fallback_used"] for d in data),
            "content_tokens_attempted": sum(d["content_tokens_attempted"] for d in data),
            "preparation_ms": prep,
            "mean_execution_ms_per_request": mean_total / len(report["templates"]),
            "target_usage": count_usage([c for d in data for c in d["calls"]]),
            "distinct_prompt_inputs": sum(
                d.get("cache_application", {}).get("selected_label", "original") != "original"
                for d in data
            ),
        }
        projections[arm] = {}
        for n in config["reuse_points"]:
            measured = n in config["measured_points"]
            cost = (
                sum(
                    sum(t["policies"][arm]["elapsed_ms"] for t in r["test"][:n])
                    for r in report["templates"]
                )
                if measured
                else n * mean_total
            )
            content = (
                sum(
                    sum(t["policies"][arm]["content_tokens_attempted"] for t in r["test"][:n])
                    for r in report["templates"]
                )
                if measured
                else n
                * sum(
                    sum(t["policies"][arm]["content_tokens_attempted"] for t in r["test"])
                    / len(r["test"])
                    for r in report["templates"]
                )
            )
            passed = (
                sum(
                    sum(t["policies"][arm]["passed"] for t in r["test"][:n])
                    for r in report["templates"]
                )
                if measured
                else None
            )
            projections[arm][str(n)] = {
                "measured": measured,
                "requests": n * len(report["templates"]),
                "total_ms_including_preparation": prep + cost,
                "ms_per_request": (prep + cost) / (n * len(report["templates"])),
                "preparation_ms_per_request": prep / (n * len(report["templates"])),
                "content_tokens_attempted": content,
                "passed": passed,
            }
    baseline = summary["original"]["mean_execution_ms_per_request"] * len(report["templates"])
    for arm in ("english", "mixed"):
        summary[arm]["projected_time_break_even_uses_per_template"] = break_even_uses(
            summary[arm]["preparation_ms"],
            baseline,
            summary[arm]["mean_execution_ms_per_request"] * len(report["templates"]),
            summary[arm]["distinct_prompt_inputs"] > 0,
        )
    report.update(
        complete=True,
        summary=summary,
        reuse=projections,
        actual_experiment_usage={
            "generator": count_usage(generator.calls),
            "reviewer": count_usage(reviewer.calls),
            "target": count_usage(target.calls),
        },
        total_wall_ms=(time.perf_counter() - overall) * 1000,
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
