"""Audit and summarize the frozen language-control gateway experiment offline."""

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

from strict_two_stage import oracle

ARMS = ("english", "chinese", "mixed")
FAMILIES = ("stock", "overlap", "latest")


def exact_answer(text, expected):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-JSON constant: " + value)

    try:
        parsed = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (TypeError, ValueError):
        return False
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True) == json.dumps(expected, ensure_ascii=False, sort_keys=True)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_files(directory, mapping):
    for name, expected in mapping.items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected, name


def difference_interval(rows, reference, case_ids, seed):
    # Equal family weighting and resampling whole case clusters preserve repeats.
    contrasts = {}
    for case_id in case_ids:
        selected = [r for r in rows if r["case"] == case_id]
        means = {arm: statistics.mean(r["correct"] for r in selected if r["arm"] == arm) for arm in ("mixed", reference)}
        contrasts[case_id] = (selected[0]["family"], means["mixed"] - means[reference])
    families = {f: [v for k, v in contrasts.values() if k == f] for f in FAMILIES}
    families = {f: values for f, values in families.items() if values}
    rng = random.Random(seed)
    draws = sorted(statistics.mean(statistics.mean(rng.choices(values, k=len(values))) for values in families.values()) for _ in range(10000))
    return {"mixed_minus": reference, "cases": len(case_ids), "families": list(families),
            "difference": statistics.mean(statistics.mean(values) for values in families.values()),
            "bootstrap_95pct": [draws[249], draws[9749]], "resamples": 10000,
            "method": "Family-stratified case-cluster percentile bootstrap; exploratory, not a confirmatory significance test."}


