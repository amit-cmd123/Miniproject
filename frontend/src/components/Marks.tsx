/**
 * Shared presentation for a marked answer.
 *
 * The interface has one job here that matters more than looking tidy: a score
 * must never appear without the reasoning that produced it, and reasoning the
 * system could not verify must be visibly marked as such. So the criterion
 * table always shows the quotation behind each mark, and a quotation that was
 * not found in the transcription is flagged rather than quietly rendered.
 */

import type { Evaluation, EvaluationCriterion, ReviewBand, Verdict } from "../lib/types";

const BAND_STYLE: Record<ReviewBand, { bg: string; text: string; ring: string }> = {
  auto_accept: { bg: "bg-band1", text: "text-band1", ring: "border-band1" },
  quick_review: { bg: "bg-band2", text: "text-band2", ring: "border-band2" },
  mandatory_review: { bg: "bg-band3", text: "text-band3", ring: "border-band3" },
  detailed_verification: { bg: "bg-band4", text: "text-band4", ring: "border-band4" },
};

export function reviewBandStyle(band: ReviewBand) {
  return BAND_STYLE[band] ?? BAND_STYLE.detailed_verification;
}

const VERDICT_LABEL: Record<Verdict, string> = {
  satisfied: "Met",
  partially_satisfied: "Partly met",
  not_satisfied: "Not met",
};

const VERDICT_STYLE: Record<Verdict, string> = {
  satisfied: "text-band1 border-band1",
  partially_satisfied: "text-band3 border-band3",
  not_satisfied: "text-band4 border-band4",
};

