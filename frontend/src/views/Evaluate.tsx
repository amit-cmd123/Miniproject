/**
 * Part 3 - marking a transcribed booklet, question by question.
 *
 * The screen follows the order the work actually happens in:
 *
 *   1. choose a booklet that has been transcribed
 *   2. check *where* each question's answer was found, before trusting marks
 *      derived from it - a mis-split booklet produces confident nonsense, and
 *      this is the cheap place to catch it
 *   3. mark, and read the result criterion by criterion
 *   4. accept or change each score, which is Part 4 and belongs here because
 *      it is the same sitting of work
 *
 * Step 2 exists because of something the pipeline cannot know: if the split
 * put Q4's answer under Q5, every mark below is wrong and every confidence
 * number is high, because the marker did its job correctly on the wrong text.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { EngineToggle } from "../components/EngineToggle";
import type { EngineState } from "../lib/engine";
import type {
  AnswerDetail,
  BookletResult,
  BookletSegmentation,
  Evaluation,
} from "../lib/types";
import {
  ConfidenceMeter,
  ConfidenceSignals,
  CriterionBreakdown,
  ReviewBandChip,
  ScoreBadge,
  WarningList,
} from "../components/Marks";

interface Booklet {
  ref: string;
  filename: string;
  pages: number;
  transcribedPages: number;
  when: string;
}

type Phase = "choosing" | "previewing" | "marking" | "done" | "error";

export function Evaluate({
  refreshKey,
  engine,
}: {
  refreshKey: number;
  engine: EngineState;
}) {
  const [booklets, setBooklets] = useState<Booklet[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [segmentation, setSegmentation] = useState<BookletSegmentation | null>(null);
  const [result, setResult] = useState<BookletResult | null>(null);
  const [phase, setPhase] = useState<Phase>("choosing");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const answers = await api.listAnswers();
        if (!cancelled) setBooklets(groupIntoBooklets(answers));
      } catch {
        if (!cancelled)
          setError("Could not reach the backend. Is it running on port 8000?");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Marking six questions with two readings each is a minute of waiting.
  // Silence that long reads as a hung page.
  useEffect(() => {
    if (phase !== "marking") return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 100);
    return () => clearInterval(timer);
  }, [phase]);

  const preview = useCallback(async (ref: string) => {
    setChosen(ref);
    setResult(null);
    setError(null);
    setSegmentation(null);
    setPhase("previewing");
    try {
      setSegmentation(await api.segmentation(ref));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not split that booklet.");
      setPhase("error");
    }
  }, []);

  const mark = useCallback(async () => {
    if (!chosen) return;
    setPhase("marking");
    setElapsed(0);
    setError(null);
    try {
      setResult(await api.evaluateBooklet(chosen, { engine: engine.engine }));
      setPhase("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Marking failed.");
      setPhase("error");
    }
  }, [chosen, engine.engine]);

  const reset = useCallback(() => {
    setChosen(null);
    setSegmentation(null);
    setResult(null);
    setError(null);
    setPhase("choosing");
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="eyebrow">Part 3 · Evaluation &amp; confidence</p>
          <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
            Mark a booklet against the rubric
          </h1>
          <p className="mt-1.5 max-w-[68ch] text-ink2">
            Each answer is judged criterion by criterion, twice and independently. The
            marks are then computed in Python from those verdicts — the model never sees
            a mark value and never adds anything up, so the same verdicts always give
            the same score.
          </p>
        </div>
        {(segmentation || result) && (
          <button className="btn-ghost" onClick={reset}>
            Choose another booklet
          </button>
        )}
      </header>

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-4 py-3 text-band4">
          {error}
        </p>
      )}

      <EngineToggle state={engine} />

      {phase === "choosing" && (
        <BookletPicker booklets={booklets} onChoose={preview} />
      )}

      {chosen && segmentation && !result && (
        <SegmentationPreview
          segmentation={segmentation}
          busy={phase === "marking"}
          elapsed={elapsed}
          onMark={mark}
        />
      )}

      {result && <BookletReport result={result} />}
    </div>
  );
}

/** Pages of one upload share a document_ref, so a booklet is a group of them. */
function groupIntoBooklets(answers: AnswerDetail[]): Booklet[] {
  const groups = new Map<string, AnswerDetail[]>();
  for (const answer of answers) {
    // page_number is null on the derived per-question rows a marking run
    // writes; those are not booklets of their own.
    if (!answer.document_ref || answer.page_number === null) continue;
    const list = groups.get(answer.document_ref) ?? [];
    list.push(answer);
    groups.set(answer.document_ref, list);
  }

  return [...groups.entries()]
    .map(([ref, pages]) => ({
      ref,
      filename: pages[0].source_filename ?? pages[0].original_filename ?? "booklet",
      pages: pages.length,
      transcribedPages: pages.filter((p) => p.latest_ocr).length,
      when: pages[0].created_at,
    }))
    .sort((a, b) => b.when.localeCompare(a.when));
}