def analyze(directory):
    verify_files(directory, read(directory / "sha256.json"))
    freeze = read(directory / "preflight-freeze.json")
    verify_files(directory, freeze["files"])
    execution = read(directory / "execution.json")
    amendment = read(directory / "execution-amendment.json")
    assert execution["amendment_sha256"] == hashlib.sha256((directory / "execution-amendment.json").read_bytes()).hexdigest()
    if execution.get("execution_recovery_sha256"):
        assert execution["execution_recovery_sha256"] == hashlib.sha256((directory / "execution-recovery.json").read_bytes()).hexdigest()
    assert execution["complete"], "Do not inspect interim accuracy or report a partial schedule as complete"
    cases = {c["id"]: c for c in read(directory / "cases.json")}
    assert len(cases) == 30
    for case in cases.values():
        assert case["expected"] == {"answer": oracle(case["family"], case["payload"])}
        assert case["local_length_matched_10pct"] == (max(case["token_counts"].values()) / min(case["token_counts"].values()) <= 1.10)
    schedule = read(directory / "target-schedule.json")
    jobs = {(j["connection"], j["id"]): j for j in schedule}
    assert len(jobs) == len(schedule) == amendment["target_calls"]
    for case_id, case in cases.items():
        for connection in {j["connection"] for j in schedule}:
            variants = [j for j in schedule if j["case"] == case_id and j["connection"] == connection]
            assert len(variants) == 9
            assert {(j["arm"], j["rep"]) for j in variants} == {(a, r) for a in ARMS for r in (1, 2, 3)}
            assert len({j["prompt"] for j in variants}) == 3
            payload = json.dumps(case["payload"], ensure_ascii=False, separators=(",", ":"))
            assert all(j["prompt"].endswith("SOURCE:\n" + payload) for j in variants)
    records = {r["request_id"]: r for r in execution["billing_records"]}
    assert len(records) == len(execution["billing_records"])
    attempts = execution["attempts"]
    review_job = read(directory / "review-request.json")
    first_target = min(a["started_at_utc"] for a in attempts if a["phase"] == "target")
    for profile in amendment["models"]:
        reviews = [r for r in execution["reviews"] if r["connection"] == profile["connection"]]
        assert len(reviews) == 1
        reviewer = attempts[reviews[0]["attempt_index"]]
        assert reviewer["phase"] == "review" and reviewer["complete"] and reviewer["started_at_utc"] < first_target
        assert reviewer["prompt_sha256"] == hashlib.sha256(review_job["prompt"].encode()).hexdigest()
        assert len(reviewer["answer"]["families"]) == 3
        assert all(any(r["family"] == family and r["equivalent"] is True for r in reviewer["answer"]["families"]) for family in FAMILIES)
    ids = [a["request_id"] for a in attempts if a.get("request_id")]
    assert len(ids) == len(set(ids))
    assert set(records) == set(ids), "Unexpected or missing request-level charges"
    assert all(r["type"] == 2 and isinstance(r["quota"], (int, float)) and r["quota"] >= 0 for r in records.values())
    rows = []
    seen = set()
    for trial in execution["trials"]:
        key = (trial["connection"], trial["job_id"])
        assert key not in seen
        seen.add(key)
        job = jobs[key]
        attempt = attempts[trial["attempt_index"]]
        assert attempt["job_id"] == trial["job_id"] and attempt["connection"] == trial["connection"]
        assert attempt["prompt_sha256"] == hashlib.sha256(job["prompt"].encode()).hexdigest()
        assert attempt["complete"]
        assert attempt["started_at_utc"] >= freeze["at_utc"]
        case = cases[trial["case"]]
        # Object-key order is irrelevant; array order, types, field set and values are exact.
        correct = exact_answer(attempt.get("text"), case["expected"])
        billing = records.get(attempt.get("request_id"))
        assert billing is not None, "Unmatched target charge"
        rows.append({**trial, "correct": correct, "expected": case["expected"], "actual": attempt.get("answer"),
                     "text": attempt.get("text"), "local_tokens": job["local_tokens"], "quota": billing["quota"],
                     "usage": attempt.get("usage"), "elapsed_ms": attempt["elapsed_ms"], "request_id": attempt["request_id"],
                     "local_length_matched_10pct": case["local_length_matched_10pct"]})
    assert seen == set(jobs)
    matched_attempts = [a for a in attempts if a.get("request_id") in records]
    assert len(matched_attempts) == len(attempts), "All attempts, including failures/retries, require quota accounting"
    summary = {"run_complete": True, "two_model_study_complete": execution["full_study_model_coverage_complete"],
               "identity": amendment["identity"], "models": {}, "cases": len(cases), "target_trials": len(rows),
               "attempts": len(attempts), "review_attempts": sum(a["phase"] == "review" for a in attempts),
               "target_attempts": sum(a["phase"] == "target" for a in attempts), "failed_target_attempts": sum(a["phase"] == "target" and not a["complete"] for a in attempts),
               "run_quota": sum(r["quota"] for r in records.values()), "quota_counter_delta": execution["checkpoints"][-1]["total_delta_quota"],
               "prior_setup_quota": (amendment.get("prior_setup") or {}).get("known_quota", 0),
               "local_length_matched_cases": sum(c["local_length_matched_10pct"] for c in cases.values()),
               "errors": [r for r in rows if not r["correct"]]}
    assert summary["run_quota"] == summary["quota_counter_delta"], "Log charges and interval counter do not reconcile"
    summary["whole_followup_known_quota"] = summary["run_quota"] + summary["prior_setup_quota"]
    summary["review_quota"] = sum(records[a["request_id"]]["quota"] for a in attempts if a["phase"] == "review")
    for profile in amendment["models"]:
        model_rows = [r for r in rows if r["connection"] == profile["connection"]]
        result = {"gateway_label": profile["label"], "returned_labels": sorted({attempts[r["attempt_index"]].get("model_returned", "unknown") for r in model_rows}), "arms": {}, "contrasts": []}
        for arm in ARMS:
            selected = [r for r in model_rows if r["arm"] == arm]
            result["arms"][arm] = {"correct": sum(r["correct"] for r in selected), "trials": len(selected),
                "target_quota": sum(r["quota"] for r in selected), "local_input_tokens": sum(r["local_tokens"] for r in selected),
                "reported_input_tokens": sum((r["usage"] or {}).get("prompt_tokens", 0) for r in selected),
                "reported_output_tokens": sum((r["usage"] or {}).get("completion_tokens", 0) for r in selected),
                "reported_cached_tokens": sum(((r["usage"] or {}).get("prompt_tokens_details") or {}).get("cached_tokens", 0) for r in selected),
                "median_latency_ms": statistics.median(r["elapsed_ms"] for r in selected),
                "by_family": {f: {"correct": sum(r["correct"] for r in selected if r["family"] == f), "trials": sum(r["family"] == f for r in selected)} for f in FAMILIES}}
        for subset in ("all", "local_length_matched"):
            selected_cases = [c["id"] for c in cases.values() if subset == "all" or c["local_length_matched_10pct"]]
            for ref in ("english", "chinese"):
                result["contrasts"].append({"subset": subset, **difference_interval(model_rows, ref, selected_cases, 60408)})
        summary["models"][str(profile["connection"])] = result
    return summary, rows


