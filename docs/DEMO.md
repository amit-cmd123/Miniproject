# Mid-semester demonstration runbook

Roughly 6–8 minutes of screen time. The point to land is not "we built an
uploader" — it is **that the architecture is right and the confidence number
means something.**

---

## Before you walk in

1. Start the backend **a minute early.** It loads the handwriting model in a
   background thread; the badge in the top right reads *Model loading* until it
   is ready, then *Model ready*. Do not demo before it flips.
   If you are using Gemini, run `.venv\Scripts\python scripts\check_gemini.py`
   first — on the venue's network — so a bad key or quota shows up before you
   are on stage.
2. Start the frontend. Note the URL Vite prints — if port 5173 is taken it will
   use 5174.
3. Have these open in tabs:
   - the interface
   - <http://localhost:8000/docs> (the API surface)
   - `data/samples/sample_answer_normal.png` in an image viewer
4. Regenerate the samples if `data/samples/` is empty:
   `python scripts/generate_sample_answer.py --all`
5. If you are showing a real PDF booklet, transcribe it **once before the
   session**. The result stays in the answer library, and you will know the page
   count, the timing and the quality before you are standing in front of anyone.

**Fallback:** if the model will not load on the day, set
`EVALNOVA_OCR_PROVIDER=mock` in `.env` and restart. Everything still runs end to
end, and the header badge says *Mock engine* rather than pretending. Say so out
loud — a pipeline that runs on a swapped-out engine is a demonstration that the
provider abstraction works, which is one of the design claims.

---

## The run

### 1 · Frame it (45 s)

> "EvalNova evaluates handwritten exam answers. The part that matters is not
> that AI can read handwriting — it is that every mark has to be traceable back
> to the handwriting that earned it. So we built the pipeline that produces
> evidence, not just an answer."

Point at the navigation: four sections, four team members, one per workstream.
Part 1 is live; the others are prototypes with their contracts already fixed.

### 2 · Transcribe (2 min)

Drop in `sample_answer_normal.png`. It lands in about 6 seconds, word-perfect,
at **~99% · Reliable**.

Then drop in a **real answer booklet PDF** — this is the part that shows the
engineering. The interface reports the page count and quotes the wait; pick
pages 1-3. While it runs, explain the stages on screen.

- **Page 1 is the printed cover.** It is not read, and its warning says why.
  Point out that the old pipeline spent 100 seconds turning the cover into
  invented sentences.
- **On an answer page, open *Detected lines*.** It shows the page as the
  recogniser sees it: the ruled lines, the margin, the examiner's red marks and
  the writing showing through from the back of the sheet are all gone. Only the
  student's ink is left, with one box per line.

> "A real answer sheet is ruled, printed in colour, written on both sides and
> marked in red. To a naive threshold all of that is ink, and a recogniser
> handed a ruled line confidently invents a sentence for it. So the first job
> is to find the student's writing and nothing else."

### 3 · The point of the whole demo (2 min) ← *don't rush this*

Look at the confidence on the real page.

**With Gemini:** run this page through `scripts/check_gemini.py` beforehand and
know what it produces before you show it. Point at the lines where confidence
is lower and check whether those are the ones it misread.

**With the local engine:** confidence falls to about 50%, and the page lands in
*Manual transcription*. Say so directly:

> "The local model was trained on Western cursive and cannot read this page
> well — and it knows it. We did not ask the model how confident it felt; this
> comes from its own token probabilities. It is telling the examiner to check
> this page by hand, which is exactly the right answer."

Then immediately give the caveat, because someone on the panel will otherwise
ask it:

> "This is a real measurement, but it is not yet calibrated. A confidently
> misread word still scores high. Proving the relationship between stated
> confidence and actual correctness needs a ground-truth set — that is Phase 3,
> and until then we don't let any threshold decide anything on its own."

### 4 · Evidence and correction (1.5 min)

- Switch the image tab to **Detected lines** — the boxes the recogniser was
  given. *"If a box spans two lines, segmentation is the problem, not
  recognition. We can tell those apart."*
- Edit a word in the transcription and save. *"The machine output is kept
  underneath. A corrected answer stays measurable — and an examiner doing
  ordinary work is generating ground-truth data for free."*
- Paste the contents of `sample_answer_normal.txt` into **Measure accuracy**
  and hit Measure. On the sample it is **0% character and word error rate**.

> "We can put a number on how well it reads, today."

If someone asks why word error rate is usually several times character error
rate: one wrong character ruins the whole word. Both are reported because they
answer different questions — CER tells you how well the model reads strokes,
WER tells you how much of the answer survives intact for a marker to read.

Measured with the local engine (`trocr-small-handwritten`, i9 laptop CPU):

| Page | Time | CER before | CER now | Confidence now |
|---|---|---|---|---|
| synthetic clean / normal / messy / poor | ~4 s each | 0.9–3.6% | **0%** | ~98% |
| real CN answer page (ruled, maths) | ~7 s (was 64 s) | 125% | 47% | ~53% |

The honest point is the last row. Cleaning cut the error on a real page by more
than half and the time by ~90%, but the local model is still not good enough
for real booklets — which is why the cloud engine exists and why confidence has
to be measured rather than trusted.

### 5 · What comes next (1.5 min)

Click through **Questions & rubrics → Evaluation → Examiner review →
Validation.** Each shows the real intended layout, the specific work, its
owner, and the endpoints it will call.

Then show `/docs` and hit `POST /api/v1/evaluations`:

```json
{ "workstream": "Part 3",
  "message": "Rubric-driven marking with composite confidence is Part 3 of the plan and is not built yet." }
```

> "Those endpoints are registered now and return 501 naming the workstream that
> owns them. The contracts are fixed before the code exists, which is how four
> people work in parallel without blocking each other."

### 6 · Close (30 s)

> "Part 1 is done and measured. Parts 2 and 3 have their contracts and their
> prototypes. The architecture keeps the model replaceable — the recognition
> engine is behind one interface, and we swap it with a config line."

---

## Questions to expect

**"Is 99% accuracy?"**
No — it is the model's certainty, not its correctness. Error rate is measured
separately against a known transcription; those are different numbers
measuring different things, and closing the gap between them is Phase 3.

**"Why not just use Google Vision / an existing OCR API?"**
We do: Gemini sits behind the same provider interface as the local model, and
switching is one line of configuration. What we cannot outsource is the
rubric, the confidence composition, and the audit trail.

**"Isn't sending answer sheets to Google a privacy problem?"**
Yes, and that is why it is off by default. The local engine keeps everything
on the machine; the cloud engine is an explicit choice, stated in the header
badge and recorded on every result.

**"Will it work on real student handwriting?"**
The local model, no — you just saw it score 47% character error on a real page
and flag itself for manual transcription. Measuring the cloud model against it
on our own collected samples, and fine-tuning the local one in Colab, is Part
1's remaining work.

**"What if the OCR is bad?"**
Then Parts 2–4 still work. Evaluation reads `effective_text`, which prefers a
human correction. That also gives us a clean experiment: marks on raw
recognition versus marks on corrected text, which isolates how much a
recognition error actually costs in marks.

**"Why SQLite and not PostgreSQL?"**
So Phase 1 runs with no external services. The models are SQLAlchemy; switching
is a connection string. Migrations and the move are Phase 2.
