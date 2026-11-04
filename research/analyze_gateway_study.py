import gzip
import hashlib
import importlib.util
import json
import shutil
import statistics
from importlib.machinery import SourceFileLoader
from pathlib import Path

import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "results/local/gateway-v060"
ROOT.mkdir(parents=True, exist_ok=True)
DATA = BASE / "data"
RUBRIC = DATA / "gateway-v060-rubric.txt"
loader = SourceFileLoader("gateway_rubric", str(RUBRIC))
spec = importlib.util.spec_from_loader("gateway_rubric", loader)
rubric = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rubric)
dataset = json.loads((DATA / "gateway-v060.json").read_text(encoding="utf-8"))
cases = {c["id"]: c for t in dataset["templates"] for c in t["cases"]}
assert rubric.self_check(dataset) == 50
raw = json.loads(
    gzip.decompress((BASE / "results/gateway-v060-raw.json.gz").read_bytes()).decode("utf-8")
)
assert raw["grader_sha256"] == hashlib.sha256(RUBRIC.read_bytes()).hexdigest()
requests = json.loads((BASE / "results/gateway-v060-requests.json").read_text(encoding="utf-8"))
request_map = {(r["case_id"], r["arm"]): r for r in requests}
assert len(request_map) == 150
for p in raw["profiles"]:
    completed = [t for t in p["trials"] if t.get("complete")]
    assert len({(t["case_id"], t["arm"]) for t in completed}) == len(completed)
    assert all(
        t["prompt_sha256"] == request_map[t["case_id"], t["arm"]]["prompt_sha256"]
        for t in completed
    )
    if p["complete"]:
        assert len(completed) == 150
summary = {
    "complete": raw["complete"],
    "identity_verification": raw["identity_verification"],
    "profiles": [],
    "actual_invoiced_usd": None,
    "cost_note": "Gateway prices and invoices unavailable. Token usage does not establish dollar savings. Unknown usage from failed/timed-out requests remains unknown. Preparation cost is not amortized or charged to a particular model arm.",
    "limitations": raw["limitations"],
}
summary["available_models_complete"] = raw.get("available_models_complete", False)
prep = json.loads(
    gzip.decompress((BASE / "results/gateway-v060-preparation.json.gz").read_bytes()).decode(
        "utf-8"
    )
)
prep_scopes = [
    prep["preparation"],
    prep.get("preparation_failures", []),
    prep.get("discarded_preparation", {}).get("preparation", []),
]
known_attempts = {}


def visit(value):
    if isinstance(value, dict):
        if (
            "model" in value
            and "elapsed_ms" in value
            and ("events" in value or "error_type" in value)
        ):
            key = hashlib.sha256(
                json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            known_attempts[key] = value
        for child in value.values():
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)


