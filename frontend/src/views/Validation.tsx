/**
 * Part 4 - whether any of this worked.
 *
 * The screen the project is most exposed by, and therefore the one most worth
 * having. It reports machine-examiner agreement with its sample size always
 * attached, and - the figure that matters - the modification rate per
 * confidence band.
 *
 * The design claim is that a high-confidence score rarely needs changing and
 * a low-confidence one often does. If the per-band modification rates come out
 * flat, the confidence measure is not informative, however principled its
 * components look. Showing that possibility plainly is the point: a validation
 * screen that could only ever agree with the system would be decoration.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Analytics, BandAgreement, ReviewBand } from "../lib/types";
import { reviewBandStyle } from "../components/Marks";

export function Validation({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<Analytics | null>(null);
  const [weights, setWeights] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, confidence] = await Promise.all([
        api.analytics(),
        api.confidenceWeights(),
      ]);
      setData(summary);
      setWeights(confidence.weights);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the metrics.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="eyebrow">Part 4 · Validation</p>
          <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
            Did it work?
          </h1>
          <p className="mt-1.5 max-w-[68ch] text-ink2">
            Computed from the records the system wrote while being used, not from a
            separate study. Every figure is shown with the number of reviews behind it,
            because an agreement rate over four answers is not evidence.
          </p>
        </div>
        <button className="btn-ghost" onClick={() => void load()}>
          Refresh
        </button>
      </header>

      {error && (
        <p className="rounded-md border border-band4 bg-surface px-4 py-3 text-band4">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Answers uploaded" value={String(data.answers_uploaded)} />
            <Metric label="Transcribed" value={String(data.answers_transcribed)} />
            <Metric label="Marked" value={String(data.evaluations)} />
            <Metric label="Reviewed" value={String(data.reviewed_evaluations)} />
          </section>

          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Mean transcription confidence"
              value={pct(data.mean_transcription_confidence)}
            />
            <Metric
              label="Mean marking confidence"
              value={pct(data.mean_evaluation_confidence)}
            />
            <Metric
              label="Exact mark agreement"
              value={pct(data.exact_agreement)}
              footnote={`over ${data.reviewed_evaluations} reviewed`}
            />
            <Metric
              label="Within half a mark"
              value={pct(data.within_half_mark)}
              footnote={`over ${data.reviewed_evaluations} reviewed`}
            />
          </section>

          {data.note && (
            <p className="rounded-md border border-band3 bg-surface px-4 py-3 text-sm text-ink2">
              {data.note}
            </p>
          )}

          <section className="flex flex-col gap-3">
            <div>
              <p className="eyebrow">The test that matters</p>
              <h2 className="mt-1 font-display text-lg font-semibold">
                Does confidence predict disagreement?
              </h2>
              <p className="mt-1 max-w-[72ch] text-sm text-ink2">
                The modification rate should fall as confidence rises. If it is flat
                across these rows, the confidence number is not telling an examiner
                anything useful and the weights need refitting.
              </p>
            </div>
            <BandTable rows={data.by_band} />
          </section>

          <section className="grid gap-3 sm:grid-cols-2">
            <Metric
              label="Mean absolute error"
              value={
                data.mean_absolute_error === null
                  ? "—"
                  : `${data.mean_absolute_error.toFixed(2)} marks`
              }
              footnote="machine score vs examiner score"
            />
            <Metric
              label="Mean time per review"
              value={
                data.mean_review_seconds === null
                  ? "—"
                  : `${data.mean_review_seconds.toFixed(1)}s`
              }
              footnote="measured, not estimated"
            />
          </section>

          {weights && (
            <section className="card p-4">
              <p className="eyebrow">Confidence weights in force</p>
              <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
                {Object.entries(weights).map(([name, weight]) => (
                  <li key={name} className="font-mono text-sm">
                    <span className="text-ink2">{name.replace(/_/g, " ")}</span>{" "}
                    <span className="font-semibold">{weight.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-ink3">
                Combined as a weighted geometric mean, so one collapsed signal drags the
                whole result down instead of being averaged away. These values are an
                uncalibrated hypothesis — the table above is what would justify changing
                them.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function BandTable({ rows }: { rows: BandAgreement[] }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[46rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <Th>Confidence band</Th>
            <Th align="right">Marked</Th>
            <Th align="right">Reviewed</Th>
            <Th align="right">Accepted</Th>
            <Th align="right">Changed</Th>
            <Th align="right">Change rate</Th>
            <Th align="right">Mean error</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const style = reviewBandStyle(row.band as ReviewBand);
            return (
              <tr key={row.band} className="border-b border-line last:border-b-0">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full ${style.bg}`} />
                    <span className={style.text}>{row.label}</span>
                  </span>
                </td>
                <Td>{row.evaluations}</Td>
                <Td>{row.reviewed}</Td>
                <Td>{row.accepted}</Td>
                <Td>{row.modified}</Td>
                <Td>
                  {row.modification_rate === null
                    ? "—"
                    : `${(row.modification_rate * 100).toFixed(0)}%`}
                </Td>
                <Td>
                  {row.mean_absolute_delta === null
                    ? "—"
                    : row.mean_absolute_delta.toFixed(2)}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-line px-4 py-2 text-xs text-ink3">
        A dash means nothing has been reviewed in that band yet, so the band is
        untested rather than perfect.
      </p>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`px-4 py-2 font-display text-[0.68rem] font-semibold uppercase tracking-wider text-ink3 ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td className="px-4 py-2.5 text-right font-mono tabular-nums">{children}</td>
  );
}

function Metric({
  label,
  value,
  footnote,
}: {
  label: string;
  value: string;
  footnote?: string;
}) {
  return (
    <div className="card p-4">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold tabular-nums">{value}</p>
      {footnote && <p className="mt-0.5 font-mono text-[0.66rem] text-ink3">{footnote}</p>}
    </div>
  );
}

function pct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}
