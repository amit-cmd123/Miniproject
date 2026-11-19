"""Chapter 3 - Proposed Work: design, architecture and implementation."""

from __future__ import annotations

from pathlib import Path

FIGURES = Path(__file__).resolve().parents[2] / "docs" / "report" / "figures"


def chapter_3(r) -> None:
    r.chapter_heading("Proposed Work")


    # ------------------------------------------------------------------ 3.1
    r.section("Design Principles")
    r.para(
        "Four principles were fixed before implementation; every subsequent "
        "decision follows from one of them."
    )
    r.bullets([
        "**P1. The rubric is institution-owned truth; the model is a "
        "replaceable estimator.** A marking scheme is the artefact a department "
        "is accountable for, so it lives in the database as structured, "
        "versioned, editable data — never embedded in a prompt. Models live "
        "behind a provider interface and are expected to be swapped.",
        "**P2. Confidence is a hypothesis to be measured, not an output to be "
        "trusted.** Because asked-for confidence is poorly calibrated [18][20], "
        "every confidence here is computed in project code from observable "
        "signals, and the machine's result is stored immutably beside the "
        "human's so the agreement can be reported.",
        "**P3. The model judges; Python computes.** A model is asked only for "
        "per-criterion verdicts and supporting quotations. All arithmetic "
        "happens in ordinary Python, so a model cannot award four marks from "
        "criteria totalling three.",
        "**P4. Nothing is substituted silently.** Where a result could have "
        "come from one of several sources, the source is recorded with it, and "
        "a specifically requested source that cannot run produces an error "
        "rather than a quiet replacement.",
    ])

    # ------------------------------------------------------------------ 3.2
    r.section("System Architecture")
    r.para(
        "The system is a layered web application: a React single-page interface "
        "over a FastAPI backend, with SQLAlchemy persistence and pluggable model "
        "providers (Figure 3.1). Two rules hold the structure together, and both "
        "are checkable by reading import statements rather than by trusting a "
        "diagram: nothing above `providers/` imports `torch`, `transformers` or "
        "any vendor SDK; and nothing in `services/` imports from `api/`."
    )
    r.figure(FIGURES / "fig_3_1_architecture.png",
             "Layered architecture. The marked boundary below `services/` is "
             "where model vendors are confined.", width=4.9)
    r.para(
        "The value of the first rule was demonstrated rather than asserted: a "
        "complete cloud recognition engine was added without changing a line of "
        "application logic, because the application depends on the "
        "`OCRProvider` abstract class and not on any model. The same boundary "
        "later admitted a second marking engine and a per-request engine switch "
        "(Section 3.7) with no change above it."
    )

    # ------------------------------------------------------------------ 3.3
    r.section("Data Model")
    r.para(
        "The relational model comprises fifteen tables covering the whole "
        "system (Table 3.1, Figure 3.2). It was created in full before the "
        "later parts were implemented, so four members could develop in "
        "parallel against frozen contracts. An answer additionally moves "
        "through an explicit lifecycle — `REGISTERED` → `OCR_RUNNING` "
        "→ `OCR_DONE` → `EVALUATED` → `UNDER_REVIEW` → "
        "`FINALIZED`, with `OCR_FAILED` as a terminal branch — whose "
        "transitions are enforced in the service layer. Representing status as "
        "a state machine rather than free text is what will later allow a job "
        "queue without changing the API."
    )
    r.table(
        "The fifteen tables of the data model, with the invariant each enforces.",
        ["Table", "Holds", "Rule it enforces"],
        [
            ["`organizations`", "Tenant reference", "Nullable now; a zero-cost hook for later scale-out"],
            ["`users`", "Admin / examiner / operator", "Role is recorded on every write"],
            ["`exams`", "Title, subject, code, term", "Subject code is the idempotency key for seeding"],
            ["`questions`", "Text, topic, type, maximum marks", "Marks must be positive"],
            ["`answer_keys`", "Reference answer", "Versioned; one active version per question"],
            ["`rubrics`", "Marking scheme, scoring rules", "Versioned; never mutated in place"],
            ["`rubric_criteria`", "Criterion, marks, concepts, alternatives", "**Criterion marks must sum to the question maximum**"],
            ["`answers`", "Image path, booklet and page reference", "Status is a state machine, not free text"],
            ["`ocr_results`", "Extracted and corrected text, confidence, model", "Correction never overwrites machine output"],
            ["`evaluations`", "Score, confidence, band, model metadata", "**Append-only**"],
            ["`evaluation_criteria`", "Verdict, marks, evidence quote", "**Append-only**"],
            ["`reviews`", "Examiner action, final score, duration", "**Append-only**; a new row, never an overwrite"],
            ["`ground_truth`", "Verified transcription and human marks", "The set everything is measured against"],
            ["`config_settings`", "Thresholds and confidence weights", "Configuration in data, not in code"],
            ["`audit_logs`", "Actor, action, object, timestamp", "Written on every state change"],
        ],
        widths=[1.3, 1.95, 2.45],
        font=8.5,
    )
    r.figure(FIGURES / "fig_3_4_er_diagram.png",
             "Entity relationships. Append-only tables are those whose rows are "
             "never updated after insertion.", width=4.6)
    r.para(
        "The append-only property of `evaluations` and `reviews` is the most "
        "consequential modelling decision in the project. If an examiner's "
        "correction overwrote the machine's score, the agreement between the "
        "two could never be measured and the validation of Section 3.6 would be "
        "impossible. The machine's original judgement therefore survives the "
        "human's correction permanently."
    )

    # ------------------------------------------------------------------ 3.4
    r.section("Part 1 — Handwriting Recognition")
    r.para(
        "Part 1 converts an uploaded image or PDF booklet into text with a "
        "per-line and per-page confidence, through the thirteen stages of "
        "Table 3.2."
    )
    r.table(
        "The thirteen stages of the recognition pipeline.",
        ["#", "Stage", "What it does", "Why it is necessary"],
        [
            ["1", "Load and resize", "Decode; cap at 2000 px wide", "Beyond this, more pixels add time but not legibility"],
            ["2", "Denoise", "3×3 median filter", "Removes sensor speckle; 5× faster than non-local-means"],
            ["3", "Assess quality", "Laplacian-variance blur; Otsu ink contrast", "Measured *after* denoising: noise makes a blurred photo look sharp"],
            ["4", "Flatten illumination", "Estimate blank paper and divide it out", "A shadowed corner then reads like a lit one"],
            ["5", "Isolate ink — colour", "Drop red and orange on bright paper", "Removes printed form colour and examiner marks"],
            ["6", "Isolate ink — darkness", "Threshold anchored to the page's darkest ink", "Rejects show-through while keeping faint pencil"],
            ["7", "Remove ruling", "Long-run morphology, Hough for dashed rules, solid-along-path test", "A recogniser handed a ruled line invents a sentence for it"],
            ["8", "Classify the page", "Coloured print outweighing ink ⇒ printed cover", "Skips the cover instead of inventing text from it"],
            ["9", "Deskew", "Rotate until horizontal ink projection is sharpest", "Segmentation assumes horizontal lines"],
            ["10", "Segment lines", "Projection profile; merge fragments; split fused bands", "Handwriting models read one line at a time"],
            ["11", "Filter boxes", "Drop boxes with almost no ink", "A stray mark otherwise costs a decode and returns invented text"],
            ["12", "Recognise", "TrOCR per line, or Gemini per page", "A per-line token budget stops runaway decoding"],
            ["13", "Score and store", "Confidence, band, warnings, audit entry", "Evidence, not just an answer"],
        ],
        widths=[0.28, 1.2, 1.95, 2.27],
        font=8.2,
    )
    r.figure(FIGURES / "fig_3_2_pipeline.png",
             "Pipeline stages, grouped by purpose: image preparation, ink "
             "isolation, geometry, and recognition.", width=3.9)
    r.para(
        "Stage 7 is where the gain reported in Section 4.3 originates, solving "
        "with classical geometry a problem for which the literature trains a "
        "convolutional network [8]: a candidate rule is accepted only if it is "
        "solid along its own path with bare paper beside it, which "
        "distinguishes a printed rule from a line of writing. Stage 12 applies "
        "a per-line token budget from the line's width-to-height ratio — "
        "without it, TrOCR on an unreadable crop repeats itself to the "
        "generation limit, so the worst lines became the slowest. This targets "
        "the runaway generation the TrOCR authors themselves report [1]."
    )
    r.subsection("Transcription confidence")
    r.para(
        "For the local engine the decoder yields a probability for every token "
        "chosen; the line score is their geometric mean, and the page score is "
        "the length-weighted mean of its lines reduced by a penalty for a soft "
        "image, so long hesitant lines outweigh short confident ones:"
    )
    r.code("line_confidence = exp( (1/N) · Σ log P(token_i) )\n"
           "page_confidence = ( Σ len(l)·conf(l) / Σ len(l) ) × sharpness_penalty")
    r.para(
        "For the cloud engine this is unavailable: none of the four "
        "flash-class models tested exposes token log-probabilities, each "
        "returning `Logprobs is not enabled for this model`. The page is "
        "therefore read **twice, independently**, and each line scored by how "
        "closely the two readings agree — a line read identically twice is "
        "one the model could actually see. The method used is stored with every "
        "result. Setting the sample count to one halves the cost and records "
        "confidence as *unmeasured* rather than inventing one."
    )
    r.subsection("Multi-page booklets")
    r.para(
        "A PDF booklet is rasterised to a target pixel width rather than a "
        "fixed DPI, matching the width preprocessing will keep. Each page then "
        "passes through the identical pipeline as its own answer with its own "
        "confidence; pages of one upload share a `document_ref`, which is what "
        "allows the booklet to be marked as a unit, and a page that fails is "
        "reported in place rather than discarding the rest."
    )

    # ------------------------------------------------------------------ 3.5
    r.section("Part 2 — Questions and Rubrics")
    r.para(
        "A question carries its text, topic, type and maximum marks; an answer "
        "key carries the reference answer; a rubric carries an ordered list of "
        "criteria. Each criterion records more than a description and a mark: "
        "`essential_concepts` (what it is really testing, shown to the marker "
        "as *meaning* and never as strings to match literally, so a student who "
        "expresses the idea in their own words still scores), "
        "`acceptable_alternatives`, `common_mistakes`, `allows_partial` (false "
        "makes it all-or-nothing, for points where a half-stated fact is not "
        "half correct) and `load_bearing` (a criterion the rest of the answer "
        "depends on; getting these wrong costs confidence rather than marks)."
    )
    r.subsection("Versioning and the sum invariant")
    r.para(
        "A rubric is never modified in place: saving writes a new version and "
        "deactivates the previous one, so a mark awarded last term still "
        "resolves to the rubric it was marked against. Answer keys behave "
        "identically, and a question that has already been marked against "
        "cannot be deleted at all, because its evaluations cite its rubric."
    )
    r.para(
        "The validator enforces one invariant above all: **the criteria of a "
        "rubric must sum to the question's maximum marks**, within 0.001. A "
        "rubric summing to 4.5 out of 5 silently caps every student at ninety "
        "per cent and produces scores that look reasonable and are wrong for "
        "every script, so the system refuses to mark against it. Raising a "
        "question's maximum does not rescale its rubric either: the mismatch is "
        "reported and marking refuses, because redistributing marks is an "
        "examiner's judgement, not an arithmetical one."
    )
    r.subsection("Authoring and importing a paper")
    r.para(
        "A paper can be created in four ways, all converging on the same "
        "validated representation: typed in through the rubric editor; seeded "
        "from the bundled JSON; imported as exported JSON; or **read out of the "
        "Word or PDF file the department already has it in**. The last route "
        "matters because marking schemes are written as Word tables far more "
        "often than as structured data. Extracting a `.docx` by pulling every "
        "text run in file order destroys exactly the structure that matters "
        "— criterion and mark land on separate lines with nothing linking "
        "them — so the importer reads tables *as tables*, emitting "
        "pipe-delimited rows that preserve the association. A `.docx` is a ZIP "
        "of XML, so this needs no dependency beyond the standard library."
    )
    r.para(
        "Two parsers are offered. A deterministic regular-expression parser "
        "handles bulleted, tabulated, tab-separated and dot-leader layouts; it "
        "cannot invent a criterion because it only copies spans of the "
        "document, and it lists the lines it could not place. A cloud parser "
        "handles prose and irregular layouts the expressions cannot, but can "
        "paraphrase. Both produce a **proposal**: nothing is written to the "
        "database until an examiner reviews the parsed questions and criteria "
        "on screen and approves them. A rubric whose criteria do not sum is "
        "imported exactly as the document had it, with a warning."
    )

    # ------------------------------------------------------------------ 3.6
    r.section("Parts 3 and 4 — Evaluation, Confidence and Review")
    r.subsection("The marking contract and deterministic scoring")
    r.para(
        "The marking provider receives a typed task: the question, its maximum "
        "marks, the answer key, every criterion with its concepts and "
        "alternatives, the scoring rules, and the student's transcribed text. "
        "It returns, per criterion, one of three verdicts — satisfied, "
        "partially satisfied, not satisfied — a coverage fraction where "
        "partial, a reason, and a quotation from the student's own answer. The "
        "response is schema-constrained JSON; a malformed response is retried "
        "rather than guessed at. Marks are then computed in Python with no "
        "model involved:"
    )
    r.code(
        "satisfied            -> the criterion's full marks\n"
        "partially_satisfied  -> coverage × max_marks, snapped to the mark grid,\n"
        "                        or zero if the criterion forbids partial credit\n"
        "not_satisfied        -> zero\n"
        "total                 = min( Σ criterion marks , question maximum )"
    )
    r.para(
        "Because this module has no network, no model and no database, it is "
        "exhaustively testable: the same verdicts always produce the same "
        "marks, and thirty-six automated tests cover it alone. Every mark in a "
        "score traces to exactly one criterion, which is what makes the "
        "breakdown shown to an examiner trustworthy."
    )
    r.subsection("Composite confidence and routing")
    r.para(
        "Four signals are measured, not asked for, and combined as a weighted "
        "geometric mean (Table 3.3). The geometric mean is chosen deliberately "
        "over an arithmetic one: one signal collapsing must drag the result "
        "down, because an answer marked from an unreadable transcription is "
        "untrustworthy however confidently the marker agreed with itself, and "
        "an arithmetic mean would hide that behind three good numbers. When a "
        "signal cannot be measured its weight is redistributed and the omission "
        "recorded. The weights are an explicitly uncalibrated starting "
        "hypothesis, stored with every evaluation so a validation study can "
        "replace them."
    )
    r.table(
        "The four confidence signals and their current weights.",
        ["Signal", "Weight", "What it measures", "Why it matters"],
        [
            ["Transcription", "0.30", "How well the handwriting was read; a human-corrected transcription scores 1.0",
             "Marks from text we misread are wrong however good the marker is"],
            ["Agreement", "0.30", "How far two independent markings coincide, criterion by criterion",
             "A verdict that changes between readings is a guess [21][22]"],
            ["Grounding", "0.25", "Share of mark-bearing verdicts whose quoted evidence is found in the transcription",
             "A fabricated quotation means the verdict was not read off the page"],
            ["Decisiveness", "0.15", "How far verdicts sit from the partial-credit boundary, weighted by marks",
             "A criterion judged exactly half-met is a coin flip"],
        ],
        widths=[0.9, 0.5, 1.95, 2.35],
        font=8.3,
    )
    r.figure(FIGURES / "fig_3_5_confidence.png",
             "Composition of the evaluation confidence from four measured "
             "signals.", width=4.5)
    r.figure(FIGURES / "fig_3_6_bands.png",
             "Trust bands for transcription (left) and review routing (right), "
             "served from the API rather than hard-coded in the interface.",
             width=5.2)
    r.para(
        "The auto-accept band is a candidate only: no result is auto-accepted "
        "in the present system, because until the false-auto-accept rate has "
        "been measured against examiner decisions everything is still reviewed. "
        "This is the selective-prediction policy of [24] and [25] with hand-set "
        "rather than fitted thresholds, and the report says so."
    )
    r.subsection("Booklet marking and examiner review")
    r.para(
        "Marking a booklet proceeds in three phases, a structure forced by the "
        "fact that a SQLAlchemy session is not thread-safe: a database phase "
        "assembling every marking task, a parallel network phase performing all "
        "readings concurrently through a bounded pool, and a second database "
        "phase persisting the results. No database work occurs during the "
        "parallel phase."
    )
    r.para(
        "The examiner is then shown, on one screen, the original handwriting, "
        "the transcription, the per-criterion verdicts with their quoted "
        "evidence, the composite confidence with its four component signals, "
        "and the resulting band. The examiner accepts or modifies the score, "
        "optionally with a comment, and the time taken is recorded. The "
        "decision is written as a **new row**; the machine's score, confidence, "
        "model name and version, prompt version and rubric version all remain "
        "exactly as recorded. This is what makes the validation view possible: "
        "it reports how often examiners accepted the machine's score unchanged, "
        "the mean absolute difference where they did not, and both broken down "
        "by confidence band — the measurement that would eventually justify "
        "moving a threshold or enabling auto-accept."
    )

    # ------------------------------------------------------------------ 3.7
    r.section("Engine Selection")
    r.para(
        "Both recognition and marking are provided through interfaces with "
        "multiple implementations (Table 3.4). The engine is selected **per "
        "request** rather than per deployment: every endpoint that reads "
        "handwriting or awards a mark accepts an `engine` parameter and the "
        "interface offers a switch, because comparing two engines on the same "
        "booklet otherwise requires editing configuration and restarting the "
        "server between readings."
    )
    r.table(
        "Available engines and their roles.",
        ["Engine", "Implementation", "Role", "Network"],
        [
            ["TrOCR (local)", "`microsoft/trocr-small-handwritten` via PyTorch", "Reads one segmented line at a time", "None"],
            ["Gemini (cloud)", "REST, no vendor SDK", "Reads a whole page with layout; marks against the rubric", "Yes"],
            ["Rubric concept matcher", "Project code", "Marks by concept overlap, criterion by criterion", "None"],
            ["Mock", "Project code", "Deterministic stand-in for tests and offline development", "None"],
        ],
        widths=[1.15, 1.85, 1.95, 0.6],
        font=8.5,
    )
    r.para(
        "Principle P4 governs the behaviour: a specifically requested engine is "
        "never substituted. Requesting the cloud engine with no API key "
        "configured returns HTTP 503 with the reason rather than quietly "
        "reading the page with the local model, because the provider's name is "
        "written onto every stored transcription and every stored score and a "
        "silent substitution would make the record claim something that did not "
        "happen. The *configured default* still falls back, that being a "
        "deployment preference rather than a stated intent. A status endpoint "
        "reports which engines can run, so the switch is shown disabled with "
        "its reason instead of failing when flipped."
    )
    r.para(
        "With the cloud engine off, marking runs on the rubric concept matcher. "
        "It walks the same criteria and awards the same partial credit but "
        "decides by concept overlap rather than by reading, and every score it "
        "produces is flagged and carries the warning that it is a baseline to "
        "compare against and not a result to report. Its real value is as that "
        "baseline: it is what makes “the language model is better” a "
        "number rather than an opinion."
    )

    # ------------------------------------------------------------------ 3.8
    r.section("Implementation Summary")
    r.table(
        "Implementation scale, measured from the repository.",
        ["Component", "Files", "Lines", "Notes"],
        [
            ["Backend application (Python)", "49", "10,911", "FastAPI, SQLAlchemy, OpenCV, PyTorch"],
            ["Automated tests (Python)", "11", "3,217", "244 tests, `unittest`, no network required"],
            ["Frontend (TypeScript, TSX, CSS)", "19", "6,056", "React 19, Vite 8.3, Tailwind"],
            ["Operational scripts", "9", "~2,400", "Benchmarking, Gemini checks, start-up, report build"],
            ["Documentation (Markdown)", "6", "2,673", "Brief, demo script, presenter guide, related work"],
            ["**Total**", "**94**", "**~25,250**", "47 API endpoints over 15 tables"],
        ],
        widths=[2.15, 0.6, 0.75, 2.05],
        font=8.5,
    )
    r.table(
        "Technology stack and the reason for each choice.",
        ["Technology", "Version", "Used for", "Why"],
        [
            ["FastAPI", "0.141.1", "HTTP API", "Type-checked contracts; live interactive API documentation"],
            ["Pydantic", "2.13.5", "Schema validation", "The frozen contracts between the four parts are Pydantic models"],
            ["SQLAlchemy", "2.0.52", "ORM, 15 tables", "Database-agnostic: SQLite to PostgreSQL is a connection string"],
            ["SQLite", "built in", "Storage", "Zero external services, so any member can clone and run"],
            ["OpenCV", "5.0.0.93", "Preprocessing, segmentation", "Classical vision is fast, explainable, needs no training data"],
            ["PyTorch", "2.14.0 (CPU)", "Running TrOCR", "CPU build; no GPU available"],
            ["Transformers", "4.57.6", "Loading TrOCR", "Pinned below 5.0: 5.x removed the tokenizer conversion TrOCR needs"],
            ["PyMuPDF", "1.28.2", "PDF rasterisation", "Booklets arrive as PDFs; recognition works on images"],
            ["jiwer", "4.0.0", "Character and word error rate", "Turns “it works well” into a number"],
            ["httpx", "0.28.1", "Calling Gemini over REST", "No vendor SDK; the exact request is visible in project code"],
            ["React / TypeScript", "19.2 / 6.0", "Interface", "Live examiner review screen; integration errors caught at compile time"],
            ["Vite", "8.3", "Dev server and build", "Proxies `/api`, so no CORS and no hard-coded backend URL"],
            ["Tailwind CSS", "3.4", "Styling", "One design-token layer; the whole theme is two files"],
        ],
        widths=[1.15, 0.8, 1.45, 2.35],
        font=8.2,
    )