def write_report(directory, summary):
    lines = ["# Three-language control follow-up", "", "This is a targeted exploratory gateway study. Upstream model identities are unverified.", "",
             f"Completed **{summary['target_trials']} target answers** on **30 fresh opaque-ID inputs**, with three arms and three repeats. "
             + ("Two gateway labels completed." if summary["two_model_study_complete"] else "**Only one gateway label was available; the planned second-model comparison remains incomplete.**"), "",
             "The supplied Gemini connection returned HTTP 400 during semantic review; the Grok connection returned HTTP 403 `routes_paused`. Neither produced benchmark answers. Those failures and the first successful GPT review are preserved in the setup evidence.", "",
             "| Arm | Exact correct | Target-only quota | Median request seconds |", "|---|---:|---:|---:|"]
    for model in summary["models"].values():
        for arm, metrics in model["arms"].items():
            lines.append(f"| {model['gateway_label']} / {arm} | {metrics['correct']}/{metrics['trials']} | {metrics['target_quota']:,} | {metrics['median_latency_ms']/1000:.2f} |")
        lines += ["", "| Family | English correct | Chinese-only correct | Mixed correct |", "|---|---:|---:|---:|"]
        for family in FAMILIES:
            values = [model["arms"][arm]["by_family"][family] for arm in ARMS]
            lines.append("| " + family + " | " + " | ".join(f"{v['correct']}/{v['trials']}" for v in values) + " |")
        lines += ["", "| Subset | Paired contrast | Difference (percentage points) | Exploratory cluster-bootstrap 95% interval |", "|---|---|---:|---:|"]
        for c in model["contrasts"]:
            lo, hi = c["bootstrap_95pct"]
            lines.append(f"| {c['subset']} ({c['cases']} cases) | Mixed minus {c['mixed_minus']} | {c['difference']*100:.2f} | [{lo*100:.2f}, {hi*100:.2f}] |")
    lines += ["", f"All run attempts cost **{summary['run_quota']:,} gateway quota units**, including **{summary['review_quota']:,}** for the run's semantic review. "
              f"Earlier setup attempts add **{summary['prior_setup_quota']:,}**, for **{summary['whole_followup_known_quota']:,}** known units in the whole follow-up. "
              "All attempt IDs were matched to consumption records; the completed run's sum reconciles to its interval usage counter. These are not official-provider prices.", "",
              "## Interpretation limits", "",
              "This study tests accuracy controls, not automatic compression admission or end-to-end optimizer savings. No production defaults changed. "
              "Mixed means a Chinese rule clause followed by an English clause, not word-by-word search. "
              "Translations were author-written and received an automated review from the same gateway label used to answer; no independent bilingual human certified them. "
              "The local o200k_base length subset includes 20 cases, not a model-native tokenizer match. All 30 cases remain the primary analysis. "
              "The three families were chosen after earlier failures. Repeats are clustered within inputs and the bootstrap resamples cases within family; "
              "only three templates and limited structural diversity remain, so intervals do not measure uncertainty across arbitrary tasks or models. "
              "A zero-width interval or perfect score on a narrow subset would not establish a zero population effect. "
              "Cache behavior, provider-default sampling/reasoning, hidden gateway wrappers and load are uncontrolled. "
              "Target-only quota differences exclude authoring labor and any future optimizer preparation. No answer was repaired or rerun based on correctness.", "",
              "The gateway's metadata endpoints returned HTTP 429 after 15 target trials, with Retry-After 1200 seconds. "
              "The run paused without grading answers, honored the cooldown, and resumed the unmodified remaining schedule only after quota/log verification. "
              "The recovery amendment reduced metadata polling to at most once per 90 further requests, with the same soft quota caps. "
              "This introduces a time gap and possible load/cache drift, and increases possible cap overshoot between checks.", "",
              "## Reproduce offline", "", "Run `python research/analyze_language_control.py --input <unpacked study directory> --out <new output directory>` with project dependencies installed. "
              "The auditor checks frozen hashes, exact request membership, expected-answer oracles, source consistency, attempt provenance and complete quota matching before grading.", ""]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")


def plots(directory, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    model = next(iter(summary["models"].values()))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    colors = ["#5470C6", "#35A17D", "#ED974B"]
    for n, arm in enumerate(ARMS):
        values = [model["arms"][arm]["by_family"][f] for f in FAMILIES]
        bars = axes[0].bar([i+(n-1)*.25 for i in range(3)], [v["correct"]/v["trials"]*100 for v in values], width=.24, label=arm, color=colors[n])
        axes[0].bar_label(bars, labels=[f"{v['correct']}/{v['trials']}" for v in values], fontsize=8, padding=3)
    axes[0].set(xticks=range(3), xticklabels=FAMILIES, ylabel="Exact accuracy (%)", ylim=(0, 112), title="Accuracy on fresh boundary cases")
    axes[0].legend(loc="lower left", fontsize=8)
    contrasts = model["contrasts"]
    for i, c in enumerate(contrasts):
        value = c["difference"]*100
        lo, hi = [x*100 for x in c["bootstrap_95pct"]]
        axes[1].plot([lo, hi], [i, i], color="#5470C6", linewidth=3)
        axes[1].scatter(value, i, color="#ED974B", zorder=3)
    axes[1].axvline(0, color="gray", linestyle="--")
    axes[1].set(yticks=range(len(contrasts)), yticklabels=[f"Mixed − {c['mixed_minus']}\n{c['subset']} ({c['cases']} inputs)" for c in contrasts], xlabel="Accuracy difference (percentage points)", title="Exploratory 95% case-cluster intervals")
    fig.suptitle(f"{model['gateway_label']} — unverified gateway label; one-model portion")
    fig.supxlabel("30 inputs × 3 arms × 3 repeats. Local length subset is a proxy; no independent second model.", fontsize=9)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(directory / ("comparison."+ext), dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary, rows = analyze(args.input)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, value in (("summary.json", summary), ("trials.json", rows)):
        (args.out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    write_report(args.out, summary)
    plots(args.out, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