visit(prep_scopes)
counter_calls = (
    prep.get("counter_calls", [])
    + prep.get("previous_counter_calls", [])
    + prep.get("discarded_preparation", {}).get("counter_calls", [])
)
summary["preparation_overhead"] = {
    "known_model_request_attempts": len(known_attempts),
    "known_attempts_without_usage": sum(not a.get("usage") for a in known_attempts.values()),
    "reported_input_tokens": sum(
        (a.get("usage") or {}).get("promptTokenCount", 0) for a in known_attempts.values()
    ),
    "reported_output_tokens": sum(
        (a.get("usage") or {}).get("candidatesTokenCount", 0) for a in known_attempts.values()
    ),
    "reported_thinking_tokens": sum(
        (a.get("usage") or {}).get("thoughtsTokenCount", 0) for a in known_attempts.values()
    ),
    "known_template_preparation_wall_ms": sum(
        p.get("elapsed_ms", 0) for scope in prep_scopes for p in scope
    ),
    "token_counter_requests": len(counter_calls),
    "summed_counter_request_latency_ms": sum(c.get("elapsed_ms", 0) for c in counter_calls),
    "scope_note": "Includes discarded English-copy draft, malformed JSON preparation, retained preparation failures, and the final candidate pool. Counter-latency sum is not wall time because some reads ran concurrently. A kernel-reset in-flight preparation has unknown completion/usage, so overhead is a recorded lower bound. Gemini 3.6 reselection used the existing pool. This is shared preparation, not separate per-gateway-model optimization.",
}
arms = ["original", "concise_english", "mixed"]
for p in raw["profiles"]:
    for t in p["trials"]:
        if t.get("complete"):
            t["validation"] = (
                rubric.grade(cases[t["case_id"]], t.get("answer"))
                if not t.get("answer_parse_error")
                else {"passed": False, "reason": "invalid_json"}
            )
    rows = {a: [t for t in p["trials"] if t["arm"] == a and t.get("complete")] for a in arms}
    common = set.intersection(*[{t["case_id"] for t in rows[a]} for a in arms])
    profile = {
        "model_label": p["label"],
        "connection": p["connection"],
        "complete": p["complete"],
        "stopped": p["stopped"],
        "completed_answers": sum(len(r) for r in rows.values()),
        "planned_requests": 150,
        "fully_paired_inputs": len(common),
        "arms": {},
        "stop_reason": p.get("stop_reason"),
        "last_http_status": p["request_attempts"][-1].get("http_status")
        if p["request_attempts"]
        else None,
        "returned_model_labels": sorted(
            {t.get("model_returned", "unknown") for t in p["trials"] if t.get("complete")}
        ),
    }
    for arm, ts in rows.items():
        valid = [t for t in ts if t["case_id"] in common]
        prompt = [t["usage"].get("prompt_tokens") for t in ts if isinstance(t.get("usage"), dict)]
        output = [
            t["usage"].get("completion_tokens") for t in ts if isinstance(t.get("usage"), dict)
        ]
        profile["arms"][arm] = {
            "planned_inputs": 50,
            "successful_responses": len(ts),
            "rubric_passes": sum(t["validation"]["passed"] for t in ts),
            "fully_paired_passes": sum(t["validation"]["passed"] for t in valid),
            "input_tokens": sum(v for v in prompt if isinstance(v, int))
            if len(prompt) == len(ts) and all(isinstance(v, int) for v in prompt) and ts
            else None,
            "output_tokens": sum(v for v in output if isinstance(v, int))
            if len(output) == len(ts) and all(isinstance(v, int) for v in output) and ts
            else None,
            "reported_cached_input_tokens": sum(
                t.get("usage", {}).get("prompt_tokens_details", {}).get("cached_tokens", 0)
                for t in ts
            ),
            "mean_latency_ms": statistics.mean(t["elapsed_ms"] for t in ts) if ts else None,
            "by_category": {
                kind: {
                    "responses": sum(t["kind"] == kind for t in ts),
                    "passed": sum(t["validation"]["passed"] for t in ts if t["kind"] == kind),
                }
                for kind in ["extraction", "filtering", "arithmetic", "summary", "code"]
            },
        }
    paired_en = {t["case_id"]: t for t in rows["concise_english"] if t["case_id"] in common}
    paired_mix = {t["case_id"]: t for t in rows["mixed"] if t["case_id"] in common}
    identical = [
        i for i in common if paired_en[i]["prompt_sha256"] == paired_mix[i]["prompt_sha256"]
    ]
    profile["identical_english_mixed_inputs"] = len(identical)
    profile["different_answers_on_identical_prompts"] = sum(
        paired_en[i].get("answer") != paired_mix[i].get("answer") for i in identical
    )
    profile["different_pass_fail_on_identical_prompts"] = sum(
        paired_en[i]["validation"]["passed"] != paired_mix[i]["validation"]["passed"]
        for i in identical
    )
    differences = [
        paired_mix[i].get("usage", {}).get("prompt_tokens", 0)
        - paired_en[i].get("usage", {}).get("prompt_tokens", 0)
        for i in identical
    ]
    profile["same_prompt_input_usage_differences"] = {
        str(x): differences.count(x) for x in sorted(set(differences))
    }
    profile["same_prompt_pairs_with_different_reported_input_tokens"] = sum(
        x != 0 for x in differences
    )
    profile["diagnostic_only_summary_wrapper_omissions"] = {
        a: sum(
            t["kind"] == "summary"
            and t["validation"]["reason"] == "wrong_transport"
            and isinstance(t.get("answer"), dict)
            and rubric.grade(cases[t["case_id"]], {"answer": t["answer"]})["passed"]
            for t in rows[a]
        )
        for a in arms
    }
    profile["diagnostic_note"] = (
        "Primary scores unchanged. This diagnostic only checks whether failed summaries pass the frozen rubric after adding a missing outer answer wrapper; it is not a new independent accuracy test."
    )
    if profile["same_prompt_pairs_with_different_reported_input_tokens"]:
        profile["usage_caveat"] = (
            "Byte-identical user prompts produced different reported input-token counts. Hidden gateway context/routing/usage accounting is unobserved; raw input differences cannot be isolated as prompt-content savings."
        )
    summary["profiles"].append(profile)
