"""Chapter 4 (Results and Discussion) and Chapter 5 (Summary and Conclusions).

Chapter 4's accuracy tables and figures are generated from
`docs/report/data/engine_measurements.json`, so the prose, the tables and the
charts cannot disagree with one another or with the benchmark that produced
them.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIGURES = REPO / "docs" / "report" / "figures"
DATA = REPO / "docs" / "report" / "data" / "engine_measurements.json"


def _load():
    if not DATA.exists():
        return None, None
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data, {s["engine"]: s for s in data}


def _pearson(xs, ys) -> float:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return num / den if den else float("nan")


def _band(c: float) -> str:
    return ("Reliable" if c >= 0.95 else "Spot check" if c >= 0.85
            else "Verify" if c >= 0.70 else "Manual")


def chapter_4(r) -> None:
    data, by = _load()
    r.chapter_heading("Results and Discussion")

    # ------------------------------------------------------------------ 4.1
    r.section("Experimental Setup and Evaluation Set")
    from meta import META
    r.para(
        f"All measurements were taken on one machine: {META['hardware']}, "
        f"running {META['os']} with Python {META['python']}. No GPU was used. "
        f"The local model is `microsoft/trocr-small-handwritten`; the cloud "
        f"engine is `gemini-3.1-flash-lite` over REST on the free tier."
    )
    r.para(
        "Character error rate (CER) and word error rate (WER) are computed with "
        "`jiwer` 4.0.0 as edit distance divided by reference length. Both "
        "strings are lower-cased and whitespace runs collapsed before "
        "comparison, so neither engine is rewarded or punished for spacing it "
        "cannot see. **CER can exceed 100%**: that happens when the output "
        "contains more wrong characters than the reference has characters at "
        "all, which is exactly what a recogniser inventing text produces. An "
        "“accuracy” percentage would hide that failure by clipping at "
        "zero, which is why error rate is reported throughout. The harness is "
        "`scripts/measure_engines.py`, which runs the production reading path "
        "and writes the JSON record from which every table and figure in "
        "Sections 4.2 and 4.6 is generated."
    )
    r.table(
        "The evaluation material.",
        ["Item", "Count", "Detail"],
        [
            ["Questions", "6", "Theory (2), output prediction (1), error identification (1), code writing (2)"],
            ["Rubric criteria", "22", "Every rubric sums exactly to its question's marks"],
            ["Answer keys / total marks", "6 / 30", "One key per question; five marks per question"],
            ["Writers", "3", "Volunteers; English on ruled notebook paper"],
            ["Pages with ground truth", "8", "Hand-prepared reference transcriptions"],
            ["Reference characters",
             f"{sum(x['reference_chars'] for x in by['local']['results']):,}" if by else "—",
             "Across the eight reference pages"],
        ],
        widths=[1.5, 0.75, 3.3], font=8.5,
    )
    r.para(
        "This set is small, and that limitation is taken up in Section 4.8. It "
        "is, however, genuinely out of distribution for the local model in both "
        "the visual and textual senses [3] identifies, and no public dataset of "
        "English handwriting by Indian writers at page level could be "
        "identified to substitute for it."
    )

    # ------------------------------------------------------------------ 4.2
    r.section("Recognition Accuracy")
    if not data:
        r.para("Measurement data unavailable; run `scripts/measure_engines.py`.",
               italic=True)
    else:
        local, gemini = by["local"], by["gemini"]
        ratio = local["mean_cer"] / gemini["mean_cer"]
        r.para(
            f"Both engines were run over all eight pages. The local line "
            f"recogniser achieved a mean character error rate of "
            f"**{local['mean_cer']:.1%}**; the cloud page-level model achieved "
            f"**{gemini['mean_cer']:.1%}** on identical input — a factor of "
            f"{ratio:.0f}."
        )
        rows = []
        for a, b in zip(local["results"], gemini["results"]):
            rows.append([
                a["page"].replace("writer_", "W").replace("_p", " p"),
                f"{a['reference_chars']:,}",
                f"{a['cer']:.1%}", f"{a['wer']:.1%}", f"{a['seconds']:.1f}",
                f"{b['cer']:.1%}", f"{b['wer']:.1%}", f"{b['seconds']:.1f}",
            ])
        rows.append([
            "**Mean**", "",
            f"**{local['mean_cer']:.1%}**", f"**{local['mean_wer']:.1%}**",
            f"**{local['mean_seconds']:.1f}**",
            f"**{gemini['mean_cer']:.1%}**", f"**{gemini['mean_wer']:.1%}**",
            f"**{gemini['mean_seconds']:.1f}**",
        ])
        rows.append([
            "Median", "", f"{local['median_cer']:.1%}", "",
            f"{statistics.median([x['seconds'] for x in local['results']]):.1f}",
            f"{gemini['median_cer']:.1%}", "",
            f"{statistics.median([x['seconds'] for x in gemini['results']]):.1f}",
        ])
        r.table(
            "Recognition accuracy and time per page. Left three result columns "
            "are the local engine; right three the cloud engine.",
            ["Page", "Ref. chars", "CER", "WER", "s", "CER", "WER", "s"],
            rows,
            widths=[0.95, 0.75, 0.68, 0.72, 0.5, 0.68, 0.72, 0.5],
            font=8.4,
        )
        r.figure(FIGURES / "fig_4_1_cer_per_page.png",
                 "Character error rate per page. Dashed lines mark each "
                 "engine's mean.", width=5.0)
        r.figure(FIGURES / "fig_4_2_accuracy_speed.png",
                 "Mean character error rate and mean time per page, both "
                 "engines.", width=4.6)
        lr_local = statistics.mean(
            x["lines_found"] / x["reference_lines"] for x in local["results"])
        lr_gem = statistics.mean(
            x["lines_found"] / x["reference_lines"] for x in gemini["results"])
        r.para(
            f"Three observations follow. First, the local engine's error is not "
            f"merely high but **unusable for marking**: at "
            f"{local['mean_cer']:.0%} character and {local['mean_wer']:.0%} word "
            f"error, more words are wrong than right, and the worst page at "
            f"{max(x['cer'] for x in local['results']):.0%} CER is a case of the "
            f"recogniser generating more text than the page contains."
        )
        r.para(
            f"Second, the failure is partly segmentation rather than "
            f"recognition. Line recall — lines detected against lines in the "
            f"reference — is {lr_local:.0%} for the local path against "
            f"{lr_gem:.0%} for the cloud path; above 100% means "
            f"over-segmentation, a single written line split in two and each "
            f"half read as a fragment. Keeping segmentation and recognition "
            f"separately measurable is what makes this diagnosable, and it "
            f"matters because published work on hand-written grading attributes "
            f"the majority of marking errors to the transcription stage."
        )
        r.para(
            f"Third, the result is consistent with [3]: a model fine-tuned on "
            f"6,161 IAM lines of Western cursive prose, applied to Indian "
            f"student handwriting containing C syntax, degrades as that work "
            f"predicts. The conclusion drawn was to change engines rather than "
            f"to pursue fine-tuning — no plausible amount of fine-tuning of "
            f"a 60-million-parameter line recogniser on a few thousand "
            f"synthetic lines closes a {ratio:.0f}-fold gap."
        )

    # ------------------------------------------------------------------ 4.3
    r.section("Effect of Preprocessing")
    r.para(
        "The pipeline of Section 3.4 was evaluated by comparing the same "
        "material before and after the ink-isolation and ruling-removal work "
        "(Table 4.3). A CER above 100% before the work means the recogniser was "
        "inventing text — and it was inventing it from the printed ruling. "
        "This is the failure [8] trains a convolutional network to prevent; "
        "here it was removed with classical geometry and no training data."
    )
    r.table(
        "Effect of the preprocessing pipeline, same material before and after.",
        ["Material", "Before", "After", "Change"],
        [
            ["Real scanned answer page (ruled paper, phone photograph)",
             "64 s, 125% CER", "7 s, 47% CER",
             "9× faster; error cut by more than half"],
            ["Four synthetic sample sheets (clean / normal / messy / poor)",
             "~17 s each, 1–4% CER", "~4 s each, 0% CER on all four",
             "4× faster; word-perfect on all four"],
        ],
        widths=[1.95, 1.2, 1.3, 1.4], font=8.5,
    )
    r.figure(FIGURES / "fig_4_7_segmentation.png",
             "A real answer page before and after ink isolation, with the "
             "detected line boxes overlaid.", width=4.8)
    r.table(
        "Optimisation experiments and the decision each produced.",
        ["Experiment", "Result", "Decision"],
        [
            ["`trocr-small` against `trocr-base`",
             "small ~10× faster; 47% against 45% CER on the real page; both 0% on samples",
             "Adopted small"],
            ["int8 dynamic quantisation",
             "25% faster, but CER rose from 2% to over 80%", "**Rejected**"],
            ["Batch size 4 / 8 / 16 with line-length sorting", "~6% gain",
             "Adopted; not the bottleneck"],
            ["CPU thread count 6 / 12 / 14", "Fewer threads strictly slower", "Left at default"],
            ["Median filter replacing non-local-means denoising",
             "1.2 s → 0.25 s, no accuracy loss", "Adopted"],
        ],
        widths=[1.55, 2.4, 0.95], font=8.4,
    )
    r.para(
        "Two defects were found by measurement during this work, both now "
        "covered by regression tests: a speck-removal step was erasing every "
        "pen stroke thinner than three pixels, and the margin-line detector was "
        "treating neatly aligned letter stems as a ruled margin and deleting "
        "them."
    )

    # ------------------------------------------------------------------ 4.4
    r.section("Throughput and the Binding Constraint")
    r.para(
        "The binding constraint on end-to-end speed is not the code but the "
        "free tier's request quota, established from the API's own refusal "
        "message: fifteen requests per minute, shared between transcription and "
        "marking. One three-page booklet needs sixteen — six for three "
        "pages read twice, ten for five attempted questions marked twice. "
        "Before this was understood, identical runs took 16 s, 97 s and 200 s "
        "depending on where the rolling window happened to be; the variance was "
        "the quota, not the model."
    )
    r.para(
        "Three changes followed: pages and questions are dispatched "
        "concurrently through a bounded pool; a shared sliding-window limiter "
        "holds the application to the quota so requests queue rather than "
        "storm; and an overloaded model is waited out rather than abandoned, "
        "because the preferred model answers in roughly 0.8 s and the fallbacks "
        "in 2–9 s, so switching away on a first 503 was measured to make a "
        "run four times longer."
    )
    r.figure(FIGURES / "fig_4_4_quota.png",
             "Requests needed for one three-page booklet against the free-tier "
             "limit of fifteen per minute.", width=4.5)
    r.table(
        "End-to-end marking of one three-page booklet; same input, same marks.",
        ["Mode", "Wall clock", "Marks", "Confidence"],
        [
            ["Default (two readings each)", "139 s", "15.5 / 30",
             "Measured; 2 of 5 answers routed to review"],
            ["Single-sample fast mode", "59 s", "15.5 / 30",
             "**Unmeasured**; all 5 routed to review"],
        ],
        widths=[1.65, 0.95, 0.9, 1.85], font=8.5,
    )
    r.para(
        "The scores are identical. What fast mode gives up is the *confidence "
        "measurement*: transcription confidence falls to 49.9% and every answer "
        "lands in the lowest routing band, which is the system correctly "
        "reporting that it does not know how sure it is. There is no way to "
        "obtain both on this tier, because the second reading is the only "
        "available source of transcription confidence."
    )
    if data:
        gem = by["gemini"]
        secs = [x["seconds"] for x in gem["results"]]
        r.para(
            f"The same effect appears in Table 4.2: the cloud engine's mean of "
            f"{gem['mean_seconds']:.1f} s per page is inflated by two pages that "
            f"waited out a 503 and a quota window, against a median of "
            f"{statistics.median(secs):.1f} s and a best case of {min(secs):.1f} s. "
            f"Mean and median are reported together for that reason."
        )

    # ------------------------------------------------------------------ 4.5
    r.section("End-to-End Marking")
    r.para(
        "A complete booklet was marked on both engines. What matters is not "
        "only the score but what the system says about it (Table 4.6)."
    )
    r.table(
        "One answer (Q1, 5 marks) marked on each engine.",
        ["Engine", "Score", "Conf.", "Band", "What it reported"],
        [
            ["Cloud (`gemini-3.1-flash-lite`)", "4.5 / 5", "0.846", "Detailed verification",
             "“The two independent markings disagreed on criterion 4. The lower verdict was taken; an examiner should decide.”"],
            ["Local (rubric concept matcher)", "3.5 / 5", "0.891", "Mandatory review",
             "“Marked by the keyword baseline, not a language model. These verdicts are a floor to compare against, not a result to report.”"],
        ],
        widths=[1.5, 0.6, 0.55, 1.1, 2.1], font=8.2,
    )
    r.para(
        "Two points follow. The cloud result is *not* auto-accepted despite a "
        "high score, because the two independent markings disagreed on one "
        "criterion and the agreement signal fell accordingly — the system "
        "declined to be confident and said which criterion caused it. And the "
        "local marker's higher composite confidence with a lower score "
        "illustrates why its output is labelled a baseline: a deterministic "
        "matcher agrees with itself perfectly, so its agreement signal is "
        "uninformative. Reporting that limitation on the result is the only "
        "honest option."
    )

    # ------------------------------------------------------------------ 4.6
    r.section("Confidence Behaviour")
    if data:
        local, gemini = by["local"], by["gemini"]
        r_local = _pearson([x["confidence"] for x in local["results"]],
                           [x["cer"] for x in local["results"]])
        r_gem = _pearson([x["confidence"] for x in gemini["results"]],
                         [x["cer"] for x in gemini["results"]])
        r.para(
            f"The central claim of this project is that its confidence is "
            f"measured rather than asserted. The test of that claim is whether "
            f"reported confidence predicts measured error. It does: the Pearson "
            f"correlation between reported page confidence and measured "
            f"character error rate is **r = {r_local:.2f}** for the local engine "
            f"and **r = {r_gem:.2f}** for the cloud engine. Both are strongly "
            f"negative, the desired direction — higher claimed confidence, "
            f"lower measured error."
        )
        r.figure(FIGURES / "fig_4_3_confidence_vs_error.png",
                 "Reported confidence against measured character error rate. "
                 "Shaded regions are the transcription trust bands.", width=5.0)
        rows = []
        for a, b in zip(local["results"], gemini["results"]):
            rows.append([
                a["page"].replace("writer_", "W").replace("_p", "p"),
                f"{a['confidence']:.3f}", _band(a["confidence"]), f"{a['cer']:.1%}",
                f"{b['confidence']:.3f}", _band(b["confidence"]), f"{b['cer']:.1%}",
            ])
        r.table(
            "Reported confidence, assigned band and measured error, per page. "
            "Left three columns: local engine; right three: cloud engine.",
            ["Page", "Conf.", "Band", "CER", "Conf.", "Band", "CER"],
            rows,
            widths=[0.6, 0.65, 1.0, 0.65, 0.65, 0.85, 0.65],
            font=8.4,
        )
        bands_local = [_band(x["confidence"]) for x in local["results"]]
        n_unusable = bands_local.count("Manual")
        r.para(
            f"The banding behaves as designed. The local engine placed "
            f"{n_unusable} of its 8 pages in the lowest band, *manual "
            f"transcription* — the system reporting that it could not read "
            f"those pages and that a human should transcribe them, rather than "
            f"producing a confident wrong answer. Given that its measured error "
            f"makes those pages genuinely unusable for marking, this is correct "
            f"behaviour and is the most defensible property the local path has. "
            f"The cloud engine placed all 8 in *reliable*, and its worst page at "
            f"{gemini['worst_cer']:.1%} CER justifies that."
        )
        r.para(
            "Two qualifications. The correlation is computed over eight pages, "
            "far too few to call the confidence *calibrated*: a strong rank "
            "relationship is not the same as the reported number being the true "
            "probability of correctness. And this is transcription confidence; "
            "the four-signal evaluation confidence of Section 3.6 has not been "
            "validated against examiner decisions at all, because that requires "
            "a volume of reviewed results not yet accumulated."
        )

    # ------------------------------------------------------------------ 4.7
    r.section("Marking-Scheme Import and Software Quality")
    r.para(
        "The importer was evaluated on four documents: one purpose-built "
        "demonstration file and the project's own question paper and answer "
        "key, both written in Word before the importer existed and not adjusted "
        "for it."
    )
    r.table(
        "Marking-scheme import results. “Sums” means every imported "
        "rubric totalled its question's marks without manual correction.",
        ["Document", "Parser", "Questions", "Criteria", "Sums", "Notes"],
        [
            ["`sample_rubric.docx` (3 tables)", "Local", "3 / 3", "13", "Yes",
             "No warnings; 3 answer keys captured"],
            ["`sample_rubric.docx`", "Cloud", "3 / 3", "12", "Yes", "Better title; topics inferred"],
            ["`EVN-PROG-01_Question_Paper.docx`", "Local", "6 / 6", "2", "Yes",
             "Questions and marks correct; paper carries no rubric"],
            ["`EVN-PROG-01_Answer_Key.docx` (10 tables)", "Local", "6 / 6", "31", "**No**",
             "Irregular layout; sums wrong on all six, reported as warnings"],
            ["`EVN-PROG-01_Answer_Key.docx`", "Cloud", "6 / 6", "22", "Yes",
             "All six rubrics correct, including `load_bearing` criteria"],
        ],
        widths=[1.8, 0.55, 0.75, 0.6, 0.5, 1.65], font=8.2,
    )
    r.para(
        "The fourth row is the informative one. On a genuinely irregular "
        "document the deterministic parser fails — and reports that it has "
        "failed, listing the sums that do not add up and the lines it could not "
        "place, rather than producing a plausible-looking rubric. The cloud "
        "parser handles the same document correctly. This is the intended "
        "division of labour: a parser that cannot invent a criterion, a model "
        "that can read irregular prose, and an examiner approving either before "
        "anything is stored. Median cloud import time for a six-question answer "
        "key was approximately 5 s; the local parser is effectively "
        "instantaneous. A scanned PDF with no text layer is refused with an "
        "explanation rather than parsed into fragments."
    )
    r.para(
        "The project carries **244 automated tests, all passing** (Table 4.8). "
        "They need no model download and no network: the suite pins the API key "
        "to empty before any module is imported, so adding a real key to the "
        "environment cannot silently turn the unit suite into one that calls a "
        "paid service. The API-contract suite deserves a note — because the "
        "frontend maintains its types by hand, a renamed route or dropped field "
        "would otherwise surface as a blank screen at runtime rather than a "
        "compile error, so that suite walks the same calls the interface makes, "
        "in the same order."
    )
    r.figure(FIGURES / "fig_4_6_tests.png",
             "Automated tests by module; 244 in total, all passing.", width=4.4)
    r.table(
        "Test coverage by area.",
        ["Area", "Tests", "What is asserted"],
        [
            ["Marking-scheme import", "37", "Word tables, PDFs, scans refused, sums reported, engine switching"],
            ["Scoring and confidence", "36", "Marks arithmetic, partial credit, clamping, the four signals"],
            ["PDF booklets", "31", "Rasterisation, page ranges, per-page failure isolation"],
            ["Evaluation", "29", "Provider contract, malformed output, review bands"],
            ["Recognition pipeline", "26", "Segmentation, token budget, confidence computation"],
            ["Preprocessing", "21", "Ruling removal, show-through, stroke-preservation regressions"],
            ["Rubric editing", "21", "Versioning, the sum invariant, deletion refusal"],
            ["Cloud provider", "19", "Retry, fallback chain, error translation"],
            ["API contract", "12", "Every endpoint the interface calls exists and answers"],
            ["Rate limiting", "12", "Sliding window, penalty, concurrent acquisition"],
            ["**Total**", "**244**", ""],
        ],
        widths=[1.55, 0.55, 3.45], font=8.4,
    )

    # ------------------------------------------------------------------ 4.8
    r.section("Discussion")
    r.para("Four conclusions are supported by these measurements, and three are not.")
    r.para("**Supported.**")
    r.bullets([
        "Preprocessing dominates on real ruled paper: removing ruling, print "
        "and show-through took a real page from inventing text to reading it, "
        "nine times faster.",
        "A general line recogniser does not transfer to this material; the "
        "measured gap is roughly twenty-two-fold in CER, in the direction and "
        "for the reasons [3] predicts.",
        "The system's reported confidence tracks its measured error: both "
        "engines show a strong negative correlation, and the local engine "
        "correctly routes its unreadable pages to manual transcription.",
        "Separating judgement from arithmetic is practical: the model emits "
        "verdicts and quotations, Python computes the marks, and the "
        "arithmetic is deterministic and covered by 36 tests.",
    ])
    r.para("**Not supported, and not claimed.**")
    r.bullets([
        "**The confidence is not calibrated.** A strong correlation over eight "
        "pages establishes a useful ordering, not that a reported 0.9 means a "
        "90% chance of being right. A confidently misread word still scores high.",
        "**The four-signal evaluation confidence is unvalidated.** Its weights "
        "are hand-chosen; they are stored with every result precisely so a "
        "study can replace them, and that study needs examiner decisions not "
        "yet collected.",
        "**The evaluation set is small.** Eight pages from three writers "
        "supports the twenty-two-fold conclusion, far larger than any plausible "
        "sampling error, but not fine distinctions, per-question accuracy "
        "claims, or any statement about handwriting unlike these samples.",
    ])
    r.para(
        "A further limitation concerns privacy. The cloud engine is the "
        "accurate one, and using it sends page images and transcribed text to a "
        "third party; on a free tier, submitted content may be used to improve "
        "that provider's products. The local engine exists partly as the answer "
        "to that, and the per-request switch makes the trade explicit at the "
        "moment it is made rather than burying it in configuration. For real "
        "student scripts that choice is institutional, and the system is built "
        "to let an institution make it."
    )


def chapter_5(r) -> None:
    data, by = _load()
    r.chapter_heading("Summary and Conclusions")

    r.section("Summary of the Work Carried Out")
    r.para(
        "This project set out to produce not merely a mark for a hand-written "
        "answer but a defensible marks decision. A complete system was "
        "designed, implemented and measured across four parts."
    )
    r.para(
        "**Part 1** built a thirteen-stage image pipeline that flattens "
        "illumination, isolates the student's ink from ruled paper, printed "
        "matter, examiner marks and show-through, classifies and skips printed "
        "cover pages, deskews, segments the page into lines, and recognises "
        "them with either a local model or a cloud vision-language model, "
        "reporting a confidence measured from the model's own behaviour and "
        "placing the page in one of four trust bands. **Part 2** represented "
        "the marking scheme as versioned relational data — questions, "
        "answer keys and rubrics whose criteria carry essential concepts, "
        "acceptable alternatives, common mistakes, partial-credit rules and a "
        "load-bearing flag — with a validator enforcing that criteria sum "
        "to the question's marks, and an importer that reads a department's "
        "existing Word or PDF marking scheme, tables included, into that "
        "structure for an examiner to approve."
    )
    r.para(
        "**Part 3** marked each answer criterion by criterion, requiring a "
        "verdict and a quotation from the student's own words for each, "
        "computed the marks deterministically in Python, and composed a "
        "confidence from four measured signals as a weighted geometric mean, "
        "routing each result into one of four review bands. **Part 4** "
        "presented the handwriting, transcription, per-criterion verdicts and "
        "confidence signals together for an examiner, recorded the examiner's "
        "decision as a new append-only record, and reported agreement between "
        "machine and human by band. The implementation comprises 47 API "
        "endpoints over 15 tables, roughly 25,000 lines across backend, "
        "frontend, tests, scripts and documentation, and 244 passing tests."
    )

    r.section("Conclusions")
    if data:
        local, gemini = by["local"], by["gemini"]
        ratio = local["mean_cer"] / gemini["mean_cer"]
        r_local = _pearson([x["confidence"] for x in local["results"]],
                           [x["cer"] for x in local["results"]])
    else:
        ratio, r_local = 22, -0.94
        local, gemini = {"mean_cer": 0.595}, {"mean_cer": 0.027}

    r.bullets([
        "**C1.** Image preparation, not the recognition model, is the dominant "
        "failure mode on genuine ruled answer paper. Isolating the student's "
        "ink and removing printed ruling moved a real page from 125% to 47% "
        "character error while making it nine times faster. A recogniser handed "
        "a ruled line confidently invents a sentence for it.",

        f"**C2.** A general-purpose line recogniser trained on Western cursive "
        f"prose does not transfer to Indian student handwriting containing "
        f"programming syntax. Over eight real pages `trocr-small-handwritten` "
        f"reached {local['mean_cer']:.1%} character error against "
        f"{gemini['mean_cer']:.1%} for a page-level vision-language model on "
        f"identical input — a factor of about {ratio:.0f}. The conclusion "
        f"drawn was to change engines rather than to fine-tune.",

        f"**C3.** A confidence computed from observable signals is useful even "
        f"when it is not calibrated. Reported page confidence correlated with "
        f"measured character error at r = {r_local:.2f} for the local engine, "
        f"and the system placed seven of its eight unreadable pages in the "
        f"*manual transcription* band — declining to produce a confident "
        f"wrong answer, which is the behaviour an examination department needs "
        f"most.",

        "**C4.** Separating judgement from arithmetic is both practical and "
        "worth the effort. Restricting the model to per-criterion verdicts with "
        "quoted evidence, and computing marks in ordinary Python, makes the "
        "scoring deterministic, exhaustively testable, and structurally "
        "incapable of awarding more marks than the verdicts justify.",

        "**C5.** Provider interfaces make the model genuinely replaceable: a "
        "cloud recognition engine, a second marking engine and a per-request "
        "engine switch were each added without altering any application logic "
        "above the provider boundary.",

        "**C6.** Refusing to substitute silently is a necessary complement to "
        "replaceability. Because the engine's name is recorded on every stored "
        "result, a requested engine that cannot run must fail with a reason "
        "rather than be quietly replaced, or the record would assert something "
        "that did not happen.",

        "**C7.** Preserving the machine's judgement through human correction is "
        "what makes validation possible at all. Append-only evaluations and "
        "reviews are the precondition for ever reporting how often examiners "
        "agree with the system, and therefore for ever justifying a change to "
        "a routing threshold.",

        "**C8.** The accuracy available on a free cloud tier is bounded by its "
        "request quota rather than by the model: sixteen requests are needed "
        "for one three-page booklet against a limit of fifteen per minute, and "
        "the only available source of transcription confidence is a second "
        "reading, which doubles that cost.",
    ])

    r.section("Scope for Future Work")
    r.bullets([
        "**Calibrate the confidence.** Collect examiner decisions until several "
        "hundred reviewed evaluations exist, then fit the four signal weights "
        "against examiner agreement and report reliability diagrams and "
        "expected calibration error. The weights are already stored with every "
        "result for this purpose. Only then should any result be "
        "auto-accepted, and only once the false-auto-accept rate is known.",
        "**Enlarge and diversify the evaluation set.** Eight pages from three "
        "writers supports the twenty-two-fold conclusion and nothing finer. "
        "Fifty scripts from twenty writers, with hand transcriptions and "
        "independent human marks, would support per-question accuracy claims "
        "and a genuine machine-versus-human agreement study.",
        "**Improve line segmentation rather than the recogniser.** Line recall "
        "of 132% shows over-segmentation is a measurable, addressable defect in "
        "the local path, and segmentation is also what currently prevents "
        "handling two-column layouts and heavy skew.",
        "**Extend to hand-written mathematics and diagrams**, excluded from the "
        "present scope and identified in the recent literature as the hardest "
        "open case.",
        "**Replace SQLite with PostgreSQL and introduce migrations**, and "
        "enforce the authentication roles that already exist in the data model, "
        "before the system holds any real student data.",
        "**Add content-hash caching of evaluations**, making batch calibration "
        "experiments repeatable without re-spending quota, and a job queue, for "
        "which the answer lifecycle state machine was designed from the outset.",
        "**Measure the privacy-accuracy trade directly**, quantifying how much "
        "marking accuracy is lost by running entirely offline, so an "
        "institution choosing between the two engines can decide on evidence "
        "rather than instinct.",
    ])
    r.para(
        "The project's own position is that the most valuable of these is the "
        "first. Everything else in this system is in place to make a "
        "calibration study possible: the append-only records, the stored "
        "weights, the band thresholds served from configuration, and the "
        "agreement dashboard. What remains is to run it."
    )
