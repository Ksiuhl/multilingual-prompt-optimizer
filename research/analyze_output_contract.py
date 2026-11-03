"""Offline checks for the targeted, unchanged-rubric output-contract regression."""

import gzip
import hashlib
import importlib.util
import json
import statistics
from importlib.machinery import SourceFileLoader
from pathlib import Path

import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
RESULTS = BASE / "results"
OUT = RESULTS / "local/output-contract-v060"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_archive(path):
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def analyze():
    protocol = read_json(RESULTS / "output-contract-v060-protocol.json")
    requests_path = RESULTS / "output-contract-v060-requests.json"
    assert hashlib.sha256(requests_path.read_bytes()).hexdigest() == protocol["requests_sha256"]
    previous_bytes = gzip.decompress((RESULTS / "gateway-v060-raw.json.gz").read_bytes())
    assert hashlib.sha256(previous_bytes).hexdigest() == protocol["source_results_sha256"]
    rubric_path = DATA / "gateway-v060-rubric.txt"
    assert hashlib.sha256(rubric_path.read_bytes()).hexdigest() == protocol["grader_sha256"]
    loader = SourceFileLoader("contract_frozen_rubric", str(rubric_path))
    spec = importlib.util.spec_from_loader("contract_frozen_rubric", loader)
    rubric = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rubric)
    cases = {c["id"]: c for c in read_json(DATA / "output-contract-v060-cases.json")}
    requests = read_json(requests_path)
    lookup = {(r["case_id"], r["arm"], r["repetition"]): r for r in requests}
    original_requests = {
        (r["case_id"], r["arm"]): r for r in read_json(RESULTS / "gateway-v060-requests.json")
    }
    assert len(cases) == 6 and len(lookup) == 36
    for r in requests:
        assert hashlib.sha256(r["prompt"].encode()).hexdigest() == r["prompt_sha256"]
        before = original_requests[r["case_id"], r["arm"]]
        before_system, before_json = before["prompt"].split("\n\n", 1)
        after_system, after_json = r["prompt"].split("\n\n", 1)
        assert before_system == after_system
        before_value = json.loads(before_json)["user_prompt"]
        after_value = json.loads(after_json)["user_prompt"]
        assert after_value == before_value + "\n\n" + r["output_contract"]
    raw = read_archive(RESULTS / "output-contract-v060-raw.json.gz")
    previous = json.loads(previous_bytes)
    summary = {
        "complete": raw["complete"],
        "unique_inputs": 6,
        "repetitions": 2,
        "requests_per_model": 36,
        "scope": protocol["type"],
        "profiles": [],
        "limitations": protocol["limitations"]
        + ["All concise-English/mixed-policy pairs in this regression have identical prompts."],
        "actual_invoiced_usd": None,
    }
    for profile in raw["profiles"]:
        assert profile["complete"] and len(profile["trials"]) == 36
        assert len({(t["case_id"], t["arm"], t["repetition"]) for t in profile["trials"]}) == 36
        for trial in profile["trials"]:
            request = lookup[trial["case_id"], trial["arm"], trial["repetition"]]
            assert trial["complete"] and trial["prompt_sha256"] == request["prompt_sha256"]
            trial["validation"] = (
                rubric.grade(cases[trial["case_id"]], trial.get("answer"))
                if not trial.get("answer_parse_error")
                else {"passed": False, "reason": "invalid_json"}
            )
        old = next(p for p in previous["profiles"] if p["label"] == profile["label"])
        entry = {"model_label": profile["label"], "arms": {}}
        for arm in ["original", "concise_english", "mixed"]:
            before = [t for t in old["trials"] if t["case_id"] in cases and t["arm"] == arm]
            after = [t for t in profile["trials"] if t["arm"] == arm]
            entry["arms"][arm] = {
                "before_correct": sum(t["validation"]["passed"] for t in before),
                "before_n": len(before),
                "after_correct": sum(t["validation"]["passed"] for t in after),
                "after_n": len(after),
                "correct_by_repeat": [
                    sum(t["validation"]["passed"] for t in after if t["repetition"] == n)
                    for n in [1, 2]
                ],
                "missing_wrapper_after": sum(
                    t["validation"].get("reason") == "wrong_transport" for t in after
                ),
                "input_tokens_before": sum(t["usage"]["prompt_tokens"] for t in before),
                "input_tokens_after": sum(t["usage"]["prompt_tokens"] for t in after),
                "output_tokens_before": sum(t["usage"]["completion_tokens"] for t in before),
                "output_tokens_after": sum(t["usage"]["completion_tokens"] for t in after),
                "mean_latency_ms_after": statistics.mean(t["elapsed_ms"] for t in after),
            }
        summary["profiles"].append(entry)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    plot(summary)
    (OUT / "plot-manifest.json").write_text(
        json.dumps(
            {
                "raw_archive_sha256": hashlib.sha256(
                    (RESULTS / "output-contract-v060-raw.json.gz").read_bytes()
                ).hexdigest(),
                "summary_sha256": hashlib.sha256((OUT / "summary.json").read_bytes()).hexdigest(),
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary))


def plot(summary):
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    names = ["Original", "Concise EN", "Mixed policy"]
    for ax, profile in zip(axes, summary["profiles"]):
        before = [profile["arms"][a] for a in ["original", "concise_english", "mixed"]]
        positions = [0, 1, 2]
        old = ax.bar(
            [x - 0.18 for x in positions],
            [100 * a["before_correct"] / a["before_n"] for a in before],
            width=0.34,
            label="Earlier run: 6 inputs",
            color="#bd8965",
        )
        new = ax.bar(
            [x + 0.18 for x in positions],
            [100 * a["after_correct"] / a["after_n"] for a in before],
            width=0.34,
            label="Contract: 6 inputs x 2 repeats",
            color="#438f7a",
        )
        for bars, prefix in [(old, "before"), (new, "after")]:
            for bar, row in zip(bars, before):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 2,
                    f"{row[prefix + '_correct']}/{row[prefix + '_n']}",
                    ha="center",
                    fontsize=9,
                )
        ax.set_xticks(positions, names)
        ax.set(
            ylim=(0, 115),
            title=profile["model_label"] + " (gateway label)",
            ylabel="Strict task/format checks passed (%)",
        )
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].legend(loc="lower right", fontsize=8)
    fig.suptitle("Explicit JSON contract: targeted regression, unchanged grader", weight="bold")
    fig.supxlabel(
        "Six selected known problem inputs; not a new benchmark. English/mixed prompts are identical.\n"
        "Contract overhead is included in usage. Original study scores remain unchanged.",
        fontsize=9,
    )
    for suffix in ["png", "svg", "pdf"]:
        fig.savefig(OUT / f"comparison.{suffix}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    analyze()
