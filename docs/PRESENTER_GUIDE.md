# EvalNova — The Presenter's Guide

*Everything explained from zero, with analogies, reasons, and the questions a
panel will ask. Read section 1 and 2 even if you read nothing else.*

---

## How to use this

- **Sections 1–3** = what to say in the first three minutes.
- **Sections 4–9** = the actual technical understanding, taught from nothing.
- **Section 10** = every likely panel question with an answer.
- **Section 11** = the demo, and what to do when it breaks.
- **Section 12** = one-page cheat sheet. Print this one.

**The golden rule for tomorrow:** you will be believed more for saying *"we
measured it, and it is not good enough yet"* than for claiming success. Your
strongest result is not accuracy. It is that **the system knows when it cannot
read something.**

---

## 1. What the project is (in plain words)

A teacher collects 200 handwritten answer booklets. Marking them takes days, and
two teachers marking the same script often give different marks.

**EvalNova is a system that reads a handwritten answer, marks it against the
official marking scheme, says how sure it is, and hands the doubtful ones to a
human teacher.**

The important part is the last bit. We are **not** building "AI that marks exams."
We are building a careful assistant that:
- shows its working,
- admits when it cannot read something,
- and never gets the final say.

### The analogy to use on stage

> "Think of a junior assistant marking scripts. A bad assistant hands you a pile
> of marks and says 'trust me'. A good assistant hands you the marks, shows which
> line of the student's answer earned each mark, and says 'these twelve I'm
> confident about; these three I couldn't read properly, please check them
> yourself.' We are building the good assistant."

### Why "just ask ChatGPT to mark it" is not the project

If you photograph an answer and ask an AI "how many marks?", you get a number
with nothing behind it. If a student challenges the mark, you cannot explain it.
No university can defend that.

So we built a **chain of evidence**: the handwriting → the text we read from it →
the specific marking-scheme criterion it satisfies → the exact words from the
student's answer that prove it → how confident we are → what the human examiner
decided. Every mark can be traced backwards through that chain.

---

## 2. The 60-second version (memorise this)

> "EvalNova evaluates handwritten exam answers. It has four parts: reading the
> handwriting, storing the marking scheme, doing the marking, and the examiner's
> review screen. We have built part one completely.
>
> The hard problem in part one turned out not to be the AI model — it was the
> paper. A real answer booklet is ruled, printed in colour, written on both sides
> and marked in red. To a computer all of that looks like ink, and a recognition
> model handed a ruled line will confidently invent a sentence for it. Our system
> scored 125% error on a real page — worse than reading nothing.
>
> We built a cleaning stage that keeps only the student's ink. Error dropped to
> 47% and time dropped from 64 seconds to 7. It is still not good enough to mark
> a real booklet — and the system says so itself: confidence falls to 53% and it
> routes the page to a human. That honesty is the point of the design."

---

## 3. Technology basics, taught from zero

You said you know nothing technical. Here is everything you need, in order.

### 3.1 What a digital image actually is

A photograph is a grid of tiny squares called **pixels**. Each pixel is just a
number for how bright it is: 0 is black, 255 is white. A page photo is about
2000 pixels wide and 2800 tall — around 5.6 million numbers.

**The computer does not see letters.** It sees numbers. Everything our cleaning
stage does is arithmetic on those numbers.

> **Analogy:** a mosaic. Stand far back and you see a face; up close it is just
> coloured tiles. The computer only ever sees the tiles.

### 3.2 What OCR and HTR mean

- **OCR** (Optical Character Recognition) = turning a picture of text into actual
  text you can search and copy.
- **HTR** (Handwritten Text Recognition) = the same thing, but for handwriting.

Printed text is easy — every "a" looks identical. Handwriting is hard because
every "a" is different, letters join up, and people write at angles.

> **Analogy:** reading a printed book versus reading a friend's shopping list.

### 3.3 What "a model" is, and what training means

