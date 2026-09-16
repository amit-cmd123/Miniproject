/**
 * Prototypes of the screens Parts 2, 3 and 4 will build.
 *
 * Each shows the real intended layout behind a "not built yet" state, so the
 * shape of the finished product is visible now and the owning member has a
 * target rather than a blank page.
 */

import { ComingSoon } from "../components/ComingSoon";

/* ---------------- Part 2 · Questions & rubrics ---------------- */

export function Rubrics() {
  return (
    <ComingSoon
      part="Part 2"
      title="Questions &amp; rubrics"
      question="What should a correct answer contain?"
      phase="Phase 1"
      owner="Member 2 — question bank, answer keys, marking schemes"
      scope={[
        "Author 15–20 Computer Science theory questions",
        "Reference answer and marking scheme for each",
        "Break each question into criteria with per-criterion marks",
        "Record acceptable alternatives and partial-credit rules",
        "Validate that criterion marks sum to the question maximum",
      ]}
      endpoints={[
        "GET  /questions",
        "GET  /questions/{id}/rubric",
        "POST /rubrics/validate",
      ]}
    >
      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="card overflow-hidden">
          <p className="border-b border-line px-4 py-2.5 eyebrow">Question bank</p>
          <ul>
            {[
              ["Q1", "Explain polymorphism", "5 marks"],
              ["Q2", "Normalisation to 3NF", "5 marks"],
              ["Q3", "Process vs thread", "4 marks"],
              ["Q4", "Deadlock conditions", "6 marks"],
            ].map(([id, title, marks], i) => (
              <li
                key={id}
                className={`flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 ${
                  i === 0 ? "bg-accentSoft" : ""
                }`}
              >
                <div>
                  <p className="font-mono text-[0.68rem] text-ink3">{id}</p>
                  <p className="font-display text-sm">{title}</p>
                </div>
                <span className="font-mono text-xs text-ink3">{marks}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card overflow-hidden">
          <p className="border-b border-line px-4 py-2.5 eyebrow">
            Rubric — explain polymorphism (5 marks)
          </p>
          <table className="w-full border-collapse font-display text-sm">
            <thead>
              <tr>
                <th className="border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">
                  Criterion
                </th>
                <th className="w-20 border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">
                  Marks
                </th>
                <th className="w-28 border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">
                  Partial
                </th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Defines polymorphism correctly", "1"],
                ["One interface, many implementations", "1"],
                ["Overriding or overloading explained", "1"],
                ["Technically correct example", "1"],
                ["Correct terminology throughout", "1"],
              ].map(([criterion, marks]) => (
                <tr key={criterion}>
                  <td className="border-b border-line px-4 py-2.5 text-ink2">{criterion}</td>
                  <td className="border-b border-line px-4 py-2.5 font-mono tabular-nums">
                    {marks}
                  </td>
                  <td className="border-b border-line px-4 py-2.5 font-mono text-xs text-ink3">
                    allowed
                  </td>
                </tr>
              ))}
              <tr>
                <td className="px-4 py-2.5 font-semibold">Total</td>
                <td className="px-4 py-2.5 font-mono font-semibold tabular-nums">5</td>
                <td className="px-4 py-2.5 font-mono text-xs text-band1">sums correctly</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </ComingSoon>
  );
}

/* ---------------- Part 3 · Evaluation & confidence ---------------- */

export function Evaluation() {
  return (
    <ComingSoon
      part="Part 3"
      title="Evaluation &amp; confidence"
      question="How many marks does this answer deserve, and how sure are we?"
      phase="Phase 2"
      owner="Member 3 — provider abstraction, scoring engine, confidence"
      scope={[
        "Send question, rubric and transcription to the model with a constrained output schema",
        "Get a verdict and an evidence quote for every criterion",
        "Sum marks deterministically in Python, never in the model",
        "Compose confidence from self-consistency, self-report, OCR quality and rubric coverage",
        "Route the result to one of four review bands",
      ]}
      endpoints={["POST /evaluations", "GET /evaluations/{answer_id}", "GET /config/thresholds"]}
    >
      <div className="flex flex-col gap-4">
        <div className="card p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-bold tabular-nums">4</span>
              <span className="font-display text-lg text-ink3">/ 5</span>
            </div>
            <span className="rounded-full border border-band2 px-2.5 py-1 font-display text-[0.7rem] font-semibold uppercase tracking-wider text-band2">
              Quick review · 92.4%
            </span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface2">
            <div className="h-full w-[92%] rounded-full bg-band2" />
          </div>
        </div>

        <div className="card overflow-hidden">
          <p className="border-b border-line px-4 py-2.5 eyebrow">Criterion breakdown</p>
          {/* Tailwind only sees class names that appear literally in the source,
              so these are written out rather than built from a variable. */}
          {[
            { criterion: "Defines polymorphism correctly", marks: "1/1", ok: true },
            { criterion: "One interface, many implementations", marks: "1/1", ok: true },
            { criterion: "Overriding or overloading explained", marks: "1/1", ok: true },
            { criterion: "Technically correct example", marks: "0/1", ok: false },
            { criterion: "Correct terminology throughout", marks: "1/1", ok: true },
          ].map(({ criterion, marks, ok }) => (
            <div
              key={criterion}
              className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3"
            >
              <span
                className={`h-2 w-2 flex-none rounded-full ${ok ? "bg-band1" : "bg-band4"}`}
              />
              <span className="flex-1 text-sm text-ink2">{criterion}</span>
              <span
                className={`font-display text-xs font-semibold ${
                  ok ? "text-band1" : "text-band4"
                }`}
              >
                {ok ? "satisfied" : "not satisfied"}
              </span>
              <span className="w-12 text-right font-mono text-sm tabular-nums">{marks}</span>
            </div>
          ))}
          <p className="px-4 py-3 text-sm italic text-ink3">
            Each verdict will carry the student's own words that justified it.
          </p>
        </div>
      </div>
    </ComingSoon>
  );
}

/* ---------------- Part 4 · Examiner review ---------------- */

export function Review() {
  return (
    <ComingSoon
      part="Part 4"
      title="Examiner review"
      question="Can a human verify the AI decision and correct it?"
      phase="Phase 2"
      owner="Member 4 — examiner interface and audit trail"
      scope={[
        "Show the original handwriting beside the text and the criterion verdicts",
        "Make the review band and its reason obvious at a glance",
        "Accept the AI score, or modify it with a comment",
        "Write the final score as a new row — never overwriting the AI result",
        "Record every action in the audit log",
      ]}
      endpoints={["GET /answers?review_status=", "POST /reviews", "POST /audit"]}
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card overflow-hidden">
          <p className="border-b border-line px-4 py-2.5 eyebrow">Original handwriting</p>
          <div className="flex h-[260px] items-center justify-center bg-surface2 text-sm text-ink3">
            the student's page, with zoom
          </div>
        </div>
        <div className="card flex flex-col overflow-hidden">
          <p className="border-b border-line px-4 py-2.5 eyebrow">AI recommendation</p>
          <div className="flex-1 p-4">
            <p className="font-display text-2xl font-bold tabular-nums">4 / 5</p>
            <p className="mt-1 text-sm text-ink2">
              Four of five criteria satisfied. No correct worked example was found.
            </p>
          </div>
          <div className="flex gap-2 border-t border-line p-4">
            <span className="btn-primary">Accept 4 / 5</span>
            <span className="btn-ghost">Modify score</span>
          </div>
        </div>
      </div>
    </ComingSoon>
  );
}

/* ---------------- Part 4 · Validation ---------------- */

export function Validation() {
  return (
    <ComingSoon
      part="Part 4"
      title="Validation"
      question="Does the system actually work, and how would we know?"
      phase="Phase 3"
      owner="Member 4 — metrics and the validation report"
      scope={[
        "Character and word error rate for recognition",
        "Exact agreement, mean absolute error and proportion within one mark",
        "Calibration curve and false-auto-accept rate for confidence",
        "Human review rate and processing time",
        "Marks on raw recognition versus corrected transcription",
      ]}
      endpoints={["GET /analytics/summary", "GET /analytics/calibration"]}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Character error rate", "—", "recognition"],
          ["Exact mark agreement", "—", "marking"],
          ["Within ±1 mark", "—", "marking"],
          ["False auto-accept", "—", "confidence"],
        ].map(([label, value, group]) => (
          <div key={label} className="card p-5">
            <p className="eyebrow">{label}</p>
            <p className="mt-2 font-display text-2xl font-bold tabular-nums">{value}</p>
            <p className="mt-1 font-mono text-[0.68rem] text-ink3">{group}</p>
          </div>
        ))}
        <div className="card col-span-full p-5">
          <p className="eyebrow">Calibration — stated confidence against measured correctness</p>
          <div className="mt-3 flex h-40 items-center justify-center rounded bg-surface2 text-sm text-ink3">
            plotted once a ground-truth set exists
          </div>
          <p className="mt-3 max-w-[64ch] text-sm text-ink2">
            Until this curve exists, no confidence threshold can be trusted to decide
            anything on its own. Producing it is the point of Phase 3.
          </p>
        </div>
      </div>
    </ComingSoon>
  );
}
