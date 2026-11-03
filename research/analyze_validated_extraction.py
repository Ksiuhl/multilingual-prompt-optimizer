"""Offline audit of the fixed extraction template and separately frozen supplement."""

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt

from multilingual_prompt_optimizer import JsonExtractionTemplate


def data(directory, name):
    path = directory / name
    return (
        path.read_bytes()
        if path.exists()
        else gzip.decompress((directory / (name + ".gz")).read_bytes())
    )


def read(directory, name):
    return json.loads(data(directory, name))


def analyze(directory, out):
    protocol = read(directory, "protocol.json")
    supplement = read(directory / "supplement", "protocol.json")
    for base, p in [(directory, protocol), (directory / "supplement", supplement)]:
        for name, expected in p["files"].items():
            assert hashlib.sha256(data(base, name)).hexdigest() == expected, name
    template = JsonExtractionTemplate.from_dict(read(directory, "template.json"))
    assert template.fingerprint == protocol["template_fingerprint"]
    spec = importlib.util.spec_from_file_location(
        "frozen_extraction_grader", directory / "grader-source.py"
    )
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    charges = read(directory, "billing-matched.json")["records"]
    by_id = {}
    for r in charges:
        if r["type"] == 2:
            assert type(r["quota"]) is int and r["quota"] >= 0
            assert r["request_id"] not in by_id, "ambiguous billing"
            by_id[r["request_id"]] = r["quota"]
    trials = []
    aggregated_charges = []
    scores = {
        s: {a: {"correct": 0, "completed": 0, "planned": 0} for a in ["original", "compressed"]}
        for s in ["development", "holdout"]
    }
    used = set()
    failures = []
    for base in [directory, directory / "supplement"]:
        cases = {c["id"]: c for c in read(base, "dataset.json")["cases"]}
        requests = {(r["case_id"], r["arm"]): r for r in read(base, "requests.json")}
        report = read(base, "results.json")
        assert report["complete"]
        profile = report["profiles"][0]
        assert len(profile["trials"]) == len(requests)
        seen = set()
        for t in profile["trials"]:
            case = cases[t["case_id"]]
            key = t["case_id"], t["arm"]
            assert key not in seen
            seen.add(key)
            assert t["prompt_sha256"] == requests[key]["prompt_sha256"]
            assert (
                hashlib.sha256(requests[key]["prompt"].encode()).hexdigest() == t["prompt_sha256"]
            )
            assert case["expected"] == template.expected(case["payload"])
            attempts = [profile["request_attempts"][i] for i in t["attempt_indices"]]
            for a in attempts:
                assert a["prompt_sha256"] == t["prompt_sha256"]
                if a.get("gateway_request_id"):
                    assert a["gateway_request_id"] not in used
                    used.add(a["gateway_request_id"])
            final = attempts[-1]
            check = (
                grader.grade(case, final.get("text"))
                if t.get("complete")
                else {"passed": False, "reason": "incomplete_request"}
            )
            assert template.check(case["payload"], final.get("text")).passed == check["passed"]
            metric = scores[case["split"]][t["arm"]]
            metric["planned"] += 1
            metric["completed"] += bool(t.get("complete"))
            metric["correct"] += check["passed"]
            if not check["passed"]:
                failures.append({"case_id": case["id"], "arm": t["arm"], **check})
            rid = final.get("gateway_request_id")
            trials.append(
                {
                    "split": case["split"],
                    "case_id": case["id"],
                    "arm": t["arm"],
                    "payload": case["payload"],
                    "prompt_sha256": t["prompt_sha256"],
                    "response_text": final.get("text"),
                    "request_id": rid,
                }
            )
            # Include any charged bounded retries in this trial's fee.
            fee = sum(by_id.get(a.get("gateway_request_id"), 0) for a in attempts)
            if rid in by_id:
                aggregated_charges.append({"request_id": rid, "quota": fee})
    assert set(by_id) <= used, "unrelated billing record retained"
    interval = read(directory, "billing-combined-interval.json")
    ledger_total = sum(by_id.values())
    evidence = {
        "template_fingerprint": template.fingerprint,
        "trials": trials,
        "charges": aggregated_charges,
        "counter_delta_quota": interval["counter_delta_quota"],
        "preparation_quota": protocol["preparation_quota"],
    }
    admission = template.assess(evidence)
    unique = {
        s: len(
            {
                json.dumps(json.loads(t["payload"]), sort_keys=True, ensure_ascii=False)
                for t in trials
                if t["split"] == s
            }
        )
        for s in scores
    }
    cost = {
        s: {
            a: sum(
                c["quota"]
                for c in aggregated_charges
                if any(
                    t["request_id"] == c["request_id"] and t["split"] == s and t["arm"] == a
                    for t in trials
                )
            )
            for a in ["original", "compressed"]
        }
        for s in scores
    }
    summary = {
        "scores": scores,
        "distinct_payloads": unique,
        "admission": admission,
        "failures": failures,
        "quota_by_split_arm": cost,
        "matched_ledger_quota": ledger_total,
        "counter_delta_quota": interval["counter_delta_quota"],
        "counter_reconciles": ledger_total == interval["counter_delta_quota"],
        "quota_per_unit": interval["quota_per_unit"],
        "display_unit": interval["display_unit"],
        "primary_planned": 60,
        "supplement_planned": 4,
        "note": supplement["reason"],
        "limitations": protocol["limitations"],
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in [("summary.json", summary), ("evidence.json", evidence)]:
        (out / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
        )
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for offset, arm, label, color in [
        (-0.18, "original", "Original", "#8e9eae"),
        (0.18, "compressed", "Compressed", "#3b8872"),
    ]:
        bars = axes[0].bar(
            [i + offset for i in range(2)],
            [100 * scores[s][arm]["correct"] / scores[s][arm]["planned"] for s in scores],
            width=0.34,
            label=label,
            color=color,
        )
        for bar, s in zip(bars, scores):
            axes[0].text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 2,
                f"{scores[s][arm]['correct']}/{scores[s][arm]['planned']}",
                ha="center",
                fontsize=9,
            )
        values = [cost[s][arm] for s in scores]
        bars = axes[1].bar(
            [i + offset for i in range(2)], values, width=0.34, label=label, color=color
        )
        for bar, v in zip(bars, values):
            axes[1].text(
                bar.get_x() + bar.get_width() / 2,
                v + max(values) * 0.03,
                f"{v:,} units",
                ha="center",
                fontsize=8,
            )
    for ax in axes:
        ax.set_xticks(range(2), ["Development (10 distinct)", "Holdout (20 distinct)"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].set(title="Strict extraction checks", ylim=(0, 118), ylabel="Correct / planned (%)")
    axes[0].legend(loc="lower right")
    axes[1].set(title="Matching gateway charges", ylabel="Gateway quota units")
    axes[1].margins(y=0.2)
    fig.suptitle(
        "One fixed extraction template: admission "
        + ("PASSED" if admission["admitted"] else "REJECTED"),
        weight="bold",
    )
    fig.supxlabel(
        "64 trials; holdout includes 2 duplicate pairs retained plus 2 separately frozen new pairs.\nNo candidate tuning or answer repair. Deterministic projection is also possible without an LLM.",
        fontsize=8,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / f"comparison.{ext}", dpi=180)
    plt.close(fig)
    manifest = {
        name: hashlib.sha256(data(directory, name)).hexdigest()
        for name in [
            "protocol.json",
            "results.json",
            "billing-matched.json",
            "billing-combined-interval.json",
        ]
    }
    manifest["supplement_results_sha256"] = hashlib.sha256(
        data(directory / "supplement", "results.json")
    ).hexdigest()
    manifest["summary_sha256"] = hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()
    manifest["evidence_sha256"] = hashlib.sha256((out / "evidence.json").read_bytes()).hexdigest()
    manifest["analyzer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "scores": scores,
                "admission": admission,
                "quota_by_split_arm": cost,
                "matched_ledger_quota": ledger_total,
                "counter_reconciles": summary["counter_reconciles"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.directory, args.out)
