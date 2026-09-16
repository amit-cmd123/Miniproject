# EvalNova — Complete Project Brief

*Source material for building a presentation. Everything here is factual as of
16 September 2026. Claims are explicitly labelled **MEASURED**, **BUILT**,
**PLANNED** or **UNVERIFIED** — please preserve those distinctions in any
slides, because the project's credibility rests on not overclaiming.*

---

## 0. How to use this document

If you are generating a presentation from this brief:

- The audience is a **mid-semester project review panel** (faculty + peers) for
  a 4-person engineering mini-project.
- The single most important message: **this is not "upload an answer and ask an
  AI if it's correct."** It is an accountable marking pipeline where every mark
  traces back to the handwriting that earned it.
- Do **not** present planned work as finished. A suggested slide outline is in
  section 14.
- Honest limitations (section 12) are a strength in a review, not a weakness.
  Panels reward teams who know where their system fails.

---

## 1. What the project is

**EvalNova** is a confidence-aware, rubric-driven system for evaluating
handwritten examination answers.

A student writes an answer by hand. The system:
1. reads it,
2. evaluates it against the marking scheme the department actually uses,
3. reports how confident it is in that judgement,
4. routes uncertain cases to a human examiner who has the final say,
5. and records every step.

**The defining distinction.** Asking a language model "is this answer correct?"
produces an unaccountable number that no institution can defend. EvalNova
produces a *defensible marks decision*: for every mark awarded there is a chain
from the original handwriting → the extracted text → the specific rubric
criterion it satisfies → the evidence quoted from the student's own words → the
confidence in that judgement → the examiner's accept-or-modify → the final
score.

**Two principles drive the whole architecture:**

1. **The rubric is institution-owned truth; the AI model is a replaceable
   estimator.** So rubrics live in the database as structured data, and models
   live behind a swappable provider interface.
2. **Confidence is a hypothesis to be measured, not an output to be trusted.**
   So the AI's result is stored immutably alongside the human's, forever, and we
   report how often the two agree.

**Domain:** Computer Science theory questions.
**Duration:** 6–8 weeks, 4 phases.
**Team:** 4 members, 4 parallel workstreams.
**Repository:** https://github.com/amit-cmd123/Miniproject

---

## 2. The four workstreams

| Part | Owner | Question it answers | Consumes | Produces | Status |
|---|---|---|---|---|---|
| 1 · Handwriting & OCR | Member 1 | "What did the student write?" | answer image | text + confidence | **BUILT** |
| 2 · Questions & Rubrics | Member 2 | "What should a correct answer contain?" | — | question, answer key, criteria | PLANNED |
| 3 · Evaluation & Confidence | Member 3 | "How many marks, and how sure are we?" | Part 1 text + Part 2 rubric | marks, reasons, confidence | PLANNED |
| 4 · Examiner App & Validation | Member 4 | "Can a human verify and correct it?" | Part 3 result | final score, metrics | PLANNED |

**Why these run in parallel rather than in sequence:** all shared data contracts
were frozen on day one, and mock providers return realistic stand-in data. Every
member develops and tests against their neighbours' contracts without waiting
for their code. File-level ownership keeps four people out of each other's merge
conflicts.

---

## 3. Current status — what is actually built

### BUILT and working (Part 1)

Upload a photograph, a scan, or a multi-page PDF answer booklet, and the system:

1. Cleans the image — flattens uneven lighting, corrects rotation
2. Isolates the student's ink — removes printed ruling and margin lines,
   coloured print, the examiner's red marks, and writing showing through from
   the back of the sheet
3. Detects and skips a printed cover/form page, stating why
4. Splits the page into individual handwriting lines
5. Reads the handwriting (locally with TrOCR, or with Gemini when configured)
6. Reports a confidence score measured from the model's own behaviour
7. Places the result in one of four trust bands
8. Lets a human correct the text **without destroying the machine output**, so
   error rate stays measurable
9. Measures character and word error rate against a known transcription

For a PDF, each page is rasterised and put through the same pipeline as its own
answer, with its own confidence. Pages share a `document_ref`, and a page that
fails is reported in place rather than discarding the rest of the booklet.

