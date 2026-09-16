import { useState } from "react";
import { api } from "../lib/api";
import type { DocumentTranscription } from "../lib/types";
import { BandChip, ConfidenceBar, LineConfidence } from "../components/Confidence";

/**
 * A whole PDF booklet, read.
 *
 * Each page is its own answer with its own confidence, so the page selector is
 * not decoration - it is how a marker finds the page that needs attention.
 */
export function DocumentResult({ doc }: { doc: DocumentTranscription }) {
  const [selected, setSelected] = useState(doc.pages[0]?.page_number ?? 1);
  const [showCombined, setShowCombined] = useState(false);
  const page = doc.pages.find((p) => p.page_number === selected) ?? doc.pages[0];

  return (
    <div className="flex flex-col gap-6">
      {/* Document-level summary */}
      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <BandChip band={doc.transcription_band} label={doc.band_label} />
            <span className="font-display text-sm font-semibold">{doc.filename}</span>
            <span className="text-sm text-ink2">
              {doc.pages_processed} of {doc.total_pages} page
              {doc.total_pages !== 1 ? "s" : ""} read
            </span>
          </div>
          <dl className="flex flex-wrap gap-x-7 gap-y-2 font-display text-xs">
            <Stat label="Lines" value={String(doc.total_lines)} />
            <Stat label="Words" value={String(doc.total_words)} />
            <Stat label="Time" value={`${(doc.duration_ms / 1000).toFixed(1)}s`} />
          </dl>
        </div>
        <div className="mt-4">
          <ConfidenceBar value={doc.overall_confidence} band={doc.transcription_band} />
        </div>
        <p className="mt-2 text-xs text-ink3">
          Document confidence is each page's score weighted by how much text it
          carries, so a near-blank page neither drags down nor props up the rest.
        </p>
      </div>

      {doc.warnings.length > 0 && (
        <ul className="flex flex-col gap-2">
          {doc.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-md border-l-[3px] border-band3 bg-surface px-4 py-2.5 text-sm text-ink2"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}

      {/* Page selector — confidence is visible per page, so the weak page is
          findable without opening each one. */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <p className="eyebrow">Pages</p>
          <button
            className="font-display text-xs font-semibold text-accent hover:underline"
            onClick={() => setShowCombined((v) => !v)}
          >
            {showCombined ? "Show single page" : "Show whole document text"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2 p-3">
          {doc.pages.map((p) => {
            const active = p.page_number === selected && !showCombined;
            const failed = !!p.error;
            return (
              <button
                key={p.page_number}
                onClick={() => {
                  setSelected(p.page_number);
                  setShowCombined(false);
                }}
                className={`flex min-w-[92px] flex-col items-start gap-0.5 rounded-md border px-3 py-2
                            text-left transition-colors ${
                              active
                                ? "border-accent bg-accentSoft"
                                : "border-line bg-surface hover:bg-surface2"
                            }`}
              >
                <span className="font-display text-xs font-semibold">
                  Page {p.page_number}
                </span>
                {failed ? (
                  <span className="font-mono text-[0.68rem] text-band4">failed</span>
                ) : (
                  <LineConfidence value={p.ocr?.confidence ?? 0} />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {showCombined ? (
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <p className="eyebrow">Whole document</p>
            <button
              className="font-display text-xs font-semibold text-accent hover:underline"
              onClick={() => void navigator.clipboard?.writeText(doc.combined_text)}
            >
              Copy text
            </button>
          </div>
          <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap p-4 font-mono text-sm leading-relaxed text-ink">
            {doc.combined_text}
          </pre>
        </section>
      ) : page?.error ? (
        <div className="card border-band4 p-6">
          <p className="font-display text-sm font-semibold text-band4">
            Page {page.page_number} could not be read
          </p>
          <p className="mt-1 text-ink2">{page.error}</p>
          <p className="mt-2 text-sm text-ink3">
            The other pages were unaffected — one bad page does not discard the booklet.
          </p>
        </div>
      ) : page?.ocr && page.answer ? (
        <PageDetail
          answerId={page.answer.id}
          ocr={page.ocr}
          pageNumber={page.page_number}
        />
      ) : null}
    </div>
  );
}

function PageDetail({
  answerId,
  ocr,
  pageNumber,
}: {
  answerId: string;
  ocr: NonNullable<DocumentTranscription["pages"][number]["ocr"]>;
  pageNumber: number;
}) {
  const [tab, setTab] = useState<"original" | "segmentation">("original");

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card overflow-hidden">
          <div className="flex items-center gap-1 border-b border-line px-3 py-2">
            {(["original", "segmentation"] as const).map((id) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`rounded px-2.5 py-1 font-display text-xs font-semibold transition-colors ${
                  tab === id ? "bg-accentSoft text-accent" : "text-ink3 hover:bg-surface2"
                }`}
              >
                {id === "original" ? "Scanned page" : "Detected lines"}
              </button>
            ))}
            <span className="ml-auto font-mono text-[0.68rem] text-ink3">
              page {pageNumber}
            </span>
          </div>
          <img
            src={tab === "original" ? api.imageUrl(answerId) : api.segmentationUrl(answerId)}
            alt={tab === "original" ? `Scanned page ${pageNumber}` : "Detected lines"}
            className="max-h-[620px] w-full bg-surface2 object-contain"
          />
        </section>

        <section className="card flex flex-col overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
            <p className="eyebrow">Page {pageNumber} transcription</p>
            <span className="font-mono text-[0.68rem] text-ink3">
              {(ocr.confidence * 100).toFixed(1)}% · {ocr.line_count} lines
            </span>
          </div>
          <pre className="min-h-[320px] flex-1 overflow-auto whitespace-pre-wrap p-4 font-mono text-sm leading-relaxed text-ink">
            {ocr.effective_text || "Nothing was read from this page."}
          </pre>
        </section>
      </div>

      {ocr.warnings.length > 0 && (
        <ul className="flex flex-col gap-2">
          {ocr.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-md border-l-[3px] border-band3 bg-surface px-4 py-2.5 text-sm text-ink2"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}

      <section className="card overflow-hidden">
        <div className="border-b border-line px-4 py-2.5">
          <p className="eyebrow">Line-by-line confidence · page {pageNumber}</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse font-display text-sm">
            <thead>
              <tr>
                <th className="w-14 border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">#</th>
                <th className="w-24 border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">Conf.</th>
                <th className="border-b border-line bg-surface2 px-4 py-2 text-left eyebrow">Text read</th>
              </tr>
            </thead>
            <tbody>
              {ocr.lines.map((line) => (
                <tr key={line.index}>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink3">
                    {line.index + 1}
                  </td>
                  <td className="border-b border-line px-4 py-2">
                    <LineConfidence value={line.confidence} />
                  </td>
                  <td className="border-b border-line px-4 py-2 font-mono text-xs text-ink2">
                    {line.text || <span className="italic text-ink3">nothing read</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="eyebrow">{label}</dt>
      <dd className="font-mono text-sm tabular-nums text-ink">{value}</dd>
    </div>
  );
}
