"""Offline audit of the fresh-input, repeated quota/cache study; no API calls."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from multilingual_prompt_optimizer import JsonExtractionTemplate


def raw(directory, name):
    path = directory / name
    return (
        path.read_bytes()
        if path.exists()
        else gzip.decompress((directory / (name + ".gz")).read_bytes())
    )


def read(directory, name):
    return json.loads(raw(directory, name))


def analyze(directory, out):
    protocol = read(directory, "protocol.json")
    for name, expected in protocol["files"].items():
        assert hashlib.sha256(raw(directory, name)).hexdigest() == expected, name
    cases = {c["id"]: c for c in read(directory, "dataset.json")["cases"]}
    requests = read(directory, "requests.json")
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in requests}
    assert len(by_key) == len(requests) == 120 and len(cases) == 20
    template = JsonExtractionTemplate.from_dict(read(directory, "template.json"))
    assert template.fingerprint == protocol["template_fingerprint"]
    prior = Path(__file__).resolve().parents[1] / "results/validated-extraction-v060"
    assert raw(directory, "template.json") == raw(prior, "template.json")

    def canonical(payload):
        return json.dumps(json.loads(payload), sort_keys=True, ensure_ascii=False)

    payloads = {canonical(c["payload"]) for c in cases.values()}
    assert len(payloads) == 20
    assert len({json.dumps(c["expected"], sort_keys=True) for c in cases.values()}) == 20
    for base in [prior, prior / "supplement", prior.parent / "cache-followup-v060"]:
        assert not payloads.intersection(
            canonical(c["payload"]) for c in read(base, "dataset.json")["cases"]
        ), "overlap with an earlier corpus"
    for c in cases.values():
        assert template.expected(c["payload"]) == c["expected"]
    assert len(protocol["paired_blocks"]) == 60
    for rep in range(1, 4):
        blocks = [b for b in protocol["paired_blocks"] if b["repetition"] == rep]
        assert len(blocks) == 20
        assert {b["case_id"] for b in blocks} == set(cases)
        assert sum(b["arms"][0] == "original" for b in blocks) == 10
    for index, block in enumerate(protocol["paired_blocks"], 1):
        assert set(block["arms"]) == {"original", "compressed"}
        for arm, r in zip(block["arms"], requests[2 * (index - 1) : 2 * index]):
            assert (r["case_id"], r["arm"], r["repetition"], r["block"]) == (
                block["case_id"],
                arm,
                block["repetition"],
                index,
            )
    for r in requests:
        instruction = (
            template.original_instruction
            if r["arm"] == "original"
            else template.compressed_instruction
        )
        assert r["prompt"] == template.request(cases[r["case_id"]]["payload"]).compose(instruction)
        assert hashlib.sha256(r["prompt"].encode()).hexdigest() == r["prompt_sha256"]
    spec = importlib.util.spec_from_file_location(
        "fresh_cache_frozen_grader", directory / "grader-source.py"
    )
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    report = read(directory, "results.json")
    assert report["dataset_sha256"] == protocol["files"]["dataset.json"]
    assert report["prepared_source_sha256"] == protocol["files"]["requests.json"]
    assert report["grader_sha256"] == protocol["files"]["grader-source.py"]
    assert report["protocol"] == protocol
    profile = report["profiles"][0]
    assert profile["label"] == protocol["model_label"]
    assert [(t["case_id"], t["arm"], t["repetition"]) for t in profile["trials"]] == [
        (r["case_id"], r["arm"], r["repetition"]) for r in requests[: len(profile["trials"])]
    ], "serial order changed"
    logs = read(directory, "billing-matched.json")["records"]
    bills = {}
    for r in logs:
        if r["type"] == 2:
            assert r["request_id"] not in bills
            assert type(r["quota"]) is int and r["quota"] >= 0
            bills[r["request_id"]] = r
    seen, used_indices, used_ids, rows, attempt_rows = set(), set(), set(), [], []
    for trial in profile["trials"]:
        key = trial["case_id"], trial["arm"], trial["repetition"]
        assert key in by_key and key not in seen
        seen.add(key)
        req = by_key[key]
        assert trial["prompt_sha256"] == req["prompt_sha256"]
        fee = 0
        for ordinal, index in enumerate(trial["attempt_indices"], 1):
            assert index not in used_indices
            used_indices.add(index)
            attempt = profile["request_attempts"][index]
            assert attempt["prompt_sha256"] == req["prompt_sha256"]
            rid = attempt.get("gateway_request_id")
            if rid:
                assert rid not in used_ids
                used_ids.add(rid)
            bill = bills.get(rid)
            fee += bill["quota"] if bill else 0
            attempt_rows.append(
                {
                    "case_id": key[0],
                    "arm": key[1],
                    "repetition": key[2],
                    "attempt": ordinal,
                    "request_id": rid,
                    "http_status": attempt.get("http_status"),
                    "error_type": attempt.get("error_type"),
                    "complete": bool(attempt.get("complete")),
                    "charged_quota": bill["quota"] if bill else None,
                }
            )
        final = profile["request_attempts"][trial["attempt_indices"][-1]]
        first = profile["request_attempts"][trial["attempt_indices"][0]]
        duration = (
            datetime.fromisoformat(final["started_at_utc"])
            - datetime.fromisoformat(first["started_at_utc"])
        ).total_seconds() * 1000 + final["elapsed_ms"]
        check = (
            grader.grade(cases[key[0]], final.get("text"))
            if trial.get("complete")
            else {"passed": False, "reason": "incomplete_request"}
        )
        usage = final.get("usage") or {}
        details = usage.get("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        if cached is not None:
            assert type(cached) is int and 0 <= cached <= usage["prompt_tokens"]
        if usage and final.get("gateway_request_id") in bills:
            assert usage["prompt_tokens"] == bills[final["gateway_request_id"]]["prompt_tokens"]
            assert (
                usage["completion_tokens"]
                == bills[final["gateway_request_id"]]["completion_tokens"]
            )
        rows.append(
            {
                "case_id": key[0],
                "arm": key[1],
                "repetition": key[2],
                "block": req["block"],
                "complete": bool(trial.get("complete")),
                "validation": check,
                "attempts": len(trial["attempt_indices"]),
                "charged_quota": fee,
                "charge_coverage_complete": all(
                    a["charged_quota"] is not None
                    for a in attempt_rows[-len(trial["attempt_indices"]) :]
                ),
                "cached_tokens": cached,
                "cache_category": "unknown"
                if cached is None
                else "reported_positive"
                if cached > 0
                else "reported_zero",
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "successful_attempt_ms": trial.get("elapsed_ms"),
                "request_ms_including_retries": duration,
                "final_consumption_record_present": final.get("gateway_request_id") in bills,
            }
        )
    assert used_indices == set(range(len(profile["request_attempts"])))
    assert set(bills) <= used_ids
    if report["complete"]:
        assert seen == set(by_key)
    interval = read(directory, "quota-interval.json")
    total = sum(r["charged_quota"] for r in rows)
    assert total == sum(r["quota"] for r in bills.values())
    reconciles = (
        total == interval["counter_delta_quota"]
        if interval["counter_delta_quota"] is not None
        else None
    )
    complete_charge_coverage = all(r["charged_quota"] is not None for r in attempt_rows)
    arms = {}
    for arm in ["original", "compressed"]:
        selected = [r for r in rows if r["arm"] == arm]
        arms[arm] = {
            "planned": 60,
            "attempted": len(selected),
            "completed": sum(r["complete"] for r in selected),
            "correct": sum(r["validation"]["passed"] for r in selected),
            "http_attempts": sum(r["attempts"] for r in selected),
            "charged_quota": sum(r["charged_quota"] for r in selected),
            "final_consumption_records_present": sum(
                r["final_consumption_record_present"] for r in selected
            ),
            "median_request_ms_including_retries": statistics.median(
                r["request_ms_including_retries"] for r in selected if r["complete"]
            )
            if any(r["complete"] for r in selected)
            else None,
            "quality_errors": sum(
                r["complete"] and not r["validation"]["passed"] for r in selected
            ),
            "incomplete": sum(not r["complete"] for r in selected),
            "input_tokens": sum(r["input_tokens"] or 0 for r in selected),
            "output_tokens": sum(r["output_tokens"] or 0 for r in selected),
            "cache_categories": {
                c: sum(r["cache_category"] == c for r in selected)
                for c in ["reported_positive", "reported_zero", "unknown"]
            },
        }
    repetitions = {
        str(rep): {
            arm: {
                "planned": 20,
                "attempted": sum(r["repetition"] == rep and r["arm"] == arm for r in rows),
                "correct": sum(
                    r["validation"]["passed"]
                    for r in rows
                    if r["repetition"] == rep and r["arm"] == arm
                ),
                "completed": sum(
                    r["complete"] for r in rows if r["repetition"] == rep and r["arm"] == arm
                ),
                "charged_quota": sum(
                    r["charged_quota"] for r in rows if r["repetition"] == rep and r["arm"] == arm
                ),
            }
            for arm in arms
        }
        for rep in range(1, 4)
    }
    paired = {(r["block"], r["arm"]): r for r in rows}
    blocks = []
    for i, spec_block in enumerate(protocol["paired_blocks"], 1):
        if all((i, a) in paired for a in arms):
            a, b = paired[i, "original"], paired[i, "compressed"]
            blocks.append(
                {
                    "block": i,
                    "case_id": a["case_id"],
                    "repetition": a["repetition"],
                    "first_arm": spec_block["arms"][0],
                    "original_quota": a["charged_quota"],
                    "compressed_quota": b["charged_quota"],
                    "difference": b["charged_quota"] - a["charged_quota"]
                    if a["charge_coverage_complete"] and b["charge_coverage_complete"]
                    else None,
                    "original_cached": a["cached_tokens"],
                    "compressed_cached": b["cached_tokens"],
                    "cache_counts_equal": a["cached_tokens"] == b["cached_tokens"]
                    if a["cached_tokens"] is not None and b["cached_tokens"] is not None
                    else None,
                }
            )
    first_arm_groups = {}
    for arm in arms:
        group = [b for b in blocks if b["first_arm"] == arm]
        first_arm_groups[arm] = {
            "blocks": len(group),
            "fully_matched_blocks": sum(b["difference"] is not None for b in group),
            "compressed_minus_original_quota": sum(
                b["difference"] for b in group if b["difference"] is not None
            ),
        }
    case_repeats = []
    for cid in cases:
        for arm in arms:
            selected = [r for r in rows if r["case_id"] == cid and r["arm"] == arm]
            correct = sum(r["validation"]["passed"] for r in selected)
            case_repeats.append(
                {
                    "case_id": cid,
                    "arm": arm,
                    "observed": len(selected),
                    "correct": correct,
                    "unstable": 0 < correct < len(selected),
                }
            )
    summary = {
        "scope": protocol["type"],
        "execution_complete": bool(report["complete"]),
        "arms": arms,
        "new_distinct_inputs": 20,
        "observed_distinct_inputs": len({r["case_id"] for r in rows}),
        "planned_requests": 120,
        "unattempted_requests": 120 - len(rows),
        "first_arm_groups": first_arm_groups,
        "case_repeats": case_repeats,
        "paired_blocks_costlier_with_compression": sum(
            b["difference"] > 0 for b in blocks if b["difference"] is not None
        ),
        "same_reported_cache_pairs": sum(b["cache_counts_equal"] is True for b in blocks),
        "quota_comparison_complete": bool(
            report["complete"] and reconciles and complete_charge_coverage
        ),
        "attempt_charge_coverage_complete": complete_charge_coverage,
        "charge_interpretation": "Matched charges only; unmatched attempts are unknown, not free. Full comparison requires complete coverage and counter reconciliation.",
        "execution_notes": read(directory, "execution.json"),
        "repetitions": repetitions,
        "paired_blocks": blocks,
        "counter_reconciles": reconciles,
        "total_matched_quota": total,
        "total_quota": total if complete_charge_coverage and reconciles else None,
        "display_unit": "gateway quota units",
        "compressed_charge_reduction": 1
        - arms["compressed"]["charged_quota"] / arms["original"]["charged_quota"]
        if arms["original"]["charged_quota"] and complete_charge_coverage and reconciles
        else None,
        "failed_attempts": [r for r in attempt_rows if not r["complete"]],
        "final_consumption_records_present": sum(
            r["final_consumption_record_present"] for r in rows
        ),
        "attempts_without_consumption_record": sum(
            r["charged_quota"] is None for r in attempt_rows
        ),
        "stop_guard": read(directory, "quota-checkpoints.json"),
        "limitations": protocol["limitations"],
        "prior_admission_changed": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("summary.json", summary),
        ("trials.json", rows),
        ("attempts.json", attempt_rows),
    ]:
        (out / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    plot(summary, out)
    manifest = {
        name: hashlib.sha256(raw(directory, name)).hexdigest()
        for name in [
            "protocol.json",
            "results.json",
            "billing-matched.json",
            "quota-interval.json",
            "quota-checkpoints.json",
            "execution.json",
            "analysis-plan.json",
        ]
    }
    manifest["summary_sha256"] = hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()
    manifest["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest["generated_files"] = {
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in [
            "trials.json",
            "attempts.json",
            "comparison.png",
            "comparison.svg",
            "comparison.pdf",
        ]
    }
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "complete": summary["execution_complete"],
                "arms": {a: r for a, r in arms.items()},
                "repetitions": repetitions,
                "counter_reconciles": reconciles,
                "total_quota": summary["total_quota"],
            }
        )
    )


def plot(summary, out):
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.4), layout="constrained")
    for arm, label, color, offset in [
        ("original", "Original", "#8e9eae", -0.18),
        ("compressed", "Compressed", "#3b8872", 0.18),
    ]:
        rows = summary["paired_blocks"]
        axes[0].plot(
            [r["block"] for r in rows],
            [r[arm + "_cached"] if r[arm + "_cached"] is not None else float("nan") for r in rows],
            marker="o",
            color=color,
            label=label,
            linewidth=3.5 if arm == "original" else 1.5,
            markersize=7 if arm == "original" else 4,
        )
        values = [summary["repetitions"][str(rep)][arm]["charged_quota"] for rep in range(1, 4)]
        bars = axes[1].bar(
            [rep + offset for rep in range(1, 4)], values, width=0.34, label=label, color=color
        )
        for rep, bar, v in zip(range(1, 4), bars, values):
            axes[1].text(
                bar.get_x() + bar.get_width() / 2,
                v + max(values) * 0.04,
                f"{v:,}\nunits" if summary["repetitions"][str(rep)][arm]["attempted"] else "unsent",
                ha="center",
                fontsize=8,
            )
        correct = [summary["repetitions"][str(rep)][arm]["correct"] for rep in range(1, 4)]
        bars = axes[2].bar(
            [rep + offset for rep in range(1, 4)], correct, width=0.34, label=label, color=color
        )
        for rep, bar, v in zip(range(1, 4), bars, correct):
            count = summary["repetitions"][str(rep)][arm]["attempted"]
            axes[2].text(
                bar.get_x() + bar.get_width() / 2,
                v + 0.4,
                f"{v}/{count}" if count else "unsent",
                ha="center",
                fontsize=8,
            )
    for x in [20.5, 40.5]:
        axes[0].axvline(x, color="#bbb", linestyle="--", linewidth=0.8)
    axes[0].set(
        title="Observed cache counts (missing = gaps)",
        xlabel="Serial paired block; 20 blocks per repetition",
        ylabel="Gateway-reported cached input tokens",
        xticks=[1, 20, 40, 60],
    )
    axes[0].legend(loc="best")
    known = [
        r[a + "_cached"]
        for r in summary["paired_blocks"]
        for a in ["original", "compressed"]
        if r[a + "_cached"] is not None
    ]
    axes[0].set_ylim(0, max(max(known, default=0) * 1.15, 1))
    axes[1].set(
        title="Matched charges only; incomplete ledger\nArm totals not comparable"
        if not summary["attempt_charge_coverage_complete"]
        else "All charges, including first use and retries",
        xlabel="Repetition (not a controlled cache treatment)",
        ylabel="Gateway quota units",
        xticks=[1, 2, 3],
    )
    axes[1].margins(y=0.25)
    axes[2].set(
        title="Exact passes / attempted requests",
        xlabel="Repetition (20 new inputs reused)",
        ylabel="Correct (20 per arm/repetition planned)",
        xticks=[1, 2, 3],
        ylim=(0, 24),
    )
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    observed = sum(a["attempted"] for a in summary["arms"].values())
    prefix = "" if summary["execution_complete"] else f"PARTIAL: {observed}/120 requests. "
    fig.suptitle(prefix + "Fresh-input quota/cache follow-up", weight="bold")
    fig.supxlabel(
        "No cache reset or free warm-up; first repetition is not called cold. Full planned order is balanced; a stopped prefix may not be.\nUnsent requests are not graded. Observational gateway metadata; no causal cache claim or change to prior admission.",
        fontsize=8,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / f"comparison.{ext}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.directory, args.out)