### BUILT as contracts only (Parts 2–4)

- All 15 database tables for the *entire* system exist and are migrated.
- Five endpoints are registered and deliberately return **HTTP 501** with a
  message naming the workstream that owns them: `/questions`,
  `/questions/{id}/rubric`, `/evaluations`, `/reviews`, `/analytics/summary`.
- The frontend has prototype screens for all four parts showing intended layout,
  owner and the endpoints each will call.

**Why fix contracts before writing code:** the API documentation shows the whole
system from day one, the frontend can wire real calls and get an honest failure,
and no member has to guess another member's route names.

### Scale

- **14 implemented API endpoints** + 5 registered-but-unimplemented + `/health`
- **15 database tables**
- **96 automated tests, all passing** — no model download and no network needed
- **74 files** in the repository

---

## 4. MEASURED results (Part 1)

All figures measured on an **Intel Core i9-13900H laptop, CPU only, no GPU**.

### Before and after the optimisation work of 15 September 2026

| Page | Before | After | Change |
|---|---|---|---|
| **Real scanned answer page** (ruled paper, handwritten maths, phone photo) | 64 s, **125% character error** | **7 s, 47% character error** | 9× faster, error cut by more than half |
| **4 synthetic sample sheets** (clean / normal / messy / poor) | ~17 s each, 1–4% character error | **~4 s each, 0% character error on all four** | 4× faster, perfect on samples |

*A character error rate above 100% means the output contained more wrong
characters than the reference had characters at all — the model was inventing
text. This is what happens when a recogniser is handed printed ruling lines.*

### Confidence behaves correctly

On the real answer page the local model's confidence falls to **~53%**, placing
the page in the *Manual transcription* band. The system correctly says "I cannot
read this, give it to a human" rather than producing a confident wrong answer.
On the synthetic samples confidence is ~98% (*Reliable*), and the text is
word-perfect.

### Engineering decisions validated by measurement, not opinion

| Experiment | Result | Decision |
|---|---|---|
| `trocr-small` vs `trocr-base` | small is ~10× faster; 47% vs 45% error on the real page; both 0% on samples | **Adopted small** as default |
| int8 quantisation of the model | 25% faster, but error rose from 2% to over 80% | **Rejected** |
| Batch size 4 / 8 / 16, line sorting | ~6% gain only | Adopted batching; noted it is not the bottleneck |
| CPU thread count 6 / 12 / 14 | fewer threads strictly slower | Left at default |
| Replacing non-local-means denoising with a median filter | 1.2 s → 0.25 s, no accuracy loss | Adopted |

**Presentation point:** every one of these was decided by running the experiment
and recording the number, including the one that was rejected.

---

## 5. Current tech stack, and why

### Backend — Python 3.10

| Technology | Version | Used for | Why this choice |
|---|---|---|---|
| **FastAPI** | 0.141.1 | HTTP API layer | Type-checked request/response contracts; generates live interactive API docs so all four members see the interface before it is finished |
| **Pydantic** | 2.13.5 | Schema validation | The frozen contracts between the four parts are Pydantic models — invalid data fails at the boundary, not deep inside |
| **SQLAlchemy** | 2.0.52 | ORM / all 15 tables | Database-agnostic: moving from SQLite to PostgreSQL is a connection-string change, not a rewrite |
| **SQLite** | built in | Storage (for now) | Runs with zero external services, so any teammate can clone and run immediately |
| **OpenCV** | 5.0.0.93 | Page cleanup, line segmentation | The real engineering of Part 1; classical computer vision is fast, explainable and needs no training data |
| **NumPy** | 2.2.6 | Array maths | Underpins all image and confidence computation |
| **PyTorch** | 2.14.0 (CPU) | Running TrOCR locally | Standard runtime for the model; CPU build because no GPU is available |
| **Transformers** | 4.57.6 | Loading TrOCR | Pinned **below 5.0 deliberately**: 5.x removed the tokenizer conversion TrOCR checkpoints depend on |
| **PyMuPDF** | 1.28.2 | PDF → page images | Scanned booklets arrive as PDFs; recognition works on images |
| **jiwer** | 4.0.0 | Character/word error rate | Turns "it works well" into a number |
| **httpx** | 0.28.1 | Calling Gemini over REST | No vendor SDK to install; the exact request is visible in our own code |
| **uvicorn** | 0.53.0 | ASGI server | Standard FastAPI server, hot reload in development |
| **unittest** | built in | 96 tests | No extra dependency; runs anywhere |

