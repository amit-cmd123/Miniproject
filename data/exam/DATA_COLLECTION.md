# Handwriting Data Collection Protocol — EVN-PROG-01

*Read this once before handing the paper to anyone. The quality of this dataset
decides whether recognition improves. An hour of care here is worth a week of
model tuning later.*

---

## What we need, and why

We need the same text written by many different people, **with the exact text known
in advance.** That combination is what lets us do two things:

1. **Fine-tune the recogniser.** To teach a model, you must show it an image and the
   correct answer. If we know exactly what was written, every line becomes a free
   training example.
2. **Measure error honestly.** Character error rate needs a ground truth to compare
   against. Guessing afterwards at what a student "probably wrote" is not ground truth.

This is why most of the scripts are **copied word for word from the answer key**.
It feels artificial, and it is — deliberately. A writer copying known text gives us
perfect labels at zero labelling cost.

---

## What each writer produces

Each writer produces **two things**:

### Page 0 — the calibration page (everyone writes this)

Copy the passage below **exactly**, one numbered line per line of the page.
It is deliberately dense in the characters that break code recognition — braces,
semicolons, operators, digits and identifiers.

```
1.  int main void return if else while for do break continue
2.  printf scanf include stdio float double char long short
3.  int count = 0;   float avg = 12.75;   char grade = 'A';
4.  sum = a + b * (c - d) / e;   rem = x % y;
5.  if (p == q) { r = 1; } else { r = 0; }
6.  while (i != n) { i++; total += arr[i]; }
7.  for (i = 0; i < 10; i--) { j = j - 1; }
8.  int *ptr = &value;   *ptr = 25;   arr[3] = arr[0];
9.  flag == 1 && count != 0 || done == 0
10. 0 1 2 3 4 5 6 7 8 9   10 25 100 512 1024
11. a b c d e f g h i j k l m n o p q r s t u v w x y z
12. A B C D E F G H I J K L M N O P Q R S T U V W X Y Z
13. printf("%d %c %f \n", num, ch, avg);
14. The quick brown fox jumps over the lazy dog.
15. A pointer stores the address of another variable.
```

**Keep the line numbers.** They let us align each image line with its true text
automatically, with no manual matching.

### Pages 1+ — the six answers

Then the writer answers the six questions.

---

## Two sets of scripts — collect both

### Set A — verbatim scripts (most of your writers)

The writer **copies the model answer from the answer key exactly**, including the
code. Do not paraphrase. Do not fix the wording.

- **Purpose:** training data and clean error measurement.
- **How many:** aim for **6 to 10 writers**, one script each.
- **Ground truth:** already known — it is the answer key. Nothing to type up.

### Set B — natural scripts (3 or 4 scripts)

The writer answers **in their own words**, without copying. We need a spread:

| Script | What the writer should do |
|---|---|
| B1 | Answer everything correctly, in their own words |
| B2 | Answer about half the criteria — leave parts out |
| B3 | Make two or three deliberate mistakes (e.g. swap & and *, answer 15 in Q2) |
| B4 *(optional)* | Write untidily — fast, cramped, the way a real student writes under time pressure |

- **Purpose:** testing whether the **marking** is correct, not whether the reading is.
- **Ground truth:** the writer (or you) must **type out exactly what they wrote**,
  mistakes and all, into a plain text file. Without this the script is unusable.

**Why both sets:** Set A tells us how well we *read*. Set B tells us how well we
*mark*. A system that is perfect at one and poor at the other is of no use.

---

## Writing rules — give these to every writer

1. **Blue or black ballpoint only.** No pencil, no red ink (red is the examiner's
   colour and the system deliberately removes it), no gel pen that soaks through.
2. **Write the question number** at the start of every answer: `Q1.`, `Q2.`
3. **One blank line between answers.**
4. **Stay inside the ruled area.** Nothing in the margin.
5. **Write on one side of the sheet only** if you can. Double-sided writing shows
   through and makes the page harder to clean.
6. **Do not strike out heavily.** A single thin line through a mistake is fine; a
   scribbled block is not.
7. **Write normally.** Do not write extra neatly for the camera — we are trying to
   measure real handwriting, so unusually careful writing makes the result a lie.
8. Use the same ruled sheets for everyone if possible, so the paper itself is not
   an extra variable.

---

## Photographing or scanning

Quality here matters more than anything else in this document.

**If you can scan, scan.** A flatbed scan at 300 DPI beats any phone photo.

**If using a phone:**

- Put the page on a **flat, plain, dark surface** — a wooden desk is fine, a
  patterned tablecloth is not.
- **Daylight, or a bright even room light.** Not a desk lamp from one side.
- **Hold the phone directly above the page**, parallel to it — not at an angle.
- **Your shadow must not fall on the page.** Stand with the light behind the page, not behind you.
- The **whole page in frame**, with a small margin of desk visible around it.
- Tap to focus, check the photo is sharp before moving on.
- **Do not** use a scanner app's "auto-enhance", "whiten" or "magic colour" setting.
  Those destroy the faint strokes our cleaning stage relies on. Plain photo only.

**One PDF per writer**, pages in order: calibration page first, then Q1 to Q6.

---

## What to send me

```
data/exam/scans/
    writer_01.pdf          ← Set A, verbatim
    writer_02.pdf
    ...
    natural_B1.pdf         ← Set B, own words
    natural_B1.txt         ← exactly what B1 wrote, typed out
    natural_B2.pdf
    natural_B2.txt
```

For each writer also tell me, in one line: **a label and whether the hand is neat,
average or untidy** — for example `writer_03, average, left-handed`.
Left-handed writers often slant the opposite way, and that is useful to know.

---

## How much is enough

| Scripts | What it gives us |
|---|---|
| 3 writers | Enough to measure, not enough to train |
| **6 writers** | **Minimum useful** — around 300 lines of labelled handwriting |
| **10 writers** | **Target** — around 500 lines, enough for a visible fine-tuning gain |
| 15+ writers | Better still, if the people are available |

Ten writers × one calibration page × 15 lines, plus six answers of roughly 5 lines,
gives about **450 labelled lines**. That is a small dataset by research standards but
a reasonable one for adapting a model to a specific population of writers — and it is
500 more lines of real Indian student handwriting than exist in any public corpus.

---

## Privacy

These are real people's handwriting samples.

- **Do not** write anyone's roll number, phone number or address on the sheet. A
  label like `writer_03` is all we need.
- The scans stay out of the public repository — `data/exam/scans/` is git-ignored,
  the same as the answer-sheet storage.
- Tell each writer what the samples are for and that they can ask for theirs to be
  deleted.

---

## While you collect

I will be working on:

1. **Preprocessing for code** — handwritten code has tighter line spacing, deep
   indentation, and symbol-dense lines that the current segmentation was never
   tested against.
2. **The fine-tuning pipeline** — ready to run the moment the first scripts arrive,
   using the public IAM corpus for the base adaptation.
3. **Parts 2 and 3** — the question bank and rubric structures are already designed
   around this exact paper, so marking can be built before the scripts arrive.

Send me even **two scripts early** as a pilot. If something about the pen, the paper
or the lighting is wrong, I would rather find out on script two than on script ten.
