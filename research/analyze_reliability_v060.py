"""Offline grading and matched-charge audit for the selected-failure repeats."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def raw_bytes(directory, name):
    path = directory / name
    return (
        path.read_bytes()
        if path.exists()
        else gzip.decompress((directory / (name + ".gz")).read_bytes())
    )


def read(directory, name):
    return json.loads(raw_bytes(directory, name))


def analyze(directory, out):
    protocol = read(directory, "protocol.json")
    for name, expected in protocol["files"].items():
        assert hashlib.sha256(raw_bytes(directory, name)).hexdigest() == expected, name
    source = directory / "grader-source.py"
    spec = importlib.util.spec_from_file_location("reliability_frozen_grader", source)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    cases = {c["id"]: c for c in read(directory, "dataset.json")["cases"]}
    grader.self_check(list(cases.values()))
    requests = read(directory, "requests.json")
    prior = ROOT / "results/heldout-v060"
    assert (
        hashlib.sha256((ROOT / "results/heldout-v060-summary.json").read_bytes()).hexdigest()
        == protocol["prior_summary_sha256"]
    )
    prior_cases = {c["id"]: c for c in read(prior, "dataset.json")["cases"]}
    assert all(c == prior_cases[cid] for cid, c in cases.items())
    prior_requests = {(r["case_id"], r["arm"]): r for r in read(prior, "requests.json")}
    expected = {(r["case_id"], r["arm"], r["repetition"]): r for r in requests}
    assert len(requests) == len(expected) == 40
    assert len(cases) == 4 and set(cases) == set(protocol["selected_case_ids"])
    for r in requests:
        assert hashlib.sha256(r["prompt"].encode()).hexdigest() == r["prompt_sha256"]
        assert r["prompt"] == prior_requests[r["case_id"], r["arm"]]["prompt"]
        assert r["repetition"] in range(1, 6)
    result = read(directory, "results.json")
    assert result["dataset_sha256"] == protocol["files"]["dataset.json"]
    assert result["prepared_source_sha256"] == protocol["files"]["requests.json"]
    assert result["grader_sha256"] == protocol["files"]["grader-source.py"]
    profile = result["profiles"][0]
    assert profile["label"] == protocol["model_label"]
    seen, indices, scored, id_to_arm = set(), [], [], {}
    for trial in profile["trials"]:
        key = trial["case_id"], trial["arm"], trial["repetition"]
        assert key not in seen
        seen.add(key)
        assert trial["prompt_sha256"] == expected[key]["prompt_sha256"]
        for i in trial["attempt_indices"]:
            indices.append(i)
            attempt = profile["request_attempts"][i]
            assert attempt["prompt_sha256"] == trial["prompt_sha256"]
            request_id = attempt.get("gateway_request_id")
            if request_id:
                assert request_id not in id_to_arm
                id_to_arm[request_id] = trial["arm"]
        final = profile["request_attempts"][trial["attempt_indices"][-1]]
        first = profile["request_attempts"][trial["attempt_indices"][0]]
        request_ms = trial.get("elapsed_ms")
        if trial.get("complete"):
            request_ms = (
                datetime.fromisoformat(final["started_at_utc"])
                - datetime.fromisoformat(first["started_at_utc"])
            ).total_seconds() * 1000 + final["elapsed_ms"]
        validation = (
            grader.grade(cases[trial["case_id"]], final.get("text"))
            if trial.get("complete")
            else {"passed": False, "reason": "incomplete_request"}
        )
        scored.append({**trial, "request_ms": request_ms, "validation": validation})
    if result["complete"]:
        assert seen == set(expected)
        assert len(indices) == len(set(indices)) == len(profile["request_attempts"])
        assert set(indices) == set(range(len(profile["request_attempts"])))
    summary = {
        "execution_complete": bool(result["complete"]),
        "all_responses_complete": len(scored) == 40 and all(t.get("complete") for t in scored),
        "model_label": profile["label"],
        "unique_selected_inputs": 4,
        "repetitions": 5,
        "planned_trials": 40,
        "http_attempts": len(profile["request_attempts"]),
        "scope": protocol["type"],
        "limitations": protocol["limitations"],
        "arms": {},
        "cases": {},
        "failures": [],
        "unstable_prompt_groups": [],
    }
    for arm in protocol["arms"]:
        trials = [t for t in scored if t["arm"] == arm]
        complete = [t for t in trials if t.get("complete")]
        summary["arms"][arm] = {
            "correct": sum(t["validation"]["passed"] for t in trials),
            "planned": 20,
            "completed": len(complete),
            "transport_failures": len(trials) - len(complete),
            "median_request_ms": statistics.median(t["request_ms"] for t in complete)
            if complete
            else None,
            "provider_usage": {
                k: sum((t.get("usage") or {}).get(k) or 0 for t in trials)
                for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
            },
        }
    for cid in cases:
        summary["cases"][cid] = {}
        for arm in protocol["arms"]:
            trials = sorted(
                (t for t in scored if t["case_id"] == cid and t["arm"] == arm),
                key=lambda t: t["repetition"],
            )
            checks = [t["validation"]["passed"] if t.get("complete") else None for t in trials]
            summary["cases"][cid][arm] = {
                "correct": sum(v is True for v in checks),
                "completed": sum(v is not None for v in checks),
                "planned": 5,
                "pass_by_repetition": checks,
            }
            if True in checks and False in checks:
                summary["unstable_prompt_groups"].append({"case_id": cid, "arm": arm})
    for t in scored:
        if not t["validation"]["passed"]:
            summary["failures"].append(
                {
                    "case_id": t["case_id"],
                    "arm": t["arm"],
                    "repetition": t["repetition"],
                    **t["validation"],
                }
            )
    pairs = {(t["case_id"], t["arm"], t["repetition"]): t for t in scored}
    pair_counts = {
        "both_correct": 0,
        "both_wrong": 0,
        "original_only": 0,
        "english_only": 0,
        "incomplete_pair": 0,
    }
    for cid in cases:
        for rep in range(1, 6):
            a, b = pairs.get((cid, "original", rep)), pairs.get((cid, "concise_english", rep))
            if not a or not b or not a.get("complete") or not b.get("complete"):
                pair_counts["incomplete_pair"] += 1
            else:
                x, y = a["validation"]["passed"], b["validation"]["passed"]
                pair_counts[
                    "both_correct"
                    if x and y
                    else "original_only"
                    if x
                    else "english_only"
                    if y
                    else "both_wrong"
                ] += 1
    summary["paired_repetitions"] = pair_counts
    billing = read(directory, "billing-matched.json")
    interval = read(directory, "billing-interval.json")
    unit = interval.get("quota_per_unit")
    quota = {arm: 0 for arm in protocol["arms"]}
    charge_ids, ambiguous = set(), []
    for request_id in id_to_arm:
        records = [
            r for r in billing["records"] if r["request_id"] == request_id and r.get("type") == 2
        ]
        if len(records) > 1:
            ambiguous.append(request_id)
        elif len(records) == 1:
            q = records[0].get("quota")
            assert isinstance(q, int) and not isinstance(q, bool) and q >= 0
            quota[id_to_arm[request_id]] += q
            charge_ids.add(request_id)
    assert all(r["request_id"] in id_to_arm for r in billing["records"])
    observed = sum(quota.values())
    usd = (
        {arm: q / unit for arm, q in quota.items()}
        if isinstance(unit, (int, float)) and unit > 0 and interval.get("display_unit") == "USD"
        else None
    )
    summary["billing"] = {
        "source": "Gateway-reported matching consumption-log quota; USD conversion from gateway's public quota_per_unit. Not an invoice.",
        "interval": interval,
        "attempts_with_request_id": len(id_to_arm),
        "matched_consumption_records": len(charge_ids),
        "ambiguous_request_ids": ambiguous,
        "charged_quota_by_arm": quota,
        "charged_quota_total": observed,
        "displayed_usd_by_arm": usd,
        "displayed_usd_total": sum(usd.values()) if usd else None,
        "matches_interval_counter": observed == interval.get("used_quota_delta") and not ambiguous,
        "all_completed_attempts_have_consumption_record": all(
            profile["request_attempts"][t["attempt_indices"][-1]].get("gateway_request_id")
            in charge_ids
            for t in scored
            if t.get("complete")
        ),
        "english_charge_reduction": 1 - usd["concise_english"] / usd["original"]
        if usd and usd["original"]
        else None,
        "attribution_limit": "Shared-key external activity, late settlement, refunds and deployment reporting errors remain possible; log/counter reconciliation is reported rather than assumed. Reused preparation incurred no new translation API calls; authoring labor and earlier preparation are excluded.",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    plot(summary, out)
    manifest = {
        name: hashlib.sha256(raw_bytes(directory, name)).hexdigest()
        for name in [
            "protocol.json",
            "results.json",
            "billing-matched.json",
            "billing-interval.json",
        ]
    }
    manifest["summary_sha256"] = hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()
    manifest["analyzer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "arms": summary["arms"],
                "unstable_groups": len(summary["unstable_prompt_groups"]),
                "charged_quota_by_arm": summary["billing"]["charged_quota_by_arm"],
                "counter_reconciles": summary["billing"]["matches_interval_counter"],
            }
        )
    )


def plot(summary, out):
    plt.switch_backend("Agg")
    fig, axs = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    case_ids = sorted(summary["cases"])
    for offset, arm, label, color in [
        (-0.18, "original", "Original", "#8e9eae"),
        (0.18, "concise_english", "Concise EN", "#3b8872"),
    ]:
        values = [summary["cases"][cid][arm]["correct"] for cid in case_ids]
        bars = axs[0].bar(
            [i + offset for i in range(4)], values, width=0.34, label=label, color=color
        )
        for bar, value in zip(bars, values):
            axs[0].text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.1,
                f"{value}/5",
                ha="center",
                fontsize=9,
            )
    axs[0].set_xticks(range(4), [c.removeprefix("new-") for c in case_ids])
    axs[0].set(
        title="Unchanged prompts: strict passes by case",
        ylabel="Correct responses / five planned repetitions",
        ylim=(0, 6.1),
    )
    axs[0].legend(loc="upper right", fontsize=9)
    quota = summary["billing"]["charged_quota_by_arm"]
    if quota:
        values = [quota[a] for a in ["original", "concise_english"]]
        bars = axs[1].bar(
            ["Original (20 trials)", "Concise EN (20 trials)"], values, color=["#8e9eae", "#3b8872"]
        )
        for bar, value in zip(bars, values):
            axs[1].text(
                bar.get_x() + bar.get_width() / 2,
                value + max(values) * 0.04,
                f"{value:,} units",
                ha="center",
                fontsize=10,
            )
        axs[1].set(
            title="Matched gateway usage-log charges",
            ylabel="Gateway quota units",
            ylim=(0, max(max(values) * 1.3, 0.001)),
        )
    else:
        axs[1].text(0.5, 0.5, "Gateway quota unavailable", ha="center", transform=axs[1].transAxes)
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle("Selected-failure reliability follow-up: gpt-6.1-sol gateway label", weight="bold")
    fig.supxlabel(
        "Four known failure cases, five repeats per arm; not twenty independent tasks.\nExact earlier strings and grader; no output repair. Prior study scores remain unchanged.",
        fontsize=9,
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