### Frontend

| Technology | Version | Why |
|---|---|---|
| **React** | 19.2 | Component model suits an examiner review screen with live state |
| **TypeScript** | 6.0 | Types generated from the API contract catch integration errors at compile time |
| **Vite** | 8.3 | Instant dev server; proxies `/api` to the backend so there is **no CORS setup and no hard-coded backend URL** |
| **Tailwind CSS** | 3.4 | Consistent design system without a separate stylesheet to maintain |
| **oxlint** | 1.81 | Fast linting |

### Models and external services

| Engine | What it is | Role | Status |
|---|---|---|---|
| **TrOCR** `microsoft/trocr-small-handwritten` | Microsoft handwriting recognition model, via Hugging Face. Vision encoder + text decoder, reads one line at a time | **Default engine.** Fully offline — no data leaves the machine | MEASURED |
| **Google Gemini** `gemini-3.5-flash` | Cloud vision-language model, reads a whole page with its layout | Optional high-accuracy engine, opt-in via config | **BUILT but UNVERIFIED** — no API key available yet, so never run live |
| **Mock engine** | Returns fixed deterministic text without reading the image | Tests, offline development, demo fallback | BUILT |

**Why two recognition engines:** TrOCR was trained on the IAM corpus — Western
cursive, everyday English. Real answer booklets are Indian student handwriting
with stacked fractions and exponents on ruled paper: outside its training
distribution. A vision-language model reads whole pages with layout and is
expected to do much better, *but it sends student answer sheets to Google*. So
it is a deliberate configuration choice, never a default, and the local engine
is always there as a fallback.

### Supporting tools

- **Git + GitHub** — version control, per-member branches, pull requests
- **Hugging Face Hub** — one-time model weight download
- **Google Colab / Kaggle** (PLANNED) — free GPU sessions for benchmarking and
  fine-tuning, outside the request path
- **Claude Code** — AI pair-programming assistant used during development

---

## 6. Architecture

```
frontend/                React · TypeScript · Tailwind
    │  REST/JSON, proxied through Vite (no CORS in development)
backend/app/
    api/v1/              HTTP surface only — no business logic
    services/            preprocessing, transcription, confidence, audit
    providers/ocr/       TrOCR │ Gemini │ mock   ← the replaceability boundary
    db/                  SQLAlchemy models for the whole data model
    core/                configuration and thresholds
scripts/                 sample generation, Gemini check, start-up helpers
```

**Two rules hold the structure together, and both are checkable by reading
imports:**

1. **Nothing above `providers/` imports torch, transformers, or any vendor SDK.**
2. **Nothing in `services/` imports from `api/`.**

**Why this matters — proved in practice:** a complete cloud recognition engine
was added in one session without changing a single line of application logic.
That is the "the model is replaceable" claim demonstrated rather than asserted.

### Answer lifecycle (a state machine, not a free-text status)

```
REGISTERED → OCR_RUNNING → OCR_DONE → EVALUATED → UNDER_REVIEW → FINALIZED
                    ↓
               OCR_FAILED
```

Transitions are enforced in the service layer. The state machine is what allows
a job queue to be added later without changing the API.

### Data model — 15 tables

| Entity | Holds | Rule |
|---|---|---|
| User | admin / examiner / operator | role gates every write |
| Organization | tenant reference | nullable now; zero-cost hook for later scale-out |
| Exam → Question | text, subject, topic, maximum marks | — |
| AnswerKey | reference answer | versioned |
| Rubric → RubricCriterion | criteria, marks, alternatives, partial-credit rules | versioned; **criterion marks must sum to the question maximum** |
| Answer | image reference, lifecycle status | status is a state machine |
| OCRResult | extracted text, corrected text, confidence, model version | evaluation reads the corrected text when one exists |
| Evaluation → EvaluationCriterion | score, per-criterion verdicts, evidence, confidence, full model metadata | **append-only, never updated** |
| Review | final score, action, reviewer, comment, timestamp | append-only; a separate row, never an overwrite |
| GroundTruth | verified transcription and human marks | the validation set everything is measured against |
| ConfigSetting | thresholds and confidence weights | in the database, never in code |
| AuditLog | actor, action, object, timestamp | written on every state change |

