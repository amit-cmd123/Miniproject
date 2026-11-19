/**
 * Part 2 - what a correct answer should contain, and editing it.
 *
 * The screen a panel or an examiner looks at to answer "on what basis was
 * this marked?". It shows the rubric as data: every criterion, what it is
 * worth, what it is really testing, and what counts as an acceptable
 * alternative. The validation banner is the important part - a rubric whose
 * criteria do not sum to the question's marks produces scores that look
 * entirely reasonable and are wrong for every student, so it is surfaced
 * before anything is marked rather than discovered afterwards.
 *
 * Everything here is editable, because a marking scheme that can only be
 * changed by editing a JSON file and restarting the server is not owned by
 * the institution in any useful sense. Two rules shape how:
 *
 *   - A rubric is never mutated. Saving writes a new version and retires the
 *     old one, so a score awarded last week still resolves to the rubric it
 *     was actually marked against. Answer keys work the same way.
 *   - A question that has already been marked against cannot be deleted. Its
 *     scores cite its rubric; removing it would leave marks nobody can
 *     explain to the student who received them.
 */

import { useCallback, useEffect, useState } from "react";
import { RubricEditor } from "../components/RubricEditor";
import { api, ApiError } from "../lib/api";
import type { EngineState } from "../lib/engine";
import type {
  Exam,
  ExamDetail,
  ParsedPaper,
  Question,
  RubricValidation,
} from "../lib/types";