(ROOT / "results.json").write_text(
    json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
(ROOT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
lines = [
    "GATEWAY FROZEN-PROMPT STUDY",
    "Gateway labels are unverified; these are not direct-provider measurements.",
    "50 synthetic inputs, ten templates, one request per arm/model. Mixed policy often retains English.",
    "",
]
for p in summary["profiles"]:
    lines.append(
        f"{p['model_label']}: {p['completed_answers']}/150 completed; fully paired inputs {p['fully_paired_inputs']}"
    )
    for arm, a in p["arms"].items():
        lines.append(
            f"  {arm}: {a['rubric_passes']}/{a['successful_responses']} rubric passes; input={a['input_tokens']}; output={a['output_tokens']}; latency_ms={a['mean_latency_ms']}"
        )
    lines.append(
        f"  Identical English/mixed prompt pairs: {p['identical_english_mixed_inputs']}; answer changes on those pairs: {p['different_answers_on_identical_prompts']}"
    )
    lines.append(
        f"  Missing outer answer wrapper, facts pass diagnostic: {p['diagnostic_only_summary_wrapper_omissions']}"
    )
    lines.append(
        f"  Identical prompt pairs with different reported input counts: {p['same_prompt_pairs_with_different_reported_input_tokens']}"
    )
    if p.get("usage_caveat"):
        lines.append("  " + p["usage_caveat"])
    lines.append("")
lines.extend(
    [
        "SHARED PREPARATION OVERHEAD",
        json.dumps(summary["preparation_overhead"], indent=2),
        summary["cost_note"],
        "",
        "Unavailable responses are missing, not wrong answers. Accuracy is conditional on a completed response. The fact/format summary rubric is not full semantic evaluation.",
    ]
)
(ROOT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
shutil.copyfile(RUBRIC, ROOT / "frozen-rubric.txt")
shutil.copyfile(DATA / "gateway-v060.json", ROOT / "dataset.json")
shutil.copyfile(__file__, ROOT / "analyze_gateway_study.py")
print(
    json.dumps(
        {
            "completed_answers": sum(p["completed_answers"] for p in summary["profiles"]),
            "available_models_complete": summary["available_models_complete"],
            "scores": {
                p["model_label"]: {a: x["rubric_passes"] for a, x in p["arms"].items()}
                for p in summary["profiles"]
            },
            "preparation": summary["preparation_overhead"],
        }
    )
)

plt.switch_backend("Agg")

working = [p for p in summary["profiles"] if p["completed_answers"]]
if working:
    fig, axes = plt.subplots(
        2, len(working), figsize=(6 * len(working), 8), squeeze=False, layout="constrained"
    )
    colors = ["#627e95", "#45917c", "#c18c35"]
    for col, p in enumerate(working):
        ax = axes[0, col]
        vals = [p["arms"][a]["rubric_passes"] for a in arms]
        bars = ax.bar(["Original", "Concise EN", "Mixed policy"], vals, color=colors)
        ax.set(
            ylim=(0, 56),
            ylabel="Strict task/format passes out of 50 inputs",
            title=p["model_label"] + " (gateway label)",
        )
        for bar, a in zip(bars, arms):
            r = p["arms"][a]
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{r['rubric_passes']}/{r['successful_responses']}",
                ha="center",
            )
        ax = axes[1, col]
        base = p["arms"]["original"]["input_tokens"]
        vals = [
            100 * p["arms"][a]["input_tokens"] / base
            if base and p["arms"][a]["input_tokens"] is not None
            else 0
            for a in arms
        ]
        bars = ax.bar(["Original", "Concise EN", "Mixed policy"], vals, color=colors)
        ax.set(
            ylim=(0, 115),
            ylabel="Reported input tokens, original = 100%",
            title="Gateway-reported input tokens",
        )
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.1f}%", ha="center")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    fig.suptitle("Frozen prompts across two gateway model labels", weight="bold", fontsize=15)
    fig.supxlabel(
        "45/50 English/mixed prompt pairs are identical. GPT failures omit the outer answer wrapper.\nGPT usage varies on six identical pairs. Grok unavailable (403). Model identity and billed cost unverified.",
        fontsize=9,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(ROOT / f"comparison.{ext}", dpi=180)
    plt.close(fig)
    (ROOT / "plot-manifest.json").write_text(
        json.dumps(
            {
                "source_results_sha256": hashlib.sha256(
                    (ROOT / "results.json").read_bytes()
                ).hexdigest(),
                "summary_sha256": hashlib.sha256((ROOT / "summary.json").read_bytes()).hexdigest(),
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