**Why evaluations and reviews are append-only:** the AI's original result must
survive the examiner's correction. That separation is what makes the entire
validation study possible — you cannot measure AI-vs-human agreement if the
human overwrote the AI.

---

## 7. The Part 1 pipeline, step by step

This is the most technically substantial part of the current build and deserves
a slide of its own.

| # | Stage | What it does | Why |
|---|---|---|---|
| 1 | Load & resize | Decode, cap at 2000 px wide | Beyond this, more pixels add time but not legibility |
| 2 | Denoise | 3×3 median filter | Removes sensor speckle; 5× faster than the non-local-means method it replaced |
| 3 | Assess quality | Blur score (Laplacian variance), ink-to-paper contrast (Otsu) | Measured *after* denoising, because sensor noise makes a blurry photo look artificially sharp |
| 4 | Flatten illumination | Estimate the blank paper and divide it out | A shadowed corner then reads like a lit one, so one threshold works across the page |
| 5 | Isolate ink — colour | Drop red/orange on bright paper | Removes printed form colour and the examiner's marks. Restricted to bright paper so a wooden desk at the photo's edge is not mistaken for print |
| 6 | Isolate ink — darkness | Threshold anchored to the page's own darkest ink | Rejects the faint mirror-image writing showing through from the back of the sheet, while still catching faint pencil |
| 7 | Remove ruling | Long straight runs, plus a Hough transform for rules broken into dashes, each candidate tested for "solid along its path, bare paper beside it" | A recogniser handed a ruled line **confidently invents a sentence for it** — this was the single biggest cause of bad output |
| 8 | Classify the page | Coloured print outweighing handwriting ⇒ printed cover/form | Skips the cover page instead of spending 100 s inventing text from it |
| 9 | Deskew | Rotate until the horizontal ink projection is sharpest | Segmentation assumes horizontal lines |
| 10 | Segment lines | Projection profile; merge stray fragments into the nearest line; split bands fused by a tall stroke | Handwriting models read **one line at a time**; feeding a whole page produces nonsense |
| 11 | Filter | Drop boxes with almost no ink | A stray mark otherwise costs a full decode and returns invented text |
| 12 | Recognise | TrOCR per line (batched, sorted by length, token budget capped by line width) or Gemini per page | The token cap stops the decoder looping "000500050005…" on an unreadable crop |
| 13 | Score & store | Confidence, trust band, warnings, audit entry | Evidence, not just an answer |

**Two bugs found and fixed by measurement during this work**, both now covered by
tests that fail if the bug returns:
- A speck-removal step was erasing every pen stroke thinner than 3 px.
- The margin-line detector treated neatly aligned letter stems as a ruled margin
  and deleted them.

---

## 8. Confidence — the part that has to be earned

**Asking a model "how confident are you?" gives a number that correlates weakly
with being right.** Models are systematically overconfident. Shipping that raw
number would make the entire validation story collapse under questioning. So
confidence is computed in our own code.

### Part 1 — transcription confidence (BUILT, MEASURED)

Per line, the decoder gives a probability for every character it chose. The line
score is the geometric mean of those:

```
line_confidence = exp( mean( log P(token_i) ) )
```

The page score weights each line by its length, then applies a penalty for a
soft image:

```
page = (length-weighted mean of line confidences) × sharpness_penalty
```

Long hesitant lines therefore outweigh short confident ones, and a blurred
photograph drags the whole page down even when the decoder sounds certain.

For Gemini, the same measure is used when the API returns token
log-probabilities. When it does not, the page is read **twice** and each line is
scored by how closely the two independent readings agree — a line read
identically twice is one the model can actually see. The method used is stored
with every result.

