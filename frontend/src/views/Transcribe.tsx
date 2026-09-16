import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type {
  Accuracy,
  AnswerWithOCR,
  DocumentTranscription,
  PdfInspection,
} from "../lib/types";
import { BandChip, ConfidenceBar, LineConfidence } from "../components/Confidence";
import { DocumentResult } from "./DocumentResult";

type Phase = "idle" | "confirming" | "working" | "done" | "error";

const isPdf = (file: File) =>
  file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

export function Transcribe({ onSaved }: { onSaved: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<AnswerWithOCR | null>(null);
  const [docResult, setDocResult] = useState<DocumentTranscription | null>(null);
  const [pending, setPending] = useState<{ file: File; info: PdfInspection } | null>(null);
  const [pageRange, setPageRange] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // A page takes ~20s on CPU. Silence for that long reads as a broken page, so
  // the elapsed counter runs while we wait.
  useEffect(() => {
    if (phase !== "working") return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 100);
    return () => clearInterval(timer);
  }, [phase]);

  const reset = useCallback(() => {
    setResult(null);
    setDocResult(null);
    setPending(null);
    setPageRange("");
    setError(null);
    setPhase("idle");
  }, []);

  /** A PDF is inspected first so the wait can be quoted before it starts. */
  const accept = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setDocResult(null);

    if (isPdf(file)) {
      setPhase("working");
      try {
        const info = await api.inspectPdf(file);
        setPending({ file, info });
        setPageRange(info.total_pages > 4 ? `1-${Math.min(4, info.total_pages)}` : "");
        setPhase("confirming");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not read that PDF.");
        setPhase("error");
      }
      return;
    }

    setPhase("working");
    setElapsed(0);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(file);
    });
    try {
      setResult(await api.uploadAndTranscribe(file));
      setPhase("done");
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the transcription service. Is the backend running?",
      );
      setPhase("error");
    }
  }, [onSaved]);

  const runDocument = useCallback(async () => {
    if (!pending) return;
    setPhase("working");
    setElapsed(0);
    setPreview(null);
    try {
      setDocResult(await api.transcribeDocument(pending.file, pageRange));
      setPhase("done");
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read that PDF.");
      setPhase("error");
    }
  }, [pending, pageRange, onSaved]);

  const run = accept;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="eyebrow">Part 1 · Handwriting &amp; OCR</p>
          <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight">
            Read a handwritten answer
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-ink2">
            Upload a photograph or scan. Ruling, printed text and examiner marks are
            stripped away, the student's writing is read, and every line gets a
            confidence score measured from the model's behaviour — not its own opinion.
          </p>
        </div>
        {(result || docResult) && (
          <button className="btn-ghost" onClick={reset}>
            Transcribe another
          </button>
        )}
      </header>

      {phase === "idle" && (
        <DropZone
          dragging={dragging}
          setDragging={setDragging}
          inputRef={inputRef}
          onFile={run}
        />
      )}

      {phase === "confirming" && pending && (
        <ConfirmDocument
          info={pending.info}
          pageRange={pageRange}
          setPageRange={setPageRange}
          onRun={runDocument}
          onCancel={reset}
        />
      )}

      {phase === "working" && (
        <Working elapsed={elapsed} preview={preview} pending={pending} />
      )}

      {phase === "error" && (
        <ErrorState message={error!} onRetry={() => { setPhase("idle"); setError(null); }} />
      )}

      {phase === "done" && result && <Result result={result} />}
      {phase === "done" && docResult && <DocumentResult doc={docResult} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function DropZone({
  dragging,
  setDragging,
  inputRef,
  onFile,
}: {
  dragging: boolean;
  setDragging: (v: boolean) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onFile: (file: File) => void;
}) {
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={`flex flex-col items-center justify-center gap-4 rounded-lg border-2 border-dashed
                  px-6 py-20 text-center transition-colors ${
                    dragging ? "border-accent bg-accentSoft" : "border-line bg-surface"
                  }`}
    >
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="1.4" className="text-ink3" aria-hidden="true">
        <path d="M3 16.5V19a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2.5" />
        <path d="M12 3v13M7.5 7.5 12 3l4.5 4.5" />
      </svg>
      <div>
        <p className="font-display text-base font-semibold">
          Drop a handwritten answer or scanned booklet here
        </p>
        <p className="mt-1 text-sm text-ink2">
          A single image, or a scanned PDF booklet
        </p>
        <p className="mt-0.5 text-xs text-ink3">
          PDF · JPEG · PNG · WEBP · BMP · TIFF
        </p>
      </div>
      <button className="btn-primary" onClick={() => inputRef.current?.click()}>
        Choose a file
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      <p className="max-w-[46ch] text-xs text-ink3">
        Sample sheets for testing are in <code className="font-mono">data/samples/</code>.
      </p>
    </div>
  );
}

