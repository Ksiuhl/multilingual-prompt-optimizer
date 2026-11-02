"""Export measured task-quality charts as PNG, SVG and PDF (no simulated values)."""

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/task-quality-v040.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures"))
    args = parser.parse_args()
    raw = args.input.read_bytes()
    report = json.loads(raw)
    if not report.get("complete"):
        raise ValueError("Cannot graph an incomplete experiment")
    arms = ["original", "english", "mixed", "guarded_mixed"]
    labels = ["Original", "English-only", "Mixed", "Checked\nmixed"]
    colors = ["#426B96", "#D18A25", "#378B76", "#7655A3"]
    stats = [report["summary"][a] for a in arms]
    trials = stats[0]["trials"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []

    def save(fig, name):
        for suffix in ("png", "svg", "pdf"):
            p = args.output_dir / (name + "." + suffix)
            fig.savefig(p, dpi=220, bbox_inches="tight", facecolor="white")
            if suffix == "svg":
                p.write_text(
                    "\n".join(line.rstrip() for line in p.read_text(encoding="utf-8").splitlines())
                    + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            artifacts.append(p.name)
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.8))
    fig.suptitle(
        "v0.4 — Task checks, prompt tokens and processing time",
        fontsize=18,
        fontweight="bold",
        y=1.02,
    )
    x = np.arange(4)
    rates = [100 * s["pass_rate"] for s in stats]
    axes[0].bar(x, rates, color=colors, zorder=3)
    for i, s in enumerate(stats):
        axes[0].text(i, rates[i] + 2, f"{s['passed']}/{s['trials']}", ha="center", fontsize=11)
    axes[0].set_ylim(0, 112)
    axes[0].set_ylabel("Passed configured task checks (%)")
    axes[0].set_title("A. Validated task success")
    tokens = [s["content_tokens_attempted"] for s in stats]
    axes[1].bar(x, tokens, color=colors, zorder=3)
    for i, value in enumerate(tokens):
        axes[1].text(i, value + max(tokens) * 0.025, f"{value:,}", ha="center", fontsize=10)
    axes[1].set_ylim(0, max(tokens) * 1.18)
    axes[1].set_ylabel(f"Attempted input-content tokens, {trials} requests")
    axes[1].set_title("B. Prompt usage, including fallback")
    width = 0.34
    standalone = [s["standalone_ms_per_request"] / 1000 for s in stats]
    reused = [s["reuse_amortized_ms_per_request"] / 1000 for s in stats]
    axes[2].bar(
        x - width / 2, standalone, width, color="#426B96", label="Charge prep per request", zorder=3
    )
    axes[2].bar(
        x + width / 2, reused, width, color="#8BBEAE", label="Amortize prep / 3 uses", zorder=3
    )
    for i, (a, b) in enumerate(zip(standalone, reused)):
        axes[2].text(i - width / 2, a + max(standalone) * 0.02, f"{a:.2f}", ha="center", fontsize=9)
        axes[2].text(i + width / 2, b + max(standalone) * 0.02, f"{b:.2f}", ha="center", fontsize=9)
    axes[2].set_ylim(0, max(standalone) * 1.3)
    axes[2].set_ylabel("Measured seconds per request")
    axes[2].set_title("C. Local processing overhead")
    axes[2].legend(loc="upper left", fontsize=9, frameon=False)
    for ax in axes:
        ax.set_xticks(x, labels)
        ax.grid(axis="y", color="#E3E7EB", zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.02,
        -0.05,
        "20 synthetic development fixtures × 3 repeats; repeats share templates and frozen candidates, so are not independent samples.\n"
        "Configured source-oracle / bounded-code checks; checked mixed can return no valid answer. Local Qwen3 4B target + 8B reviewer.\n"
        "Content tokens: o200k_base, excluding model wrappers. Timings include real fallback and preparation; no monetary cost was measured.",
        fontsize=10,
        color="#46515D",
    )
    fig.tight_layout(w_pad=2.5)
    save(fig, "v040-overview")

    kinds = ["extraction", "filtering", "arithmetic", "code"]
    values = np.array(
        [
            [
                100
                * report["summary"][a]["by_kind"][k]["passed"]
                / report["summary"][a]["by_kind"][k]["trials"]
                for a in arms
            ]
            for k in kinds
        ]
    )
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    im = ax.imshow(values, vmin=0, vmax=100, cmap="YlGnBu", aspect="auto")
    for i, k in enumerate(kinds):
        for j, a in enumerate(arms):
            s = report["summary"][a]["by_kind"][k]
            ax.text(
                j,
                i,
                f"{s['passed']}/{s['trials']}\n{values[i, j]:.0f}%",
                ha="center",
                va="center",
                color="white" if values[i, j] > 65 else "#17212B",
                fontsize=12,
                fontweight="bold",
            )
    ax.set_xticks(range(4), labels)
    ax.set_yticks(range(4), [k.capitalize() for k in kinds])
    ax.set_title("Task-check passes by category", fontweight="bold", pad=16)
    fig.colorbar(im, ax=ax, label="Passed configured checks (%)", shrink=0.8)
    fig.text(
        0.02,
        0.005,
        "Five fixtures per category, three repeated outputs each. Code checks cover a restricted Python subset.\n"
        "Synthetic development results; configured-oracle success is not general accuracy or semantic proof.",
        fontsize=10,
        color="#46515D",
    )
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    save(fig, "v040-by-category")
    manifest = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_canonical_sha256": hashlib.sha256(
            json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "matplotlib_version": matplotlib.__version__,
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "artifacts": artifacts,
        "trials_per_arm": trials,
        "data": report["summary"],
    }
    (args.output_dir / "v040-plot-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"artifacts": artifacts}), flush=True)


if __name__ == "__main__":
    main()