export function ReviewBandChip({ band, label }: { band: ReviewBand; label: string }) {
  const style = reviewBandStyle(band);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1
                  font-display text-[0.7rem] font-semibold uppercase tracking-wider
                  ${style.ring} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.bg}`} />
      {label}
    </span>
  );
}

/** The score, large, with the maximum it is out of. */
export function ScoreBadge({
  score,
  max,
  band,
}: {
  score: number;
  max: number;
  band: ReviewBand;
}) {
  const style = reviewBandStyle(band);
  return (
    <div className="flex items-baseline gap-1">
      <span className={`font-display text-3xl font-bold tabular-nums ${style.text}`}>
        {score % 1 === 0 ? score : score.toFixed(1)}
      </span>
      <span className="font-mono text-base text-ink3">/ {max % 1 === 0 ? max : max.toFixed(1)}</span>
    </div>
  );
}

/** Confidence as a bar, coloured by the band it falls in. */
export function ConfidenceMeter({
  value,
  band,
  label = "Marking confidence",
}: {
  value: number;
  band: ReviewBand;
  label?: string;
}) {
  const style = reviewBandStyle(band);
  const pct = Math.round(value * 1000) / 10;
  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full bg-surface2"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className={`h-full rounded-full ${style.bg} transition-[width] duration-500`}
          style={{ width: `${Math.max(pct, 1.5)}%` }}
        />
      </div>
      <span className="font-mono text-sm font-semibold tabular-nums">{pct.toFixed(1)}%</span>
    </div>
  );
}

function CriterionRow({ criterion }: { criterion: EvaluationCriterion }) {
  const full = criterion.awarded_marks >= criterion.max_marks - 1e-6;
  const none = criterion.awarded_marks <= 1e-6;

  return (
    <li className="border-t border-line px-4 py-3 first:border-t-0">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1.5">
        <span className="font-mono text-xs text-ink3">{criterion.position}</span>
        <p className="min-w-[18ch] flex-1 text-sm">{criterion.description}</p>

        <span
          className={`rounded border px-1.5 py-0.5 font-display text-[0.62rem]
                      font-semibold uppercase tracking-wider ${VERDICT_STYLE[criterion.verdict]}`}
        >
          {VERDICT_LABEL[criterion.verdict] ?? criterion.verdict}
        </span>

        <span
          className={`font-mono text-sm font-semibold tabular-nums ${
            full ? "text-band1" : none ? "text-band4" : "text-band3"
          }`}
        >
          {criterion.awarded_marks}/{criterion.max_marks}
        </span>
      </div>

      {criterion.reason && (
        <p className="mt-1.5 pl-6 text-sm text-ink2">{criterion.reason}</p>
      )}

      {criterion.evidence_quote && (
        <blockquote
          className={`mt-1.5 ml-6 border-l-2 pl-3 font-mono text-xs ${
            criterion.evidence_found
              ? "border-line text-ink2"
              : "border-band4 text-band4"
          }`}
        >
          “{criterion.evidence_quote}”
          {!criterion.evidence_found && (
            <span className="mt-1 block font-display text-[0.68rem] font-semibold uppercase tracking-wider">
              Not found in the transcription — this mark is unverified
            </span>
          )}
        </blockquote>
      )}

      {!criterion.evidence_quote && criterion.verdict !== "not_satisfied" && (
        <p className="mt-1.5 pl-6 font-display text-[0.68rem] font-semibold uppercase tracking-wider text-band3">
          No quotation was given for this mark
        </p>
      )}
    </li>
  );
}

export function CriterionBreakdown({ criteria }: { criteria: EvaluationCriterion[] }) {
  if (!criteria.length) {
    return <p className="text-sm text-ink3">No criterion detail was recorded.</p>;
  }
  return (
    <ul className="card overflow-hidden">
      {criteria.map((criterion) => (
        <CriterionRow key={criterion.id} criterion={criterion} />
      ))}
    </ul>
  );
}

const SIGNAL_LABEL: Record<string, string> = {
  transcription: "Transcription",
  agreement: "Marker agreement",
  grounding: "Evidence grounding",
  decisiveness: "Decisiveness",
};

/**
 * What the confidence number was made of.
 *
 * Shown because a single percentage is not actionable: 62% caused by a poor
 * transcription is fixed by correcting the text, and 62% caused by the two
 * readings disagreeing is fixed by a human deciding. The breakdown says which.
 */
export function ConfidenceSignals({ evaluation }: { evaluation: Evaluation }) {
  const { signals = {}, weights = {}, unmeasured = [], samples } =
    evaluation.confidence_signals ?? {};
  const names = Object.keys(SIGNAL_LABEL);

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">Where this confidence came from</p>
        <p className="font-mono text-[0.68rem] text-ink3">
          weighted geometric mean · {samples ?? 1} reading{samples === 1 ? "" : "s"}
        </p>
      </div>

      <dl className="mt-3 flex flex-col gap-2">
        {names.map((name) => {
          const value = signals[name];
          const weight = weights[name];
          const missing = value === undefined || unmeasured.includes(name);
          return (
            <div key={name} className="flex items-center gap-3">
              <dt className="w-[14ch] flex-none text-sm text-ink2">{SIGNAL_LABEL[name]}</dt>
              <dd className="flex flex-1 items-center gap-3">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface2">
                  {!missing && (
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.max((value ?? 0) * 100, 1.5)}%` }}
                    />
                  )}
                </div>
                <span className="w-[6ch] flex-none text-right font-mono text-xs tabular-nums">
                  {missing ? "—" : `${((value ?? 0) * 100).toFixed(0)}%`}
                </span>
                <span className="w-[7ch] flex-none text-right font-mono text-[0.68rem] text-ink3">
                  {weight === undefined ? "" : `w ${weight.toFixed(2)}`}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>

      {unmeasured.length > 0 && (
        <p className="mt-3 text-xs text-ink3">
          Not measured for this answer: {unmeasured.map((n) => SIGNAL_LABEL[n] ?? n).join(", ")}.
          The remaining weights were rescaled to sum to one.
        </p>
      )}
      <p className="mt-2 text-xs text-ink3">
        These weights are an uncalibrated starting hypothesis, stored with every
        evaluation so they can be refitted against examiner agreement.
      </p>
    </div>
  );
}

export function WarningList({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <ul className="flex flex-col gap-1.5">
      {warnings.map((warning, index) => (
        <li
          key={index}
          className="flex gap-2 rounded-md border border-band3 bg-surface px-3 py-2 text-sm text-ink2"
        >
          <span aria-hidden className="font-mono text-band3">
            !
          </span>
          <span>{warning}</span>
        </li>
      ))}
    </ul>
  );
}
