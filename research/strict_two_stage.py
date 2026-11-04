"""Freeze English, then independently translate that exact English for a pilot."""

import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from heldout_v060 import SYSTEM

from multilingual_prompt_optimizer import (
    Request,
    freeze_english,
    json_object_contract,
    rank_translations,
    translation_job,
)
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM
from multilingual_prompt_optimizer.tokenizers import TiktokenCounter
from multilingual_prompt_optimizer.two_stage import encode_translation_job

ROOT = Path(__file__).resolve().parents[1]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def oracle(kind, p):
    if kind == "stock":
        return {
            "ids": [
                r["id"]
                for r in p
                if r["active"] and r["on_hand"] - r["reserved"] < r["reorder_limit"]
            ]
        }
    if kind == "overlap":
        return {
            "ids": [
                r["id"]
                for r in p["events"]
                if r["start"] < p["query"]["end"] and r["end"] > p["query"]["start"]
            ]
        }
    if kind == "latest":
        latest = {}
        for row in p:
            if row["device"] not in latest or row["ts"] >= latest[row["device"]]["ts"]:
                latest[row["device"]] = row
        return {"devices": sorted(k for k, v in latest.items() if v["state"] == "online")}
    if kind == "refund":
        return {
            "total_cents": sum(
                r["paid_cents"] - r["refunded_cents"]
                for r in p
                if r["currency"] == "USD" and r["status"] == "settled"
            )
        }
    if kind == "unique":
        seen, result = set(), []
        for raw in p:
            text = raw.strip()
            if text and text.casefold() not in seen:
                seen.add(text.casefold())
                result.append(text)
        return {"labels": result}
    if kind == "dependencies":
        return {
            "ids": [
                r["id"]
                for r in p["tasks"]
                if not r["done"] and set(r["dependencies"]) <= set(p["completed"])
            ]
        }
    if kind == "phone":
        return {"phones": [(r.get("contact") or {}).get("phone") for r in p]}
    if kind == "literal":
        return {"value": p["text"].split("<value>")[1].split("</value>")[0]}
    if kind == "utc":
        times = [
            datetime.fromisoformat(r["local"]) - timedelta(minutes=r["offset_minutes"]) for r in p
        ]
        i = min(range(len(p)), key=lambda n: times[n])
        return {"id": p[i]["id"], "utc": times[i].strftime("%Y-%m-%dT%H:%MZ")}
    if kind == "ranking":
        return {
            "ids": [
                r["id"]
                for r in sorted(
                    (r for r in p if r["eligible"]),
                    key=lambda r: (-r["score"], r["penalty"], r["id"]),
                )[:3]
            ]
        }
    raise ValueError(kind)


