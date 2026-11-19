# EvalNova Core

Confidence-aware, rubric-driven evaluation of handwritten examination answers.

**Status: all four parts are built and run end to end.** A scanned booklet goes
in; per-question marks, a criterion-by-criterion justification, a measured
confidence and a review decision come out.

### Measured, not claimed

On the eight real handwritten booklet pages in `data/exam/pages`, transcribed
against hand-written reference transcripts:

| | Local TrOCR | **Gemini (current)** |
|---|---|---|
| Character error rate | 59.7% | **2.9%** |
| Line recall | 131% (over-segmenting) | **101.7%** |
| Seconds per page | ~10 | ~17 |

Reproduce with `python scripts/benchmark.py --dataset data/exam/pages --provider gemini`.

**What is *not* yet validated: the confidence calibration.** Every score carries
a confidence built from four measured signals, but the weights combining them
were chosen by hand. Whether "90% confident" really means a 10% chance of
examiner disagreement needs reviewed answers to establish, and
`GET /api/v1/analytics/summary` is the endpoint that will say so. Until then the
top band is labelled an auto-accept *candidate* and still routes to a human.

---

## The whole pipeline in one command

```bash
.venv\Scripts\python scripts\demo_end_to_end.py
```

Takes a real booklet from `data/exam/scans/`, transcribes it, splits it per
question, marks it against the rubric, shows the confidence breakdown and the
review queue, and prints the validation metrics. Nothing is mocked.

---

## What works today

### Part 1 — reading the handwriting

Upload a photograph, a scan, or a **multi-page PDF answer booklet**, and the
system will:

1. Clean the image — flatten uneven lighting, correct rotation, and isolate the
   student's ink: printed ruling and margin lines, coloured print, the
   examiner's red marks and writing showing through from the back of the sheet
   are all removed
2. Recognise a printed cover or form page and skip it, saying so
3. Split the page into individual handwriting lines
4. Read the handwriting — locally with TrOCR, or with a Gemini vision model
   when a key is configured (see *Recognition engines*)
5. Report a **confidence score measured from the model's behaviour** (token
   probabilities, or agreement between two independent readings), not from
   asking the model how sure it feels
6. Place the result in one of four trust bands
7. Let a human correct the text **without destroying the machine output**, so
   character error rate stays measurable
8. Measure character and word error rate against a known transcription

For a PDF, each page is rasterised and put through that same pipeline as its own
answer, with its own confidence. Pages share a `document_ref` so the booklet
stays together, and a page that fails is reported in place rather than
discarding the rest.

### Part 2 — what a correct answer must contain

A paper is loaded from one JSON file (`data/exam/seed_exam.json`) as questions,
answer keys and rubrics. Each rubric is a list of criteria, and each criterion
says what it is testing, what counts as an acceptable alternative, whether it
allows partial credit, and what it is worth.

`GET /exams/{id}/validate` refuses a rubric that is not fit to mark with. The
check that matters: **criteria must sum to the question's marks.** A rubric
summing to 4.5 out of 5 caps every student at 90% and produces entirely
plausible-looking scores — invisible in the output, obvious here. Marking is
blocked until it is fixed.

Rubrics are versioned. Editing one writes a new version and retires the old;
evaluations record the version they used, so a past score stays explainable.

### Part 3 — marking, and knowing when not to trust it

1. The booklet's transcription is **split per question** — by the student's own
   numbering where it exists (exact, free, and shown to the user), by a model
   only when that fails
2. Each answer is judged **criterion by criterion, twice, independently**
3. **The model never sees a mark value and never adds anything up.** It returns
   a verdict and a quotation per criterion; the marks are computed in Python.
   Same verdicts, same score, every time
4. Every verdict must **quote the student's own words**, and the quotation is
   checked against the transcription — a quote that is not there is flagged and
   the marks it supports are labelled unverified
5. A **composite confidence** is computed from four measured signals and the
   answer is routed accordingly

### Part 4 — the examiner, and the measurement

An examiner accepts or changes each score in one click. The decision is written
as a **new row beside the machine's, never over it**, so machine–examiner
agreement stays computable — which makes routine marking into calibration data.
`GET /analytics/summary` reports agreement, mean absolute error, and the
modification rate per confidence band.

---

## Setup

Requires Python 3.10+ and Node 18+.

