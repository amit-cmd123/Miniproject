/**
 * Part 2 - what a correct answer should contain.
 *
 * The screen a panel or an examiner looks at to answer "on what basis was
 * this marked?". It shows the rubric as data: every criterion, what it is
 * worth, what it is really testing, and what counts as an acceptable
 * alternative. The validation banner is the important part - a rubric whose
 * criteria do not sum to the question's marks produces scores that look
 * entirely reasonable and are wrong for every student, so it is surfaced
 * before anything is marked rather than discovered afterwards.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ExamDetail, Question, RubricValidation } from "../lib/types";

export function Rubrics() {
  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [validation, setValidation] = useState<RubricValidation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The bundled paper is seeded on first use, so the screen is never
      // empty just because nobody has posted an exam yet.
      const exams = await api.exams();
      const detail = exams.length ? await api.exam(exams[0].id) : await api.seedExam();
      setExam(detail);
      setValidation(await api.validateExam(detail.id));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not load the question bank. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-6">
      <header className="border-b border-line pb-5">
        <p className="eyebrow">Part 2 · Questions &amp; rubrics</p>
        <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
          What a correct answer must contain
        </h1>
        <p className="mt-1.5 max-w-[68ch] text-ink2">
          Academic judgement is stored as data, not prose: each question breaks into
          criteria, and each criterion says what it is testing and what counts as an
          acceptable alternative. Nothing downstream can award a mark that does not
          trace back to one of these.
        </p>
      </header>

      {loading && <p className="text-ink3">Loading the question bank…</p>}
      {error && (
        <p className="rounded-md border border-band4 bg-surface px-4 py-3 text-band4">
          {error}
        </p>
      )}

      {exam && (
        <>
          <section className="card flex flex-wrap items-center gap-x-8 gap-y-3 p-4">
            <div>
              <p className="eyebrow">Paper</p>
              <p className="mt-0.5 font-display text-lg font-semibold">{exam.title}</p>
              <p className="text-sm text-ink2">
                {exam.subject}
                {exam.subject_code ? ` · ${exam.subject_code}` : ""}
              </p>
            </div>
            <Stat label="Questions" value={String(exam.question_count)} />
            <Stat label="Total marks" value={String(exam.total_marks)} />
            <Stat
              label="Criteria"
              value={String(validation?.criteria_checked ?? "—")}
            />
          </section>

          {validation && <ValidationBanner validation={validation} />}

          <section className="flex flex-col gap-3">
            {exam.questions.map((question) => (
              <QuestionCard
                key={question.id}
                question={question}
                expanded={open === question.id}
                onToggle={() =>
                  setOpen((current) => (current === question.id ? null : question.id))
                }
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function ValidationBanner({ validation }: { validation: RubricValidation }) {
  const errors = validation.problems.filter((p) => p.severity === "error");
  const warnings = validation.problems.filter((p) => p.severity === "warning");

  return (
    <section
      className={`rounded-md border px-4 py-3 ${
        validation.is_valid ? "border-band1 bg-surface" : "border-band4 bg-surface"
      }`}
    >
      <p
        className={`font-display text-sm font-semibold ${
          validation.is_valid ? "text-band1" : "text-band4"
        }`}
      >
        {validation.is_valid
          ? `Rubrics are fit to mark with — ${validation.questions_checked} questions, ${validation.criteria_checked} criteria, ${validation.total_marks} marks.`
          : `${errors.length} rubric error${errors.length === 1 ? "" : "s"} — marking is blocked until these are fixed.`}
      </p>

      {validation.is_valid && !warnings.length && (
        <p className="mt-1 text-sm text-ink2">
          Every criterion sums correctly, each has essential concepts, and each
          question has an answer key.
        </p>
      )}

      {[...errors, ...warnings].length > 0 && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {[...errors, ...warnings].map((problem, index) => (
            <li key={index} className="flex gap-2 text-sm">
              <span
                className={`font-mono text-xs ${
                  problem.severity === "error" ? "text-band4" : "text-band3"
                }`}
              >
                {problem.question}
              </span>
              <span className="text-ink2">{problem.message}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function QuestionCard({
  question,
  expanded,
  onToggle,
}: {
  question: Question;
  expanded: boolean;
  onToggle: () => void;
}) {
  const rubric = question.rubric;
  const sum = rubric?.total_criterion_marks ?? 0;
  const balanced = Math.abs(sum - question.max_marks) < 0.001;

  return (
    <article className="card overflow-hidden">
      <button
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface2"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="font-mono text-sm font-semibold text-accent">
          {question.number}
        </span>
        <span className="flex-1">
          <span className="block text-sm">{question.text}</span>
          <span className="mt-1 block font-mono text-[0.68rem] text-ink3">
            {question.topic} · {question.question_type.replace(/_/g, " ")} ·{" "}
            {rubric ? `${rubric.criteria.length} criteria` : "no rubric"}
          </span>
        </span>
        <span
          className={`font-mono text-sm font-semibold tabular-nums ${
            balanced ? "text-ink" : "text-band4"
          }`}
        >
          {question.max_marks}
        </span>
        <span aria-hidden className="font-mono text-ink3">
          {expanded ? "−" : "+"}
        </span>
      </button>

      {expanded && rubric && (
        <div className="border-t border-line px-4 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="eyebrow">Marking criteria</p>
            <p className="font-mono text-[0.68rem] text-ink3">
              version {rubric.version} · criteria sum to {sum} of {question.max_marks}
            </p>
          </div>

          <ul className="mt-2 flex flex-col gap-3">
            {rubric.criteria.map((criterion) => (
              <li key={criterion.id} className="border-l-2 border-line pl-3">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-xs text-ink3">
                    {criterion.position}
                  </span>
                  <span className="flex-1 text-sm font-semibold">
                    {criterion.description}
                  </span>
                  <span className="font-mono text-sm tabular-nums">
                    {criterion.max_marks}
                  </span>
                </div>

                <dl className="mt-1 flex flex-col gap-0.5 text-xs text-ink2">
                  {criterion.essential_concepts.length > 0 && (
                    <Row label="Must convey" items={criterion.essential_concepts} />
                  )}
                  {criterion.acceptable_alternatives.length > 0 && (
                    <Row
                      label="Also accepted"
                      items={criterion.acceptable_alternatives}
                    />
                  )}
                  {criterion.common_mistakes.length > 0 && (
                    <Row label="Watch for" items={criterion.common_mistakes} />
                  )}
                </dl>

                <div className="mt-1 flex flex-wrap gap-1.5">
                  {!criterion.allows_partial && (
                    <Tag>all or nothing</Tag>
                  )}
                  {criterion.load_bearing && <Tag>load-bearing</Tag>}
                </div>
              </li>
            ))}
          </ul>

          {question.answer_key && (
            <details className="mt-4">
              <summary className="cursor-pointer font-display text-sm font-semibold">
                Model answer
              </summary>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-surface2 p-3 font-mono text-xs">
                {question.answer_key}
              </pre>
            </details>
          )}
        </div>
      )}

      {expanded && !rubric && (
        <p className="border-t border-line px-4 py-4 text-sm text-band4">
          This question has no active rubric, so it cannot be marked.
        </p>
      )}
    </article>
  );
}

function Row({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="flex gap-2">
      <dt className="w-[13ch] flex-none text-ink3">{label}</dt>
      <dd className="flex-1">{items.join(" · ")}</dd>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-line px-1.5 py-0.5 font-display text-[0.6rem] font-semibold uppercase tracking-wider text-ink3">
      {children}
    </span>
  );
}