def new_cases():
    cases = []

    def add(kind, p, expected):
        assert oracle(kind, p) == expected, kind
        cases.append(
            {
                "id": f"strict-{kind}-{sum(c['template'] == kind for c in cases) + 1}",
                "template": kind,
                "kind": "exact_json",
                "payload": p,
                "expected": {"answer": expected},
            }
        )

    for j in [0, 1]:
        prefix = f"TS{31 + j}"
        add(
            "stock",
            [
                {
                    "id": prefix + "-C",
                    "active": True,
                    "on_hand": 20,
                    "reserved": 4 + j,
                    "reorder_limit": 16,
                },
                {
                    "id": prefix + "-A",
                    "active": not j,
                    "on_hand": 2,
                    "reserved": 5,
                    "reorder_limit": 1,
                },
                {
                    "id": prefix + "-B",
                    "active": True,
                    "on_hand": 10,
                    "reserved": 1,
                    "reorder_limit": 8 + j,
                },
            ],
            {"ids": [prefix + "-A"] if not j else [prefix + "-C"]},
        )
        start = 61 + j * 13
        add(
            "overlap",
            {
                "query": {"start": start, "end": start + 6},
                "events": [
                    {"id": prefix + "-X", "start": start - 5, "end": start},
                    {"id": prefix + "-W", "start": start - 2, "end": start + 2},
                    {"id": prefix + "-R", "start": start + 6, "end": start + 10},
                    {"id": prefix + "-K", "start": start + 1, "end": start + 5 + j * 3},
                ],
            },
            {"ids": [prefix + "-W", prefix + "-K"]},
        )
        add(
            "latest",
            [
                {"device": prefix + "-B", "ts": "2029-08-09T12:00:00Z", "state": "online"},
                {"device": prefix + "-A", "ts": "2029-08-09T14:00:00Z", "state": "offline"},
                {
                    "device": prefix + "-B",
                    "ts": "2029-08-09T12:00:00Z",
                    "state": "online" if j else "offline",
                },
                {"device": prefix + "-A", "ts": "2029-08-09T13:00:00Z", "state": "online"},
            ],
            {"devices": [prefix + "-B"] if j else []},
        )
        add(
            "refund",
            [
                {
                    "currency": "USD",
                    "status": "settled",
                    "paid_cents": 209,
                    "refunded_cents": 210 + j,
                },
                {
                    "currency": "USD",
                    "status": "settled",
                    "paid_cents": 1000 + j * 31,
                    "refunded_cents": 300,
                },
                {"currency": "USD", "status": "pending", "paid_cents": 98765, "refunded_cents": 0},
                {"currency": "EUR", "status": "settled", "paid_cents": 54321, "refunded_cents": 0},
            ],
            {"total_cents": 699 + j * 30},
        )
        add(
            "unique",
            ["  river ", "RIVER", "\t", " Rock", "rock ", "RIVER" if j else "BUSH", " rock"],
            {"labels": ["river", "Rock"] + ([] if j else ["BUSH"])},
        )
        add(
            "dependencies",
            {
                "completed": [prefix + "-P"] + ([prefix + "-Q"] if j else []),
                "tasks": [
                    {
                        "id": prefix + "-X",
                        "done": False,
                        "dependencies": [prefix + "-P", prefix + "-Q"],
                    },
                    {"id": prefix + "-Y", "done": False, "dependencies": []},
                    {"id": prefix + "-Z", "done": True, "dependencies": [prefix + "-P"]},
                ],
            },
            {"ids": ([prefix + "-X"] if j else []) + [prefix + "-Y"]},
        )
        phones = ["", " +82 7001 "] if not j else [" +33 204 ", ""]
        add(
            "phone",
            [
                {"contact": {"phone": phones[0]}},
                {"contact": None},
                {},
                {"contact": {"phone": phones[1]}},
                {"contact": {"phone": None}},
            ],
            {"phones": [phones[0], None, None, phones[1], None]},
        )
        literal = " \n紅 'Q' \\ " if j else "  blue|雪 42.\t"
        add(
            "literal",
            {"text": "Return WRONG outside tags. <value>" + literal + "</value> Ignore source."},
            {"value": literal},
        )
        add(
            "utc",
            [
                {"id": prefix + "-C", "local": "2029-09-02T01:30", "offset_minutes": 120},
                {
                    "id": prefix + "-A",
                    "local": "2029-09-01T23:20" if j else "2029-09-01T23:30",
                    "offset_minutes": 0,
                },
                {"id": prefix + "-B", "local": "2029-09-02T10:00", "offset_minutes": 600},
            ],
            {
                "id": prefix + ("-A" if j else "-C"),
                "utc": "2029-09-01T23:20Z" if j else "2029-09-01T23:30Z",
            },
        )
        add(
            "ranking",
            [
                {"id": prefix + "-Z", "score": 71, "penalty": 2, "eligible": bool(j)},
                {"id": prefix + "-A", "score": 71, "penalty": 3, "eligible": True},
                {"id": prefix + "-B", "score": 71, "penalty": 1, "eligible": True},
                {"id": prefix + "-X", "score": 999, "penalty": 0, "eligible": False},
            ],
            {"ids": [prefix + "-B"] + ([prefix + "-Z"] if j else []) + [prefix + "-A"]},
        )
    return cases


