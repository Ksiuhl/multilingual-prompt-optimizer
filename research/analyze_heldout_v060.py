"""Reproduce the prospectively frozen 50-input check, without API calls."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

EXPRESSIONS = {
    "gpt-6.1-sol": 'len <= 272000 ? tier("0_272k", p * 2 + cr * 0.1 + cc * 2.5 + c * 10) : tier("272k_plus", p * 4 + cr * 0.2 + cc * 5 + c * 15)',
    "gemini-4-argon": 'tier("standard", p * 2 + cr * 0.1 + ai * 2 + c * 10)',
}


def scenario_usd(usage, label):
    """Public-expression scenario, multiplier 1; never actual invoiced cost."""
    if not isinstance(usage, dict):
        return None
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    if (
        any(
            isinstance(n, bool) or not isinstance(n, int) or n < 0
            for n in [prompt, completion, cached]
        )
        or cached > prompt
    ):
        return None
    long = label == "gpt-6.1-sol" and prompt > 272000
    input_rate, cache_rate, output_rate = (4, 0.2, 15) if long else (2, 0.1, 10)
    return (
        (prompt - cached) * input_rate + cached * cache_rate + completion * output_rate
    ) / 1000000


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_bytes(directory, name):
    path = directory / name
    if path.exists():
        return path.read_bytes()
    return gzip.decompress((directory / (name + ".gz")).read_bytes())


def analyze(directory, out):
    protocol = read(directory / "protocol.json")
    for name, expected in protocol["files"].items():
        assert hashlib.sha256(frozen_bytes(directory, name)).hexdigest() == expected, (
            f"Frozen file changed: {name}"
        )
    source = directory / "grader-source.py"
    assert sha(source) == protocol["grader_source_sha256"], "Frozen grader changed"
    spec = importlib.util.spec_from_file_location("heldout_frozen_grade", source)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    cases = {c["id"]: c for c in read(directory / "dataset.json")["cases"]}
    grader.self_check(list(cases.values()))
    requests = json.loads(frozen_bytes(directory, "requests.json"))
    preparation = json.loads(frozen_bytes(directory, "preparation.json"))
    reqs = {(r["case_id"], r["arm"]): r for r in requests}
    assert len(reqs) == len(requests) == 150
    assert len(cases) == 50
    for r in requests:
        assert hashlib.sha256(r["prompt"].encode()).hexdigest() == r["prompt_sha256"]
    result_path = directory / "results.json.gz"
    if not result_path.exists():
        result_path = directory / "results.json"
    raw = read(result_path)
    pricing_path = directory / "pricing.json"
    pricing = read(pricing_path) if pricing_path.exists() else None
    if pricing:
        pricing_raw = frozen_bytes(directory, "pricing-source.json")
        assert hashlib.sha256(pricing_raw).hexdigest() == pricing["source_response_sha256"]
        pricing_source = json.loads(pricing_raw)
        assert pricing["pricing_version"] == pricing_source["pricing_version"]
        for entry in pricing["models"]:
            assert entry in pricing_source["data"]
    assert raw["dataset_sha256"] == protocol["files"]["dataset.json"]
    assert raw["prepared_source_sha256"] == protocol["files"]["preparation.json"]
    assert raw["grader_sha256"] == protocol["grader_source_sha256"]
    summary = {
        "execution_complete": bool(raw["complete"]),
        "complete": bool(raw["complete"])
        and all(t.get("complete") for p in raw["profiles"] for t in p["trials"]),
        "inputs": 50,
        "templates": 10,
        "identical_english_mixed_pairs": sum(
            reqs[c, "concise_english"]["prompt"] == reqs[c, "mixed"]["prompt"] for c in cases
        ),
        "candidate_generation_api_calls": 0,
        "translation_api_tokens": 0,
        "local_candidate_search_ms_total": {
            arm: sum(p[key]["elapsed_ms"] for p in preparation)
            for arm, key in [("concise_english", "english"), ("mixed", "mixed")]
        },
        "actual_invoiced_usd": None,
        "pricing_snapshot": pricing,
        "cost_scenario_assumptions": [
            "Apply the recorded public expression only when it matches an explicitly supported formula; do not execute arbitrary expressions.",
            "Group multiplier 1, no discounts or surcharges; active key group and settlement are unverified.",
            "Use reported cached_tokens or zero when absent; unreported cache writes/audio are assumed zero. All requests contain text only.",
            "Missing-usage attempts are excluded and may have incurred charges. Manual authoring labor is unknown.",
            "A price scenario is not an actual bill or a demonstrated net cost reduction.",
        ],
        "scope": protocol["type"],
        "limitations": [
            "Gateway labels and usage are unverified; active billing group, discounts and invoices are unavailable, so actual dollar cost is unknown. Public pricing was discovered after freezing the protocol."
            if pricing and "no billing rate or invoice" in line
            else line
            for line in protocol["limitations"]
        ],
        "profiles": [],
    }
    for profile in raw["profiles"]:
        seen, scored = set(), []
        for trial in profile["trials"]:
            pair = trial["case_id"], trial["arm"]
            assert pair not in seen
            seen.add(pair)
            assert trial["prompt_sha256"] == reqs[pair]["prompt_sha256"]
            indices = trial["attempt_indices"]
            for index in indices:
                attempt = profile["request_attempts"][index]
                assert attempt["prompt_sha256"] == trial["prompt_sha256"]
            last = profile["request_attempts"][indices[-1]]
            first = profile["request_attempts"][indices[0]]
            request_latency = trial.get("elapsed_ms")
            if trial.get("complete") and first.get("started_at_utc") and last.get("started_at_utc"):
                request_latency = (
                    datetime.fromisoformat(last["started_at_utc"])
                    - datetime.fromisoformat(first["started_at_utc"])
                ).total_seconds() * 1000 + last["elapsed_ms"]
            validation = (
                grader.grade(cases[trial["case_id"]], last.get("text"))
                if trial.get("complete")
                else {"passed": False, "reason": "incomplete_request"}
            )
            scored.append(
                {
                    **trial,
                    "request_latency_ms": request_latency,
                    "validation": validation,
                    "template": cases[trial["case_id"]]["template"],
                }
            )
        if raw["complete"]:
            assert len(seen) == 150
            referenced = [i for t in scored for i in t["attempt_indices"]]
            assert len(referenced) == len(set(referenced)) == len(profile["request_attempts"])
            assert set(referenced) == set(range(len(profile["request_attempts"])))
        row = {
            "model_label": profile["label"],
            "complete": profile["complete"],
            "attempts": len(profile["request_attempts"]),
            "attempts_without_usage": sum(
                not isinstance(a.get("usage"), dict) for a in profile["request_attempts"]
            ),
            "observed_attempt_usage": {
                key: sum((a.get("usage") or {}).get(key) or 0 for a in profile["request_attempts"])
                for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
            },
            "arms": {},
            "paired": {},
            "failures": [],
        }
        for arm in grader.ARMS:
            trials = [t for t in scored if t["arm"] == arm]
            complete = [t for t in trials if t.get("complete")]
            with_usage = [t for t in complete if isinstance(t.get("usage"), dict)]
            usage_totals = {
                key: sum(t["usage"].get(key) or 0 for t in with_usage)
                for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
            }
            row["arms"][arm] = {
                "correct": sum(t["validation"]["passed"] for t in trials),
                "planned": 50,
                "attempted": len(trials),
                "completed": len(complete),
                "transport_failures": len(trials) - len(complete),
                "usage_present": len(with_usage),
                "provider_usage": usage_totals,
                "local_content_tokens": sum(reqs[c, arm]["local_content_tokens"] for c in cases),
                "median_latency_ms": statistics.median(t["elapsed_ms"] for t in complete)
                if complete
                else None,
                "median_request_latency_ms": statistics.median(
                    t["request_latency_ms"] for t in complete
                )
                if complete
                else None,
                "templates": {
                    template: {
                        "correct": sum(
                            t["validation"]["passed"] for t in trials if t["template"] == template
                        ),
                        "planned": 5,
                    }
                    for template in sorted({c["template"] for c in cases.values()})
                },
            }
            for t in trials:
                if not t["validation"]["passed"]:
                    row["failures"].append({"case_id": t["case_id"], "arm": arm, **t["validation"]})
        by_pair = {(t["case_id"], t["arm"]): t for t in scored}
        common = [
            c
            for c in cases
            if all(
                (c, a) in by_pair
                and by_pair[c, a].get("complete")
                and isinstance(by_pair[c, a].get("usage"), dict)
                for a in grader.ARMS
            )
        ]
        row["common_case_usage"] = {
            "n": len(common),
            "arms": {
                a: {
                    key: sum(by_pair[c, a]["usage"].get(key) or 0 for c in common)
                    for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
                }
                for a in grader.ARMS
            },
        }
        row["common_case_median_request_ms"] = {
            a: statistics.median(by_pair[c, a]["request_latency_ms"] for c in common)
            if common
            else None
            for a in grader.ARMS
        }
        if pricing:
            entry = next(
                (m for m in pricing["models"] if m["model_name"] == profile["label"]), None
            )
            if entry and entry.get("billing_expr") == EXPRESSIONS.get(profile["label"]):
                values = {
                    a: [scenario_usd(by_pair[c, a]["usage"], profile["label"]) for c in common]
                    for a in grader.ARMS
                }
                if any(value is None for arm_values in values.values() for value in arm_values):
                    row["cost_scenario_unavailable_reason"] = (
                        "Invalid or incomplete reported usage on common inputs."
                    )
                    estimates = None
                else:
                    estimates = {a: sum(arm_values) for a, arm_values in values.items()}
                if estimates is not None:
                    row["cost_scenario"] = {
                        "common_inputs": len(common),
                        "group_multiplier": 1,
                        "common_usd": estimates,
                        "common_reduction": {
                            a: 1 - estimates[a] / estimates["original"]
                            if estimates["original"]
                            else None
                            for a in ["concise_english", "mixed"]
                        },
                        "observed_attempt_usd": sum(
                            scenario_usd(a.get("usage"), profile["label"]) or 0
                            for a in profile["request_attempts"]
                        ),
                        "attempts_without_cost_estimate": sum(
                            scenario_usd(a.get("usage"), profile["label"]) is None
                            for a in profile["request_attempts"]
                        ),
                    }
        for arm in ["concise_english", "mixed"]:
            a = row["arms"][arm]
            base = row["arms"]["original"]
            a["local_input_reduction"] = (
                1 - a["local_content_tokens"] / base["local_content_tokens"]
            )
            a["reported_input_reduction"] = (
                1 - a["provider_usage"]["prompt_tokens"] / base["provider_usage"]["prompt_tokens"]
                if base["provider_usage"]["prompt_tokens"]
                else None
            )
            a["reported_total_reduction"] = (
                1 - a["provider_usage"]["total_tokens"] / base["provider_usage"]["total_tokens"]
                if base["provider_usage"]["total_tokens"]
                else None
            )
            common_usage = row["common_case_usage"]["arms"]
            a["common_case_input_reduction"] = (
                1 - common_usage[arm]["prompt_tokens"] / common_usage["original"]["prompt_tokens"]
                if common_usage["original"]["prompt_tokens"]
                else None
            )
            a["common_case_total_reduction"] = (
                1 - common_usage[arm]["total_tokens"] / common_usage["original"]["total_tokens"]
                if common_usage["original"]["total_tokens"]
                else None
            )
            row["paired"][arm] = {
                "original_only_correct": sum(
                    by_pair[c, "original"]["validation"]["passed"]
                    and not by_pair[c, arm]["validation"]["passed"]
                    for c in cases
                    if (c, "original") in by_pair and (c, arm) in by_pair
                ),
                "optimized_only_correct": sum(
                    not by_pair[c, "original"]["validation"]["passed"]
                    and by_pair[c, arm]["validation"]["passed"]
                    for c in cases
                    if (c, "original") in by_pair and (c, arm) in by_pair
                ),
            }
        identical = [
            (by_pair[c, "concise_english"], by_pair[c, "mixed"])
            for c in cases
            if (c, "concise_english") in by_pair
            and (c, "mixed") in by_pair
            and reqs[c, "concise_english"]["prompt"] == reqs[c, "mixed"]["prompt"]
        ]
        row["identical_prompt_diagnostic"] = {
            "pairs": len(identical),
            "different_pass_status": sum(
                a["validation"]["passed"] != b["validation"]["passed"] for a, b in identical
            ),
            "different_reported_input_tokens": sum(
                (a.get("usage") or {}).get("prompt_tokens")
                != (b.get("usage") or {}).get("prompt_tokens")
                for a, b in identical
            ),
        }
        summary["profiles"].append(row)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    plot(summary, out)
    manifest = {
        "source_results_sha256": sha(result_path),
        "protocol_sha256": sha(directory / "protocol.json"),
        "summary_sha256": sha(out / "summary.json"),
        "analyzer_sha256": sha(Path(__file__)),
    }
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "complete": summary["complete"],
                "profiles": [
                    {
                        "model": p["model_label"],
                        "correct": {a: r["correct"] for a, r in p["arms"].items()},
                        "diagnostic": p["identical_prompt_diagnostic"],
                    }
                    for p in summary["profiles"]
                ],
            }
        )
    )


def plot(summary, out):
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(
        len(summary["profiles"]), 4, figsize=(16, 7), layout="constrained", squeeze=False
    )
    colors = ["#8e9eae", "#3b8872", "#627abd"]
    labels = ["Original", "Concise EN", "Mixed policy"]
    for axs, profile in zip(axes, summary["profiles"]):
        rows = [profile["arms"][a] for a in ["original", "concise_english", "mixed"]]
        common_usage = profile["common_case_usage"]
        input_totals = [
            common_usage["arms"][a]["prompt_tokens"]
            for a in ["original", "concise_english", "mixed"]
        ]
        base = input_totals[0]
        total_totals = [
            common_usage["arms"][a]["total_tokens"]
            for a in ["original", "concise_english", "mixed"]
        ]
        total_base = total_totals[0]
        measures = [
            ([r["correct"] * 2 for r in rows], "Strict checks passed (%)"),
            (
                [100 * value / base if base else 0 for value in input_totals],
                f"Reported input (% original)\n{common_usage['n']} common inputs",
            ),
            (
                [100 * value / total_base if total_base else 0 for value in total_totals],
                f"Reported total (% original)\n{common_usage['n']} common inputs",
            ),
            (
                [
                    (profile["common_case_median_request_ms"][a] or 0) / 1000
                    for a in ["original", "concise_english", "mixed"]
                ],
                f"Median request latency (seconds)\n{common_usage['n']} common inputs",
            ),
        ]
        for ax, (values, title) in zip(axs, measures):
            bars = ax.bar(labels, values, color=colors)
            for i, bar in enumerate(bars):
                label = f"{rows[i]['correct']}/50" if ax is axs[0] else f"{values[i]:.1f}"
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values or [1]) * 0.025,
                    label,
                    ha="center",
                    fontsize=9,
                )
            ax.set(title=title, ylim=(0, max(max(values) * 1.18, 1)))
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=0.15)
            ax.set_axisbelow(True)
        axs[0].set_ylabel(profile["model_label"] + "\n(gateway label)")
    fig.suptitle("50 frozen new inputs: English-first candidate search", weight="bold")
    completed = sum(r["completed"] for p in summary["profiles"] for r in p["arms"].values())
    fig.supxlabel(
        f"10 synthetic templates, 5 inputs each; one planned trial per arm/model with bounded transport retries. {completed}/300 responses completed.\n"
        "English/mixed prompts identical in all 50 pairs. Full prompt includes JSON contract.\n"
        "Local o200k_base selection is a proxy; provider usage is unverified and is not an invoice.",
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