```bash
# Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

The first transcription downloads the handwriting model (~250 MB) from Hugging
Face. To avoid that wait during a demo, start the backend a minute early — it
warms the model up in the background at startup and the header badge turns
from *Model loading* to *Model ready*.

## Recognition engines

| `EVALNOVA_OCR_PROVIDER` | Reads | Speed (i9 laptop CPU) | Leaves the machine? |
|---|---|---|---|
| `trocr` (default) | one segmented line at a time | ~6 s per page | No |
| `gemini` | the whole page at once | one request per page | **Yes — page images go to Google** |
| `mock` | nothing; generated text | instant | No |

TrOCR was trained on Western English cursive and reads poorly on real answer
booklets: stacked fractions, exponents, Indian handwriting. A vision-language
model reads the whole page with its layout and is expected to do much better;
the Gemini path has not yet been measured against our reference pages, so do
that with `check_gemini.py` before relying on it. To use it:

1. Get a key at <https://aistudio.google.com/apikey>
2. Add to `.env`: `EVALNOVA_GEMINI_API_KEY=...` and `EVALNOVA_OCR_PROVIDER=gemini`
3. Check it: `.venv\Scripts\python scripts\check_gemini.py`
4. Restart the backend

If a Gemini request fails (no network, quota, bad key), that page is read by
the local engine instead and the result carries a warning saying so. On
Google's free tier, submitted content may be used to improve Google's
products — weigh that before sending real students' answer sheets.

### Switching engine per request

`EVALNOVA_OCR_PROVIDER` sets the default. It is not the only way to choose:
every endpoint that reads handwriting or awards a mark accepts `?engine=`, and
the interface has a Gemini switch on the Transcribe and Evaluation screens
that sends it.

```
?engine=gemini   Google's model
?engine=local    TrOCR for reading, the rubric concept matcher for marking
?engine=auto     whatever .env configures (the default when omitted)
```

`GET /api/v1/engines` reports which are available, so the switch can be shown
as disabled with a reason rather than failing when it is flipped.

One rule makes this safe to rely on: **an explicitly requested engine is never
substituted.** Asking for `gemini` with no key configured returns 503 with the
reason; it does not quietly read the page with TrOCR. The provider's name is
written onto every stored transcription and every stored score, so a silent
substitution would make the record claim something that did not happen. The
*configured default* still falls back, because that is a deployment preference
rather than somebody's stated intent.

With the switch off, marking runs on the concept matcher in
`providers/evaluation/mock_evaluator.py` — it walks the same criteria and
awards the same partial credit, but decides by concept overlap rather than by
reading. Every score it produces is flagged `is_mock` and carries a warning
saying it is a baseline, not a result to report.

## Running

Two terminals:

```bash
# Terminal 1 — API on :8000
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — interface on :5173
cd frontend
npm run dev
```

Open the URL Vite prints. Interactive API docs are at
<http://localhost:8000/docs>.

On Windows, `scripts\start.ps1` launches both in one go.

## Sample data

```bash
python scripts/generate_sample_answer.py --all
```

Writes four synthetic handwritten sheets to `data/samples/` at descending
quality (`clean`, `normal`, `messy`, `poor`), each with a `.txt` file holding
the true transcription for measuring error rate. These are for exercising the
pipeline — they are **not** a substitute for the real handwriting samples the
project will be measured on.

## Tests

```bash
cd backend
python -m unittest discover -s tests -t .
```

96 tests, no model download and no network required — they run against the
mock engine, and Gemini calls are replaced with canned API replies.

---

## How it is put together

```
frontend/               React + TypeScript + Tailwind
    │  REST, proxied through Vite so there is no CORS in development
backend/app/
    api/v1/             HTTP surface only — no business logic
    services/           preprocessing, transcription, confidence, audit
    providers/ocr/      TrOCR | Gemini | mock  ← the replaceability boundary
    db/                 SQLAlchemy models for the whole data model
    core/               config and thresholds
