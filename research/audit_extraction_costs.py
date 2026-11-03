"""Offline descriptive decomposition; never changes the admission experiment."""

import argparse
import gzip
import hashlib
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from multilingual_prompt_optimizer import TiktokenCounter


def raw(directory, name):
    path = directory / name
    return (
        path.read_bytes()
        if path.exists()
        else gzip.decompress((directory / (name + ".gz")).read_bytes())
    )


def read(directory, name):
    return json.loads(raw(directory, name))


def audit(directory, out, pricing):
    bills = read(directory, "billing-matched.json")["records"]
    ledger = {}
    for record in bills:
        if record["type"] == 2:
            assert record["request_id"] not in ledger
            assert type(record["quota"]) is int and record["quota"] >= 0
            ledger[record["request_id"]] = record
    counter = TiktokenCounter()
    attempts, finals, paired = [], [], {}
    for base in [directory, directory / "supplement"]:
        protocol = read(base, "protocol.json")
        for name, expected in protocol["files"].items():
            assert hashlib.sha256(raw(base, name)).hexdigest() == expected, name
        requests = {(r["case_id"], r["arm"]): r for r in read(base, "requests.json")}
        report = read(base, "results.json")
        assert report["complete"]
        profile = report["profiles"][0]
        assert profile["label"] == "gpt-6.1-sol"
        seen_indices = set()
        for trial in profile["trials"]:
            req = requests[trial["case_id"], trial["arm"]]
            assert trial["prompt_sha256"] == req["prompt_sha256"]
            assert hashlib.sha256(req["prompt"].encode()).hexdigest() == req["prompt_sha256"]
            assert trial["complete"]
            for ordinal, index in enumerate(trial["attempt_indices"], 1):
                assert index not in seen_indices
                seen_indices.add(index)
                saved = profile["request_attempts"][index]
                assert saved["prompt_sha256"] == req["prompt_sha256"]
                rid = saved["gateway_request_id"]
                bill = ledger[rid]
                usage = saved.get("usage")
                details = (usage or {}).get("prompt_tokens_details")
                cached = details.get("cached_tokens") if isinstance(details, dict) else None
                if cached is not None:
                    assert type(cached) is int and 0 <= cached <= bill["prompt_tokens"]
                if usage:
                    assert usage["prompt_tokens"] == bill["prompt_tokens"]
                    assert usage["completion_tokens"] == bill["completion_tokens"]
                row = {
                    "case_id": trial["case_id"],
                    "split": req["split"],
                    "arm": trial["arm"],
                    "attempt": ordinal,
                    "request_id": rid,
                    "complete": bool(saved.get("complete")),
                    "http_status": saved.get("http_status"),
                    "error_type": saved.get("error_type"),
                    "elapsed_ms": saved["elapsed_ms"],
                    "quota": bill["quota"],
                    "ledger_input_tokens": bill["prompt_tokens"],
                    "ledger_output_tokens": bill["completion_tokens"],
                    "client_usage_present": bool(usage),
                    "reported_cached_tokens": cached,
                    "is_final_attempt": index == trial["attempt_indices"][-1],
                }
                attempts.append(row)
                if row["is_final_attempt"]:
                    assert row["complete"] and usage
                    row["local_content_tokens"] = counter.count(req["prompt"])
                    row["reported_minus_local_tokens"] = (
                        bill["prompt_tokens"] - row["local_content_tokens"]
                    )
                    finals.append(row)
                    paired.setdefault(trial["case_id"], {})[trial["arm"]] = row
        assert seen_indices == set(range(len(profile["request_attempts"])))
    assert len({r["request_id"] for r in attempts}) == len(attempts)
    assert {r["request_id"] for r in attempts} == set(ledger)
    assert len(finals) == 64 and len(paired) == 32
    assert all(set(p) == {"original", "compressed"} for p in paired.values())
    interval = read(directory, "billing-combined-interval.json")
    assert sum(r["quota"] for r in attempts) == interval["counter_delta_quota"] == 16787
    assert interval["post_run_check"]["stable"]
    totals = {}
    split_totals = {}
    for split in [None, "development", "holdout"]:
        values = {}
        for arm in ["original", "compressed"]:
            all_rows = [
                r for r in attempts if r["arm"] == arm and (split is None or r["split"] == split)
            ]
            final_rows = [r for r in all_rows if r["is_final_attempt"]]
            values[arm] = {
                "trials": len(final_rows),
                "http_attempts": len(all_rows),
                "charged_quota": sum(r["quota"] for r in all_rows),
                "final_attempt_quota": sum(r["quota"] for r in final_rows),
                "nonfinal_attempt_quota": sum(
                    r["quota"] for r in all_rows if not r["is_final_attempt"]
                ),
                "local_content_tokens": sum(r["local_content_tokens"] for r in final_rows),
                "reported_final_input_tokens": sum(r["ledger_input_tokens"] for r in final_rows),
                "reported_final_output_tokens": sum(r["ledger_output_tokens"] for r in final_rows),
                "known_cached_tokens": sum(r["reported_cached_tokens"] or 0 for r in final_rows),
                "missing_cache_breakdowns": sum(
                    r["reported_cached_tokens"] is None for r in final_rows
                ),
            }
        if split is None:
            totals = values
        else:
            split_totals[split] = values
    outlier = max(finals, key=lambda r: r["quota"])
    pair = paired[outlier["case_id"]]
    other_pairs = [p for cid, p in paired.items() if cid != outlier["case_id"]]
    other_difference = sum(p["compressed"]["quota"] - p["original"]["quota"] for p in other_pairs)
    pair_difference = pair["compressed"]["quota"] - pair["original"]["quota"]
    retry_difference = (
        totals["compressed"]["nonfinal_attempt_quota"]
        - totals["original"]["nonfinal_attempt_quota"]
    )
    gap = totals["compressed"]["charged_quota"] - totals["original"]["charged_quota"]
    assert other_difference + pair_difference + retry_difference == gap == 951
    recorded = json.loads(pricing.read_text(encoding="utf-8"))
    entry = next(m for m in recorded["models"] if m["model_name"] == "gpt-6.1-sol")
    assert (
        entry["billing_expr"]
        == 'len <= 272000 ? tier("0_272k", p * 2 + cr * 0.1 + cc * 2.5 + c * 10) : tier("272k_plus", p * 4 + cr * 0.2 + cc * 5 + c * 15)'
    )
    assert all(r["ledger_input_tokens"] <= 272000 for r in attempts)

    # An inferred billing scenario, not authenticated key-group metadata.
    def base_quota(r, cached):
        return (
            (
                (r["ledger_input_tokens"] - cached) * 2
                + cached * 0.1
                + r["ledger_output_tokens"] * 10
            )
            / 1000000
            * interval["quota_per_unit"]
        )

    ratios = [
        r["quota"] / base_quota(r, r["reported_cached_tokens"])
        for r in finals
        if r["reported_cached_tokens"] is not None
    ]
    median_multiplier = statistics.median(ratios)
    fitted_multiplier = round(median_multiplier, 1)
    modeled = []
    for row in attempts:
        prediction = fitted_multiplier * base_quota(row, row["reported_cached_tokens"] or 0)
        modeled.append(
            {
                "request_id": row["request_id"],
                "observed_quota": row["quota"],
                "modeled_quota_before_rounding": prediction,
                "residual": row["quota"] - prediction,
            }
        )
    hypothetical_outlier = round(
        fitted_multiplier
        * base_quota(pair["compressed"], pair["original"]["reported_cached_tokens"])
    )
    summary = {
        "scope": "Post-hoc offline descriptive audit of existing records; no new model or billing calls. Primary evidence and rejected admission unchanged.",
        "totals": totals,
        "splits": split_totals,
        "local_input_reduction": 1
        - totals["compressed"]["local_content_tokens"] / totals["original"]["local_content_tokens"],
        "reported_input_reduction": 1
        - totals["compressed"]["reported_final_input_tokens"]
        / totals["original"]["reported_final_input_tokens"],
        "reported_minus_local_per_success": sorted(
            {r["reported_minus_local_tokens"] for r in finals}
        ),
        "output_token_increase": totals["compressed"]["reported_final_output_tokens"]
        - totals["original"]["reported_final_output_tokens"],
        "same_reported_cache_pairs": sum(
            p["original"]["reported_cached_tokens"] == p["compressed"]["reported_cached_tokens"]
            for p in paired.values()
        ),
        "exceptional_pair": pair,
        "observed_gap_decomposition": {
            "other_31_successful_pairs": other_difference,
            "exceptional_successful_pair": pair_difference,
            "timed_out_attempts": retry_difference,
            "total": gap,
        },
        "failed_attempts": [r for r in attempts if not r["complete"]],
        "recorded_pricing_reference": {
            "path": str(pricing.name),
            "observed_at_utc": recorded["observed_at_utc"],
            "expression": entry["billing_expr"],
        },
        "billing_fit_diagnostic": {
            "known_cache_rows_for_fit": len(ratios),
            "median_effective_multiplier": median_multiplier,
            "rounded_scenario_multiplier": fitted_multiplier,
            "rows_matching_nearest_integer_quota": sum(
                round(r["modeled_quota_before_rounding"]) == r["observed_quota"] for r in modeled
            ),
            "attempts": len(modeled),
            "max_absolute_residual_units": max(abs(r["residual"]) for r in modeled),
            "hypothetical_outlier_quota_with_original_cache_count": hypothetical_outlier,
            "assumptions": "Saved short-context rates; zero unreported cache writes; absent cache metadata treated as zero only in this diagnostic; inferred effective multiplier 0.3. Not proof of actual cache state or account group.",
        },
        "interpretation": [
            "Actual total compressed debit remains 951 units higher; the admission rejection is unchanged.",
            "The 31-pair remainder is a post-hoc diagnostic, not a replacement savings result or admission sample.",
            "The high-charge response lacks cache metadata and matches a no-cache-discount billing scenario. A cache miss cannot be proven from these records.",
            "The constant reported-minus-local difference may reflect added context, a tokenizer difference or gateway accounting; hidden prompt text is unavailable.",
            "Charged timeouts and caching/accounting differences dominated this run; the small output increase did not explain the main gap.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("summary.json", summary),
        ("attempts.json", attempts),
        ("billing-fit.json", modeled),
    ]:
        (out / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    plot(summary, out)
    manifest = {
        "primary_results_sha256": hashlib.sha256(raw(directory, "results.json")).hexdigest(),
        "supplement_results_sha256": hashlib.sha256(
            raw(directory / "supplement", "results.json")
        ).hexdigest(),
        "billing_sha256": hashlib.sha256(raw(directory, "billing-matched.json")).hexdigest(),
        "pricing_snapshot_sha256": hashlib.sha256(pricing.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256((out / "summary.json").read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "plot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "gap": summary["observed_gap_decomposition"],
                "local_reduction": summary["local_input_reduction"],
                "reported_reduction": summary["reported_input_reduction"],
                "fit": summary["billing_fit_diagnostic"],
            }
        )
    )


def plot(summary, out):
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    labels = [
        "Other 31\nsuccessful pairs",
        "Exceptional\nsuccessful pair",
        "Five timed-out\nattempts",
        "Full observed\nincrease",
    ]
    parts = summary["observed_gap_decomposition"]
    values = [
        parts["other_31_successful_pairs"],
        parts["exceptional_successful_pair"],
        parts["timed_out_attempts"],
    ]
    level = 0
    for i, value in enumerate(values):
        bottom = min(level, level + value)
        axes[0].bar(i, abs(value), bottom=bottom, color="#3b8872" if value < 0 else "#bb8060")
        axes[0].text(i, bottom + abs(value) + 45, f"{value:+,}", ha="center", fontsize=9)
        level += value
    axes[0].bar(3, level, color="#627abd")
    axes[0].text(3, level + 45, f"{level:+,}", ha="center", fontsize=9)
    axes[0].axhline(0, color="#555", linewidth=0.8)
    axes[0].set_xticks(range(4), labels)
    axes[0].set(
        title="Where the extra charge appears",
        ylabel="Compressed minus original: charged quota units",
        ylim=(-800, 1250),
    )
    for offset, arm, color, label in [
        (-0.18, "original", "#8e9eae", "Original"),
        (0.18, "compressed", "#3b8872", "Compressed"),
    ]:
        vals = [
            100 if arm == "original" else 100 * (1 - summary[k])
            for k in ["local_input_reduction", "reported_input_reduction"]
        ]
        bars = axes[1].bar(
            [i + offset for i in range(2)], vals, width=0.34, color=color, label=label
        )
        for bar, v in zip(bars, vals):
            axes[1].text(
                bar.get_x() + bar.get_width() / 2, v + 2, f"{v:.2f}", ha="center", fontsize=9
            )
    axes[1].set_xticks(
        range(2), ["Local o200k_base\ncontent count", "Gateway-reported\ninput count"]
    )
    axes[1].set(
        title="Same prompts, different counting scope",
        ylabel="Input tokens (% of original within each scope)",
        ylim=(0, 118),
    )
    axes[1].legend(loc="lower right")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Extraction cost audit: actual result remains +951 quota units (+12.01%)", weight="bold"
    )
    fig.supxlabel(
        "Post-hoc diagnostics only; no observations removed from the primary result.\nCache-state explanation is inferred; gateway credits are not an invoice. No new paid model calls.",
        fontsize=9,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / f"comparison.{ext}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--pricing",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results/heldout-v060/pricing.json",
    )
    args = parser.parse_args()
    audit(args.directory, args.out, args.pricing)