### Part 1 trust bands (served from the API, never hard-coded in the UI)

| Confidence | Band | Meaning |
|---|---|---|
| ≥ 95% | Reliable | May proceed to evaluation without routine checking |
| 85–95% | Spot check | Largely trustworthy; a quick read-through advised |
| 70–85% | Verify | A human should confirm before marks depend on it |
| < 70% | Manual transcription | Too unreliable to evaluate; correct by hand |

### Part 3 — composite evaluation confidence (PLANNED)

Four signals, combined in our code with weights tuned in Phase 3:

| Signal | What it captures |
|---|---|
| **Self-consistency** | The same answer is evaluated three times; we measure how often the criterion-level verdicts agree. A model disagreeing with itself is the strongest available signal of genuine uncertainty |
| **Model self-report** | The model's stated confidence — included, but weighted as one weak signal rather than treated as the answer |
| **Recognition confidence** | An evaluation built on an unreliable transcription cannot itself be reliable, however sure the model sounds |
| **Rubric coverage** | Did every criterion receive a real evidence quote from the student's answer? Unsupported verdicts lower the score |

### Part 3 review-routing bands (contract already recorded in code)

| Confidence | Routing |
|---|---|
| ≥ 95% | Auto-accept candidate — *only* once the false-auto-accept rate has been measured; until then still reviewed |
| 90–95% | Quick review — examiner confirms the total |
| 85–90% | Mandatory review — examiner must open the criterion breakdown |
| < 85% | Detailed verification — original handwriting must be inspected |

**Critical honesty point for the presentation:** these bands are *starting
hypotheses*, not established values. They live in one file and are served over
the API precisely so Phase 3 can move them based on measurement. Confidence is
currently **measured but not calibrated** — a confidently misread word still
scores high.

---

## 9. What happens next — the full future pipeline

### How one answer will travel end to end (target state)

1. **Answer registered** — image uploaded, `Answer` row created, status `REGISTERED` ✅ *built*
2. **Handwriting recognition** — preprocess, segment, recognise; produces text, confidence and model version; low confidence raises a verification flag rather than failing ✅ *built*
3. **Academic context assembled** — question text, maximum marks, answer key, rubric criteria, acceptable alternatives and partial-credit rules loaded into one typed evaluation input *(Part 2)*
4. **Model judges each criterion** — returns, per criterion, a verdict and a quoted piece of evidence from the student's own words; output is schema-constrained JSON; malformed responses are retried, never guessed at *(Part 3)*
5. **Marks computed deterministically** — Python sums criterion marks, applies partial-credit rules, clamps to the maximum *(Part 3)*
6. **Confidence composed and routed** — four signals → one composite → one of four review bands *(Part 3)*
7. **Evaluation written immutably** — append-only rows carrying provider, model name and version, prompt version, rubric version and latency *(Part 3)*
8. **Examiner reviews** — handwriting, extracted text, criterion verdicts and reasons side by side; accept or modify with an optional comment *(Part 4)*
9. **Final score stored separately** — a new review row, audited; the AI's original result is never overwritten *(Part 4)*

**Why the scoring arithmetic is deterministic and outside the model:** the model
judges each criterion and quotes its evidence; Python does the addition. A model
can therefore never award 4 marks from criteria that total 3.

### Technology to be added, and why

| Technology | For | Why |
|---|---|---|
| **Google Gemini** (free tier) via `EvaluationProvider` | Part 3 evaluation | Supports a constrained JSON response schema, which removes most malformed-output risk. Behind a provider interface so it can be replaced without touching anything above it |
| **PostgreSQL + Alembic** | Phase 2 persistence | Real migrations before the schema has to survive real data; concurrent access for four developers |
| **Authentication + role enforcement** | Phase 2 | Roles already exist in the data model; enforcement gates every write |
| **Content-hash evaluation caching** | Phase 3 | Free-tier rate limits and cost; also makes batch experiments repeatable |
| **Temperature fixed at 0** | Part 3 | Determinism, so an experiment can be rerun and compared |
| **Google Colab / Kaggle notebooks** | Offline, outside the request path | Free GPU for the recognition benchmark, fine-tuning TrOCR on our own handwriting, and calibration analysis — a real contribution rather than pure integration |
| **Validation dashboard** | Part 4 | Turns the project from a demo into a project with evidence |