export function Rubrics({ engine }: { engine: EngineState }) {
  const [papers, setPapers] = useState<Exam[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [exam, setExam] = useState<ExamDetail | null>(null);
  const [validation, setValidation] = useState<RubricValidation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newPaper, setNewPaper] = useState(false);
  // A paper read out of a Word or PDF file, waiting to be approved. It is
  // held here and not written anywhere until the examiner says so.
  const [proposed, setProposed] = useState<ParsedPaper | null>(null);
  const [reading, setReading] = useState(false);

  /**
   * `wanted` names the paper to show. Importing creates additional papers and
   * the list is newest-first, so without an explicit choice an experiment
   * imported five minutes ago would quietly replace the real paper on screen.
   */
  const load = useCallback(
    async (keepOpen?: string | null, wanted?: string | null) => {
      setLoading(true);
      setError(null);
      try {
        // The bundled paper is seeded on first use, so the screen is never
        // empty just because nobody has posted an exam yet.
        let list = await api.exams();
        if (!list.length) {
          await api.seedExam();
          list = await api.exams();
        }
        setPapers(list);

        const target =
          (wanted && list.some((e) => e.id === wanted) && wanted) ||
          (chosen && list.some((e) => e.id === chosen) && chosen) ||
          list[0].id;
        setChosen(target);

        const detail = await api.exam(target);
        setExam(detail);
        setValidation(await api.validateExam(target));
        if (keepOpen !== undefined) setOpen(keepOpen);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not load the question bank. Is the backend running?",
        );
      } finally {
        setLoading(false);
      }
    },
    [chosen],
  );

  useEffect(() => {
    void load();
    // Deliberately once: `load` keeps the chosen paper itself, and re-running
    // on every change to it would refetch on each selection twice over.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function removePaper() {
    if (!exam) return;
    if (
      !window.confirm(
        `Delete the whole paper "${exam.title}" and all ${exam.question_count} ` +
          `of its questions? This cannot be undone, and is refused if anything ` +
          `has been marked against it.`,
      )
    ) {
      return;
    }
    setError(null);
    try {
      await api.deleteExam(exam.id);
      setNotice(`Deleted "${exam.title}".`);
      await load(null, null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "The paper could not be deleted.",
      );
    }
  }

  async function exportPaper() {
    if (!exam) return;
    setNotice(null);
    try {
      const document_ = await api.exportExam(exam.id);
      const blob = new Blob([JSON.stringify(document_, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${exam.subject_code || "exam"}_seed.json`;
      link.click();
      URL.revokeObjectURL(url);
      setNotice(
        "Exported. This is the same shape as data/exam/seed_exam.json, so it can " +
          "be committed to the repository and seeded elsewhere.",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed.");
    }
  }

  /** Read a typed paper. Nothing is saved; the result is a proposal. */
  async function readDocument(file: File) {
    setError(null);
    setNotice(null);
    setProposed(null);
    setReading(true);
    try {
      setProposed(await api.parseDocument(file, engine.engine));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "That document could not be read.",
      );
    } finally {
      setReading(false);
    }
  }

  /** Commit an approved proposal through the ordinary import route. */
  async function acceptProposal(seed: Record<string, unknown>) {
    setError(null);
    try {
      const created = await api.importExam(seed);
      setProposed(null);
      setNotice(
        `Imported "${created.title}" with ${created.question_count} question(s), ` +
          `worth ${created.total_marks} marks. Check each rubric below before ` +
          `marking against it.`,
      );
      await load(null, created.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "That paper could not be saved.",
      );
    }
  }

  async function importPaper(file: File) {
    setError(null);
    setNotice(null);
    try {
      const parsed = JSON.parse(await file.text());
      const created = await api.importExam(parsed);
      setNotice(
        `Imported "${created.title}" as a new paper with ${created.question_count} ` +
          `question(s), worth ${created.total_marks} marks.`,
      );
      await load(null, created.id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "That file could not be read as an exam definition.",
      );
    }
  }

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
      {notice && (
        <p className="rounded-md border border-band1 bg-surface px-4 py-3 text-sm text-ink2">
          {notice}
        </p>
      )}

      {exam && (
        <>
          <section className="card flex flex-wrap items-center gap-x-8 gap-y-3 p-4">
            <div>
              <p className="eyebrow">Paper</p>
              {papers.length > 1 ? (
                <select
                  className="input mt-1 max-w-[32ch] font-display text-base font-semibold"
                  value={chosen ?? exam.id}
                  onChange={(e) => void load(null, e.target.value)}
                >
                  {papers.map((paper) => (
                    <option key={paper.id} value={paper.id}>
                      {paper.title}
                      {paper.subject_code ? ` (${paper.subject_code})` : ""} —{" "}
                      {paper.question_count}q / {paper.total_marks}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="mt-0.5 font-display text-lg font-semibold">
                  {exam.title}
                </p>
              )}
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

            <div className="ml-auto flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() => setNewPaper(true)}
              >
                New paper
              </button>
              <button type="button" className="btn-ghost text-sm" onClick={exportPaper}>
                Export JSON
              </button>
              <label
                className={`btn-ghost cursor-pointer text-sm ${
                  reading ? "pointer-events-none opacity-60" : ""
                }`}
              >
                {reading ? "Reading\u2026" : "Import Word / PDF"}
                <input
                  type="file"
                  accept=".docx,.pdf,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void readDocument(file);
                    e.target.value = "";
                  }}
                />
              </label>
              <label className="btn-ghost cursor-pointer text-sm">
                Import JSON
                <input
                  type="file"
                  accept="application/json,.json"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void importPaper(file);
                    e.target.value = "";
                  }}
                />
              </label>
              {papers.length > 1 && (
                <button
                  type="button"
                  className="btn-ghost text-sm text-band4"
                  onClick={removePaper}
                >
                  Delete paper
                </button>
              )}
            </div>
          </section>

          {proposed && (
            <ImportPreview
              parsed={proposed}
              onAccept={acceptProposal}
              onCancel={() => setProposed(null)}
            />
          )}

          {newPaper && (
            <NewPaper
              onDone={(id) => {
                setNewPaper(false);
                setNotice(
                  "Paper created. Add its questions below, then open each one " +
                    "and choose Edit rubric.",
                );
                void load(null, id);
              }}
              onCancel={() => setNewPaper(false)}
            />
          )}

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
                onChanged={() => void load(question.id)}
                onDeleted={() => void load(null)}
                onError={setError}
              />
            ))}
          </section>

          {adding ? (
            <NewQuestion
              examId={exam.id}
              onDone={() => {
                setAdding(false);
                void load(null);
              }}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <button
              type="button"
              className="btn-ghost self-start"
              onClick={() => setAdding(true)}
            >
              + Add a question
            </button>
          )}
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
        validation.is_valid ? "border-band1" : "border-band4"
      } bg-surface`}
    >
      <p
        className={`font-display text-sm font-semibold ${
          validation.is_valid ? "text-band1" : "text-band4"
        }`}
      >
        {validation.is_valid
          ? `Rubrics are fit to mark with — ${validation.questions_checked} questions, ` +
            `${validation.criteria_checked} criteria, ${validation.total_marks} marks`
          : `${errors.length} problem(s) would make marking wrong`}
      </p>

      {!validation.is_valid && (
        <p className="mt-1 max-w-[68ch] text-sm text-ink2">
          A rubric whose criteria do not sum to its question silently caps every
          student, with a breakdown that looks entirely reasonable. Marking is
          refused until these are fixed.
        </p>
      )}

      {validation.problems.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {[...errors, ...warnings].map((problem, index) => (
            <li key={index} className="flex gap-2">
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

type Mode = "view" | "rubric" | "question" | "key";

function QuestionCard({
  question,
  expanded,
  onToggle,
  onChanged,
  onDeleted,
  onError,
}: {
  question: Question;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  onError: (message: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const rubric = question.rubric;
  const sum = rubric?.total_criterion_marks ?? 0;
  const balanced = Math.abs(sum - question.max_marks) < 0.001;

  async function remove() {
    if (
      !window.confirm(
        `Delete ${question.number ?? "this question"}? This cannot be undone. ` +
          `It is refused if anything has already been marked against it.`,
      )
    ) {
      return;
    }
    try {
      await api.deleteQuestion(question.id);
      onDeleted();
    } catch (err) {
      onError(
        err instanceof ApiError ? err.message : "The question could not be deleted.",
      );
    }
  }

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
            {rubric ? ` · v${rubric.version}` : ""}
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

      {expanded && (
        <div className="border-t border-line px-4 py-4">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => setMode(mode === "rubric" ? "view" : "rubric")}
            >
              {mode === "rubric" ? "Close rubric editor" : "Edit rubric"}
            </button>
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => setMode(mode === "question" ? "view" : "question")}
            >
              {mode === "question" ? "Close" : "Edit question"}
            </button>
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => setMode(mode === "key" ? "view" : "key")}
            >
              {mode === "key" ? "Close" : "Edit model answer"}
            </button>
            <button
              type="button"
              className="btn-ghost ml-auto text-sm text-band4"
              onClick={remove}
            >
              Delete question
            </button>
          </div>

          {mode === "question" && (
            <QuestionFields
              question={question}
              onSaved={() => {
                setMode("view");
                onChanged();
              }}
              onCancel={() => setMode("view")}
            />
          )}

          {mode === "key" && (
            <AnswerKeyField
              question={question}
              onSaved={() => {
                setMode("view");
                onChanged();
              }}
              onCancel={() => setMode("view")}
            />
          )}

          {mode === "rubric" && (
            <RubricEditor
              question={question}
              onSaved={() => {
                setMode("view");
                onChanged();
              }}
              onCancel={() => setMode("view")}
            />
          )}

          {mode === "view" && rubric && (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="eyebrow">Marking criteria</p>
                <p className="font-mono text-[0.68rem] text-ink3">
                  version {rubric.version} · criteria sum to {sum} of{" "}
                  {question.max_marks}
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
                      {!criterion.allows_partial && <Tag>all or nothing</Tag>}
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
            </>
          )}

          {mode === "view" && !rubric && (
            <p className="text-sm text-band4">
              This question has no active rubric, so it cannot be marked. Use
              <strong> Edit rubric</strong> to write one.
            </p>
          )}
        </div>
      )}
    </article>
  );
}

/** The question's own fields. The rubric is versioned separately. */
function QuestionFields({
  question,
  onSaved,
  onCancel,
}: {
  question: Question;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [number, setNumber] = useState(question.number ?? "");
  const [text, setText] = useState(question.text);
  const [topic, setTopic] = useState(question.topic ?? "");
  const [type, setType] = useState(question.question_type);
  const [marks, setMarks] = useState(question.max_marks);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rubricSum = question.rubric?.total_criterion_marks ?? 0;
  const willBreak =
    question.rubric != null && Math.abs(rubricSum - marks) > 0.001;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.updateQuestion(question.id, {
        number: number.trim() || null,
        text: text.trim(),
        topic: topic.trim() || null,
        question_type: type,
        max_marks: Number(marks),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <div className="grid gap-3 md:grid-cols-[6rem_1fr_8rem]">
        <Field label="Number" hint="Q1, Q2 …">
          <input
            className="input w-full font-mono"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
          />
        </Field>
        <Field label="Topic">
          <input
            className="input w-full"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </Field>
        <Field label="Marks">
          <input
            type="number"
            min={0.5}
            step={0.5}
            className="input w-full font-mono tabular-nums"
            value={marks}
            onChange={(e) => setMarks(Number(e.target.value))}
          />
        </Field>
      </div>

      <Field label="Question text">
        <textarea
          className="input min-h-[5rem] w-full"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>

      <Field label="Type">
        <select
          className="input w-full md:w-64"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="theory">theory</option>
          <option value="short_answer">short answer</option>
          <option value="long_answer">long answer</option>
          <option value="code">code</option>
          <option value="numerical">numerical</option>
          <option value="diagram">diagram</option>
        </select>
      </Field>

      {willBreak && (
        <p className="rounded-md border border-band3 bg-surface px-3 py-2 text-sm text-ink2">
          <strong className="text-band3">The rubric will no longer sum.</strong> Its
          criteria total {rubricSum} and you are setting the question to {marks}.
          That is allowed, and reported as invalid until you adjust the criteria —
          deciding what each one is now worth is your judgement, not something this
          screen should guess by rescaling them.
        </p>
      )}

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-3 py-2 text-sm text-band4">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={save}
          disabled={busy || text.trim().length < 3}
        >
          {busy ? "Saving…" : "Save question"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function AnswerKeyField({
  question,
  onSaved,
  onCancel,
}: {
  question: Question;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(question.answer_key ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveAnswerKey(question.id, value);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <Field
        label="Model answer"
        hint="Shown to the marker as a reference, never as text to match. A student who says the same thing differently still scores."
      >
        <textarea
          className="input min-h-[9rem] w-full font-mono text-xs"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </Field>

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-3 py-2 text-sm text-band4">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={save}
          disabled={busy || value.trim().length === 0}
        >
          {busy ? "Saving…" : "Save as a new version"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <span className="text-sm text-ink3">
          The previous key is kept, deactivated.
        </span>
      </div>
    </div>
  );
}

/**
 * Starting a new paper.
 *
 * Here so that a whole exam can be built without touching a file. Export and
 * Import exist for backup and for moving a finished paper between machines -
 * they are not meant to be the way a marking scheme gets written, and if
 * hand-editing JSON were the only route in then the rubric would not really
 * be owned by the examiner at all.
 */
function NewPaper({
  onDone,
  onCancel,
}: {
  onDone: (examId: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("");
  const [code, setCode] = useState("");
  const [term, setTerm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createExam({
        title: title.trim(),
        subject: subject.trim(),
        subject_code: code.trim() || null,
        term: term.trim() || null,
      });
      onDone(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the paper.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-3 p-4">
      <p className="eyebrow">New paper</p>

      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Title">
          <input
            className="input w-full"
            value={title}
            placeholder="Data Structures — Mid-term"
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Subject">
          <input
            className="input w-full"
            value={subject}
            placeholder="Computer Science"
            onChange={(e) => setSubject(e.target.value)}
          />
        </Field>
        <Field
          label="Subject code"
          hint="Optional, but it must be unique — seeding and import match on it."
        >
          <input
            className="input w-full font-mono"
            value={code}
            placeholder="EVN-DS-02"
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
        <Field label="Term (optional)">
          <input
            className="input w-full"
            value={term}
            placeholder="2026 Odd Semester"
            onChange={(e) => setTerm(e.target.value)}
          />
        </Field>
      </div>

      <p className="text-sm text-ink3">
        The paper starts empty. Add each question, then open it and choose{" "}
        <strong>Edit rubric</strong> to write the criteria. No files involved.
      </p>

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-3 py-2 text-sm text-band4">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={create}
          disabled={busy || title.trim().length < 3 || subject.trim().length < 2}
        >
          {busy ? "Creating…" : "Create paper"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </section>
  );
}

/**
 * Adding a question.
 *
 * Deliberately creates the question first, with no rubric, rather than asking
 * for everything at once. A half-finished paper is a normal state - it is
 * reported as not yet markable - and a long form that must be completed in
 * one sitting is how rubrics end up with placeholder criteria in them.
 */
function NewQuestion({
  examId,
  onDone,
  onCancel,
}: {
  examId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [number, setNumber] = useState("");
  const [text, setText] = useState("");
  const [topic, setTopic] = useState("");
  const [marks, setMarks] = useState(5);
  const [type, setType] = useState("theory");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api.addQuestion(examId, {
        number: number.trim() || null,
        text: text.trim(),
        topic: topic.trim() || null,
        question_type: type,
        max_marks: Number(marks),
        answer_key: key.trim() || null,
        rubric: null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the question.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-3 p-4">
      <p className="eyebrow">New question</p>

      <div className="grid gap-3 md:grid-cols-[6rem_1fr_8rem]">
        <Field label="Number" hint="Q1, Q2 …">
          <input
            className="input w-full font-mono"
            value={number}
            placeholder="Q7"
            onChange={(e) => setNumber(e.target.value)}
          />
        </Field>
        <Field label="Topic">
          <input
            className="input w-full"
            value={topic}
            placeholder="Recursion"
            onChange={(e) => setTopic(e.target.value)}
          />
        </Field>
        <Field label="Marks">
          <input
            type="number"
            min={0.5}
            step={0.5}
            className="input w-full font-mono tabular-nums"
            value={marks}
            onChange={(e) => setMarks(Number(e.target.value))}
          />
        </Field>
      </div>

      <Field label="Question text">
        <textarea
          className="input min-h-[5rem] w-full"
          value={text}
          placeholder="Explain what recursion is, with an example."
          onChange={(e) => setText(e.target.value)}
        />
      </Field>

      <Field
        label="Type"
        hint="Passed to the marker as context: a code answer and a theory answer are not read the same way."
      >
        <select
          className="input w-full md:w-64"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="theory">theory</option>
          <option value="short_answer">short answer</option>
          <option value="long_answer">long answer</option>
          <option value="code">code</option>
          <option value="numerical">numerical</option>
          <option value="diagram">diagram</option>
        </select>
      </Field>

      <Field label="Model answer (optional)">
        <textarea
          className="input min-h-[4rem] w-full font-mono text-xs"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </Field>

      <p className="text-sm text-ink3">
        The question is created without a rubric. Open it and choose{" "}
        <strong>Edit rubric</strong> to write the criteria — until then it is
        reported as not yet markable.
      </p>

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-3 py-2 text-sm text-band4">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          className="btn-primary"
          onClick={create}
          disabled={busy || text.trim().length < 3}
        >
          {busy ? "Adding…" : "Add question"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="eyebrow">{label}</label>
      <div className="mt-1">{children}</div>
      {hint && <p className="mt-1 max-w-[60ch] text-xs text-ink3">{hint}</p>}
    </div>
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


/* ------------------------------------------------------------------ */

/**
 * What a document turned out to contain, shown before anything is saved.
 *
 * The whole point of this panel is that it is refusable. A marking scheme
 * decides a student's grade; a parser - or a language model - reading one out
 * of a Word file is a proposal about what the document said, and the examiner
 * is the one who knows whether it got it right. So the criteria are laid out
 * with their marks and their sums, the parser's own doubts are printed, and
 * the lines it could not place are listed, because a criterion silently
 * dropped is invisible in a rubric that otherwise looks complete.
 */
function ImportPreview({
  parsed,
  onAccept,
  onCancel,
}: {
  parsed: ParsedPaper;
  onAccept: (seed: Record<string, unknown>) => void | Promise<void>;
  onCancel: () => void;
}) {
  const seed = parsed.seed as {
    exam?: { title?: string; subject?: string; code?: string };
    questions?: {
      number?: string;
      text: string;
      max_marks: number;
      answer_key?: string;
      criteria?: { position: number; description: string; max_marks: number }[];
    }[];
  };

  const [title, setTitle] = useState(seed.exam?.title ?? "Imported paper");
  const [subject, setSubject] = useState(seed.exam?.subject ?? "Unspecified");
  const [saving, setSaving] = useState(false);

  const questions = seed.questions ?? [];
  const mismatched = questions.filter((q) => {
    const criteria = q.criteria ?? [];
    if (!criteria.length) return false;
    const total = criteria.reduce((sum, c) => sum + c.max_marks, 0);
    return Math.abs(total - q.max_marks) > 0.001;
  });

  async function accept() {
    setSaving(true);
    try {
      await onAccept({
        ...parsed.seed,
        exam: { ...(seed.exam ?? {}), title, subject },
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line p-5">
        <div>
          <p className="eyebrow">Read from a document — not saved yet</p>
          <h2 className="mt-1 font-display text-lg font-bold tracking-tight">
            {parsed.question_count} question(s), {parsed.total_marks} marks
          </h2>
          <p className="mt-1 text-sm text-ink2">
            <span className="font-mono text-xs">{parsed.source.filename}</span> ·{" "}
            {parsed.source.kind.toUpperCase()}
            {parsed.source.page_count > 1 && ` · ${parsed.source.page_count} pages`}
            {parsed.source.table_count > 0 &&
              ` · ${parsed.source.table_count} table(s)`}{" "}
            · read by{" "}
            {parsed.strategy === "gemini" ? "Gemini" : "the built-in parser"}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost text-sm" onClick={onCancel} disabled={saving}>
            Discard
          </button>
          <button className="btn-primary text-sm" onClick={() => void accept()} disabled={saving}>
            {saving ? "Saving\u2026" : "Create this paper"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 border-b border-line p-5 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="eyebrow">Paper title</span>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="eyebrow">Subject</span>
          <input
            className="input"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
        </label>
      </div>

      {(parsed.warnings.length > 0 || mismatched.length > 0) && (
        <div className="border-b border-line bg-surface2 p-5">
          <p className="eyebrow text-band3">Check these before saving</p>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm text-ink2">
            {mismatched.length > 0 && (
              <li>
                <span className="font-semibold text-band3">
                  {mismatched.length} question(s) have criteria that do not sum to
                  the question's marks.
                </span>{" "}
                They are imported exactly as the document had them — rebalancing a
                marking scheme is your call, not the importer's. Fix each one in the
                rubric editor below, or that question cannot be marked.
              </li>
            )}
            {parsed.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <ol className="divide-y divide-line">
        {questions.map((question, index) => {
          const criteria = question.criteria ?? [];
          const total = criteria.reduce((sum, c) => sum + c.max_marks, 0);
          const sums = !criteria.length || Math.abs(total - question.max_marks) <= 0.001;
          return (
            <li key={index} className="p-5">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-xs font-semibold text-accent">
                  {question.number ?? `Q${index + 1}`}
                </span>
                <span className="font-display text-sm font-semibold">
                  {question.max_marks} marks
                </span>
                {criteria.length > 0 && (
                  <span
                    className={`font-mono text-xs ${sums ? "text-band1" : "text-band4"}`}
                  >
                    criteria sum to {total}
                    {sums ? "" : " — does not match"}
                  </span>
                )}
                {!criteria.length && (
                  <span className="font-mono text-xs text-band3">
                    no rubric found — add one below
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-sm text-ink">{question.text}</p>
              {criteria.length > 0 && (
                <ul className="mt-2 flex flex-col gap-1">
                  {criteria.map((criterion) => (
                    <li
                      key={criterion.position}
                      className="flex gap-3 text-sm text-ink2"
                    >
                      <span className="w-10 shrink-0 text-right font-mono text-xs text-ink3">
                        {criterion.max_marks}
                      </span>
                      <span>{criterion.description}</span>
                    </li>
                  ))}
                </ul>
              )}
              {question.answer_key && (
                <p className="mt-2 border-l-2 border-line pl-3 text-xs text-ink3">
                  <span className="font-semibold">Answer key: </span>
                  {question.answer_key}
                </p>
              )}
            </li>
          );
        })}
      </ol>

      {parsed.unplaced_lines.length > 0 && (
        <details className="border-t border-line p-5">
          <summary className="cursor-pointer font-display text-sm font-semibold">
            {parsed.unplaced_lines.length} line(s) the parser could not place
          </summary>
          <p className="mt-2 text-xs text-ink3">
            Headers and page furniture usually land here, which is harmless. A
            criterion in this list is not harmless — it means the rubric above is
            missing it.
          </p>
          <ul className="mt-2 flex flex-col gap-0.5 font-mono text-xs text-ink2">
            {parsed.unplaced_lines.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
