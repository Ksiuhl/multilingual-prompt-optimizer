"""Offline audit of the strict staged pilot, including paid preparation."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import re
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from strict_two_stage import frozen_for, oracle

from multilingual_prompt_optimizer import (
    Request,
    freeze_english,
    rank_translations,
    translation_job,
)
from multilingual_prompt_optimizer.semantic import REVIEW_SCHEMA, REVIEW_SYSTEM
from multilingual_prompt_optimizer.two_stage import encode_translation_job


def raw(d, name):
    p = d / name
    return p.read_bytes() if p.exists() else gzip.decompress((d / (name + ".gz")).read_bytes())


def read(d, name):
    return json.loads(raw(d, name))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def audit(d, out):
    protocol = read(d, "protocol.json")
    for freeze_name in ["protocol.json", "review-freeze.json", "target-freeze.json"]:
        for name, expected in read(d, freeze_name)["files"].items():
            assert sha(raw(d, name)) == expected, name
    english = read(d, "stage-one.json")
    repo = Path(__file__).resolve().parents[1]
    for name, expected in read(d, "implementation-manifest.json")["files"].items():
        assert sha((repo / name).read_bytes()) == expected
    templates = {t["id"]: t for t in english["templates"]}
    cases = {c["id"]: c for c in read(d, "dataset.json")["cases"]}
    assert len(cases) == 20 and len(templates) == 10

    def canonical(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    payloads = {canonical(c["payload"]) for c in cases.values()}
    assert len(payloads) == 20
    for c in cases.values():
        assert oracle(c["template"], c["payload"]) == c["expected"]["answer"]
    for rel in [
        "genuine-mix-v060/dataset.json",
        "heldout-v060/dataset.json",
        "fresh-cache-v060/dataset.json",
    ]:
        assert not payloads.intersection(
            canonical(c["payload"])
            for c in json.loads((repo / "results" / rel).read_text(encoding="utf-8"))["cases"]
        )
    prep = {p["case_id"]: p for p in read(d, "preparation.json")}
    for t in templates.values():
        f = freeze_english(Request(t["english"]), t["segments"])
        assert f.sha256 == t["english_sha256"]
    for r in read(d, "translation-requests.json"):
        t = templates[r["case_id"]]
        job = translation_job(freeze_english(Request(t["english"]), t["segments"]))
        assert r["job"] == job and r["prompt"] == encode_translation_job(job)
        assert set(job["data"]) == {"frozen_english_sha256", "english_segments", "target_languages"}
    translated = read(d, "translation-results.json")["profiles"][0]
    translations = {
        t["case_id"]: translated["request_attempts"][t["attempt_indices"][-1]].get("answer")
        for t in translated["trials"]
    }
    for cid, p in prep.items():
        frozen = frozen_for(templates[p["template"]], cases[cid])
        assert (
            p["english_sha256"] == frozen.sha256
            and p["english_instruction"] == frozen.request.instruction
        )
        assert p["english_prompt"] == frozen.request.compose(frozen.request.instruction)
        try:
            ranked = rank_translations(frozen, translations.get(p["template"]))
            assert ranked["shortest_genuine"] == p["ranking"]["shortest_genuine"]
            assert ranked["provenance"] == p["ranking"]["provenance"]
            diagnostic = ranked["shortest_genuine"]
            if diagnostic:
                for lang, segment in zip(diagnostic["languages"], diagnostic["segments"]):
                    if lang == "en":
                        assert segment in frozen.segments
                    else:
                        assert len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", segment)) >= 4
        except ValueError:
            assert "error" in p["ranking"]
    for r in read(d, "review-requests.json"):
        assert r["prompt"] == REVIEW_SYSTEM + "\n\nDATA:\n" + json.dumps(
            r["data"], ensure_ascii=False
        ) + "\n\nOUTPUT_SCHEMA:\n" + json.dumps(REVIEW_SCHEMA)
        matching = [p for p in prep.values() if p["review_id"] == r["case_id"]]
        assert matching
        for p in matching:
            assert r["data"]["original"] == p["english_instruction"]
            assert r["data"]["candidate"] == p["ranking"]["shortest_genuine"]["instruction"]
    reviews = read(d, "review-results.json")["profiles"][0]
    opinions = {}
    for t in reviews["trials"]:
        a = reviews["request_attempts"][t["attempt_indices"][-1]]
        opinion = a.get("answer")
        opinions[t["case_id"]] = bool(
            t.get("complete")
            and isinstance(opinion, dict)
            and set(opinion) == {"equivalent", "reason"}
            and opinion["equivalent"] is True
            and isinstance(opinion["reason"], str)
            and len(opinion["reason"]) <= 240
        )
    for p in prep.values():
        assert p["semantic_review_approved"] == opinions.get(p["review_id"], False)
        genuine = p["ranking"].get("shortest_genuine")
        assert p["policy_uses_mixed"] == bool(
            p["semantic_review_approved"] and genuine and genuine["strictly_shorter_than_english"]
        )
    spec = importlib.util.spec_from_file_location("strict_frozen_grader", d / "grader-source.py")
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    grader.self_check(list(cases.values()))
    bills = {}
    for b in read(d, "billing-matched.json")["records"]:
        if b["type"] == 2:
            assert b["request_id"] not in bills and type(b["quota"]) is int and b["quota"] >= 0
            bills[b["request_id"]] = b
    all_rows, attempts, seen_ids, phases = [], [], set(), {}
    for phase, req_name, result_name in [
        ("translation", "translation-requests.json", "translation-results.json"),
        ("review", "review-requests.json", "review-results.json"),
        ("target", "target-requests.json", "target-results.json"),
    ]:
        requests = read(d, req_name)
        report = read(d, result_name)
        assert report["dataset_sha256"] == protocol["files"]["dataset.json"]
        assert report["prepared_source_sha256"] == sha(raw(d, req_name))
        profile = report["profiles"][0]
        frozen_time = (
            english["frozen_at_utc"]
            if phase == "translation"
            else read(d, "review-freeze.json" if phase == "review" else "target-freeze.json")[
                "frozen_at_utc"
            ]
        )
        if profile["request_attempts"]:
            assert datetime.fromisoformat(frozen_time) <= datetime.fromisoformat(
                profile["request_attempts"][0]["started_at_utc"]
            )
        assert profile["label"] == protocol["model_label"]
        assert [(t["case_id"], t["arm"], t["repetition"]) for t in profile["trials"]] == [
            (r["case_id"], r["arm"], r["repetition"]) for r in requests[: len(profile["trials"])]
        ]
        used = set()
        for t, r in zip(profile["trials"], requests):
            assert t["prompt_sha256"] == r["prompt_sha256"] == sha(r["prompt"].encode())
            trial_attempts = []
            for index in t["attempt_indices"]:
                assert index not in used
                used.add(index)
                a = profile["request_attempts"][index]
                assert a["prompt_sha256"] == r["prompt_sha256"]
                rid = a.get("gateway_request_id")
                if rid:
                    assert rid not in seen_ids
                    seen_ids.add(rid)
                b = bills.get(rid)
                usage = a.get("usage") or {}
                if usage and b:
                    assert (
                        usage["prompt_tokens"] == b["prompt_tokens"]
                        and usage["completion_tokens"] == b["completion_tokens"]
                    )
                row = {
                    "phase": phase,
                    "case_id": r["case_id"],
                    "arm": r["arm"],
                    "repetition": r["repetition"],
                    "attempt_index": index,
                    "request_id": rid,
                    "complete": bool(a.get("complete")),
                    "http_status": a.get("http_status"),
                    "error_type": a.get("error_type"),
                    "quota": b["quota"] if b else None,
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                }
                attempts.append(row)
                trial_attempts.append(row)
            final = profile["request_attempts"][t["attempt_indices"][-1]]
            first = profile["request_attempts"][t["attempt_indices"][0]]
            elapsed = (
                datetime.fromisoformat(final["started_at_utc"])
                - datetime.fromisoformat(first["started_at_utc"])
            ).total_seconds() * 1000 + final["elapsed_ms"]
            check = (
                (
                    grader.grade(cases[r["case_id"]], final.get("text"))
                    if t.get("complete")
                    else {"passed": False, "reason": "incomplete_request"}
                )
                if phase == "target"
                else None
            )
            all_rows.append(
                {
                    "phase": phase,
                    "case_id": r["case_id"],
                    "arm": r["arm"],
                    "repetition": r["repetition"],
                    "complete": bool(t.get("complete")),
                    "validation": check,
                    "known_quota": sum(a["quota"] or 0 for a in trial_attempts),
                    "charge_complete": all(a["quota"] is not None for a in trial_attempts),
                    "attempts": len(trial_attempts),
                    "elapsed_ms_including_retries": elapsed,
                    "cached_tokens": (
                        (final.get("usage") or {}).get("prompt_tokens_details") or {}
                    ).get("cached_tokens"),
                    "input_tokens": sum(a["input_tokens"] or 0 for a in trial_attempts),
                    "output_tokens": sum(a["output_tokens"] or 0 for a in trial_attempts),
                }
            )
        assert used == set(range(len(profile["request_attempts"])))
        phases[phase] = {
            "planned": len(requests),
            "recorded": len(profile["trials"]),
            "execution_complete": report["complete"],
            "http_attempts": len(profile["request_attempts"]),
            "known_quota": sum(r["known_quota"] for r in all_rows if r["phase"] == phase),
            "model_request_ms": sum(
                r["elapsed_ms_including_retries"] for r in all_rows if r["phase"] == phase
            ),
        }
    assert set(bills) <= seen_ids
    total = sum(a["quota"] or 0 for a in attempts)
    interval = read(d, "quota-interval.json")
    reconciles = (
        total == interval["counter_delta_quota"]
        if interval["counter_delta_quota"] is not None
        else None
    )
    cost_complete = all(a["quota"] is not None for a in attempts) and reconciles is True
    targets = [r for r in all_rows if r["phase"] == "target"]
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in targets}
    assert len(by_key) == len(targets)
    for r in read(d, "target-requests.json"):
        p = prep[r["case_id"]]
        assert r["prompt"] == (
            p["english_prompt"]
            if r["arm"] == "concise_english"
            else p["ranking"]["shortest_genuine"]["prompt"]
        )
        assert r["arm"] == "concise_english" or p["semantic_review_approved"]
    arm_summary = {}
    for arm in ["concise_english", "genuine_diagnostic"]:
        rows = [r for r in targets if r["arm"] == arm]
        arm_summary[arm] = {
            "attempted": len(rows),
            "completed": sum(r["complete"] for r in rows),
            "correct": sum(r["validation"]["passed"] for r in rows),
            "known_quota": sum(r["known_quota"] for r in rows),
            "http_attempts": sum(r["attempts"] for r in rows),
            "median_request_ms": statistics.median(r["elapsed_ms_including_retries"] for r in rows)
            if rows
            else None,
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
        }
    selected = []
    for cid, p in prep.items():
        for rep in [1, 2, 3]:
            key = (cid, "genuine_diagnostic" if p["policy_uses_mixed"] else "concise_english", rep)
            if key in by_key:
                selected.append(by_key[key])
    allocation = read(d, "cost-allocation-before-target.json")
    required_reviews = allocation["required_review_ids"]
    for rid, required in required_reviews.items():
        assert required == any(
            p["review_id"] == rid
            and p["ranking"]["shortest_genuine"]["strictly_shorter_than_english"]
            for p in prep.values()
        )
    minimal_prep = phases["translation"]["known_quota"] + sum(
        r["known_quota"]
        for r in all_rows
        if r["phase"] == "review" and required_reviews[r["case_id"]]
    )
    all_prep = phases["translation"]["known_quota"] + phases["review"]["known_quota"]
    baseline = arm_summary["concise_english"]["known_quota"]
    policy_target = sum(r["known_quota"] for r in selected)
    paired = []
    for cid in cases:
        for rep in [1, 2, 3]:
            en = by_key.get((cid, "concise_english", rep))
            mixed = by_key.get((cid, "genuine_diagnostic", rep))
            if en and mixed:
                paired.append(
                    {
                        "case_id": cid,
                        "repetition": rep,
                        "english_pass": en["validation"]["passed"],
                        "mixed_pass": mixed["validation"]["passed"],
                    }
                )
    summary = {
        "execution_complete": all(p["execution_complete"] for p in phases.values()),
        "cases": 20,
        "families": 10,
        "repetitions": 3,
        "phases": phases,
        "arms": arm_summary,
        "actual_experiment_quota": total,
        "counter_reconciles": reconciles,
        "cost_complete": cost_complete,
        "policy_mixed_cases": sum(p["policy_uses_mixed"] for p in prep.values()),
        "approved_diagnostic_cases": sum(p["semantic_review_approved"] for p in prep.values()),
        "policy_observations": len(selected),
        "policy_correct": sum(r["validation"]["passed"] for r in selected),
        "policy_target_quota": policy_target,
        "minimal_policy_preparation_quota": minimal_prep,
        "all_preparation_quota": all_prep,
        "minimal_policy_total_quota": minimal_prep + policy_target,
        "conservative_all_prep_policy_quota": all_prep + policy_target,
        "baseline_target_quota": baseline,
        "all_prep_forced_genuine_quota": all_prep
        + arm_summary["genuine_diagnostic"]["known_quota"],
        "all_prep_forced_genuine_vs_baseline_change": (
            all_prep + arm_summary["genuine_diagnostic"]["known_quota"]
        )
        / baseline
        - 1
        if cost_complete and baseline and len(paired) == 60
        else None,
        "case_arm_results": {
            cid: {
                arm: {
                    "attempted": sum(r["case_id"] == cid and r["arm"] == arm for r in targets),
                    "correct": sum(
                        r["validation"]["passed"]
                        for r in targets
                        if r["case_id"] == cid and r["arm"] == arm
                    ),
                }
                for arm in ["concise_english", "genuine_diagnostic"]
            }
            for cid in cases
        },
        "diagnostic_token_deltas": {
            cid: p["ranking"]["shortest_genuine"]["tokens"] - p["english_tokens"]
            for cid, p in prep.items()
            if p["ranking"].get("shortest_genuine")
        },
        "minimal_policy_vs_baseline_change": (minimal_prep + policy_target) / baseline - 1
        if cost_complete and baseline
        else None,
        "diagnostic_target_vs_english_change": arm_summary["genuine_diagnostic"]["known_quota"]
        / baseline
        - 1
        if cost_complete and baseline and len(paired) == 60
        else None,
        "mixed_only_passes": sum(p["mixed_pass"] and not p["english_pass"] for p in paired),
        "english_only_passes": sum(p["english_pass"] and not p["mixed_pass"] for p in paired),
        "paired_comparisons": paired,
        "failed_attempts": [a for a in attempts if not a["complete"]],
        "unknown_attempt_charges": sum(a["quota"] is None for a in attempts),
        "limitations": protocol["limitations"],
        "prior_admission_changed": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("summary.json", summary),
        ("trials.json", all_rows),
        ("attempts.json", attempts),
    ]:
        (out / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    counts = [
        arm_summary["concise_english"]["correct"],
        arm_summary["genuine_diagnostic"]["correct"],
        summary["policy_correct"],
    ]
    labels = ["English", "Genuine probe", "Token policy*"]
    for ax, values, title, ylabel in [
        (axes[0], counts, "Exact answers (60 planned per representation)", "Correct"),
        (
            axes[1],
            [
                baseline,
                arm_summary["genuine_diagnostic"]["known_quota"],
                minimal_prep + policy_target,
            ],
            "Target-only versus overhead-inclusive quota",
            "Gateway quota units",
        ),
    ]:
        bars = ax.bar(labels, values, color=["#507da6", "#44856c", "#9b78b1"])
        for b, v in zip(bars, values):
            ax.text(
                b.get_x() + b.get_width() / 2,
                v + max(values, default=1) * 0.035,
                f"{v:,}",
                ha="center",
                fontsize=9,
            )
        ax.set(title=title, ylabel=ylabel)
        ax.margins(y=0.2)
    axes[0].set_ylim(0, 70)
    values = [
        phases["translation"]["known_quota"],
        phases["review"]["known_quota"],
        phases["target"]["known_quota"],
    ]
    bars = axes[2].bar(
        ["Translate", "Review", "All targets"], values, color=["#b99549", "#ab7971", "#81929e"]
    )
    for b, v in zip(bars, values):
        axes[2].text(
            b.get_x() + b.get_width() / 2,
            v + max(values) * 0.035,
            f"{v:,}",
            ha="center",
            fontsize=9,
        )
    axes[2].set(title="Actual experiment charges: all calls", ylabel="Gateway quota units")
    axes[2].margins(y=0.2)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Strict two-stage pilot: frozen concise English → translation-only mixing", weight="bold"
    )
    fig.supxlabel(
        "*Policy reuses the matching English/probe outcome; not an independent third arm. Policy cost includes necessary preparation.\nGenuine probe is forced even when longer; no cache control, external bilingual certification or general causal claim.",
        fontsize=8,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / ("comparison." + ext), dpi=180)
    plt.close(fig)
    manifest = {
        name: sha(raw(d, name))
        for name in [
            "protocol.json",
            "stage-one.json",
            "review-freeze.json",
            "target-freeze.json",
            "cost-allocation-before-target.json",
            "translation-results.json",
            "review-results.json",
            "target-results.json",
            "billing-matched.json",
            "quota-interval.json",
        ]
    }
    manifest["generator_sha256"] = sha(Path(__file__).read_bytes())
    for name in [
        "implementation-manifest.json",
        "execution.json",
        "quota-checkpoints.json",
        "prior-extraction-audit.json",
        "error-inspection.json",
    ]:
        if (d / name).exists():
            manifest[name] = sha(raw(d, name))
    manifest["outputs"] = {
        p.name: sha(p.read_bytes())
        for p in out.iterdir()
        if p.is_file() and p.name != "plot-manifest.json"
    }
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "execution_complete",
                    "arms",
                    "phases",
                    "policy_mixed_cases",
                    "policy_correct",
                    "actual_experiment_quota",
                    "minimal_policy_vs_baseline_change",
                    "counter_reconciles",
                    "mixed_only_passes",
                    "english_only_passes",
                ]
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    audit(args.directory, args.out)
