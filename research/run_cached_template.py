"""Reuse a pinned study cache on one source input, with fresh task validation."""

import argparse
import hashlib
import inspect
import json
from pathlib import Path

from runtime_info import local_runtime

import multilingual_prompt_optimizer.template_cache as cache_module
import multilingual_prompt_optimizer.validation as validation_module
from multilingual_prompt_optimizer import (
    OllamaModel,
    Request,
    TemplateCache,
    TiktokenCounter,
    cache_context,
    execute_checked,
    validate_answer,
)
from multilingual_prompt_optimizer.automatic import _generate_phrase_options
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM
from multilingual_prompt_optimizer.validation import answer_schema


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-compression", action="store_true")
    parser.add_argument("--input", type=Path, default=Path("data/template-reuse-development.json"))
    parser.add_argument("--study", type=Path, default=Path("results/template-reuse-v050.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/local/v050-template-cache"))
    parser.add_argument("--template", default="code")
    parser.add_argument(
        "--index", type=int, default=0, help="Index of an input in the recorded test split"
    )
    parser.add_argument("--mode", choices=["english", "mixed"], default="mixed")
    parser.add_argument("--output", type=Path, default=Path("results/local/cached-demo.json"))
    args = parser.parse_args()
    corpus = json.loads(args.input.read_text(encoding="utf-8"))
    study = json.loads(args.study.read_text(encoding="utf-8"))
    template = next(t for t in corpus["templates"] if t["id"] == args.template)
    recorded = next(t for t in study["templates"] if t["id"] == args.template)["prepared"][
        args.mode
    ]["cache_artifact"]["context"]
    if args.index < 0 or args.index >= len(template["test"]):
        raise ValueError("Index is outside recorded test inputs")
    case = template["test"][args.index]
    request = Request.from_dict(case["request"])
    runtime = local_runtime()
    revisions = {m["name"]: m["digest"] for m in runtime["models"]}
    for profile in (recorded["generator"], recorded["reviewer"], recorded["protocol"]["target"]):
        if revisions.get(profile["name"]) != profile["digest"]:
            raise ValueError("Model revision changed; prepare and calibrate a new cache")
    protocol = {
        "generator_source": hashlib.sha256(
            inspect.getsource(_generate_phrase_options).encode()
        ).hexdigest(),
        "review": digest([REVIEW_SYSTEM, REVIEW_SCHEMA]),
        "cache_policy": hashlib.sha256(inspect.getsource(cache_module).encode()).hexdigest(),
        "calibration_required": 2,
        "review_budget": 8,
        "target": recorded["protocol"]["target"],
    }
    validator = digest(
        {"source": inspect.getsource(validation_module), "oracle_digest": digest(case["oracle"])}
    )
    counter = TiktokenCounter()
    context = cache_context(
        request,
        tokenizer=counter.name,
        generator=recorded["generator"],
        reviewer=recorded["reviewer"],
        protocol=protocol,
        validator=validator,
        mode=args.mode,
    )
    applied = TemplateCache(args.cache_dir).apply(
        context, request.payload, counter, allow_compression=args.enable_compression
    )
    target = OllamaModel(recorded["protocol"]["target"]["name"])
    if target.options != recorded["protocol"]["target"]["options"]:
        raise ValueError("Target options changed; recalibrate before using this cache")

    def execute(prompt):
        return target.generate(
            "Perform the task in user_prompt. Return the answer in the supplied JSON transport schema. Put requested Python code in code; otherwise put the requested result in answer. Do not add commentary.",
            {"user_prompt": prompt},
            answer_schema(case["kind"]),
        )

    result = execute_checked(
        request.compose(request.instruction),
        applied["prompt"],
        execute,
        lambda answer: validate_answer(case, answer),
    )
    report = {
        "case_id": case["id"],
        "template": args.template,
        "cache_application": applied,
        "preparation_model_calls": 0,
        "execution": result,
        "target_calls": target.calls,
        "note": "This reuses a recorded synthetic example, not a new independent accuracy trial.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cache_hit": applied["cache_hit"],
                "reason": applied["reason"],
                "saved_tokens": applied["saved_tokens"],
                "validated": result["validated"],
                "preparation_model_calls": 0,
                "target_calls": len(target.calls),
            }
        )
    )
    return 0 if result["validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