function BookletPicker({
  booklets,
  onChoose,
}: {
  booklets: Booklet[];
  onChoose: (ref: string) => void;
}) {
  if (!booklets.length) {
    return (
      <div className="card p-6">
        <p className="font-display text-sm font-semibold">Nothing to mark yet</p>
        <p className="mt-1.5 max-w-[60ch] text-ink2">
          Marking works from a transcribed booklet. Go to{" "}
          <strong>Transcribe</strong>, upload a scanned answer booklet as a PDF, and it
          will appear here.
        </p>
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <p className="eyebrow">Transcribed booklets</p>
      {booklets.map((booklet) => (
        <button
          key={booklet.ref}
          onClick={() => onChoose(booklet.ref)}
          className="card flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-left hover:bg-surface2"
        >
          <span className="flex-1 font-display text-sm font-semibold">
            {booklet.filename}
          </span>
          <span className="font-mono text-xs text-ink3">
            {booklet.transcribedPages}/{booklet.pages} pages read
          </span>
          <span className="font-mono text-xs text-ink3">
            {new Date(booklet.when).toLocaleString()}
          </span>
          <span className="font-display text-sm font-semibold text-accent">Mark →</span>
        </button>
      ))}
    </section>
  );
}

function SegmentationPreview({
  segmentation,
  busy,
  elapsed,
  onMark,
}: {
  segmentation: BookletSegmentation;
  busy: boolean;
  elapsed: number;
  onMark: () => void;
}) {
  const found = segmentation.segments.filter((s) => s.found);
  const byMarker = found.filter((s) => s.located_by === "marker").length;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Step 1 · Where each answer was found</p>
          <p className="mt-1 max-w-[62ch] text-sm text-ink2">
            {found.length} of {segmentation.segments.length} answers located
            {byMarker > 0 && ` (${byMarker} by the student's own numbering)`}. Check
            these before trusting the marks — if an answer is under the wrong question,
            the marking will be confidently wrong.
          </p>
        </div>
        <button className="btn-primary" onClick={onMark} disabled={busy}>
          {busy ? `Marking… ${elapsed.toFixed(0)}s` : "Mark this booklet"}
        </button>
      </div>

      <WarningList warnings={segmentation.warnings} />

      <ul className="flex flex-col gap-2">
        {segmentation.segments.map((segment) => (
          <li key={segment.question_id} className="card p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-sm font-semibold text-accent">
                {segment.question_number}
              </span>
              <span className="flex-1 text-sm text-ink2">
                {segment.question_text.slice(0, 110)}
                {segment.question_text.length > 110 ? "…" : ""}
              </span>
              <span className="font-mono text-xs text-ink3">
                {segment.max_marks} marks
              </span>
            </div>

            {segment.found ? (
              <>
                <p className="mt-2 font-mono text-[0.68rem] text-ink3">
                  page{segment.page_numbers.length === 1 ? "" : "s"}{" "}
                  {segment.page_numbers.join(", ")} · located by {segment.located_by} ·
                  transcription {(segment.transcription_confidence * 100).toFixed(0)}%
                </p>
                <pre className="mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-surface2 p-3 font-mono text-xs">
                  {segment.text}
                </pre>
              </>
            ) : (
              <p className="mt-2 text-sm text-band3">
                No answer was located for this question. It will score zero unless an
                examiner finds it.
              </p>
            )}
          </li>
        ))}
      </ul>

      {segmentation.unmatched_text && (
        <details className="card p-4">
          <summary className="cursor-pointer font-display text-sm font-semibold">
            Unassigned text ({segmentation.unmatched_text.split("\n").length} lines)
          </summary>
          <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-ink2">
            {segmentation.unmatched_text}
          </pre>
        </details>
      )}
    </section>
  );
}

