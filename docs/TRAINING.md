# Improving recognition — the measurement loop

*How to make the recogniser better and prove that you did.*

---

## Settled: the cloud model won, and by how much

Measured on the eight real booklet pages in `data/exam/pages`, against
hand-written reference transcripts:

| Engine | CER | Line recall | s/page |
|---|---|---|---|
| `trocr-small-handwritten`, local | 59.7% | 131% (over-segmenting) | ~10 |
| **Gemini, page-level** | **2.9%** | **101.7%** | ~17 |

```bash
python scripts/benchmark.py --dataset data/exam/pages --provider gemini --tag gemini-real
```

**The fine-tuning work below is therefore closed, not paused.** It was chasing a
problem the cloud model does not have, and the honest reading of the numbers is
that no amount of fine-tuning a 60-million-parameter line recogniser on a few
thousand synthetic lines was going to close a twenty-fold gap.

What the effort did produce, and what is worth keeping:

* **The measurement harness.** `scripts/benchmark.py` is how the above table
  exists at all, and it is what will catch a regression when the model changes
  under us.
* **The preprocessing pipeline.** Still used: it finds the line boxes the
  interface draws, computes the ink statistics that drive the blur and contrast
  warnings, and provides the local fallback path when no key is configured.
* **The negative result itself.** "Image quality barely mattered; content type
  mattered enormously; the model was the bottleneck" is a finding, and it is the
  reason the project changed engines rather than buying a better scanner.

The rest of this document is retained because the loop it describes is how any
future engine change gets justified — and because a project that deletes the
record of what it tried and abandoned cannot be trusted about what it kept.

---

## The rule

**Never change the pipeline without a before and an after number on the same test
set.** Every improvement in this project has been justified that way, including the
ones we rejected — int8 quantisation was 25% faster and we threw it away because
error went from 2% to over 80%.

---

## Where the numbers come from

Three datasets, with different jobs. Keeping them apart is what stops us fooling
ourselves.

| Dataset | Built by | Used for | Never used for |
|---|---|---|---|
| `data/synthetic` (400 pages, 5,900 lines) | generator, seed 42 | **training** | reporting any result |
| `data/synthetic_test` (40 pages, seed 999) | generator, different seed | **the before/after number** | training |
| `data/exam/scans` (real writers) | real people | **the number we actually report** | training, until there is enough |

The synthetic sets share their handwriting fonts, so a model trained on one scores
well on the other almost by construction. That score measures whether the model
learned the *symbols*. It says very little about whether it can read a human.
**Only the real scripts answer that.**

---

## The loop

### 1 · Generate training data

```bash
python scripts/generate_code_dataset.py --pages 400 --out data/synthetic --seed 42
```

Writes ruled pages of handwritten C in ten different hands, at four levels of
photographic degradation, each with the exact text and box of every line.

### 2 · Export line crops

```bash
python scripts/export_line_crops.py --dataset data/synthetic --out data/train
```

Produces `train.jsonl` and `val.jsonl`: one line image paired with one string,
which is the only format a recogniser trains on.

When real scripts exist, include them:

```bash
python scripts/export_line_crops.py --dataset data/synthetic --scans data/exam/pages --out data/train
```

Each real page needs a matching `.txt` transcript with one line per written line.
**A page whose line count disagrees with its transcript is skipped, not guessed
at** — a mislabelled example is worse than a missing one.

### 3 · Fine-tune on Colab

Training needs a GPU; this laptop has none. Open
`notebooks/finetune_trocr.ipynb` in Google Colab, set the runtime to a T4 GPU,
and upload `data/train.zip`.

At about 146 MB the zip is more reliable through Google Drive than the browser
upload widget — put it in Drive and set `USE_DRIVE = True` in the notebook.

The notebook measures CER **before** training as well as after, so the gain is
provable rather than asserted. Roughly 20–30 minutes for 4 epochs on a T4.

### 4 · Install the fine-tuned model

Unzip the downloaded model into `models/trocr-code-final`, then in `.env`:

```
EVALNOVA_OCR_MODEL_NAME=C:\...\evalnova-core\models\trocr-code-final
```

No code changes: the provider loads a local directory exactly as it loads a
Hugging Face name. That is the provider boundary doing its job.

### 5 · Measure, on the same test set as before

```bash
python scripts/benchmark.py --dataset data/synthetic_test --tag after-finetune
```

Reports are written to `data/benchmarks/` with a timestamp, so comparisons survive
being re-run weeks apart.

---

## Reading a benchmark report

The harness deliberately separates three things that are easy to confuse:

| Metric | Question it answers | If it is bad |
|---|---|---|
| **line recall** | Did we find the lines? | Fix segmentation. The recogniser is blameless |
| **CER / WER** | Did we read the lines we found? | Fix the model — preprocessing will not help |
| **confidence** | Did the system know it was struggling? | Fix the confidence measure, not the recogniser |

A page can have perfect recognition and terrible line recall, or the reverse. An
overall accuracy number hides both.

---

## What we have measured so far

**Baseline, `trocr-small-handwritten`, on synthetic handwritten C:**

| Slice | CER |
|---|---|
| clean pages | 27.4% |
| degraded pages | 25.1% |

Image quality barely matters, and fixing segmentation (line recall 86% → 101%)
did not move CER at all. The failures are symbol failures:

| Written | Read as |
|---|---|
| `#include <stdio.h>` | `tinclude estdio-ho-` |
| `int main()` | `int mainly` |
| `flag = 1;` | `flag - 1 ;` |
| `scanf("%d", &n);` | `scant ( " rod " , en ) ;` |

**Conclusion: the model is the bottleneck, not the image pipeline.** That is why
the next step is fine-tuning rather than more OpenCV.

---

## Two traps to avoid

**Reporting the synthetic number.** It will look excellent after fine-tuning
because the model has seen those exact fonts. It is a sanity check, not a result.
The honest headline is the figure from real scanned scripts.

**Training on your test set.** `data/synthetic` uses seed 42 and
`data/synthetic_test` uses seed 999 for exactly this reason. If you regenerate
either, keep the seeds apart, and never fold the test pages into training to get
a bigger training set.