### Per-member work remaining

**Member 1 — Handwriting & OCR**
- Collect and transcribe real handwriting samples (~50 answers)
- Benchmark candidate models on a public corpus, report CER/WER
- Fine-tune on our own handwriting in Colab
- Document the failure taxonomy — what breaks recognition, and why
- Measure the Gemini engine against the local one on our own pages

**Member 2 — Questions & Rubrics**
- Author 15–20 CS theory questions with answer keys
- Criterion breakdown with per-criterion marks
- Acceptable alternatives and partial-credit rules
- Rubric schema + validator (criterion marks must sum to the question maximum)
- Test answers in four categories: correct, partial, wrong, ambiguous

**Member 3 — Evaluation & Confidence**
- Provider abstraction + mock implementation
- Prompt design with schema-constrained output
- Deterministic scoring engine
- Composite confidence and review routing
- Graceful failure on every provider error path (timeout, malformed output, outage)
- Batch experiments and calibration

**Member 4 — Examiner App & Validation**
- Worklist and review interface
- Handwriting displayed beside text and verdicts, with zoom
- Accept / modify persisted with an audit trail
- Validation dashboard and metrics
- End-to-end integration of all four parts; demonstration flow

---

## 10. Phase plan

| Phase | Duration | Goal | Exit criterion |
|---|---|---|---|
| **1 · Foundation & contracts** | ~2 weeks | Every module works and is tested in isolation; nothing integrated yet, deliberately | Each of the four modules runs and passes its own tests without depending on another member's work |
| **2 · The vertical slice** | ~2 weeks | One real handwritten image becomes one real stored final score. The make-or-break phase | A live demonstration: upload → recognition → rubric → evaluation → criterion marks with reasons → routing → examiner modifies → final score in the database, with the AI's original result intact beside it |
| **3 · Scale & validation** | ~1.5 weeks | Turn a working demo into a project with evidence | We can state, with numbers and a ground-truth set behind them, exactly where the system works and where it fails |
| **4 · Testing, hardening & polish** | ~1.5 weeks | Robust, presentable, reproducible | A stranger can clone the repository, run it, and reach the same numbers we report |

≈ 7 weeks of work inside a 6–8 week window, leaving buffer.

**Where we are now:** Phase 1 is complete for Part 1 and for all shared
contracts; Parts 2–4 have their contracts but not their implementations.

---

## 11. What we will report — the measurement plan

Claims like "95% accurate" mean nothing without a definition and a sample size.
These are the measurements the project commits to producing, each against a
human-labelled ground-truth set.

| Layer | Measurement | What it answers |
|---|---|---|
| Recognition | Character and word error rate | How much of the handwriting did we actually read? |
| Marking | Exact agreement, mean absolute error, proportion within one mark | How close is the AI to a human examiner? |
| Confidence | Calibration curve, false-auto-accept rate | When it says 95%, is it right 95% of the time? |
| Workflow | Human review rate, processing time per answer | Would this actually save an examiner effort? |
| Isolation | Marks on raw recognition vs corrected transcription | How many marks does a recognition error cost? |
| Qualitative | Failure taxonomy across recognition, evaluation and rubric | Where and why does it break? |

Every result will be reported **with its sample size stated**. On a set of
roughly fifty answers we can report an indicative finding, not a general claim —
and saying so is part of the work.

---

## 12. Honest limitations (state these openly)

1. **The local model cannot yet read a real answer booklet.** 47% character
   error on a real page. It correctly reports ~53% confidence and flags the page
   for manual transcription, but it is not usable for real marking yet.
2. **The Gemini engine is built but unmeasured.** No API key has been available,
   so it has only been tested against simulated API responses. No accuracy claim
   can be made for it yet.
3. **Confidence is measured but not calibrated.** A confidently misread word
   still scores high. Closing that gap is Phase 3.
