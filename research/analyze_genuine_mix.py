"""Audit the frozen genuine-mixing pilot offline; never call an API."""

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

from multilingual_prompt_optimizer import Request
from multilingual_prompt_optimizer.tokenizers import TiktokenCounter

ARMS = ["original", "concise_english", "genuine_mixed"]


def raw(directory, name):
    path = directory / name
    return (
        path.read_bytes()
        if path.exists()
        else gzip.decompress((directory / (name + ".gz")).read_bytes())
    )


def read(directory, name):
    return json.loads(raw(directory, name))


def digest(b):
    return hashlib.sha256(b).hexdigest()


def analyze(directory, out):
    protocol = read(directory, "protocol.json")
    for name, sha in protocol["files"].items():
        assert digest(raw(directory, name)) == sha, name
    preflight = read(directory, "preflight.json")
    assert digest(raw(directory, "oracle-check.py")) == preflight["oracle_source_sha256"]
    assert preflight["cases_checked"] == 20
    data = read(directory, "dataset.json")
    cases = {c["id"]: c for c in data["cases"]}
    assert len(cases) == 20 and len({c["template"] for c in cases.values()}) == 10

    def canonical(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    payloads = {canonical(c["payload"]) for c in cases.values()}
    assert len(payloads) == 20
    prior = Path(__file__).resolve().parents[1] / "results"
    for rel in [
        "heldout-v060/dataset.json",
        "validated-extraction-v060/dataset.json",
        "validated-extraction-v060/supplement/dataset.json",
        "cache-followup-v060/dataset.json",
        "fresh-cache-v060/dataset.json",
    ]:
        assert not payloads.intersection(
            canonical(c["payload"])
            for c in json.loads((prior / rel).read_text(encoding="utf-8"))["cases"]
        )
    prepared = {p["case_id"]: p for p in read(directory, "preparation.json")}
    requests = read(directory, "requests.json")
    keys = {(r["case_id"], r["arm"], r["repetition"]): r for r in requests}
    assert len(keys) == len(requests) == 120
    counter = TiktokenCounter()
    for r in requests:
        assert r["local_content_tokens"] == counter.count(r["prompt"])
    for cid, p in prepared.items():
        choice = p["mixed_choice"]
        assert "en" in choice["languages"] and len(set(choice["languages"])) > 1
        for lang, segment in zip(choice["languages"], choice["segments"]):
            assert (
                len(re.findall(r"[A-Za-z]+", segment)) >= 4
                if lang == "en"
                else len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", segment)) >= 4
            )
        assert choice["segments"] == [
            slot[lang] for slot, lang in zip(p["aligned_clauses"], choice["languages"])
        ]
        assert (
            choice["instruction"]
            == " ".join(choice["segments"])
            == p["instructions"]["genuine_mixed"]
        )
        assert p["instructions"]["concise_english"] in p["english_accepted"]
        assert p["instructions"]["concise_english"] != choice["instruction"]
        for arm in ARMS:
            req = Request(
                instruction=p["instructions"][arm],
                payload=p["payload"],
                output_instruction=p["output_contract"],
            )
            for rep in [1, 2]:
                r = keys[cid, arm, rep]
                assert r["prompt"] == req.compose(req.instruction)
                assert digest(r["prompt"].encode()) == r["prompt_sha256"]
    spec = importlib.util.spec_from_file_location(
        "genuine_frozen_grader", directory / "grader-source.py"
    )
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    grader.self_check(list(cases.values()))
    report = read(directory, "results.json")
    assert report["dataset_sha256"] == protocol["files"]["dataset.json"]
    assert report["prepared_source_sha256"] == protocol["files"]["requests.json"]
    assert report["grader_sha256"] == protocol["files"]["grader-source.py"]
    assert report["protocol"] == protocol
    profile = report["profiles"][0]
    assert profile["label"] == protocol["model_label"]
    assert [(t["case_id"], t["arm"], t["repetition"]) for t in profile["trials"]] == [
        (r["case_id"], r["arm"], r["repetition"]) for r in requests[: len(profile["trials"])]
    ]
    bills = {}
    for b in read(directory, "billing-matched.json")["records"]:
        if b["type"] == 2:
            assert b["request_id"] not in bills and type(b["quota"]) is int and b["quota"] >= 0
            bills[b["request_id"]] = b
    seen, used, ids, rows, attempts = set(), set(), set(), [], []
    for t in profile["trials"]:
        key = t["case_id"], t["arm"], t["repetition"]
        assert key not in seen and key in keys
        seen.add(key)
        r = keys[key]
        assert t["prompt_sha256"] == r["prompt_sha256"]
        current = []
        for index in t["attempt_indices"]:
            assert index not in used
            used.add(index)
            a = profile["request_attempts"][index]
            assert a["prompt_sha256"] == r["prompt_sha256"]
            rid = a.get("gateway_request_id")
            if rid:
                assert rid not in ids
                ids.add(rid)
            b = bills.get(rid)
            u = a.get("usage") or {}
            if b and u:
                assert u["prompt_tokens"] == b["prompt_tokens"]
                assert u["completion_tokens"] == b["completion_tokens"]
            item = {
                "case_id": key[0],
                "arm": key[1],
                "repetition": key[2],
                "attempt_index": index,
                "request_id": rid,
                "complete": bool(a.get("complete")),
                "http_status": a.get("http_status"),
                "error_type": a.get("error_type"),
                "charged_quota": b["quota"] if b else None,
                "input_tokens": u.get("prompt_tokens"),
                "output_tokens": u.get("completion_tokens"),
            }
            attempts.append(item)
            current.append(item)
        first = profile["request_attempts"][t["attempt_indices"][0]]
        final = profile["request_attempts"][t["attempt_indices"][-1]]
        elapsed = (
            datetime.fromisoformat(final["started_at_utc"])
            - datetime.fromisoformat(first["started_at_utc"])
        ).total_seconds() * 1000 + final["elapsed_ms"]
        check = (
            grader.grade(cases[key[0]], final.get("text"))
            if t.get("complete")
            else {"passed": False, "reason": "incomplete_request"}
        )
        cached = ((final.get("usage") or {}).get("prompt_tokens_details") or {}).get(
            "cached_tokens"
        )
        if cached is not None:
            assert type(cached) is int and 0 <= cached <= final["usage"]["prompt_tokens"]
        rows.append(
            {
                "case_id": key[0],
                "template": cases[key[0]]["template"],
                "arm": key[1],
                "repetition": key[2],
                "block": r["block"],
                "complete": bool(t.get("complete")),
                "validation": check,
                "attempts": len(current),
                "known_quota": sum(a["charged_quota"] or 0 for a in current),
                "charge_complete": all(a["charged_quota"] is not None for a in current),
                "reported_input_tokens": sum(a["input_tokens"] or 0 for a in current),
                "reported_output_tokens": sum(a["output_tokens"] or 0 for a in current),
                "cached_tokens": cached,
                "cache_category": "unknown" if cached is None else "positive" if cached else "zero",
                "request_ms_including_retries": elapsed,
                "local_content_tokens": r["local_content_tokens"],
            }
        )
    assert used == set(range(len(profile["request_attempts"]))) and set(bills) <= ids
    if report["complete"]:
        assert seen == set(keys)
    total = sum(r["known_quota"] for r in rows)
    interval = read(directory, "quota-interval.json")
    reconciles = (
        total == interval["counter_delta_quota"]
        if interval["counter_delta_quota"] is not None
        else None
    )
    coverage = all(a["charged_quota"] is not None for a in attempts)
    arm_summary = {}
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        arm_summary[arm] = {
            "planned": 40,
            "attempted": len(selected),
            "completed": sum(r["complete"] for r in selected),
            "correct": sum(r["validation"]["passed"] for r in selected),
            "http_attempts": sum(r["attempts"] for r in selected),
            "known_quota": sum(r["known_quota"] for r in selected),
            "reported_input_tokens": sum(r["reported_input_tokens"] for r in selected),
            "reported_output_tokens": sum(r["reported_output_tokens"] for r in selected),
            "attempts_with_input_usage": sum(
                a["arm"] == arm and a["input_tokens"] is not None for a in attempts
            ),
            "attempts_with_output_usage": sum(
                a["arm"] == arm and a["output_tokens"] is not None for a in attempts
            ),
            "local_content_tokens": sum(r["local_content_tokens"] for r in selected),
            "median_request_ms": statistics.median(
                r["request_ms_including_retries"] for r in selected
            )
            if selected
            else None,
            "cache_categories": {
                k: sum(r["cache_category"] == k for r in selected)
                for k in ["positive", "zero", "unknown"]
            },
        }
    comparisons = []
    by_key = {(r["case_id"], r["arm"], r["repetition"]): r for r in rows}
    for cid in cases:
        for rep in [1, 2]:
            if (cid, "concise_english", rep) in by_key and (cid, "genuine_mixed", rep) in by_key:
                en, mix = by_key[cid, "concise_english", rep], by_key[cid, "genuine_mixed", rep]
                comparisons.append(
                    {
                        "case_id": cid,
                        "repetition": rep,
                        "english_pass": en["validation"]["passed"],
                        "mixed_pass": mix["validation"]["passed"],
                        "equal_reported_cache": en["cached_tokens"] == mix["cached_tokens"]
                        if en["cached_tokens"] is not None and mix["cached_tokens"] is not None
                        else None,
                    }
                )
    instability = []
    for cid in cases:
        for arm in ARMS:
            selected = [r for r in rows if r["case_id"] == cid and r["arm"] == arm]
            if (
                len(selected) == 2
                and selected[0]["validation"]["passed"] != selected[1]["validation"]["passed"]
            ):
                instability.append({"case_id": cid, "arm": arm})
    summary = {
        "execution_complete": report["complete"],
        "planned_requests": 120,
        "unattempted": 120 - len(rows),
        "inputs": 20,
        "task_families": 10,
        "repetitions": 2,
        "genuinely_mixed_pairs": 20,
        "identical_english_mixed": 0,
        "arms": arm_summary,
        "total_matched_quota": total,
        "counter_reconciles": reconciles,
        "charge_coverage_complete": coverage,
        "full_quota_comparison": bool(report["complete"] and coverage and reconciles),
        "mixed_vs_english_quota_change": arm_summary["genuine_mixed"]["known_quota"]
        / arm_summary["concise_english"]["known_quota"]
        - 1
        if coverage and reconciles and arm_summary["concise_english"]["known_quota"]
        else None,
        "paired_comparisons": comparisons,
        "mixed_only_passes": sum(r["mixed_pass"] and not r["english_pass"] for r in comparisons),
        "english_only_passes": sum(r["english_pass"] and not r["mixed_pass"] for r in comparisons),
        "within_prompt_correctness_instability": instability,
        "case_arm_results": {
            cid: {
                arm: {
                    "attempted": sum(r["case_id"] == cid and r["arm"] == arm for r in rows),
                    "correct": sum(
                        r["validation"]["passed"]
                        for r in rows
                        if r["case_id"] == cid and r["arm"] == arm
                    ),
                }
                for arm in ARMS
            }
            for cid in cases
        },
        "by_template": {
            kind: {
                arm: sum(
                    r["validation"]["passed"]
                    for r in rows
                    if r["template"] == kind and r["arm"] == arm
                )
                for arm in ARMS
            }
            for kind in sorted({c["template"] for c in cases.values()})
        },
        "by_repetition": {
            str(rep): {
                arm: sum(
                    r["validation"]["passed"]
                    for r in rows
                    if r["repetition"] == rep and r["arm"] == arm
                )
                for arm in ARMS
            }
            for rep in [1, 2]
        },
        "failed_attempts": [a for a in attempts if not a["complete"]],
        "unknown_attempt_charges": sum(a["charged_quota"] is None for a in attempts),
        "limitations": protocol["limitations"],
        "prior_admission_changed": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in [
        ("summary.json", summary),
        ("trials.json", rows),
        ("attempts.json", attempts),
    ]:
        (out / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), layout="constrained")
    labels = ["Original", "Concise EN", "Genuine mix"]
    for ax, field, title, ylabel in [
        (axes[0], "correct", "Exact answers / 40 planned", "Correct"),
        (
            axes[1],
            "local_content_tokens",
            "Full-prompt local tokenizer proxy",
            "Content tokens across attempted prompts",
        ),
        (
            axes[2],
            "known_quota",
            "All matched charges" if coverage else "Incomplete ledger: totals not comparable",
            "Gateway quota units",
        ),
    ]:
        values = [arm_summary[a][field] for a in ARMS]
        bars = ax.bar(labels, values, color=["#929eaa", "#4d7ea5", "#3b8872"])
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
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)
    axes[0].set_ylim(0, 46)
    fig.suptitle(
        "Genuine multilingual pilot: 20 inputs, 10 task families, two repetitions", weight="bold"
    )
    fig.supxlabel(
        "Aligned hand-authored clauses; mixed must contain English + Chinese/Japanese. No cache control or causal language attribution.\nGateway model/accounting unverified; no significance claim, independent bilingual review or default-policy change.",
        fontsize=8,
    )
    for ext in ["png", "svg", "pdf"]:
        fig.savefig(out / ("comparison." + ext), dpi=180)
    plt.close(fig)
    manifest = {
        name: digest(raw(directory, name))
        for name in [
            "protocol.json",
            "results.json",
            "billing-matched.json",
            "quota-interval.json",
            "preflight.json",
            "oracle-check.py",
        ]
    }
    manifest["generator_sha256"] = digest(Path(__file__).read_bytes())
    for name in ["execution.json", "quota-checkpoints.json", "error-audit.json"]:
        if (directory / name).exists():
            manifest[name] = digest(raw(directory, name))
    manifest["outputs"] = {
        p.name: digest(p.read_bytes())
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
                    "counter_reconciles",
                    "mixed_only_passes",
                    "english_only_passes",
                    "total_matched_quota",
                ]
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.directory, args.out)