scripts/                sample generation and start-up helpers
```

Two rules hold the structure together, and both are easy to check by reading
imports:

- **Nothing above `providers/` imports torch, transformers, or any vendor SDK.**
- **Nothing in `services/` imports from `api/`.**

That is what makes the recognition engine swappable — for a cloud API, a
fine-tuned checkpoint, or the mock — without touching application code.

### Where the confidence number comes from

Per line, TrOCR's decoder gives a probability for each token it chose. The line
score is the geometric mean of those:

```
line_confidence = exp( mean( log P(token_i) ) )
```

The page score weights each line by its length and then applies a penalty for a
soft image:

```
page = (length-weighted mean of line confidences) × sharpness_penalty
```

Long hesitant lines therefore outweigh short confident ones, and a blurred
photograph drags the whole page down even when the decoder sounds certain.

With Gemini the line score is the same geometric mean when the API returns
token log-probabilities. When it does not, the page is read a second time with
sampling on, and each line scores by how closely the two readings agree. The
method used is stored with every result as `confidence_method`.

**This is a real measurement, but it is not yet a calibrated probability of
being correct.** A confidently misread word still scores high. Measuring that
gap — the calibration curve and the false-auto-accept rate — is Phase 3 work,
and until it is done no threshold here should be trusted to decide anything on
its own.

### Trust bands

| Confidence | Band | Meaning |
|---|---|---|
| ≥ 95% | Reliable | May proceed to evaluation without routine checking |
| 85–95% | Spot check | Largely trustworthy; a quick read-through is advised |
| 70–85% | Verify | A human should confirm before marks depend on it |
| < 70% | Manual transcription | Too unreliable to evaluate; correct by hand |

These are **starting hypotheses**, not established values. They live in
`backend/app/core/thresholds.py` and are served over the API at
`GET /api/v1/config/thresholds`, so the interface never hard-codes them and
Phase 3 can move them based on measurement.

---

## API

Implemented:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/documents/inspect` | Page count and a time estimate for a PDF |
| `POST` | `/api/v1/documents/transcribe` | Read a PDF booklet, optionally a page range |
| `GET` | `/api/v1/documents/{ref}` | Every page of one uploaded document |
| `POST` | `/api/v1/answers` | Register an answer image |
| `POST` | `/api/v1/answers/transcribe` | Upload and read in one call |
| `POST` | `/api/v1/answers/{id}/ocr` | Read a registered answer |
| `GET` | `/api/v1/answers` | Everything transcribed so far |
| `GET` | `/api/v1/answers/{id}/image` | The original handwriting |
| `GET` | `/api/v1/answers/{id}/segmentation` | The page with detected line boxes |
| `PATCH` | `/api/v1/answers/{id}/ocr/verify` | Save a human correction |
| `POST` | `/api/v1/answers/{id}/ocr/accuracy` | Character and word error rate |
| `GET` | `/api/v1/ocr/provider` | Which engine is loaded, and is it ready |
| `GET` | `/api/v1/engines` | Both engines, and whether each can run now |
| `GET` | `/api/v1/config/thresholds` | The trust bands |
| `GET` | `/api/v1/roadmap` | What is built, and what is proven |

**Part 2 — questions and rubrics**

A paper can be typed in by hand, imported as seed JSON, or read out
of the Word or PDF file it already exists in — `POST /api/v1/exams/parse-document`
returns a *proposal* and saves nothing; the examiner approves it and it
goes in through `POST /api/v1/exams/import` like any other paper.
`scripts/make_sample_rubric.py` writes `data/exam/sample_rubric.docx` to
try it against.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/exams/seed` | Load the bundled paper from disk (idempotent) |
| `POST` | `/api/v1/exams` | Define a paper, keys and rubrics in one request |
| `GET` | `/api/v1/exams/{id}` | A paper with every question and rubric |
| `GET` | `/api/v1/exams/{id}/validate` | **Is every rubric fit to mark with?** |
| `GET` | `/api/v1/questions` | The question bank |
| `GET` | `/api/v1/questions/{id}/rubric` | The active rubric |
| `PUT` | `/api/v1/questions/{id}/rubric` | Write a new rubric version |

**Part 3 — marking**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/documents/{ref}/segmentation` | Which text answers which question, before marking |
| `POST` | `/api/v1/documents/evaluate` | Mark a whole transcribed booklet |
| `POST` | `/api/v1/evaluations` | Mark one answer |
| `GET` | `/api/v1/evaluations` | The marking queue (`?needs_review`, `?unreviewed`) |
| `GET` | `/api/v1/evaluations/{id}` | One score with its full derivation |
| `GET` | `/api/v1/evaluations/provider` | Which marker is configured |
| `GET` | `/api/v1/config/confidence-weights` | The confidence signals and their weights |