A **model** is a program that learned a skill from examples instead of being
given rules. Nobody wrote "an 'a' is a circle with a tail." Instead the model was
shown hundreds of thousands of handwriting images with the correct text, and it
gradually adjusted itself until it got them right.

> **Analogy:** you never learned rules for recognising your mother's handwriting.
> You saw it a thousand times and now you just know it.

**The catch — this is the single most important concept in your project:**

The model we use, **TrOCR**, learned from a dataset called **IAM**: mostly
British and European adults writing everyday English sentences, on clean paper,
scanned properly.

Your booklet is: an Indian engineering student, writing technical Computer
Networks content with fractions and exponents, in ballpoint on ruled paper,
photographed with a phone.

That mismatch is called **distribution shift** — the model is being asked to read
something unlike anything it studied.

> **Analogy:** someone who learned English only from printed newspapers being
> handed a doctor's prescription. They know English perfectly. They still can't
> read it.

**This one idea explains your 47% error rate.** Learn it cold.

### 3.4 Why we cut the page into lines

Handwriting models read **one line at a time**. That is how they were built and
trained. Give one a whole page and you get nonsense.

So before the model ever runs, our software must find where each line of writing
is and cut it out. That is called **line segmentation**, and it is real work, not
glue — on a real booklet it is where everything went wrong.

> **Analogy:** a translator who works sentence by sentence. Hand them a whole
> newspaper page at once and they'll produce gibberish.

### 3.5 What "confidence" means here

When the model reads a line, it does not just output letters. For every single
character it also produces a number: how likely that character was.

It might be 99% sure of "P", 98% sure of "o", but only 30% sure of the next
letter. We combine those into one score for the line.

**We never ask the model "how confident are you?"** — research shows that answer
is unreliable; models are systematically overconfident. We take the numbers the
model produces internally while working. It is the difference between asking
someone "are you sure?" and watching their hand shake.

### 3.6 Calibration — the concept that makes you sound serious

**Measured confidence ≠ correct confidence.**

A weather forecaster says "70% chance of rain." They are **calibrated** if, across
all the days they said 70%, it actually rained about 70% of the time.

Our system says 95% confidence on a line. Is it right 95% of the time? **We do
not know yet.** Proving that requires a set of answers where we know the truth,
and that is Phase 3 of the project.

So the honest statement, which you should repeat whenever confidence comes up:

> "Our confidence is a real measurement, but it is not yet calibrated. A
> confidently misread word still scores high. Until we measure that, no threshold
> decides anything on its own."

### 3.7 How we measure accuracy: CER and WER

- **CER (Character Error Rate):** of all the characters, what fraction did we get
  wrong? "cat" read as "cot" = 1 wrong character out of 3 ≈ 33%.
- **WER (Word Error Rate):** same, but per word. "cot" is a wrong word, so that
  is 100% WER on a one-word sentence.

WER is always higher than CER, because one wrong letter ruins the whole word.
We report both: CER says how well we read strokes; WER says how much of the
answer survived intact for a marker to read.

**What does 125% error mean?** More errors than there were characters to begin
with — the system was *inventing* extra text. That is what happens when a
recogniser is handed ruled lines: it hallucinates sentences from them.

### 3.8 Frontend, backend, API, database

Think of a restaurant:

| Restaurant | Software | In our project |
|---|---|---|
| Dining room you sit in | **Frontend** | The web page where you upload the answer and see the result |
| Kitchen | **Backend** | The Python program that cleans the image and runs the model |
| Waiter carrying orders | **API** | The messages between the page and the program |
| Store room / ledger | **Database** | Where every answer, transcription and confidence is recorded |

- **API** (Application Programming Interface) is just an agreed list of requests
  the kitchen accepts: "here's an image, transcribe it" is one request.
- **Endpoint** = one specific item on that menu. We have 14 working ones.

### 3.9 What a "provider interface" is — the most important design idea

We wrote our program so the recognition model is a **plug-in part**.