function BookletReport({ result }: { result: BookletResult }) {
  const [reviewed, setReviewed] = useState<Record<string, number>>({});

  const finalTotal = useMemo(() => {
    return result.evaluations.reduce(
      (sum, evaluation) => sum + (reviewed[evaluation.id] ?? evaluation.score),
      0,
    );
  }, [result.evaluations, reviewed]);

  const changed = Object.keys(reviewed).length;

  return (
    <section className="flex flex-col gap-5">
      <div className="card flex flex-wrap items-center gap-x-10 gap-y-4 p-5">
        <div>
          <p className="eyebrow">Total</p>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="font-display text-4xl font-bold tabular-nums">
              {round(finalTotal)}
            </span>
            <span className="font-mono text-lg text-ink3">/ {result.total_max}</span>
          </div>
          <p className="mt-0.5 font-mono text-xs text-ink3">
            {((finalTotal / result.total_max) * 100).toFixed(1)}% ·{" "}
            {result.questions_marked} of {result.questions_total} questions marked
            {changed > 0 && ` · ${changed} score${changed === 1 ? "" : "s"} changed by you`}
          </p>
        </div>

        <div className="min-w-[16rem] flex-1">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Overall marking confidence</p>
            <ReviewBandChip band={result.review_band} label={result.band_label} />
          </div>
          <div className="mt-2">
            <ConfidenceMeter
              value={result.overall_confidence}
              band={result.review_band}
            />
          </div>
        </div>

        <div>
          <p className="eyebrow">Took</p>
          <p className="mt-1 font-mono text-lg tabular-nums">
            {(result.duration_ms / 1000).toFixed(1)}s
          </p>
        </div>
      </div>

      {result.needs_review.length > 0 && (
        <p className="rounded-md border border-band3 bg-surface px-4 py-3 text-sm">
          <strong className="font-display">
            {result.needs_review.length} question
            {result.needs_review.length === 1 ? "" : "s"} need review:
          </strong>{" "}
          <span className="font-mono">{result.needs_review.join(", ")}</span>. No score
          is auto-accepted — the top band is a candidate for it, pending a measured
          false-accept rate.
        </p>
      )}

      <WarningList warnings={result.warnings} />

      {result.evaluations.map((evaluation) => (
        <QuestionResult
          key={evaluation.id}
          evaluation={evaluation}
          onReviewed={(score) =>
            setReviewed((current) => ({ ...current, [evaluation.id]: score }))
          }
        />
      ))}
    </section>
  );
}

function QuestionResult({
  evaluation,
  onReviewed,
}: {
  evaluation: Evaluation;
  onReviewed: (score: number) => void;
}) {
  const [openedAt] = useState(() => Date.now());
  const [saved, setSaved] = useState<number | null>(null);
  const [draft, setDraft] = useState(String(evaluation.score));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = useCallback(
    async (action: "accept" | "modify") => {
      setBusy(true);
      setProblem(null);
      const score = action === "accept" ? evaluation.score : Number(draft);
      try {
        const review = await api.review({
          evaluationId: evaluation.id,
          action,
          finalScore: action === "accept" ? undefined : score,
          // Recorded, not estimated: the time-saving claim depends on it.
          durationMs: Date.now() - openedAt,
        });
        setSaved(review.final_score);
        onReviewed(review.final_score);
      } catch (err) {
        setProblem(err instanceof ApiError ? err.message : "Could not save that review.");
      } finally {
        setBusy(false);
      }
    },
    [draft, evaluation.id, evaluation.score, onReviewed, openedAt],
  );

  return (
    <article className="flex flex-col gap-3 border-t border-line pt-5">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-sm font-semibold text-accent">
            {evaluation.question_number}
          </span>
          <ScoreBadge
            score={evaluation.score}
            max={evaluation.max_score}
            band={evaluation.review_band}
          />
        </div>

        <div className="min-w-[14rem] flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="eyebrow">Confidence</p>
            <ReviewBandChip band={evaluation.review_band} label={evaluation.band_label} />
          </div>
          <div className="mt-1.5">
            <ConfidenceMeter
              value={evaluation.confidence}
              band={evaluation.review_band}
            />
          </div>
        </div>
      </div>

      {evaluation.overall_explanation && (
        <p className="max-w-[80ch] text-sm text-ink2">{evaluation.overall_explanation}</p>
      )}

      <CriterionBreakdown criteria={evaluation.criteria} />
      <WarningList warnings={evaluation.warnings} />
      <ConfidenceSignals evaluation={evaluation} />

      <div className="card flex flex-wrap items-center gap-3 p-3">
        <p className="eyebrow flex-none">Examiner decision</p>
        {saved === null ? (
          <>
            <button
              className="btn-primary"
              onClick={() => void submit("accept")}
              disabled={busy}
            >
              Accept {evaluation.score}
            </button>
            <span className="text-ink3">or</span>
            <input
              type="number"
              step="0.5"
              min={0}
              max={evaluation.max_score}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="w-20 rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm"
              aria-label="Corrected score"
            />
            <button
              className="btn-ghost"
              onClick={() => void submit("modify")}
              disabled={busy || Number(draft) === evaluation.score}
            >
              Save change
            </button>
          </>
        ) : (
          <p className="text-sm">
            <strong className="font-display">Recorded: {saved}</strong>
            {saved !== evaluation.score && (
              <span className="text-ink2">
                {" "}
                (machine said {evaluation.score}; the difference is kept for
                measuring agreement)
              </span>
            )}
          </p>
        )}
        {problem && <span className="text-sm text-band4">{problem}</span>}
      </div>

      <p className="font-mono text-[0.66rem] text-ink3">
        {evaluation.provider} · {evaluation.model_name} · prompt{" "}
        {evaluation.prompt_version} · rubric v{evaluation.rubric_version} ·{" "}
        {evaluation.text_source.replace(/_/g, " ")} ·{" "}
        {(evaluation.duration_ms / 1000).toFixed(1)}s
      </p>
    </article>
  );
}

function round(value: number): string {
  return value % 1 === 0 ? String(value) : value.toFixed(1);
}