**Part 4 — review and validation**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/reviews` | Accept or change a score (appended, never overwritten) |
| `GET` | `/api/v1/evaluations/{id}/reviews` | Every human decision on one score |
| `GET` | `/api/v1/analytics/summary` | Agreement, error, and modification rate per band |

Registered but not implemented — they return `501` with the owning workstream:
`/questions`, `/questions/{id}/rubric`, `/evaluations`, `/reviews`,
`/analytics/summary`.

---

## Configuration

Copy `.env.example` to `.env`. Nothing is hard-coded in business logic.

| Variable | Default | Notes |
|---|---|---|
| `EVALNOVA_OCR_PROVIDER` | `trocr` | `gemini`, `trocr` or `mock`. Use `gemini` — it is 20× more accurate on real pages |
| `EVALNOVA_OCR_MODEL_NAME` | `microsoft/trocr-small-handwritten` | `-base-` is ~10× slower for no measurable gain on cleaned pages |
| `EVALNOVA_GEMINI_API_KEY` | — | also read from `GEMINI_API_KEY` |
| `EVALNOVA_GEMINI_MODEL` | `gemini-3.5-flash` | any Gemini model your key can use |
| `EVALNOVA_GEMINI_FALLBACK_MODELS` | — | comma-separated; tried in order when the chosen model returns 503 |
| `EVALNOVA_EVALUATION_PROVIDER` | `mock` | `gemini` for real marking; `mock` is the keyword baseline |
| `EVALNOVA_EVALUATION_MODEL` | — | blank uses `EVALNOVA_GEMINI_MODEL` |
| `EVALNOVA_EVALUATION_SAMPLES` | `2` | independent readings per answer. `1` halves the cost and loses the agreement signal |
| `EVALNOVA_OCR_DEVICE` | `auto` | `auto` picks CUDA when available |
| `EVALNOVA_DATABASE_URL` | SQLite in `data/` | Point at PostgreSQL to switch |

### Which Gemini model to use

Availability, not accuracy, is the practical constraint. Google returns
`503 experiencing high demand` on popular models often enough to break a run,
and pro models return `429` on a free tier. Find out what a key can actually
reach:

```bash
.venv\Scripts\python scripts\check_gemini.py --list
```

It lists every model the key can see, then calls the configured ones to show
which really answer. Verified working as of November 2026:
`gemini-3.1-flash-lite`, `gemini-3-flash-preview`. The code walks
`EVALNOVA_GEMINI_FALLBACK_MODELS` on a 503 and records which model actually
served each result.

### Why SQLite rather than PostgreSQL right now

The plan specifies PostgreSQL, and the models are written against SQLAlchemy so
switching is a connection-string change. SQLite is the default only so that the
project runs with no external services during Phase 1. Alembic migrations and
the move to PostgreSQL are Phase 2, before the schema has to survive real data.

### Why `transformers` is pinned below 5.0

The 5.x line removed the slow-to-fast tokenizer conversion that the TrOCR
checkpoints depend on, and `microsoft/trocr-base-handwritten` fails to load
there. Pinned in `requirements.txt` with this reason recorded.

---

## Known limits

Honest list, because the next phases depend on knowing these:

- **The local engine cannot really read a real answer booklet.** On a
  photographed CN mid-sem page (ruled paper, stacked fractions, exponents) it
  scores ~47% character error rate — down from 125% before ink isolation, but
  still not usable, and its confidence correctly falls to ~53%. On the
  synthetic samples it is word-perfect. TrOCR was trained on the IAM corpus:
  Western cursive, everyday English. Gemini, or fine-tuning on our own samples
  in Colab, is the answer.
- **Line segmentation assumes roughly horizontal writing.** Heavy skew,
  two-column layouts, margin notes and diagrams are not handled. A stacked
  fraction is read as separate lines.
- **Ink isolation assumes the student writes in blue or black.** Red and orange
  are treated as examiner marks and printed form colour, and removed.
- **A PDF page is read as one continuous block of writing.** There is no
  question segmentation yet, so a page holding answers to three questions
  produces one transcription, not three. Splitting a booklet by question is
  explicitly out of scope for the mini-project.
- **Confidence is measured but not calibrated.** See above.
- **There is no authentication yet.** Roles exist in the data model; enforcing
  them is Phase 2.
- Answer images are treated as sensitive: `data/storage/` is git-ignored, and
  nothing is sent to any external service unless `EVALNOVA_OCR_PROVIDER=gemini`
  is set.

---

## Where the other parts plug in

| Part | Owner | Consumes | Produces |
|---|---|---|---|
| 1 · Handwriting & OCR | Member 1 | answer image | text + confidence ✅ |
| 2 · Questions & rubrics | Member 2 | — | question, key, criteria |
| 3 · Evaluation & confidence | Member 3 | Part 1 text + Part 2 rubric | marks, reasons, confidence |
| 4 · Examiner app & validation | Member 4 | Part 3 result | final score, metrics |

Part 3 reads `effective_text`, which returns the human correction when one
exists and the machine output otherwise. That single field is what stops weak
recognition from blocking the rest of the project — and it makes the
*raw versus corrected* experiment possible, which isolates how many marks a
recognition error actually costs.