> **Analogy: an electrical socket.** Your wall socket doesn't know or care whether
> you plug in a lamp, a fan or a charger. It just provides the standard shape and
> voltage. Anything that fits the plug works.

We defined the "socket": any recognition engine must accept line images and
return text plus confidence. Behind it we can plug in:
- **TrOCR** (runs on your laptop, private, free)
- **Gemini** (Google's cloud model, more accurate, but sends data to Google)
- **A mock** (a fake, explained next)

Swapping engines is one line in a settings file. **We proved it works:** the
entire Google engine was added without changing a single line of the application
logic around it.

Why it matters for marks: the whole project rests on "the AI model is a
replaceable estimator; the marking scheme is institution-owned truth." The socket
is that principle made real.

### 3.10 What a "mock" is

A **mock** is a stand-in that behaves like the real thing but does nothing real —
it returns fixed, pretend text.

> **Analogy:** a crash-test dummy, or a stunt double at a rehearsal. You can
> practise the whole scene without the lead actor.

Why we need it:
1. Tests run in seconds without downloading a 250 MB model.
2. Members 2, 3 and 4 can build against it without waiting for Part 1.
3. **If the model fails on demo day, we switch to the mock and the demo still
   runs end to end** — and we say so out loud, because a pipeline running on a
   swapped engine proves the socket design works.

### 3.11 What the "501" endpoints are

Parts 2, 3 and 4 aren't built. But their menu items already exist, and when
called they reply: *"Rubric-driven marking is Part 3 of the plan and is not built
yet."* (501 is the web code for "not implemented".)

> **Analogy:** a restaurant menu printed with the full season's dishes, where
> some say "available from November". You know exactly what's coming and can plan
> around it.

Why this is good engineering: the four members agreed the exact shape of every
message on day one. Nobody has to guess another member's design, and the
interface can already call the real address and get an honest failure instead of
a crash.

### 3.12 Tests, and why 96 of them matter

A **test** is a small program that checks your program still works. Ours run in
35 seconds and check things like "a blank page produces no lines" and "thin pen
strokes are not erased."

> **Analogy:** a smoke alarm. You don't notice it until the day it saves you.

Real example from this project: while improving the cleaning stage, I wrote code
that accidentally erased every pen stroke thinner than 3 pixels. The tests now
catch that exact bug if anyone reintroduces it.

### 3.13 Git and GitHub

- **Git** = save points in a video game. Every "commit" is a snapshot you can
  return to.
- **GitHub** = the shared cloud save, so four people can work on the same project
  without emailing files around.

Ours: `https://github.com/amit-cmd123/Miniproject`

**Say this if asked about teamwork:** each member works on their own branch and
submits changes for review, so four people never overwrite each other.

### 3.14 Local model vs cloud model (and the privacy question)

- **Local (TrOCR):** runs on the laptop. Nothing leaves the machine. Free,
  private, offline — but weaker.
- **Cloud (Gemini):** Google's model, much stronger on real handwriting — but the
  answer sheet image is **sent to Google**, and on the free tier Google may use
  submitted content to improve its products.

Our decision: **local by default, cloud only if explicitly switched on.** Student
answer sheets are sensitive, so that choice is deliberate and is shown in the
interface.

---

## 4. The pipeline — what happens to one page, step by step

This is the heart of your presentation. Thirteen stages. For each: what it does,
and why it exists.

**Stage 0 — Upload.** A photo, scan or PDF booklet arrives. A PDF is split into
page images first, because recognition works on images.

**Stage 1 — Resize.** Cap the page at 2000 pixels wide.
*Why:* beyond that, extra pixels cost time without adding legibility.

**Stage 2 — Denoise.** Remove camera speckle with a median filter.
*Why:* phone photos have sensor grain that looks like tiny ink dots.
*Analogy:* wiping dust off a window before looking through it.
*Engineering note:* we replaced a slower method here and went from 1.2 s to
0.25 s with no loss of accuracy.

**Stage 3 — Assess quality.** Measure blur and ink-to-paper contrast.
*Why:* a blurry photo should lower our confidence later. We measure blur **after**
denoising, because grain makes a blurry photo look artificially sharp.

**Stage 4 — Flatten the lighting.** Estimate what the blank paper would look like
and divide it out.
*Why:* a phone photo is bright on one side and shadowed on the other. Without
this, one setting can't work across the whole page.
*Analogy:* turning on the room lights instead of using a torch on one corner.

**Stage 5 — Isolate the ink (colour).** Drop red and orange marks.
*Why:* the printed form is orange; the examiner marks in red. Neither is the
student's answer.

**Stage 6 — Isolate the ink (darkness).** Decide how dark something must be to
count as ink, based on **this page's own darkest ink**.
*Why:* this is what removes the ghostly mirror-image writing showing through from
the back of the sheet, while still catching a faint pen. A fixed setting would
either miss faint ink or admit the show-through.

**Stage 7 — Remove the ruled lines.** *(The big one.)*
The printed lines on notebook paper look exactly like ink to a computer. Handed
a ruled line, the model **invents a sentence for it**. That is where the 125%
error came from.
We remove them in two passes: long straight runs of ink first; then a geometric
line-detector for rules broken into dashes. Each candidate faces a physical test:
**a rule is solid along its length with blank paper either side; a line of
writing has letter bodies right next to it.**
*Analogy:* erasing the lines from lined paper so only the writing is left.

**Stage 8 — Spot a cover page.** If coloured print outweighs handwriting, it is
the printed cover/form page — skip it and say why.
*Why:* on your booklet, the old system spent **100 seconds** inventing text from
the printed cover, producing "I am in America earn medical events".

**Stage 9 — Straighten the page (deskew).** Rotate until the lines of writing sit
horizontal.
*Why:* the next stage assumes horizontal lines. Phone photos are never straight.

**Stage 10 — Find the lines.** Add up the ink in each horizontal row; rows with
lots of ink are text, empty rows are gaps. Then merge stray fragments (an
exponent like 10³ belongs with its line) and split bands where a tall stroke
fused two lines together.

**Stage 11 — Filter.** Drop boxes with almost no ink.
*Why:* a stray dot otherwise costs a full model run and comes back as invented
text.

**Stage 12 — Read.** Each line image goes to the model, which returns text plus a
probability for every character.
*Detail worth mentioning:* we cap how much text the model may produce per line
based on the line's width. On an unreadable crop the model used to loop
"0005000500…" until it hit its limit — so the worst lines were also the slowest.

**Stage 13 — Score, band, store.** Combine line confidences into a page score,
assign a trust band, save everything with a full audit record.

---

## 5. How the confidence number is built

**Per line:** for every character the model produces a probability. We take the
**geometric mean** — multiply them together and take the root.

> **Why geometric, not a simple average:** a chain is as strong as its weakest
> link. If the model was 99% sure of nine characters and 2% sure of one, a plain
> average says 89% — which is a lie, because that one character is probably
> wrong. The geometric mean punishes the weak link properly.

**Per page:** a length-weighted average of the lines, multiplied by a blur
penalty.
- **Length-weighted:** a confident two-word line shouldn't outweigh a hesitant
  thirty-word one.
- **Blur penalty:** a soft photo should drag the whole page down even if the model
  sounds sure.

**Four trust bands** (traffic lights):

| Confidence | Band | Meaning |
|---|---|---|
| 95%+ | **Reliable** | Can go forward without routine checking |
| 85–95% | **Spot check** | Quick read-through advised |
| 70–85% | **Verify** | A human should confirm before marks depend on it |
| Below 70% | **Manual transcription** | Too unreliable — correct it by hand |

These numbers live in one settings file and are sent to the interface over the
API, so the web page never has them hard-coded. **They are starting guesses, not
proven values** — Phase 3 moves them based on measurement.

---

## 6. The tech stack — what each piece is and why we chose it

### Backend (the kitchen) — Python

| Tool | What it is | Why we use it |
|---|---|---|
| **Python** | The programming language | Every AI and image library exists for it |
| **FastAPI** | Builds the menu of requests | Checks every message's shape automatically and generates live documentation, so all four members can see the interface |
| **Pydantic** | Describes the shape of each message | Bad data is rejected at the door instead of causing a mysterious crash later |
| **SQLAlchemy** | Talks to the database in Python | Lets us switch database systems later by changing one line |
| **SQLite** | The database itself, a single file | Needs no server — a teammate can clone and run immediately |
| **OpenCV** | Image-processing toolbox | Does stages 1–11. Fast, explainable, needs **no training data** |
| **NumPy** | Fast number crunching | An image *is* a grid of numbers; this handles them |
| **PyTorch** | Runs the AI model | The standard engine for running models |
| **Transformers** | Downloads and loads TrOCR | One line instead of building the model ourselves |
| **PyMuPDF** | Opens PDFs | Booklets arrive as PDFs; we need page images |
| **jiwer** | Computes CER and WER | Turns "it works well" into a number |
| **httpx** | Makes web requests | How we call Google's model, without installing Google's software |

### Frontend (the dining room)

| Tool | What it is | Why |
|---|---|---|
| **React** | Builds interactive web pages | The review screen changes constantly as you edit and save |
| **TypeScript** | JavaScript that checks types | Catches "you sent the wrong kind of data" before it runs |
| **Vite** | Dev server and bundler | Instant reloads; also forwards messages to the backend so there's no address hard-coded |
| **Tailwind** | Styling shortcuts | Consistent look without a separate design file to maintain |

### The models

| Engine | What it is | Status |
|---|---|---|
| **TrOCR small** | Microsoft's handwriting model, runs locally | **Default.** ~0.2 s per line |
| **Gemini 3.5 Flash** | Google's cloud vision model, reads whole pages | **Built, switched off, never tested live** (no API key yet) |
| **Mock** | Fake engine returning fixed text | Tests, offline work, demo fallback |

**Why small instead of the bigger TrOCR:** we measured both. The big one was
**10× slower** for **no meaningful accuracy gain** on our cleaned pages (45% vs
47% error on the real page; both perfect on samples). So we chose the small one.

**A decision we rejected, and why saying so is good:** we tested "int8
quantisation" — a trick that shrinks the model to make it faster. It was 25%
faster but error jumped from 2% to over 80%. We threw it away. **Mention this.**
It shows you measure instead of assuming.

---

## 7. Architecture — and the two rules

The program is built in layers:

```
Web page (React)
    ↓ messages
API layer        — only handles requests, contains no thinking
Services layer   — the actual work: cleaning, reading, confidence, audit
Providers layer  — the swappable engines (TrOCR / Gemini / mock)
Database layer   — 15 tables
```

Two rules keep it honest, and anyone can check them by reading the code:

1. **No AI library may be mentioned above the providers layer.** Only the socket
   knows about TrOCR or Google.
2. **The services layer never talks back up to the API layer.** Work flows one
   way.

> **Analogy:** a well-designed kitchen. The waiter never cooks; the chef never
> takes orders at the table. If they start doing each other's jobs, the whole
> place seizes up when one person is off sick.

**Proof it works:** the Gemini engine was added complete — network calls, retries,
fallback, confidence — without touching any application logic.

---

## 8. Why the marks arithmetic will be done by us, not the AI (Part 3)

When marking is built, the AI's job is only: *for each criterion, is it satisfied,
and which words from the student's answer prove it?*

**Python then adds the marks up.**

> **Why this matters:** a model asked to total marks can award 4 out of a
> criterion list worth 3. Arithmetic done in code cannot. The model judges; the
> calculator counts.

Same idea for evidence: each criterion must come with a **quoted phrase from the
student's own answer**. A verdict with no quote lowers the confidence score. This
directly targets a failure found in published work — LLM graders "inferring too
much implication," i.e. giving credit for things the student never wrote.

---

## 9. The results, and what they mean

| Page | Before | After |
|---|---|---|
| Real answer page (ruled, maths, phone photo) | 64 s, **125% CER** | **7 s, 47% CER** |
| Four synthetic sample sheets | ~17 s each, 1–4% CER | **~4 s each, 0% CER** |

Plus: on the real page, confidence correctly falls to **~53%** → *Manual
transcription*. On samples it is ~98% → *Reliable*.

**How to present this honestly:**

> "Cleaning the page cut the error by more than half and the time by 90%. But 47%
> is still not usable for marking — and the system agrees. It reports 53%
> confidence and refuses to grade the page. The gap between 0% on clean samples
> and 47% on a real booklet *is* our finding: the model can read handwriting, just
> not this handwriting, and we can now prove it."

Also true and worth saying: **the improvement came from ordinary image
processing, not from a bigger AI model.** The cleaning stage uses no training
data at all.

---

## 10. Panel questions, with answers

### About the project overall

**Q: What exactly have you built, and what haven't you?**
> Part 1 — reading handwriting — is complete and measured: 14 working endpoints,
> 96 passing tests. Parts 2, 3 and 4 have their database tables, their agreed
> message formats and prototype screens, but not their logic. We deliberately
> froze all four contracts on day one so we could work in parallel.

**Q: Why four parts? What did each person do?**
> Part 1 reads the handwriting; Part 2 stores the questions and marking schemes;
> Part 3 does the marking and confidence; Part 4 is the examiner's review screen
> and the validation dashboard. They run in parallel because we agreed every
> shared message format up front and built fake stand-ins, so nobody waits.

**Q: Isn't this just ChatGPT with extra steps?**
> If you photograph an answer and ask an AI for marks, you get a number you can't
> defend. We produce a chain: handwriting → text → which criterion → the
> student's own words that prove it → confidence → the examiner's decision.
> Also, the marks are added up by our code, not by the model, so it cannot award
> 4 marks from criteria worth 3.

### About accuracy

**Q: Is 98% confidence the same as 98% accuracy?** *(They will ask this.)*
> No, and the difference matters. Confidence is the model's certainty; accuracy
> is how often it's right. We measure accuracy separately as character and word
> error rate against a known transcription. Proving that 98% confidence means 98%
> correct is called calibration, and we haven't done it yet — that's Phase 3.

**Q: 47% error — so it doesn't work?**
> On a real booklet, the local model is not good enough, and we say so. Two
> things make that a result rather than a failure. First, it was 125% before, so
> the page-cleaning work is proven. Second, the system detects its own weakness —
> 53% confidence, routed for manual transcription — so it never silently produces
> a wrong mark. A system that fails loudly is usable; one that fails quietly is
> dangerous.

**Q: Why is it perfect on your samples but bad on a real page?**
> The samples are generated with a handwriting-style font: even strokes, clean
> background, no ruling. A real booklet is ruled, double-sided, marked in red and
> photographed at an angle, by a writer whose style the model never trained on.
> The gap between those two numbers is exactly the finding we're reporting.

**Q: How do you know your confidence number is meaningful?**
> Today we know it *behaves* correctly — high on pages we read well, low on the
> page we read badly. We do not yet know it's calibrated. That needs a
> ground-truth set of about fifty answers, which is Phase 3, and we'll report a
> calibration curve and a false-auto-accept rate.

### About the technology

**Q: Why TrOCR and not Google Vision / Tesseract?**
> Tesseract is built for printed text and does poorly on handwriting. TrOCR is
> purpose-built for handwriting and runs locally, so no student data leaves the
> machine. We've also built the Google Gemini engine behind the same interface,
> so benchmarking one against the other is a configuration change — that's
> precisely why we put recognition behind a swappable interface.

**Q: Why didn't you just use a big AI model for the whole page from the start?**
> Three reasons. Privacy — answer sheets would leave the machine. Cost and
> availability — it needs a key and a network, which we can't rely on during a
> demo. And attribution: published work on handwritten grading found **87% of
> grading errors came from transcription, not from marking**. If you fuse reading
> and marking into one call, you can't tell which failed. We keep them separate.

**Q: Why is your cleaning stage classical image processing rather than a neural
network?**
> The published approach to removing ruled lines trains a CNN on synthetic data.
> Ours uses geometry and needs no training data at all, and additionally removes
> printed colour, examiner marks and show-through. It runs in a quarter of a
> second and every step is explainable — we can show the panel exactly what was
> removed.

**Q: Why SQLite and not a proper database?**
> So the project runs with no external services — anyone can clone it and start.
> The code uses SQLAlchemy, so moving to PostgreSQL is a connection-string
> change. That's Phase 2, before real data has to survive.

**Q: What happens if the AI model is unavailable on demo day?**
> We switch to the mock engine in the settings and everything still runs end to
> end — and we'd say so out loud. A pipeline that runs on a swapped engine is
> direct proof that our provider abstraction works.

### About confidence and correctness

**Q: Why not ask the model how confident it is?**
> Because that number is unreliable — models are systematically overconfident,
> and published work shows self-reported confidence correlates weakly with being
> right. We use the probabilities the model produces internally for each
> character. It's the difference between asking someone if they're sure and
> watching their hand shake.

**Q: What if the model is confidently wrong?**
> That's the honest weakness of our current measure, and we state it: a
> confidently misread word still scores high. It's why no threshold is allowed to
> auto-accept anything yet, and why Phase 3 measures the false-auto-accept rate
> before we trust any band.

### About ethics, privacy, fairness

**Q: Is it safe to put students' answer sheets through this?**
> By default nothing leaves the machine — the model runs locally. Answer images,
> the database and the configuration file are excluded from our public code
> repository, and I verified that before pushing. The cloud engine is opt-in, and
> if switched on it's shown in the interface and recorded on every result.

**Q: Could this be unfair to students with poor handwriting?**
> Yes, and that's a real risk we haven't measured yet. A student whose
> handwriting the model reads poorly would get more scrutiny — though note the
> failure direction is safe: low confidence routes to a human, not to a bad mark.
> Measuring fairness across handwriting styles is future work, and we'd rather
> name it than have it discovered.

**Q: Will it replace teachers?**
> No. The design forbids it. The examiner's decision is stored as a separate
> record and the AI's result is never overwritten — that's what lets us measure
> how often they disagree. Auto-accept is deliberately disabled until we've
> measured how often it would be wrong.

### About research

**Q: What papers did you study?**
> Three that map directly onto what we built: Gold & Zesch (ICFHR 2022) on
> removing ruled lines — they needed a trained CNN, we did it with geometry.
> Levine et al. (AIED 2026), who found 87% of grading errors came from
> transcription, not marking — which is why we invested in reading first and kept
> the stages separate. And Garrido-Munoz & Calvo-Zaragoza on generalisation,
> who showed these models don't transfer to unseen handwriting — measured
> offline; we surface it at runtime as a confidence score.

**Q: What's genuinely new here?**
> Not the recognition model, which is off the shelf. What we haven't found in the
> literature is a system that combines handwritten free-text answers, marking
> against rubric criteria with quoted evidence, confidence that routes to a
> human, and an audit trail where the AI's original result survives the human's
> correction. Each exists separately; we're building the composition. And nobody
> carries recognition confidence forward into the marking confidence — that's our
> clearest gap.

### Traps — be careful

**Q: So you've solved handwritten answer evaluation?**
> No. We've built and measured the reading stage, and it isn't good enough for
> real booklets yet. Marking isn't built. Confidence isn't calibrated. What we
> have is an architecture that makes each of those measurable, and honest numbers
> for where we are.

**Q: Your sample results are 0% error — isn't that suspicious?**
> It should be. Those are synthetic sheets generated with a handwriting font, so
> they're much easier than real writing. We keep them because they test the
> pipeline end to end and give a reproducible baseline — not because they prove
> the system reads handwriting.

**Q: How long did this take / how much is your own work?**
> The page-cleaning pipeline, the confidence design, the architecture and the
> provider interface are ours. The recognition model is off-the-shelf — training
> a handwriting model from scratch is explicitly out of scope for a mini-project.

### If you don't know an answer

Say: **"I don't know — that's not something we've measured. What we'd do to find
out is…"** and describe the experiment. Never invent a number. A panel forgives
gaps; they do not forgive bluffing.

---

## 11. The demo

**Before you walk in**
1. Start the backend **at least a minute early** and wait for the badge to say
   *Model ready*.
2. Open the interface (note the port — it may be 5174, not 5173).
3. Have `data/samples/sample_answer_normal.png` and the real booklet PDF ready.
4. **Run the real booklet once beforehand** so you know exactly what it produces.

**The run (6–8 minutes)**
1. **Frame it (45 s):** four sections, four members. Part 1 is live; the rest are
   contracts and prototypes.
2. **Sample sheet (1 min):** drop it in, ~6 seconds, word-perfect, ~98% Reliable.
3. **The real booklet (3 min)** — this is the real demo:
   - Page 1 is the printed cover: skipped, with the reason shown. Mention the old
     system spent 100 seconds inventing text from it.
   - Open **Detected lines** on an answer page: ruling, margin, red marks and
     show-through all gone; one box per line of writing.
   - Confidence ~53% → *Manual transcription*. Say plainly: "it can't read this,
     and it says so."
4. **Correction and measurement (1.5 min):** edit a word, save — machine output is
   kept underneath so error rate stays measurable. Paste the reference text into
   **Measure accuracy** for CER/WER.
5. **What's next (1 min):** click through the Part 2/3/4 prototypes, then show
   `/docs` and call `POST /evaluations` returning its 501 with the owning
   workstream.

**If something breaks**
- Model won't load → set `EVALNOVA_OCR_PROVIDER=mock`, restart, say so out loud.
- Frontend won't reach the backend → check the backend window is still running.
- A page fails → that's fine, it's reported per page; the booklet continues.
- **Never pretend.** "That's a bug we haven't fixed" costs you far less than a
  panel catching you covering.

---

## 12. One-page cheat sheet

**The pitch:** reads handwritten answers, marks them against the real marking
scheme, says how confident it is, sends doubtful ones to a human. Every mark
traceable to the handwriting that earned it.

**The numbers:**
- Real page: **125% → 47%** character error; **64 s → 7 s**
- Samples: **0% error**, ~4 s per page
- Confidence: **98% (Reliable)** on samples, **53% (Manual transcription)** on the real page
- **96 tests**, 14 endpoints, 15 database tables
- Rejected: int8 quantisation (25% faster, error 2% → 80%+)
- Model choice: small over base — **10× faster, same accuracy**

**The four parts:** 1 Handwriting ✅ · 2 Rubrics · 3 Marking & confidence · 4 Examiner app

**The five sentences to have ready:**
1. "A recogniser handed a ruled line will confidently invent a sentence for it —
   so the first job is finding the student's writing and nothing else."
2. "We never ask the model how confident it feels; we use the probabilities it
   produces per character."
3. "Confidence is measured but not calibrated — that's Phase 3, and until then no
   threshold decides anything alone."
4. "Python sums the marks. The model judges each criterion and quotes its
   evidence."
5. "The AI's original result is never overwritten — that's what makes measuring
   agreement possible."

**The three papers:** Gold & Zesch (ruled lines — CNN vs our geometry) · Levine
et al. (87% of errors are transcription) · Garrido-Munoz (models don't
generalise — we surface it at runtime).

**When cornered:** "We measured it, here's the number, and here's what we haven't
done yet."
