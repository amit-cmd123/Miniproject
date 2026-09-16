import type { TranscriptionBand } from "../lib/types";

const BAND_STYLE: Record<TranscriptionBand, { bg: string; text: string; ring: string }> = {
  reliable: { bg: "bg-band1", text: "text-band1", ring: "border-band1" },
  spot_check: { bg: "bg-band2", text: "text-band2", ring: "border-band2" },
  verify: { bg: "bg-band3", text: "text-band3", ring: "border-band3" },
  unusable: { bg: "bg-band4", text: "text-band4", ring: "border-band4" },
};

export function bandStyle(band: TranscriptionBand) {
  return BAND_STYLE[band] ?? BAND_STYLE.unusable;
}

/** Confidence as a proportion of a full bar, coloured by its trust band. */
export function ConfidenceBar({
  value,
  band,
}: {
  value: number;
  band: TranscriptionBand;
}) {
  const style = bandStyle(band);
  const pct = Math.round(value * 1000) / 10;
  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full bg-surface2"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Transcription confidence"
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

export function BandChip({
  band,
  label,
}: {
  band: TranscriptionBand;
  label: string;
}) {
  const style = bandStyle(band);
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

/** A dot whose colour encodes one line's confidence, for dense per-line lists. */
export function LineConfidence({ value }: { value: number }) {
  const band: TranscriptionBand =
    value >= 0.95 ? "reliable" : value >= 0.85 ? "spot_check" : value >= 0.7 ? "verify" : "unusable";
  const style = bandStyle(band);
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2 w-2 flex-none rounded-full ${style.bg}`} />
      <span className={`font-mono text-xs tabular-nums ${style.text}`}>
        {(value * 100).toFixed(1)}
      </span>
    </span>
  );
}
