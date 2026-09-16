import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { AnswerDetail } from "../lib/types";
import { BandChip } from "../components/Confidence";

/**
 * Everything transcribed so far.
 *
 * In Part 4 this becomes the examiner worklist, filtered by review band. For
 * now it is the audit trail for Part 1: every answer, its confidence, and
 * whether a human has corrected the text.
 */
export function Library({ refreshKey }: { refreshKey: number }) {
  const [answers, setAnswers] = useState<AnswerDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listAnswers()
      .then((rows) => !cancelled && setAnswers(rows))
      .catch(() => !cancelled && setError("Could not load answers. Is the backend running?"));
    return () => { cancelled = true; };
  }, [refreshKey]);

  return (
    <div className="flex flex-col gap-6">
      <header className="border-b border-line pb-5">
        <p className="eyebrow">Part 1 · Handwriting &amp; OCR</p>
        <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
          Answer library
        </h1>
        <p className="mt-1.5 max-w-[62ch] text-ink2">
          Every answer transcribed so far. In Part 4 this becomes the examiner worklist,
          sorted by how much attention each answer needs.
        </p>
      </header>

      {error && <p className="card border-band4 p-5 text-ink">{error}</p>}

      {!answers && !error && <p className="text-ink3">Loading…</p>}

      {answers?.length === 0 && (
        <div className="card flex flex-col items-center gap-2 px-6 py-16 text-center">
          <p className="font-display text-base font-semibold">Nothing transcribed yet</p>
          <p className="max-w-[42ch] text-sm text-ink2">
            Upload a handwritten answer on the Transcribe screen and it will appear here
            with its confidence and trust band.
          </p>
        </div>
      )}

      {answers && answers.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse font-display text-sm">
            <thead>
              <tr>
                {["Answer", "Confidence", "Band", "Lines", "Words", "Time", "Text", "Added"].map(
                  (heading) => (
                    <th
                      key={heading}
                      className="border-b border-line bg-surface2 px-4 py-2.5 text-left eyebrow"
                    >
                      {heading}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {answers.map((answer) => {
                const ocr = answer.latest_ocr;
                return (
                  <tr key={answer.id} className="align-top">
                    <td className="border-b border-line px-4 py-3">
                      <div className="flex items-center gap-3">
                        <img
                          src={api.imageUrl(answer.id)}
                          alt=""
                          className="h-10 w-14 flex-none rounded border border-line object-cover"
                        />
                        <div className="min-w-0">
                          <p className="truncate text-ink">
                            {answer.original_filename ?? "untitled"}
                          </p>
                          <p className="font-mono text-[0.68rem] text-ink3">
                            {answer.id.slice(0, 8)}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="border-b border-line px-4 py-3 font-mono tabular-nums">
                      {ocr ? `${(ocr.confidence * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="border-b border-line px-4 py-3">
                      {ocr ? (
                        <BandChip band={ocr.transcription_band} label={ocr.band_label} />
                      ) : (
                        <span className="text-ink3">{answer.status}</span>
                      )}
                    </td>
                    <td className="border-b border-line px-4 py-3 font-mono tabular-nums text-ink2">
                      {ocr?.line_count ?? "—"}
                    </td>
                    <td className="border-b border-line px-4 py-3 font-mono tabular-nums text-ink2">
                      {ocr?.word_count ?? "—"}
                    </td>
                    <td className="border-b border-line px-4 py-3 font-mono tabular-nums text-ink2">
                      {ocr ? `${(ocr.duration_ms / 1000).toFixed(1)}s` : "—"}
                    </td>
                    <td className="border-b border-line px-4 py-3">
                      <span
                        className={`font-mono text-[0.68rem] ${
                          ocr?.text_source === "human_corrected" ? "text-accent" : "text-ink3"
                        }`}
                      >
                        {ocr?.text_source === "human_corrected" ? "corrected" : "machine"}
                      </span>
                    </td>
                    <td className="border-b border-line px-4 py-3 font-mono text-[0.68rem] text-ink3">
                      {new Date(answer.created_at).toLocaleTimeString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