4. **Line segmentation assumes roughly horizontal writing.** Heavy skew,
   two-column layouts, margin notes and diagrams are not handled. A stacked
   fraction is read as separate lines.
5. **Ink isolation assumes blue or black student ink.** Red and orange are
   treated as printed form colour and examiner marks, and removed.
6. **No question segmentation.** A page holding answers to three questions
   produces one transcription, not three. Splitting a booklet by question is
   explicitly out of scope.
7. **No authentication yet.** Roles exist in the data model; enforcement is Phase 2.
8. **SQLite, not PostgreSQL, for now** — so Phase 1 runs with no external
   services. Migrations and the move are Phase 2.

**Privacy:** answer images are treated as sensitive. `data/storage/`, the
database and `.env` are git-ignored and were verified absent from the public
repository. Nothing is sent to any external service unless the Gemini engine is
explicitly enabled.

---

## 13. Risks and how they are handled

| Risk | Mitigation |
|---|---|
| **Handwriting recognition underperforms** — the single largest technical risk | Benchmarked in week one, not the last. The corrected-transcription path means poor recognition can never block the other three workstreams: it becomes a documented finding, not a project failure |
| **Confidence turns out to be poorly calibrated** | A legitimate result, provided we measure it. The composite design gives weights to tune; if it stays uncalibrated we report that honestly and raise the routing thresholds |
| **Ground-truth labelling is slow and tedious** | Budgeted explicitly and started early. ~50 answers marked independently by two people |
| **Free-tier rate limits, cost, non-determinism** | Evaluations cached by content hash; temperature fixed at 0; mock provider for all routine development and testing; batch runs scheduled overnight |
| **Four people, one codebase** | Frozen contracts, file-level ownership, mock providers. Changes to shared schemas or database models require a second reviewer |
| **Scope creep** | An explicit exclusion list, revisited at every phase exit |

### Explicitly out of scope

Training a language model from scratch · full answer-booklet segmentation ·
multiple engineering branches · numerical and proof-based marking · diagram
understanding · medical answer evaluation · institution-scale deployment · fully
autonomous grading · multi-tenant isolation · self-hosted model serving.

---

## 14. Suggested slide outline (~12–14 slides)

1. **Title** — EvalNova: confidence-aware, rubric-driven evaluation of handwritten exam answers
2. **The problem** — marking is slow and inconsistent; "just ask an LLM" produces an unaccountable number
3. **What makes this different** — the evidence chain from handwriting to final score; the two architectural principles
4. **System architecture** — the layer diagram and the two import rules; the replaceability boundary
5. **The four workstreams** — who owns what, why they run in parallel
6. **Part 1 pipeline** — the 13-stage diagram; emphasise ruled-line removal and cover-page detection
7. **Live demo / screenshots** — upload → cleaned page with detected lines → transcription + confidence + trust band
8. **Confidence: measured, not asked for** — the formula, the four trust bands, and the caveat about calibration
9. **Results** — the before/after table; the rejected experiments (int8, model size)
10. **What we built vs what is contracted** — 14 endpoints live, 5 returning 501 by design, 96 tests
11. **The road ahead** — the nine-step target pipeline and the per-member remaining work
12. **Measurement plan** — what we will report and against what ground truth
13. **Honest limitations** — the local model's 47% error, uncalibrated confidence, unverified cloud engine
14. **Phase plan and timeline**

### Numbers worth putting on a slide

- 125% → 47% character error on a real answer page; 64 s → 7 s
- 0% character error on all four synthetic samples, ~4 s per page
- 96 tests, 15 tables, 14 live endpoints, 5 contracted endpoints
- 53% confidence on the page it cannot read — the system knowing its own limits

### Phrases that land well with a review panel

- "We did not ask the model how confident it felt — that number is unreliable.
  This is computed from the decoder's own token probabilities."
- "A recogniser handed a ruled line will confidently invent a sentence for it.
  So the first job is to find the student's writing and nothing else."
- "The arithmetic never depends on the model. Python sums the marks."
- "The AI's original result is never overwritten. That separation is what makes
  the validation study possible."
- "These thresholds are starting hypotheses, not established values."
