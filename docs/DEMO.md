# Demonstrating EvalNova Core

*What to run, in what order, and what to say about each number on screen.*

---

## Before the room fills

Three things, in this order. The third is the one people forget.

```powershell
# 1 - is the key working, and which models can it actually reach?
.venv\Scripts\python scripts\check_gemini.py --list

# 2 - does the whole pipeline still run, end to end, on a real booklet?
.venv\Scripts\python scripts\demo_end_to_end.py

# 3 - start the application
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

**Why step 1 matters.** The thing that breaks a demo is not the code; it is
Google returning `503 This model is currently experiencing high demand` on a
popular model. `--list` calls each configured model and reports which answer. If
the preferred one is down, the application already falls back automatically, but
knowing beforehand is the difference between a pause and a surprise.

Then open **http://localhost:5173**. The badge in the header must say
**Model ready**. If it says *Mock engine*, `.env` is missing the API key and
every number on screen will be the keyword baseline's.

---

## The five-minute run-through

### 1 · Questions & rubrics — *"what are we marking against?"*

Open **Questions & rubrics** first, before anything is marked. It makes the rest
of the demo legible: the audience sees the standard before they see a score.

Expand **Q5 (pointers)**. Point at one criterion and say:

> Each criterion says what it is *testing*, not what words to look for. "Must
> convey: stores an address, of another variable." A student who writes that in
> their own words still scores. That is why this is a rubric and not a keyword
> search.

Then point at the green banner:

> **Rubrics are fit to mark with — 6 questions, 22 criteria, 30 marks.**

Say why it is there:

> If a rubric's criteria summed to 4.5 out of 5, every student would be silently
> capped at 90% and every score would look completely reasonable. The system
> refuses to mark until that is fixed.

That one sentence usually earns more credit than anything else on the screen,
because it is a failure the audience can immediately imagine shipping.

### 2 · Transcribe — *"what did the student write?"*

Upload `data/exam/scans/writer_1.pdf`. It quotes the expected wait before
starting — about 17 seconds a page.

While it runs, the segmentation overlay and the per-line confidence are the
things to talk about. When it finishes:

> 3 pages, 54 lines, **98.9% confidence**.

Have the measured number ready, because someone will ask how you know:

> On eight real pages with hand-written reference transcripts, the character
> error rate is **2.9%**. The local model we started with scored 59.7% on the
> same pages. That is a twenty-fold reduction, and it is why the project uses a
> cloud vision model and says so plainly in the README.

### 3 · Evaluation — *the split, then the marks*

Pick the booklet. **Do not skip the segmentation screen.** It shows which lines
answer which question, and it is the best part of the demo:

> Q1 on page 1, Q2 running across pages 1 and 2, Q4 on page 2, Q5 and Q6 on
> page 3 — each located by the student's own numbering. **Q3 was not attempted,
> and the system says so rather than marking an empty answer.**

Say why it is a separate step:

> If this split were wrong — if Q4's answer were filed under Q5 — every mark
> below would be wrong and every confidence number would still be high, because
> the marker would have done its job correctly on the wrong text. This is the
> cheap place to catch that, so we show it to a human first.

Now press **Mark this booklet**. About 30 seconds for five questions.

Open **Q5**, which scores **1 out of 5**, and read the breakdown aloud:

> The student wrote `int x = 7; int *p = &x; printf("%d", *p);` and nothing else.
> Criterion 4 wants a valid three-line example — satisfied, one mark. Criteria 1
> to 3 want the pointer, `&` and `*` explained in words. The student never
> explained them, so no marks, and the quoted evidence shows exactly why.

Then **Q6**, which scores **2 out of 5** — the sharpest moment available:

> The student wrote `int max = 0;`. The rubric lists exactly that as a known
> mistake, because it fails for an all-negative array. And the loop is
> `for (j = 0; j > n; j++)`, which never executes. The system caught both.

Finish on the confidence panel:

> Four signals, each measured rather than asked for. They are combined as a
> geometric mean, not an average, so one bad signal drags the whole number down
> instead of being hidden behind three good ones — an answer marked perfectly
> from an unreadable transcription should not score well, and with an average it
> would.

### 4 · Examiner review — *"a human still decides"*

Accept one score, change another. Then say the thing that matters:

> The correction is stored as a **new record beside the machine's**, never over
> it. That is deliberate: it is the only way to measure afterwards how often the
> machine and the examiner agreed. A system that overwrote the machine score to
> show the corrected one would destroy its own evidence the first time it was
> used.

### 5 · Validation — *"did it work?"*

Open it last, and be straightforward about the state of it:

> This is computed from the records the system wrote while we were using it, not
> from a separate study. Right now it says the sample is too small to mean
> anything, and that is the honest answer — anything under about twenty reviewed
> answers is noise.
>
> The table that matters is the modification rate per confidence band. The claim
> is that a high-confidence score rarely needs changing and a low-confidence one
> often does. **If those rates come out flat, our confidence number is not
> telling an examiner anything useful, and this screen is where that would show
> up.** We built the thing that can prove us wrong.

---

## Questions that will be asked

**"Is this just ChatGPT marking the paper?"**

No, and the difference is the point. The model is given the question, the rubric
and the student's text, and returns one verdict per criterion with a quotation
from the answer. **It is never shown what any criterion is worth and never adds
anything up.** The marks are computed in Python from those verdicts. Hand it the
same verdicts twice and you get the same score twice. Ask a model for a score
out of five and you get a plausible number with decorative reasoning.

**"What if it makes up the quotation?"**

Measured, not hoped for. Every quotation is checked against the transcription;
one that is not there is flagged in the interface and drags the *grounding*
signal — and so the confidence — down. See the `grounding` row on any answer.

**"What stops it being confidently wrong?"**

Nothing, entirely — which is why no score is auto-accepted. The top band is
labelled an auto-accept *candidate* and still routes to a human, because the
false-auto-accept rate has not been measured yet. That is stated in the README
and in `GET /api/v1/roadmap` under `not_yet_validated`.

**"Student data goes to Google?"**

Yes, when the Gemini engine is selected, and that is a configuration choice
rather than a default buried in code — `EVALNOVA_OCR_PROVIDER` in `.env`. Page
images and transcribed text are sent; mark values are not. The local TrOCR
engine sends nothing off the machine and scores 59.7% character error rate
instead of 2.9%, and that trade is the institution's to make, not ours.

**"Why is marking slower than transcription?"**

Each answer is read **twice, independently**, because that is how the agreement
signal is measured. One reading of the same thing measures nothing about
agreement. `EVALNOVA_EVALUATION_SAMPLES=1` halves the cost, and the result then
records agreement as *unmeasured* rather than quietly assuming it.

---

## If something fails mid-demo

| Symptom | Cause | What to do |
|---|---|---|
| Header says *Mock engine* | no API key in `.env` | the demo still runs; say the numbers are the keyword baseline's |
| "experiencing high demand" | Google overloaded that model | it falls back automatically; wait, or set `EVALNOVA_GEMINI_MODEL` to one `--list` reported as working |
| "exceeded your current quota" | pro model on a free tier | use `gemini-3.1-flash-lite` or `gemini-3-flash-preview` |
| A question marks as 0 with *no answer located* | the student did not number it | open the segmentation screen and show the unassigned text — this is the system being honest |
| Marking refuses with a rubric error | criteria do not sum to the question | **this is the feature.** Open Questions & rubrics and show the banner |

Nothing in that table needs hiding. A demo where the failure modes are
explainable is stronger than one where everything happens to work.

---

## Speed, and the thing that actually limits it

**The binding constraint is the free tier's quota, not the code.** Measured
from a 429 body on this key:

```
Quota exceeded for metric: generate_content_free_tier_requests,
limit: 15, model: gemini-3.1-flash-lite
```

Fifteen requests per minute, shared by transcription and marking. What one
three-page booklet needs:

| Work | Requests |
|---|---|
| 3 pages × 2 readings (the transcription-confidence signal) | 6 |
| 5 attempted questions × 2 samples (the agreement signal) | 10 |
| **Total** | **16** |

Sixteen against a limit of fifteen, so a single booklet exceeds the minute's
allowance on its own. Before this was understood, identical runs took 16s,
97s and 200s depending on where the rolling window happened to be — the
variance was the quota, not the model.

Three things were done about it:

1. **Pages and questions are now sent concurrently** rather than one at a
   time. The model sees identical bytes, so the marks are unchanged.
2. **A shared request limiter** holds the application to the quota instead of
   being refused and retrying into a limit that has not reset. Requests queue;
   they no longer storm.
3. **An overloaded model is waited out, not switched away from.** The
   preferred model answers in ~0.8s and the fallbacks in 2–9s, so abandoning
   the primary on its first 503 moved a whole run onto a model eleven times
   slower. Measured: it made the run four times longer.

### Measured, same booklet, same marks

| Mode | Wall clock | Marks | Confidence |
|---|---|---|---|
| Default (2 readings each) | **139s** | 15.5/30 | measured; 2 of 5 routed to review |
| `EVALNOVA_*_SAMPLES=1` | **59s** | 15.5/30 | **unmeasured**; all 5 routed to review |

The scores are identical. What the fast mode costs is the *confidence
measurement* — transcription confidence falls to 49.9% and every question
lands in "Detailed verification", which is the system correctly reporting
that it does not know how sure it is. That is the honest trade and it is a
setting, not a default.

**There is no way to get both on this tier.** The second reading is the only
source of transcription confidence: no flash model exposes logprobs
(`Logprobs is not enabled for this model` on all four tested), so confidence
cannot come free from a single call. A paid tier raises the ceiling to
thousands of requests per minute, and the concurrency added here is what
would then pay off.

### Before a demo

```powershell
.venv\Scripts\python scripts\check_gemini.py --list
```

If you need the run to be quick rather than defensible — a five-minute slot,
a flaky connection — set both sample counts to 1 in `.env` and **say on the
slide that confidence is unmeasured in that mode.** Reporting a fast run's
scores while implying the confidence numbers mean something would be the one
dishonest thing available here.
