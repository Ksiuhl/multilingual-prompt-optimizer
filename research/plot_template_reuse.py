"""Measured reuse endpoints and explicitly marked conditional larger-use projections."""

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
    parser.add_argument("--input", type=Path, default=Path("results/template-reuse-v050.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures"))
    args = parser.parse_args()
    raw = args.input.read_bytes()
    report = json.loads(raw)
    if not report.get("complete"):
        raise ValueError("Study must be complete before plotting")
    arms = ["original", "english", "mixed"]
    names = ["Original", "Cached English", "Cached mixed"]
    colors = ["#426B96", "#D18A25", "#378B76"]
    all_original = all(report["summary"][a].get("distinct_prompt_inputs", 0) == 0 for a in arms[1:])
    points = [1, 10, 100, 1000]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 13,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []

    def save(fig, name):
        for suffix in ("png", "svg", "pdf"):
            path = args.output_dir / (name + "." + suffix)
            fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
            if suffix == "svg":
                path.write_text(
                    "\n".join(s.rstrip() for s in path.read_text(encoding="utf-8").splitlines())
                    + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            artifacts.append(path.name)
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    fig.suptitle(
        "v0.5 — Reuse cannot save tokens without an approved shorter template"
        if all_original
        else "v0.5 — Reusable templates: measured checks and conditional reuse projections",
        fontsize=17,
        fontweight="bold",
        y=1.02,
    )
    x = np.arange(2)
    width = 0.24
    for j, (arm, name, color) in enumerate(zip(arms, names, colors)):
        stats = [report["reuse"][arm][str(n)] for n in [1, 10]]
        y = [100 * s["passed"] / s["requests"] for s in stats]
        positions = x + (j - 1) * width
        axes[0].bar(positions, y, width, color=color, label=name, zorder=3)
        for pos, value, s in zip(positions, y, stats):
            axes[0].text(pos, value + 2, f"{s['passed']}/{s['requests']}", ha="center", fontsize=9)
    axes[0].set_xticks(x, ["1 use/template\n4 fresh inputs", "10 uses/template\n40 fresh inputs"])
    axes[0].set_ylim(0, 110)
    axes[0].set_ylabel("Passed configured task checks (%)")
    axes[0].set_title("A. Measured answers only")
    axes[0].legend(loc="upper left", fontsize=9, frameon=False)
    for arm, name, color in zip(arms, names, colors):
        y = [report["reuse"][arm][str(n)]["ms_per_request"] / 1000 for n in points]
        axes[1].plot(points[:2], y[:2], color=color, marker="o", label=name)
        axes[1].plot(points[1:], y[1:], color=color, linestyle="--")
        axes[1].scatter(points[2:], y[2:], facecolors="white", edgecolors=color, zorder=4)
    axes[1].axvspan(10, 1100, color="#DCE3E9", alpha=0.25)
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xticks(points, [str(n) for n in points])
    axes[1].set_xlim(0.85, 1150)
    axes[1].set_ylabel("Seconds/request, including preparation (log scale)")
    axes[1].set_xlabel("Uses per template (four templates)")
    axes[1].set_title("B. Measured → conditional projections")
    axes[1].legend(loc="upper right", fontsize=9, frameon=False)
    totals = [report["summary"][a]["content_tokens_attempted"] for a in arms]
    axes[2].bar(range(3), totals, color=colors, zorder=3)
    for i, value in enumerate(totals):
        axes[2].text(i, value + max(totals) * 0.03, f"{value:,}", ha="center")
    axes[2].set_ylim(0, max(totals) * 1.25)
    axes[2].set_xticks(range(3), ["Original", "Cached\nEnglish", "Cached\nmixed"])
    axes[2].set_ylabel("Attempted content tokens, 40 measured inputs")
    axes[2].set_title(
        "C. No observed prompt-token saving"
        if all_original
        else "C. Measured attempted prompt tokens"
    )
    for ax in axes:
        ax.grid(axis="y", color="#E3E7EB", zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.02,
        -0.13,
        (
            "Four synthetic development templates, two calibration inputs each, then ten fresh inputs each. All test calls used original instructions.\n"
            if all_original
            else "Four synthetic development templates, two calibration inputs each, then ten fresh inputs each.\n"
        )
        + "Filled points: measured 1/10-use endpoints. Dashed/open points: 100/1000-use projections from observed mean times, not executed workloads.\n"
        "Identical-prompt timing/answer variation is not a cache benefit. No accuracy forecast or monetary saving is claimed; tokens use o200k_base.\n"
        "The 1/10-use accuracy endpoints have different case mixes; their difference does not establish an effect of reuse count.",
        fontsize=10,
        color="#46515D",
    )
    fig.tight_layout(w_pad=2.5)
    save(fig, "v050-reuse-overview")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8))
    for arm, name, color in zip(arms[1:], names[1:], colors[1:]):
        values = [report["reuse"][arm][str(n)]["preparation_ms_per_request"] / 1000 for n in points]
        axes[0].plot(points, values, color=color, marker="o", label=name)
        axes[0].text(
            points[-1], values[-1], f"  {values[-1] * 1000:.1f} ms", color=color, fontsize=10
        )
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xticks(points, [str(n) for n in points])
    axes[0].set_xlim(0.8, 2000)
    axes[0].set_xlabel("Uses per template")
    axes[0].set_ylabel("One-time preparation / requests (seconds, log scale)")
    axes[0].set_title("Calculated preparation amortization")
    axes[0].legend(frameon=False, fontsize=9)
    axes[0].grid(color="#E3E7EB")
    values = []
    cell_labels = []
    for item in report["templates"]:
        row = []
        texts = []
        for arm in ("english", "mixed"):
            p = item["prepared"][arm]
            admitted = p["cache_artifact"]["admitted"]
            shorter = (
                p["selected_tokens_on_representative"] < p["original_tokens_on_representative"]
            )
            row.append(1 if admitted and shorter else 0.5 if admitted else 0)
            texts.append(
                "Shorter admitted"
                if admitted and shorter
                else "Original only"
                if admitted
                else "Not admitted"
            )
        values.append(row)
        cell_labels.append(texts)
    from matplotlib.colors import ListedColormap

    axes[1].imshow(
        values,
        vmin=0,
        vmax=1,
        cmap=ListedColormap(["#E7ECEF", "#F4DFAF", "#7AB5A1"]),
        aspect="auto",
    )
    for i, row in enumerate(cell_labels):
        for j, text in enumerate(row):
            axes[1].text(j, i, text, ha="center", va="center", fontsize=10, color="#253543")
    axes[1].set_xticks([0, 1], ["English", "Mixed"])
    axes[1].set_yticks(range(len(values)), [t["id"].capitalize() for t in report["templates"]])
    axes[1].set_title("Calibration admission (not future certification)")
    fig.text(
        0.02,
        0.005,
        "Preparation was measured once; dividing it by N is arithmetic, not evidence that total processing becomes cheaper.\n"
        f"Shorter templates admitted: {sum(v == 1 for row in values for v in row)} / {2 * len(values)}. Original-only admitted: {sum(v == 0.5 for row in values for v in row)}. Calibration is not future certification.",
        fontsize=10,
        color="#46515D",
    )
    fig.tight_layout(w_pad=3, rect=(0, 0.1, 1, 1))
    save(fig, "v050-cache-admission")
    manifest = {
        "source_canonical_sha256": hashlib.sha256(
            json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__,
        "artifacts": artifacts,
        "summary": report["summary"],
    }
    (args.output_dir / "v050-plot-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"artifacts": artifacts}), flush=True)


if __name__ == "__main__":
    main()