/**
 * A PDF is inspected before it is read.
 *
 * Reading is roughly a minute per densely written page, so committing a
 * twenty-page booklet without warning would look like the application had
 * frozen. This quotes the cost and lets a range be chosen first.
 */
function ConfirmDocument({
  info,
  pageRange,
  setPageRange,
  onRun,
  onCancel,
}: {
  info: PdfInspection;
  pageRange: string;
  setPageRange: (v: string) => void;
  onRun: () => void;
  onCancel: () => void;
}) {
  const minutes = Math.floor(info.estimated_seconds / 60);
  const seconds = info.estimated_seconds % 60;

  return (
    <div className="card max-w-[640px] p-6">
      <p className="eyebrow">Scanned document</p>
      <h2 className="mt-1.5 font-display text-lg font-semibold">{info.filename}</h2>
      <p className="mt-1 text-ink2">
        {info.total_pages} page{info.total_pages !== 1 ? "s" : ""}. Reading all of them
        takes roughly {minutes} min {seconds} s on this machine.
      </p>

      <label className="mt-5 block">
        <span className="eyebrow">Pages to read</span>
        <input
          value={pageRange}
          onChange={(e) => setPageRange(e.target.value)}
          placeholder={`blank = all ${info.total_pages}`}
          className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2
                     font-mono text-sm text-ink outline-none placeholder:text-ink3"
        />
      </label>
      <p className="mt-1.5 text-xs text-ink3">
        A range such as <code className="font-mono">1-4</code>, or single pages like{" "}
        <code className="font-mono">2,5</code>. Leave blank to read the whole document.
      </p>

      <div className="mt-5 flex flex-wrap gap-3">
        <button className="btn-primary" onClick={onRun}>
          Read {pageRange.trim() ? "selected pages" : `all ${info.total_pages} pages`}
        </button>
        <button className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Working({
  elapsed,
  preview,
  pending,
}: {
  elapsed: number;
  preview: string | null;
  pending: { file: File; info: PdfInspection } | null;
}) {
  const isDocument = pending !== null && preview === null;

  const stages = isDocument
    ? [
        { at: 0, label: "Rendering pages from the PDF" },
        { at: 3, label: "Cleaning and deskewing each page" },
        { at: 6, label: "Reading the handwriting, page by page" },
      ]
    : [
        { at: 0, label: "Uploading the image" },
        { at: 0.6, label: "Removing ruling, print and examiner marks" },
        { at: 1.6, label: "Segmenting handwriting lines" },
        { at: 2.2, label: "Reading the handwriting" },
      ];
  const current = stages.filter((s) => elapsed >= s.at).pop() ?? stages[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="card flex flex-col items-center justify-center gap-5 p-12">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-accent"
          role="status"
          aria-label="Transcribing"
        />
        <div className="text-center">
          <p className="font-display text-base font-semibold">{current.label}…</p>
          <p className="mt-1 font-mono text-sm tabular-nums text-ink2">
            {elapsed.toFixed(1)}s elapsed
          </p>
          <p className="mt-3 max-w-[46ch] text-sm text-ink3">
            {isDocument
              ? "Every page goes through the full pipeline and gets its own confidence score. Longer documents take proportionally longer."
              : "A full page usually takes under ten seconds."}
          </p>
        </div>
      </div>
      {preview && (
        <figure className="card overflow-hidden">
          <figcaption className="border-b border-line px-4 py-2.5 eyebrow">
            Uploaded image
          </figcaption>
          <img src={preview} alt="" className="max-h-[420px] w-full object-contain" />
        </figure>
      )}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card border-band4 p-8">
      <div className="flex flex-col items-start gap-3">
        <span className="rounded-full border border-band4 px-2.5 py-0.5 font-display text-[0.68rem] font-semibold uppercase tracking-wider text-band4">
          Transcription failed
        </span>
        <p className="max-w-[60ch] text-ink">{message}</p>
        <p className="max-w-[60ch] text-sm text-ink3">
          Nothing was saved. The system will not produce a transcription it cannot
          stand behind — a silent empty result would be worse than this error.
        </p>
        <button className="btn-primary mt-1" onClick={onRetry}>
          Try another image
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Result({ result }: { result: AnswerWithOCR }) {
  const { answer, ocr } = result;
  const [tab, setTab] = useState<"original" | "segmentation">("original");
  const [text, setText] = useState(ocr.effective_text);
  const [saved, setSaved] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [accuracy, setAccuracy] = useState<Accuracy | null>(null);
  const [busy, setBusy] = useState(false);

  const dirty = text !== ocr.effective_text;

  async function saveCorrection() {
    setBusy(true);
    try {
      await api.correct(answer.id, text);
      setSaved("Correction saved. The machine transcription is kept alongside it.");
    } catch (err) {
      setSaved(err instanceof ApiError ? err.message : "Could not save the correction.");
    } finally {
      setBusy(false);
    }
  }

  async function measure() {
    setBusy(true);
    try {
      setAccuracy(await api.accuracy(answer.id, reference));
    } catch (err) {
      setSaved(err instanceof ApiError ? err.message : "Could not measure accuracy.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Headline numbers */}
      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <BandChip band={ocr.transcription_band} label={ocr.band_label} />
            <span className="text-sm text-ink2">{ocr.band_description}</span>
          </div>
          <dl className="flex flex-wrap gap-x-7 gap-y-2 font-display text-xs">
            <Stat label="Lines" value={String(ocr.line_count)} />
            <Stat label="Words" value={String(ocr.word_count)} />
            <Stat label="Time" value={`${(ocr.duration_ms / 1000).toFixed(1)}s`} />
            <Stat label="Model" value={ocr.model_version} />
            <Stat label="Device" value={ocr.device} />
          </dl>
        </div>
        <div className="mt-4">
          <ConfidenceBar value={ocr.confidence} band={ocr.transcription_band} />
        </div>
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

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Evidence: the handwriting itself must stay reachable. */}
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
                {id === "original" ? "Original" : "Detected lines"}
              </button>
            ))}
          </div>
          <img
            src={tab === "original" ? api.imageUrl(answer.id) : api.segmentationUrl(answer.id)}
            alt={tab === "original" ? "The uploaded handwritten answer" : "Detected handwriting lines"}
            className="max-h-[560px] w-full bg-surface2 object-contain"
          />
          {tab === "segmentation" && (
            <p className="border-t border-line px-4 py-2.5 text-xs text-ink3">
              The page as the recogniser sees it: ruling, print, examiner marks and
              show-through removed. Each box is one detected line — if a box spans two
              lines or cuts one in half, segmentation is the problem, not recognition.
            </p>
          )}
        </section>

        {/* Transcription, editable. */}
        <section className="card flex flex-col overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
            <p className="eyebrow">Transcription</p>
            <span className="font-mono text-[0.68rem] text-ink3">
              {ocr.text_source === "human_corrected" ? "human corrected" : "machine output"}
            </span>
          </div>
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); setSaved(null); }}
            spellCheck={false}
            className="min-h-[300px] flex-1 resize-y bg-transparent p-4 font-mono text-sm
                       leading-relaxed text-ink outline-none"
            aria-label="Extracted text, editable"
          />
          <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
            <button className="btn-primary" disabled={!dirty || busy} onClick={saveCorrection}>
              Save correction
            </button>
            <button className="btn-ghost" disabled={!dirty} onClick={() => setText(ocr.effective_text)}>
              Reset
            </button>
            <p className="text-xs text-ink3">
              Corrections never overwrite the machine output, so error rate stays
              measurable.
            </p>
          </div>
          {saved && <p className="border-t border-line px-4 py-2.5 text-sm text-accent">{saved}</p>}
        </section>
      </div>

      {/* Per-line confidence: where the page-level number comes from. */}
      <section className="card overflow-hidden">
        <div className="border-b border-line px-4 py-2.5">
          <p className="eyebrow">Line-by-line confidence</p>
          <p className="mt-1 text-sm text-ink2">
            The page score is a length-weighted mean of these, reduced for a soft image.
            Low-scoring lines are where to look first.
          </p>
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

      <div className="grid gap-6 lg:grid-cols-2">
        <AccuracyPanel
          reference={reference}
          setReference={setReference}
          accuracy={accuracy}
          busy={busy}
          onMeasure={measure}
        />
        <PreprocessingPanel ocr={ocr} />
      </div>
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

function AccuracyPanel({
  reference,
  setReference,
  accuracy,
  busy,
  onMeasure,
}: {
  reference: string;
  setReference: (v: string) => void;
  accuracy: Accuracy | null;
  busy: boolean;
  onMeasure: () => void;
}) {
  return (
    <section className="card flex flex-col overflow-hidden">
      <div className="border-b border-line px-4 py-2.5">
        <p className="eyebrow">Measure accuracy</p>
        <p className="mt-1 text-sm text-ink2">
          Paste the true transcription to get character and word error rate against the
          machine output.
        </p>
      </div>
      <textarea
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        placeholder="Type or paste what the student actually wrote…"
        className="min-h-[130px] resize-y bg-transparent p-4 font-mono text-sm text-ink outline-none
                   placeholder:text-ink3"
        aria-label="Reference transcription"
      />
      <div className="border-t border-line px-4 py-3">
        <button className="btn-primary" disabled={!reference.trim() || busy} onClick={onMeasure}>
          Measure
        </button>
      </div>
      {accuracy && (
        <dl className="grid grid-cols-2 gap-px border-t border-line bg-line">
          <Metric label="Character error rate" value={`${(accuracy.character_error_rate * 100).toFixed(2)}%`} />
          <Metric label="Word error rate" value={`${(accuracy.word_error_rate * 100).toFixed(2)}%`} />
          <Metric label="Reference words" value={String(accuracy.reference_words)} />
          <Metric label="Read words" value={String(accuracy.hypothesis_words)} />
        </dl>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 bg-surface px-4 py-3">
      <dt className="eyebrow">{label}</dt>
      <dd className="font-mono text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function PreprocessingPanel({ ocr }: { ocr: AnswerWithOCR["ocr"] }) {
  const p = ocr.preprocessing;
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line px-4 py-2.5">
        <p className="eyebrow">What was done to the image</p>
      </div>
      {p ? (
        <div className="flex flex-col gap-4 p-4">
          <ol className="flex flex-wrap gap-1.5">
            {p.steps.map((step, i) => (
              <li
                key={step}
                className="rounded border border-line bg-surface2 px-2 py-1 font-mono text-[0.7rem] text-ink2"
              >
                {i + 1}. {step}
              </li>
            ))}
          </ol>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 font-display text-xs sm:grid-cols-3">
            <Stat label="Deskewed" value={`${p.deskew_angle_deg.toFixed(2)}°`} />
            <Stat label="Sharpness" value={p.blur_score.toFixed(0)} />
            <Stat label="Lines found" value={String(p.detected_lines)} />
            <Stat label="Ink coverage" value={`${(p.estimated_ink_coverage * 100).toFixed(1)}%`} />
            <Stat label="Contrast" value={p.is_low_contrast ? "low" : "good"} />
            <Stat
              label="Processed"
              value={p.processed_size ? `${p.processed_size[0]}×${p.processed_size[1]}` : "—"}
            />
          </dl>
        </div>
      ) : (
        <p className="p-4 text-sm text-ink3">No preprocessing detail recorded.</p>
      )}
    </section>
  );
}
