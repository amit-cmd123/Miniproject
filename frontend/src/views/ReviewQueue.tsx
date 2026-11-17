/**
 * Part 4 - the examiner's queue.
 *
 * Ordered by confidence, lowest first, because that is the order that saves
 * an examiner time: the scores most likely to be wrong are the ones worth
 * opening. Whether that ordering actually works is an empirical claim, and
 * the Validation screen is where it gets tested.
 *
 * Accepting is one click. Changing a score needs a number and nothing else -
 * no justification field, no workflow. Friction here would be paid by the
 * examiner on every answer, and the project's case rests on costing them
 * less than marking by hand.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Evaluation } from "../lib/types";
import {
  ConfidenceMeter,
  CriterionBreakdown,
  ReviewBandChip,
  ScoreBadge,
  WarningList,
} from "../components/Marks";

export function ReviewQueue({ refreshKey }: { refreshKey: number }) {
  const [queue, setQueue] = useState<Evaluation[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pending = await api.evaluations({ unreviewed: true });
      // Lowest confidence first: the examiner's time goes where it pays.
      pending.sort((a, b) => a.confidence - b.confidence);
      setQueue(pending);
      setOpen(pending.length ? pending[0].id : null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load the review queue.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const remaining = queue.filter((evaluation) => !(evaluation.id in done));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="eyebrow">Part 4 · Examiner review</p>
          <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
            Confirm or change the marks
          </h1>
          <p className="mt-1.5 max-w-[68ch] text-ink2">
            Least-confident first. Your decision is stored as a new record beside the
            machine's, never on top of it — which is what lets agreement between the two
            be measured afterwards, and turns routine marking into calibration data.
          </p>
        </div>
        <button className="btn-ghost" onClick={() => void load()}>
          Refresh queue
        </button>
      </header>

      {loading && <p className="text-ink3">Loading the queue…</p>}
      {error && (
        <p className="rounded-md border border-band4 bg-surface px-4 py-3 text-band4">
          {error}
        </p>
      )}

      {!loading && !queue.length && (
        <div className="card p-6">
          <p className="font-display text-sm font-semibold">Nothing waiting</p>
          <p className="mt-1.5 max-w-[60ch] text-ink2">
            Every marked answer has been decided on. Mark a booklet on the{" "}
            <strong>Evaluation</strong> screen and it will appear here.
          </p>
        </div>
      )}

      {queue.length > 0 && (
        <p className="text-sm text-ink2">
          <strong className="font-display">{remaining.length}</strong> of {queue.length}{" "}
          left to decide.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {queue.map((evaluation) => (
          <QueueItem
            key={evaluation.id}
            evaluation={evaluation}
            expanded={open === evaluation.id}
            decided={done[evaluation.id]}
            onToggle={() =>
              setOpen((current) => (current === evaluation.id ? null : evaluation.id))
            }
            onDecided={(score) => {
              setDone((current) => ({ ...current, [evaluation.id]: score }));
              // Move straight on to the next undecided one.
              const next = queue.find(
                (candidate) =>
                  candidate.id !== evaluation.id && !(candidate.id in done),
              );
              setOpen(next ? next.id : null);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function QueueItem({
  evaluation,
  expanded,
  decided,
  onToggle,
  onDecided,
}: {
  evaluation: Evaluation;
  expanded: boolean;
  decided: number | undefined;
  onToggle: () => void;
  onDecided: (score: number) => void;
}) {
  const [openedAt, setOpenedAt] = useState(() => Date.now());
  const [draft, setDraft] = useState(String(evaluation.score));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (expanded) setOpenedAt(Date.now());
  }, [expanded]);

  const submit = useCallback(
    async (action: "accept" | "modify") => {
      setBusy(true);
      setProblem(null);
      try {
        const review = await api.review({
          evaluationId: evaluation.id,
          action,
          finalScore: action === "accept" ? undefined : Number(draft),
          durationMs: Date.now() - openedAt,
        });
        onDecided(review.final_score);
      } catch (err) {
        setProblem(
          err instanceof ApiError ? err.message : "Could not save that decision.",
        );
      } finally {
        setBusy(false);
      }
    },
    [draft, evaluation.id, onDecided, openedAt],
  );

  return (
    <article
      className={`card overflow-hidden ${decided !== undefined ? "opacity-60" : ""}`}
    >
      <button
        className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-left hover:bg-surface2"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="font-mono text-sm font-semibold text-accent">
          {evaluation.question_number ?? "—"}
        </span>
        <ScoreBadge
          score={evaluation.score}
          max={evaluation.max_score}
          band={evaluation.review_band}
        />
        <span className="min-w-[10rem] flex-1">
          <ConfidenceMeter value={evaluation.confidence} band={evaluation.review_band} />
        </span>
        <ReviewBandChip band={evaluation.review_band} label={evaluation.band_label} />
        {decided !== undefined ? (
          <span className="font-display text-sm font-semibold text-band1">
            Decided: {decided}
          </span>
        ) : (
          <span aria-hidden className="font-mono text-ink3">
            {expanded ? "−" : "+"}
          </span>
        )}
      </button>

      {expanded && decided === undefined && (
        <div className="flex flex-col gap-3 border-t border-line px-4 py-4">
          {evaluation.overall_explanation && (
            <p className="max-w-[80ch] text-sm text-ink2">
              {evaluation.overall_explanation}
            </p>
          )}

          <CriterionBreakdown criteria={evaluation.criteria} />
          <WarningList warnings={evaluation.warnings} />

          <div className="flex flex-wrap items-center gap-3">
            <button
              className="btn-primary"
              onClick={() => void submit("accept")}
              disabled={busy}
            >
              Accept {evaluation.score}
            </button>
            <span className="text-ink3">or set</span>
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
            {problem && <span className="text-sm text-band4">{problem}</span>}
          </div>

          <p className="font-mono text-[0.66rem] text-ink3">
            answer {evaluation.answer_id.slice(0, 8)} · {evaluation.model_name} · rubric
            v{evaluation.rubric_version} · {evaluation.text_source.replace(/_/g, " ")}
          </p>
        </div>
      )}
    </article>
  );
}
