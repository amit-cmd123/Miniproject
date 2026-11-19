"""Chapter 1 (Introduction) and Chapter 2 (Literature Review)."""

from __future__ import annotations

from pathlib import Path

FIGURES = Path(__file__).resolve().parents[2] / "docs" / "report" / "figures"


def chapter_1(r) -> None:
    r.chapter_heading("Introduction")

    r.section("Background and Motivation")
    r.para(
        "Descriptive, hand-written answers remain the dominant form of "
        "assessment in Indian engineering education. One mid-semester "
        "examination in a single subject produces several hundred booklets, "
        "each of which an examiner must read, judge against a marking scheme "
        "and total by hand. The work is slow, repetitive and known to be "
        "inconsistent: the same script marked by two examiners, or by one "
        "examiner on two days, does not reliably receive the same mark."
    )
    r.para(
        "Automating this is not new — the survey literature records more "
        "than thirty-five automatic short answer grading systems across five "
        "eras [11]. What has changed is capability: a modern vision-language "
        "model shown a photograph of a hand-written answer will return a mark, "
        "fluently and immediately. The temptation is to stop there, and that "
        "temptation is the problem this project is built around. A mark "
        "produced by asking a model “is this answer correct?” is an "
        "unaccountable number. It does not say what text was read off the page, "
        "which part of the marking scheme was satisfied, or what evidence "
        "supports it; it offers no honest statement of how certain it is; and "
        "if a student appeals, there is nothing to show them."
    )

    r.section("Problem Statement")
    r.para(
        "The problem addressed is therefore not “can a machine mark a "
        "hand-written answer?” but the harder question:"
    )
    r.para(
        "**Given a photographed or scanned hand-written answer script and the "
        "marking scheme a department actually uses, produce a marks decision "
        "that is defensible — every mark traceable to a specific rubric "
        "criterion, supported by evidence quoted from the student's own "
        "writing, carrying a confidence that has been measured rather than "
        "asserted, and routed to a human examiner whenever that confidence is "
        "insufficient — while preserving the machine's original judgement "
        "alongside the human's correction so the agreement between them can be "
        "measured.**"
    )
    r.para(
        "Three sub-problems follow, and the system is organised around them. "
        "The first is a computer-vision problem: real booklets are ruled, "
        "photographed under uneven light, written over by examiners in red ink, "
        "and show writing through from the reverse. The second is a "
        "representation problem: a marking scheme must exist as structured, "
        "versioned, institution-owned data rather than as a prompt. The third "
        "is an estimation problem: a confidence that is simply asked for is "
        "known to be poorly calibrated [18][20], so it must be constructed from "
        "observable signals."
    )

    r.section("Aim and Objectives")
    r.para(
        "The aim is to design, implement and evaluate an end-to-end system that "
        "converts a hand-written answer script into an auditable marks decision "
        "with a measured confidence. The objectives, each testable, are:"
    )
    r.bullets([
        "**O1.** Build an image-preparation pipeline that isolates handwriting "
        "from ruled paper, printed matter, examiner marks and show-through, "
        "segments the page into lines, and quantify its effect on error.",
        "**O2.** Recognise the segmented handwriting using interchangeable "
        "engines — one local and offline, one cloud-based — and measure "
        "both against reference transcriptions of genuine answer scripts.",
        "**O3.** Represent a paper, its answer keys and its per-criterion "
        "marking scheme as versioned relational data, with a validator that "
        "refuses a rubric whose criteria do not sum to the question's maximum.",
        "**O4.** Mark criterion by criterion, requiring a verdict and a quoted "
        "piece of evidence for each, and compute the marks deterministically "
        "outside the model.",
        "**O5.** Compose an evaluation confidence from measured signals and "
        "route each result into one of four review bands.",
        "**O6.** Provide an examiner interface showing handwriting, "
        "transcription and verdicts together, recording the examiner's decision "
        "as a new record rather than an overwrite.",
        "**O7.** Provide the measurement apparatus — error-rate tooling, an "
        "agreement dashboard and an automated test suite — by which all of "
        "the above can be checked.",
    ])

    r.section("Scope and Limitations")
    r.para(
        "The scope is deliberately narrow, because a narrow scope is what makes "
        "a meaningful accuracy figure achievable in one semester. The system is "
        "evaluated on introductory C programming theory questions. The "
        "evaluation set is a 30-mark, six-question class test hand-written by "
        "three volunteers and transcribed by hand as ground truth. Explicitly "
        "out of scope are: hand-written mathematics with stacked fractions or "
        "multi-line derivations, which breaks the assumption of horizontal text "
        "lines, and diagrams, which are neither recognised nor marked; "
        "languages other than English; **calibration of the confidence model** "
        "(confidence is *measured*, and the signal weights are stored with "
        "every result so a future study can fit them, but that study needs a "
        "volume of examiner-reviewed decisions not yet accumulated); and "
        "enforcement of authentication, the roles for which exist in the data "
        "model but are not gated, making this a departmental tool rather than a "
        "multi-tenant service."
    )

    r.section("Significant Contributions")
    r.bullets([
        "**A measured demonstration that preprocessing, not the recogniser, is "
        "the dominant failure mode on real ruled paper.** Removing ruled lines, "
        "printed matter and show-through before recognition moved a real page "
        "from 125% character error — a recogniser inventing text from ruling "
        "— to 47%, and cut per-page time from 64 s to 7 s.",
        "**A quantified engine comparison on genuine Indian student handwriting "
        "in English.** Over eight real pages the local and cloud engines differ "
        "by a factor of about twenty-two in character error rate. The "
        "literature predicts out-of-distribution degradation [3]; this work "
        "measures it on material for which no public dataset could be found.",
        "**A marks pipeline in which the model never performs arithmetic**, "
        "making scoring exhaustively testable and making it structurally "
        "impossible to award more marks than the verdicts justify.",
        "**A composite confidence from four observed signals**, with the "
        "finding that the only source of transcription confidence on the "
        "current cloud tier is a second independent reading — no "
        "flash-class model tested exposed token log-probabilities.",
        "**An engine-selection mechanism that never substitutes silently**, "
        "because the engine's name is recorded on every stored result.",
        "**A marking-scheme importer** that reads a department's existing Word "
        "or PDF scheme, tables included, and proposes a rubric for approval.",
    ])

    r.section("Organization of the Report")
    r.para(
        "**Chapter 2** reviews the literature in four areas — handwritten "
        "text recognition, document image preprocessing, automatic short answer "
        "grading, and confidence estimation with selective prediction — and "
        "identifies the gap at their intersection. **Chapter 3** presents the "
        "proposed work: design principles, architecture, data model, the "
        "recognition pipeline, rubric representation, deterministic scoring and "
        "composite confidence, the examiner review loop, engine selection and "
        "marking-scheme import. **Chapter 4** reports results: experimental "
        "setup, evaluation set, recognition accuracy, the preprocessing "
        "ablation, throughput, end-to-end marking, confidence behaviour, "
        "importer accuracy and test coverage, closing with what the numbers do "
        "and do not establish. **Chapter 5** summarises the work, states the "
        "conclusions as enumerated points and sets out future work. References "
        "and three appendices follow."
    )

    # ---------------------------------------------------------------- Ch 2
    r.chapter_heading("Literature Review")
    r.para(
        "This chapter surveys the four areas the project sits across, stating "
        "for each what the existing work establishes, what it does not address, "
        "and how the present design responds."
    )

    r.section("Handwritten Text Recognition")
    r.para(
        "Li et al. introduced TrOCR [1], an end-to-end transformer "
        "architecture for optical character recognition that dispenses with a "
        "convolutional backbone and reaches state-of-the-art results on "
        "printed, hand-written and scene text. It is the local recognition "
        "model used here, and two of its properties are decisive. First, the "
        "authors state that they “leave text detection as the future "
        "work”: TrOCR reads a single pre-cropped line and performs no "
        "detection, layout analysis or segmentation at all, so everything "
        "before the model is the integrator's responsibility. Second, the paper "
        "itself reports the model emitting unwanted symbols or truncating "
        "predictions when image and label disagree — a failure observed "
        "directly here as runaway generation on unreadable crops."
    )
    r.para(
        "TrOCR's handwriting variant is fine-tuned on the IAM database [2]: "
        "clean scans of prepared forms in Western cursive English from roughly "
        "657 writers, with text drawn from 1960s–1970s prose. Booklets "
        "photographed on a phone, written on ruled paper by Indian students and "
        "containing C syntax, lie outside that distribution both visually and "
        "textually. Garrido-Munoz and Calvo-Zaragoza quantify exactly this [3]: "
        "across 336 out-of-distribution cases over eight models, seven datasets "
        "and five languages, textual divergence between domains matters more "
        "than visual divergence and the degradation is largely predictable — "
        "but they propose no adaptation method. Their companion survey [4] "
        "notes that most HTR work is line-level and presupposes a segmentation "
        "step. For Indian handwriting, Gongidi and Jawahar released "
        "iiit-indic-hw-words [5], 872,000 word instances from 135 writers "
        "across ten Indic scripts, observing that HTR for Indian languages "
        "“is not yet a well-studied problem”; that dataset is "
        "word-level and covers Indic *scripts*, whereas the case here is "
        "English written by Indian writers at page level, for which no public "
        "dataset could be identified."
    )

    r.section("Document Image Preprocessing")
    r.para(
        "Otsu's method [6] remains the canonical automatic global threshold but "
        "assumes a bimodal histogram and uniform illumination, so it fails on "
        "shadowed photographs, page curl, faint pencil and show-through. "
        "Sauvola and Pietikäinen's adaptive binarization [7] addresses "
        "local variation but depends strongly on a hand-tuned window size with "
        "no principled per-document setting, and is not designed to separate "
        "bleed-through."
    )
    r.para(
        "Ruled-line removal is treated directly by Gold and Zesch [8], whose "
        "work is explicitly motivated by neural HTR degrading on ruled paper; "
        "they train a convolutional network to erase ruled lines while "
        "reconstructing overlapping strokes. The limitations they acknowledge "
        "are instructive: training on synthetically overlaid lines carries a "
        "synthetic-to-real transfer risk, and the method handles ruled lines "
        "only — not margin rules, answer-box borders or examiner marks, all "
        "of which occur on a real booklet. Show-through removal has been "
        "addressed by self-supervised networks [9] at roughly 33.85 dB PSNR, "
        "measured as image restoration quality and never as downstream "
        "recognition accuracy, so the benefit to a recogniser is never shown. "
        "For line segmentation, the survey by Likforman-Sulem et al. [10] "
        "diagnoses that plain projection profiles work for printed pages and "
        "only for handwriting with little overlap, and names interfering lines, "
        "show-through and noise as primary obstacles — precisely the "
        "argument for removing those obstacles before profiling."
    )

    r.section("Automatic Short Answer Grading")
    r.para(
        "Burrows, Gurevych and Stein's survey [11] is the foundational account "
        "of the field, covering more than eighty papers and thirty-five "
        "systems. It predates transformers entirely, treats typed text only, "
        "and frames accuracy as a benchmark number rather than a deployment "
        "property: confidence, routing and auditability are not among its "
        "concerns. Mohler et al. [12] contributed the widely reused "
        "computer-science short-answer dataset with a model producing a bare "
        "numeric score — no explanation, no per-criterion breakdown, no "
        "confidence — from typed text, from one instructor and one course; "
        "SemEval-2013 Task 7 [13] formalised student response analysis as a "
        "labelling task, again over typed responses."
    )
    r.para(
        "Recent work applies large language models directly: practical "
        "experience with an LLM grader [14], retrieval-augmented structured "
        "grading [15], rubric-conditioned grading examined for alignment, "
        "uncertainty and robustness [16], and a unifying rubric-based framework "
        "[17]. These establish that rubric conditioning improves alignment; all "
        "operate on typed text. The closest systems combine handwriting with "
        "grading: Liu et al. [28] and Kortemeyer et al. [29] grade hand-written "
        "university mathematics with human assistance, and Henkel et al. [30] "
        "evaluate multimodal models on hand-written student work. The "
        "consistent finding is that handwriting, not judgement, is the binding "
        "constraint, and that routing to humans remains necessary."
    )

    r.section("Confidence Estimation and Selective Prediction")
    r.para(
        "Guo et al. [18] established that modern neural networks are "
        "systematically overconfident and that accuracy and calibration are "
        "distinct properties. For language models, Kadavath et al. [19] showed "
        "some capacity to predict their own correctness, while Tian et al. [20] "
        "found verbalised confidence better than nothing but weakly calibrated. "
        "The conclusion adopted here is that a model's stated confidence may be "
        "one input among several but must not be the output."
    )
    r.para(
        "Two observable alternatives are established: self-consistency [21] "
        "samples a model repeatedly and exploits agreement between samples, and "
        "SelfCheckGPT [22] uses the same principle for hallucination detection. "
        "Both treat disagreement between independent samples as evidence of "
        "genuine uncertainty, which is the basis of the *agreement* signal in "
        "this work; the reliability of LLM judges themselves is examined by "
        "Zheng et al. [23]. What to do with an uncertain result belongs to the "
        "selective-prediction literature: Kamath et al. [24] formalise "
        "selective question answering under domain shift and Mozannar and "
        "Sontag [25] give consistent estimators for learning to defer to an "
        "expert. The four review bands used here are a hand-set instance of "
        "that deferral policy. Critically for a pipeline, van Strien et al. "
        "[26] measure how OCR quality degrades downstream NLP *accuracy* but do "
        "not examine whether downstream models become *overconfident* on noisy "
        "input, and Hemmer et al. [27] address confidence-aware OCR error "
        "detection at the recognition stage alone. How uncertainty at "
        "recognition should propagate into confidence at judgement is not "
        "answered in the surveyed literature."
    )

    r.section("Research Gap and Work Undertaken")
    r.para(
        "Across the reviewed work, handwriting recognition, rubric-based "
        "grading and confidence estimation are each studied in isolation, at a "
        "single pipeline stage. No surveyed work combines all four of: "
        "free-text **hand-written** answers; **rubric-criterion** scoring with "
        "quoted evidence; a **measured confidence that routes to a human**; and "
        "an **audit trail in which the machine's judgement survives the "
        "human's correction** (Table 2.1). In grading, the closest systems each "
        "drop one leg; in confidence, every surveyed paper studies one signal "
        "at one stage."
    )
    r.table(
        "Research gap by capability. A filled circle denotes the capability "
        "being present in that line of work.",
        ["Capability", "HTR [1][3][4]", "ASAG [11][12]", "LLM graders [14]–[17]",
         "Confidence [18]–[25]", "This work"],
        [
            ["Hand-written input", "●", "—", "—", "—", "●"],
            ["Per-criterion rubric scoring", "—", "partial", "●", "—", "●"],
            ["Evidence quoted from the answer", "—", "—", "partial", "—", "●"],
            ["Deterministic marks arithmetic", "—", "—", "—", "—", "●"],
            ["Measured, composed confidence", "partial", "—", "partial", "●", "●"],
            ["Routing to a human examiner", "—", "—", "—", "●", "●"],
            ["Machine judgement preserved on review", "—", "—", "—", "—", "●"],
        ],
        widths=[1.85, 0.9, 0.8, 0.95, 0.9, 0.7],
        font=8.2,
    )
    r.para(
        "In response, this work is constructed as the composition the "
        "literature does not supply, and treats confidence as a quantity to be "
        "measured across stages rather than trusted at one. Three positions "
        "follow. First, because [1] performs no detection and [10] identifies "
        "interfering lines as the primary obstacle to projection-based "
        "segmentation, the entire pre-recognition stage is built explicitly and "
        "its effect measured in character error rate — the metric [9] "
        "omits; where [8] required a trained network, this work uses classical "
        "geometry with no training data and additionally removes margin rules, "
        "coloured print and examiner marks. Second, because [12] and the ASAG "
        "tradition produce bare scores, the marking contract requires a verdict "
        "**and** a quoted span of the student's own text per criterion, with "
        "the arithmetic performed outside the model. Third, because [18] and "
        "[20] establish that asked-for confidence is poorly calibrated while "
        "[21] and [22] establish sampling agreement as an observable "
        "alternative, confidence is composed from four measured signals — "
        "one of which is the recognition confidence from the previous stage, "
        "addressing the composition question left open by [26]."
    )