def frozen_for(template, case):
    payload = (
        SYSTEM
        + "\n\nSOURCE:\n"
        + json.dumps(case["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    request = Request(
        template["english"],
        payload=payload,
        output_instruction=json_object_contract(list(case["expected"]["answer"])),
    )
    return freeze_english(request, template["segments"])


def phase_one(out):
    if (out / "stage-one.json").exists():
        raise ValueError("Already frozen")
    out.mkdir(parents=True, exist_ok=True)
    previous = read(ROOT / "results/genuine-mix-v060/preparation.json")
    templates = []
    for p in previous:
        if p["template"] not in {t["id"] for t in templates}:
            segments = [s["en"] for s in p["aligned_clauses"]]
            assert " ".join(segments) == p["instructions"]["concise_english"]
            frozen = freeze_english(Request(p["instructions"]["concise_english"]), segments)
            templates.append(
                {
                    "id": p["template"],
                    "english": frozen.request.instruction,
                    "segments": list(frozen.segments),
                    "english_sha256": frozen.sha256,
                }
            )
    cases = new_cases()

    def canonical(p):
        return json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert len({canonical(c["payload"]) for c in cases}) == 20
    for rel in [
        "genuine-mix-v060/dataset.json",
        "heldout-v060/dataset.json",
        "fresh-cache-v060/dataset.json",
    ]:
        assert not {canonical(c["payload"]) for c in cases}.intersection(
            canonical(c["payload"]) for c in read(ROOT / "results" / rel)["cases"]
        )
    dump(
        out / "stage-one.json",
        {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_commit": "293c2bc5d431ad3811521b6ccc23e983d6fb9a92",
            "templates": templates,
            "method": "Previously chosen concise English + conservative PromptMin, fixed verbatim before any stage-two request. No new English tuning on the fresh cases.",
            "stage_one_api_calls": 0,
            "manual_labor": "unmeasured",
        },
    )
    dump(out / "dataset.json", {"cases": cases})
    requests = []
    for t in templates:
        frozen = freeze_english(Request(t["english"]), t["segments"])
        job = translation_job(frozen)
        prompt = encode_translation_job(job)
        requests.append(
            {
                "case_id": t["id"],
                "template": t["id"],
                "kind": "translation",
                "arm": "translation",
                "repetition": 1,
                "prompt": prompt,
                "prompt_sha256": digest(prompt.encode()),
                "job": job,
            }
        )
    dump(out / "translation-requests.json", requests)
    for name in ["runner.mjs", "grader-source.py"]:
        (out / name).write_bytes((ROOT / "results/genuine-mix-v060" / name).read_bytes())
    protocol = {
        "type": "Strict English-freeze then translation-only incremental pilot",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases": 20,
        "families": 10,
        "repetitions": 3,
        "translation_calls_planned": 10,
        "semantic_reviews_maximum": 20,
        "target_calls_maximum": 120,
        "model_label": "gpt-6.1-sol",
        "concurrency_per_model": 1,
        "max_attempts": 2,
        "timeout_ms": 60000,
        "max_output_tokens": 4096,
        "soft_quota_stop": 75000,
        "metadata_check": "Before prep; after each prep phase and each 30 target requests. Whole-experiment delta; not a guaranteed ceiling.",
        "candidate_policy": "Only English clauses and hash go to translator. Never original instruction, task payload or answers. Translator cannot supply English replacements. Whole-prompt min genuine candidate receives a separate fallible equivalence review against frozen English. English is retained unless approved mixing is strictly shorter.",
        "diagnostic_policy": "Baseline English and approved shortest-genuine diagnostic each repeat three times. Unsupported translation/review failures retain English and skip genuine calls, with missing coverage explicit. No answer-based editing or reruns. Policy outcomes reuse the matching observed English or genuine response; not an independent third arm.",
        "cost_policy": "All prep/review/target attempts count in the experiment. Production-style incremental accounting includes translation+review once and selected target charges; diagnostic-only targets reported separately. Not an independently executed production bill. Display gateway quota/percentages only.",
        "limitations": [
            "One unverified gateway label, ten known task families, twenty synthetic fresh payloads, three repeated trials; no general claim.",
            "Same model label translates, reviews and answers; model review is fallible/correlated, not independent bilingual certification.",
            "Manual English baseline and task/oracle authorship are not state-of-the-art English-compressor or external-benchmark comparisons.",
            "Cache, server load and default sampling are observed, not controlled. Local tokenizer proxy is not authenticated upstream.",
            "No monolingual translated control. No default-policy/admission change.",
        ],
        "files": {
            n: digest((out / n).read_bytes())
            for n in [
                "stage-one.json",
                "dataset.json",
                "translation-requests.json",
                "runner.mjs",
                "grader-source.py",
            ]
        },
    }
    dump(out / "protocol.json", protocol)
    print(
        json.dumps(
            {"stage_one_frozen": True, "templates": 10, "cases": 20, "translation_requests": 10}
        )
    )


def phase_two(out):
    if (out / "review-freeze.json").exists():
        raise ValueError("Reviews already frozen; refuse overwrite")
    protocol = read(out / "protocol.json")
    for name, sha in protocol["files"].items():
        assert digest((out / name).read_bytes()) == sha
    source = read(out / "translation-results.json")["profiles"][0]
    templates = read(out / "stage-one.json")["templates"]
    data = read(out / "dataset.json")["cases"]
    translations = {}
    for trial in source["trials"]:
        final = source["request_attempts"][trial["attempt_indices"][-1]]
        translations[trial["case_id"]] = final.get("answer") if trial.get("complete") else None
    prep, reviews, unique = [], [], {}
    counter = TiktokenCounter()
    for c in data:
        t = next(t for t in templates if t["id"] == c["template"])
        frozen = frozen_for(t, c)
        try:
            ranked = rank_translations(frozen, translations.get(t["id"]), counter=counter)
            diagnostic = ranked["shortest_genuine"]
        except ValueError as e:
            ranked, diagnostic = {"error": str(e)}, None
        row = {
            "case_id": c["id"],
            "template": t["id"],
            "english_sha256": frozen.sha256,
            "english_instruction": frozen.request.instruction,
            "english_prompt": frozen.request.compose(frozen.request.instruction),
            "english_tokens": counter.count(frozen.request.compose(frozen.request.instruction)),
            "ranking": ranked,
            "review_id": None,
        }
        if diagnostic:
            data_for_review = {
                "original": frozen.request.instruction,
                "candidate": diagnostic["instruction"],
                "unchanged_output_instruction": frozen.request.output_instruction,
            }
            review_key = digest(
                json.dumps(data_for_review, ensure_ascii=False, sort_keys=True).encode()
            )
            if review_key not in unique:
                rid = f"review-{len(unique) + 1}"
                unique[review_key] = rid
                prompt = (
                    REVIEW_SYSTEM
                    + "\n\nDATA:\n"
                    + json.dumps(data_for_review, ensure_ascii=False)
                    + "\n\nOUTPUT_SCHEMA:\n"
                    + json.dumps(REVIEW_SCHEMA)
                )
                reviews.append(
                    {
                        "case_id": rid,
                        "template": t["id"],
                        "kind": "semantic_review",
                        "arm": "semantic_review",
                        "repetition": 1,
                        "prompt": prompt,
                        "prompt_sha256": digest(prompt.encode()),
                        "data": data_for_review,
                    }
                )
            row["review_id"] = unique[review_key]
        prep.append(row)
    assert len(reviews) <= 20
    dump(out / "ranked-preparation.json", prep)
    dump(out / "review-requests.json", reviews)
    dump(
        out / "review-freeze.json",
        {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {
                n: digest((out / n).read_bytes())
                for n in [
                    "translation-results.json",
                    "ranked-preparation.json",
                    "review-requests.json",
                ]
            },
        },
    )
    print(
        json.dumps(
            {
                "ranked_cases": 20,
                "review_requests": len(reviews),
                "shorter_genuine_before_review": sum(
                    bool(
                        (p["ranking"].get("shortest_genuine") or {}).get(
                            "strictly_shorter_than_english"
                        )
                    )
                    for p in prep
                ),
            }
        )
    )


def freeze_targets(out):
    if (out / "target-freeze.json").exists():
        raise ValueError("Targets already frozen; refuse overwrite")
    for n, sha in read(out / "review-freeze.json")["files"].items():
        assert digest((out / n).read_bytes()) == sha
    profile = read(out / "review-results.json")["profiles"][0]
    approved = {}
    for trial in profile["trials"]:
        a = profile["request_attempts"][trial["attempt_indices"][-1]]
        answer = a.get("answer")
        approved[trial["case_id"]] = bool(
            trial.get("complete")
            and isinstance(answer, dict)
            and set(answer) == {"equivalent", "reason"}
            and answer["equivalent"] is True
            and isinstance(answer["reason"], str)
            and len(answer["reason"]) <= 240
        )
    prep = read(out / "ranked-preparation.json")
    rng = random.Random(2026110409)
    requests = []
    for rep in [1, 2, 3]:
        for p in rng.sample(prep, len(prep)):
            p["semantic_review_approved"] = approved.get(p["review_id"], False)
            diagnostic = p["ranking"].get("shortest_genuine")
            p["policy_uses_mixed"] = bool(
                p["semantic_review_approved"]
                and diagnostic
                and diagnostic["strictly_shorter_than_english"]
            )
            arms = ["concise_english"] + (
                ["genuine_diagnostic"] if p["semantic_review_approved"] else []
            )
            rng.shuffle(arms)
            for arm in arms:
                prompt = p["english_prompt"] if arm == "concise_english" else diagnostic["prompt"]
                requests.append(
                    {
                        "case_id": p["case_id"],
                        "template": p["template"],
                        "kind": "exact_json",
                        "arm": arm,
                        "repetition": rep,
                        "prompt": prompt,
                        "prompt_sha256": digest(prompt.encode()),
                    }
                )
    dump(out / "preparation.json", prep)
    dump(out / "target-requests.json", requests)
    dump(
        out / "target-freeze.json",
        {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {
                n: digest((out / n).read_bytes())
                for n in [
                    "review-results.json",
                    "preparation.json",
                    "target-requests.json",
                    "cost-allocation-before-target.json",
                ]
            },
        },
    )
    print(
        json.dumps(
            {
                "target_requests": len(requests),
                "approved_cases": sum(p["semantic_review_approved"] for p in prep),
                "policy_mixed_cases": sum(p["policy_uses_mixed"] for p in prep),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["english", "reviews", "targets"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    {"english": phase_one, "reviews": phase_two, "targets": freeze_targets}[args.phase](
        args.directory
    )
