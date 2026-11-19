"""Draw every figure used in the project report.

All figures are generated from code rather than drawn by hand, which is both
what the report guidelines require and what makes them reproducible: the
accuracy charts read the measurement JSON that `scripts/measure_engines.py`
writes, so re-running the benchmark and re-running this produces a report
whose figures and tables cannot disagree with each other.

Output goes to `docs/report/figures/` as 300 dpi PNG.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "docs" / "report" / "figures"
DPI = 300

# EvalNova brand palette, so the report and the application look like one
# project rather than two.
NAVY = "#00164F"
BLUE = "#0E6CFD"
CYAN = "#00B2F3"
ICE = "#B9DCFE"
PASS = "#10B981"
REVIEW = "#F5A524"
FAIL = "#FB4A62"
GREY = "#586E92"
LINE = "#BCCDE6"

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 9,
        "axes.edgecolor": GREY,
        "axes.labelcolor": NAVY,
        "text.color": NAVY,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "axes.grid": True,
        "grid.color": LINE,
        "grid.linewidth": 0.5,
        "figure.facecolor": "white",
    }
)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  {name}")


def load_measurements() -> list[dict] | None:
    path = REPO_ROOT / "docs" / "report" / "data" / "engine_measurements.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Chapter 3 - design figures
# ---------------------------------------------------------------------------


def _box(ax, x, y, w, h, text, fc, ec=None, fs=8.5, tc="white", bold=False):
    ax.add_patch(
        patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            facecolor=fc, edgecolor=ec or fc, linewidth=1.0,
        )
    )
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=fs, color=tc,
        fontweight="bold" if bold else "normal", linespacing=1.35,
    )


def _arrow(ax, x1, y1, x2, y2, text=None, color=None):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color or GREY, linewidth=1.2,
                        shrinkA=2, shrinkB=2),
    )
    if text:
        ax.text((x1 + x2) / 2 + 0.015, (y1 + y2) / 2, text,
                fontsize=7.2, color=GREY, ha="left", va="center")


def fig_architecture():
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    _box(ax, 0.06, 0.845, 0.88, 0.115,
         "Browser  —  React 19 · TypeScript · Tailwind\n"
         "Transcribe · Library · Rubrics · Evaluation · Review · Validation",
         NAVY, fs=8.5, bold=True)
    _arrow(ax, 0.5, 0.845, 0.5, 0.775, "REST / JSON  (Vite proxy — no CORS)")

    _box(ax, 0.06, 0.655, 0.88, 0.115,
         "api/v1/   —   FastAPI routers:  answers · rubrics · evaluations · roadmap\n"
         "HTTP surface only: validation, status codes, serialisation",
         BLUE, fs=8.5, bold=True)
    _arrow(ax, 0.5, 0.655, 0.5, 0.585)

    _box(ax, 0.06, 0.465, 0.88, 0.115,
         "services/   —   preprocessing · ocr_service · evaluation_service · scoring\n"
         "rubric_service · rubric_import · document_text · review · analytics · audit",
         "#0B59CF", fs=8.5, bold=True)

    ax.annotate("", xy=(0.5, 0.345), xytext=(0.5, 0.465),
                arrowprops=dict(arrowstyle="-|>", color=FAIL, linewidth=1.6))
    ax.text(0.515, 0.405, "the replaceability boundary", fontsize=7.4,
            color=FAIL, ha="left", va="center", style="italic")

    _box(ax, 0.06, 0.225, 0.425, 0.115,
         "providers/ocr/\nTrOCR │ Gemini │ Mock", CYAN, fs=8.5, tc=NAVY, bold=True)
    _box(ax, 0.515, 0.225, 0.425, 0.115,
         "providers/evaluation/\nGemini │ Rubric matcher", CYAN, fs=8.5, tc=NAVY, bold=True)

    _box(ax, 0.06, 0.055, 0.425, 0.105,
         "db/  —  SQLAlchemy 2.0\n15 tables · SQLite", GREY, fs=8.5, bold=True)
    _box(ax, 0.515, 0.055, 0.425, 0.105,
         "core/  —  configuration\nthresholds · confidence weights", GREY, fs=8.5, bold=True)

    ax.text(0.5, 0.012,
            "Rule 1: nothing above providers/ imports torch, transformers or a vendor SDK.     "
            "Rule 2: nothing in services/ imports from api/.",
            ha="center", fontsize=6.9, color=NAVY, style="italic")
    save(fig, "fig_3_1_architecture.png")


def fig_pipeline():
    stages = [
        ("1  Load & resize", "cap at 2000 px"),
        ("2  Denoise", "3x3 median"),
        ("3  Assess quality", "blur, contrast"),
        ("4  Flatten illumination", "divide out paper"),
        ("5  Isolate ink — colour", "drop red / orange"),
        ("6  Isolate ink — darkness", "anchored to own ink"),
        ("7  Remove ruling", "morphology + Hough"),
        ("8  Classify page", "skip printed form"),
        ("9  Deskew", "sharpest projection"),
        ("10  Segment lines", "projection profile"),
        ("11  Filter boxes", "drop near-empty"),
        ("12  Recognise", "TrOCR / Gemini"),
        ("13  Score & store", "confidence, band, audit"),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    n = len(stages)
    h = 0.055
    gap = (1.0 - 0.02) / n
    colours = [BLUE] * 4 + [CYAN] * 4 + ["#0B59CF"] * 3 + [NAVY] * 2

    for i, ((title, detail), colour) in enumerate(zip(stages, colours)):
        y = 0.955 - i * gap
        tc = NAVY if colour == CYAN else "white"
        _box(ax, 0.10, y - h, 0.52, h, title, colour, fs=8.2, tc=tc, bold=True)
        ax.text(0.645, y - h / 2, detail, fontsize=7.6, color=GREY, va="center")
        if i < n - 1:
            ax.annotate("", xy=(0.36, y - h - gap + h), xytext=(0.36, y - h),
                        arrowprops=dict(arrowstyle="-|>", color=LINE, linewidth=1.1))

    ax.text(0.02, 0.50, "image preparation", rotation=90, fontsize=7.4,
            color=BLUE, ha="center", va="center", style="italic")
    save(fig, "fig_3_2_pipeline.png")


def fig_lifecycle():
    fig, ax = plt.subplots(figsize=(6.4, 1.85))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    states = ["REGISTERED", "OCR_RUNNING", "OCR_DONE", "EVALUATED",
              "UNDER_REVIEW", "FINALIZED"]
    w, h, y = 0.148, 0.26, 0.56
    for i, s in enumerate(states):
        x = 0.01 + i * 0.165
        _box(ax, x, y, w, h, s.replace("_", "\n"), NAVY, fs=7.4, bold=True)
        if i:
            ax.annotate("", xy=(x, y + h / 2), xytext=(x - 0.017, y + h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, linewidth=1.2))

    _box(ax, 0.176, 0.10, w, h, "OCR_FAILED", FAIL, fs=7.4, bold=True)
    ax.annotate("", xy=(0.25, 0.36), xytext=(0.25, 0.56),
                arrowprops=dict(arrowstyle="-|>", color=FAIL, linewidth=1.2))
    ax.text(0.5, 0.0,
            "Transitions are enforced in the service layer, not written as free text by callers.",
            ha="center", fontsize=7.2, color=GREY, style="italic")
    save(fig, "fig_3_3_lifecycle.png")


def fig_er_diagram():
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    nodes = {
        "Organization": (0.04, 0.88, BLUE),
        "User":         (0.04, 0.74, BLUE),
        "Exam":         (0.38, 0.88, NAVY),
        "Question":     (0.38, 0.74, NAVY),
        "AnswerKey":    (0.71, 0.74, GREY),
        "Rubric":       (0.38, 0.60, NAVY),
        "RubricCriterion": (0.71, 0.60, NAVY),
        "Answer":       (0.04, 0.44, "#0B59CF"),
        "OCRResult":    (0.38, 0.44, "#0B59CF"),
        "Evaluation":   (0.38, 0.28, CYAN),
        "EvaluationCriterion": (0.71, 0.28, CYAN),
        "Review":       (0.38, 0.14, PASS),
        "GroundTruth":  (0.04, 0.28, GREY),
        "ConfigSetting": (0.04, 0.03, GREY),
        "AuditLog":     (0.71, 0.03, GREY),
    }
    w, h = 0.25, 0.085
    for name, (x, y, c) in nodes.items():
        tc = NAVY if c == CYAN else "white"
        _box(ax, x, y, w, h, name, c, fs=7.6, tc=tc, bold=True)

    edges = [
        ("Organization", "User"), ("Exam", "Question"),
        ("Question", "AnswerKey"), ("Question", "Rubric"),
        ("Rubric", "RubricCriterion"), ("Answer", "OCRResult"),
        ("OCRResult", "Evaluation"), ("Evaluation", "EvaluationCriterion"),
        ("Evaluation", "Review"), ("Answer", "GroundTruth"),
        ("Question", "Answer"),
    ]
    for a, b in edges:
        ax1, ay1, _ = nodes[a]; ax2, ay2, _ = nodes[b]
        ax.annotate(
            "", xy=(ax2 + w / 2, ay2 + h), xytext=(ax1 + w / 2, ay1),
            arrowprops=dict(arrowstyle="-", color=LINE, linewidth=1.0,
                            connectionstyle="arc3,rad=0.08"),
        )

    ax.text(0.5, 0.965,
            "Append-only: Evaluation, EvaluationCriterion, Review, AuditLog",
            ha="center", fontsize=7.4, color=FAIL, style="italic")
    save(fig, "fig_3_4_er_diagram.png")


def fig_confidence():
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    signals = [
        ("Transcription", "0.30", "how well the page was read"),
        ("Agreement", "0.30", "two independent markings"),
        ("Grounding", "0.25", "quotations really occur"),
        ("Decisiveness", "0.15", "distance from the boundary"),
    ]
    for i, (name, weight, detail) in enumerate(signals):
        y = 0.78 - i * 0.195
        _box(ax, 0.02, y, 0.26, 0.145, name, BLUE, fs=8.2, bold=True)
        ax.text(0.30, y + 0.072, f"w = {weight}", fontsize=8, color=NAVY,
                va="center", fontweight="bold")
        ax.text(0.40, y + 0.072, detail, fontsize=7.4, color=GREY, va="center")
        ax.annotate("", xy=(0.80, 0.50), xytext=(0.72, y + 0.072),
                    arrowprops=dict(arrowstyle="-|>", color=LINE, linewidth=1.0))

    _box(ax, 0.80, 0.40, 0.18, 0.20,
         "weighted\ngeometric\nmean", NAVY, fs=8, bold=True)
    ax.text(0.89, 0.33, "one signal collapsing\ndrags the result down",
            ha="center", fontsize=7, color=FAIL, style="italic", va="top")
    ax.text(0.5, 0.055,
            r"$C \;=\; \prod_i s_i^{\,w_i / \sum w_i}$   —  weights redistribute when a signal cannot be measured",
            ha="center", fontsize=8.5, color=NAVY)
    save(fig, "fig_3_5_confidence.png")


def fig_bands():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 2.3))
    for ax, title, bands in (
        (a1, "Transcription bands",
         [(0.95, 1.00, "Reliable", PASS), (0.85, 0.95, "Spot check", CYAN),
          (0.70, 0.85, "Verify", REVIEW), (0.00, 0.70, "Manual transcription", FAIL)]),
        (a2, "Evaluation routing bands",
         [(0.95, 1.00, "Auto-accept candidate", PASS), (0.90, 0.95, "Quick review", CYAN),
          (0.85, 0.90, "Mandatory review", REVIEW), (0.00, 0.85, "Detailed verification", FAIL)]),
    ):
        for lo, hi, label, colour in bands:
            ax.barh(0, hi - lo, left=lo, height=0.5, color=colour, edgecolor="white")
            ax.text((lo + hi) / 2, 0.42, label, ha="center", va="bottom",
                    fontsize=6.6, color=NAVY, rotation=0)
        ax.set_xlim(0, 1); ax.set_ylim(-0.5, 0.95)
        ax.set_yticks([])
        ax.set_xticks([0, 0.7, 0.85, 0.9, 0.95, 1.0])
        ax.set_xticklabels(["0", "0.70", "0.85", "0.90", "0.95", "1.0"], fontsize=7)
        ax.set_title(title, fontsize=8.5, color=NAVY, pad=8)
        ax.grid(False)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_3_6_bands.png")


# ---------------------------------------------------------------------------
# Chapter 4 - results figures, driven by the measurement JSON
# ---------------------------------------------------------------------------


def fig_cer_per_page(data):
    local = next((s for s in data if s["engine"] == "local"), None)
    gemini = next((s for s in data if s["engine"] == "gemini"), None)
    if not (local and gemini):
        return

    pages = [r["page"] for r in local["results"]]
    lv = [r["cer"] * 100 for r in local["results"]]
    gv = [r["cer"] * 100 for r in gemini["results"]]

    x = np.arange(len(pages))
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.bar(x - 0.21, lv, 0.42, label="TrOCR (local)", color=ICE, edgecolor=GREY, linewidth=0.5)
    ax.bar(x + 0.21, gv, 0.42, label="Gemini (cloud)", color=BLUE, edgecolor=GREY, linewidth=0.5)
    ax.axhline(local["mean_cer"] * 100, color=GREY, ls="--", lw=0.9)
    ax.axhline(gemini["mean_cer"] * 100, color=BLUE, ls="--", lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([p.replace("writer_", "W").replace("_p", "p") for p in pages],
                       fontsize=7.5)
    ax.set_ylabel("Character error rate (%)")
    ax.set_xlabel("Answer page")
    ax.legend(fontsize=7.5, frameon=False)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "fig_4_1_cer_per_page.png")


def fig_accuracy_speed(data):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 2.6))
    names = [s["engine"] for s in data]
    labels = ["TrOCR\n(local, CPU)" if n == "local" else "Gemini\n(cloud)" for n in names]
    colours = [ICE if n == "local" else BLUE for n in names]

    cers = [s["mean_cer"] * 100 for s in data]
    a1.bar(labels, cers, color=colours, edgecolor=GREY, linewidth=0.6, width=0.55)
    for i, v in enumerate(cers):
        a1.text(i, v + max(cers) * 0.03, f"{v:.1f}%", ha="center", fontsize=8.5,
                color=NAVY, fontweight="bold")
    a1.set_ylabel("Mean character error rate (%)")
    a1.set_ylim(0, max(cers) * 1.22)

    secs = [s["mean_seconds"] for s in data]
    a2.bar(labels, secs, color=colours, edgecolor=GREY, linewidth=0.6, width=0.55)
    for i, v in enumerate(secs):
        a2.text(i, v + max(secs) * 0.03, f"{v:.1f} s", ha="center", fontsize=8.5,
                color=NAVY, fontweight="bold")
    a2.set_ylabel("Mean seconds per page")
    a2.set_ylim(0, max(secs) * 1.22)

    for ax in (a1, a2):
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_4_2_accuracy_speed.png")


def fig_confidence_vs_error(data):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    for s in data:
        colour = GREY if s["engine"] == "local" else BLUE
        marker = "o" if s["engine"] == "local" else "s"
        label = "TrOCR (local)" if s["engine"] == "local" else "Gemini (cloud)"
        xs = [r["confidence"] for r in s["results"]]
        ys = [min(r["cer"], 2.0) * 100 for r in s["results"]]
        ax.scatter(xs, ys, s=38, color=colour, marker=marker, label=label,
                   alpha=0.85, edgecolor="white", linewidth=0.8, zorder=3)

    for lo, hi, colour in ((0.95, 1.0, PASS), (0.85, 0.95, CYAN),
                           (0.70, 0.85, REVIEW), (0.0, 0.70, FAIL)):
        ax.axvspan(lo, hi, color=colour, alpha=0.07, zorder=0)
    for x, t in ((0.70, "Verify"), (0.85, "Spot check"), (0.95, "Reliable")):
        ax.axvline(x, color=LINE, lw=0.8, ls=":", zorder=1)

    ax.set_xlabel("Reported page confidence")
    ax.set_ylabel("Measured character error rate (%)")
    ax.set_xlim(0, 1.02)
    ax.legend(fontsize=7.5, frameon=False, loc="upper right")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "fig_4_3_confidence_vs_error.png")


def fig_quota():
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    labels = ["Transcription\n3 pages x 2 readings", "Marking\n5 questions x 2 samples"]
    values = [6, 10]
    bars = ax.barh(labels, values, color=[BLUE, CYAN], edgecolor=GREY,
                   linewidth=0.6, height=0.45)
    ax.axvline(15, color=FAIL, lw=1.6)
    ax.text(15.3, -0.52, "free-tier limit\n15 requests / minute", color=FAIL,
            fontsize=7.8, va="center")
    for b, v in zip(bars, values):
        ax.text(v + 0.3, b.get_y() + b.get_height() / 2, str(v),
                va="center", fontsize=8.5, color=NAVY, fontweight="bold")
    ax.barh(["Total for one\nthree-page booklet"], [16], color=NAVY,
            edgecolor=GREY, linewidth=0.6, height=0.45)
    ax.text(16.3, 2, "16", va="center", fontsize=8.5, color=NAVY, fontweight="bold")
    ax.set_xlabel("API requests")
    ax.set_xlim(0, 20)
    ax.tick_params(labelsize=8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_4_4_quota.png")


def fig_samples_tradeoff():
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    modes = ["Two readings\n(default)", "One reading\n(fast mode)"]
    secs = [139, 59]
    bars = ax.bar(modes, secs, color=[BLUE, ICE], edgecolor=GREY,
                  linewidth=0.6, width=0.5)
    for b, v in zip(bars, secs):
        ax.text(b.get_x() + b.get_width() / 2, v + 4, f"{v} s", ha="center",
                fontsize=9, color=NAVY, fontweight="bold")
    ax.set_ylabel("Wall clock, one 3-page booklet (s)")
    ax.set_ylim(0, 170)
    ax.text(0.5, 0.88,
            "Identical marks (15.5 / 30) in both modes.\n"
            "Fast mode buys speed by giving up the confidence measurement.",
            transform=ax.transAxes, ha="center", fontsize=7.8, color=GREY,
            style="italic", va="top")
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_4_5_samples_tradeoff.png")


def fig_tests():
    modules = {
        "rubric_document_import": 37, "scoring": 36, "pdf": 31, "evaluation": 29,
        "ocr_pipeline": 26, "preprocessing": 21, "rubric_editing": 21,
        "gemini_provider": 19, "api_contract": 12, "rate_limit": 12,
    }
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    names = list(modules)[::-1]
    vals = [modules[n] for n in names]
    ax.barh(names, vals, color=BLUE, edgecolor=GREY, linewidth=0.5, height=0.62)
    for i, v in enumerate(vals):
        ax.text(v + 0.5, i, str(v), va="center", fontsize=8, color=NAVY,
                fontweight="bold")
    ax.set_xlabel("Automated tests")
    ax.set_xlim(0, 42)
    ax.tick_params(labelsize=7.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_4_6_tests.png")


def fig_segmentation_sample():
    """A real page beside the line boxes the pipeline found on it."""
    import cv2

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.services.preprocessing import preprocess  # noqa: E402

    page = REPO_ROOT / "data" / "exam" / "pages" / "writer_1_p1.png"
    if not page.exists():
        print("  (no sample page; skipping segmentation figure)")
        return

    image = cv2.imread(str(page))
    gray, boxes, _ = preprocess(image, max_lines=40)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 4.2))
    a1.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    a1.set_title("(a)  original photograph", fontsize=8.5, color=NAVY)

    a2.imshow(gray, cmap="gray")
    for x, y, w, h in boxes:
        a2.add_patch(patches.Rectangle((x, y), w, h, fill=False,
                                       edgecolor=CYAN, linewidth=0.7))
    a2.set_title(f"(b)  ink isolated, {len(boxes)} lines detected",
                 fontsize=8.5, color=NAVY)
    for ax in (a1, a2):
        ax.axis("off"); ax.grid(False)
    fig.tight_layout()
    save(fig, "fig_4_7_segmentation.png")


def main() -> int:
    print("Drawing figures into", OUT.relative_to(REPO_ROOT))
    fig_architecture()
    fig_pipeline()
    fig_lifecycle()
    fig_er_diagram()
    fig_confidence()
    fig_bands()
    fig_quota()
    fig_samples_tradeoff()
    fig_tests()

    data = load_measurements()
    if data:
        fig_cer_per_page(data)
        fig_accuracy_speed(data)
        fig_confidence_vs_error(data)
    else:
        print("  (no measurement JSON - accuracy figures skipped)")

    try:
        fig_segmentation_sample()
    except Exception as exc:
        print(f"  (segmentation figure skipped: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
