import type { EngineState } from "../lib/engine";

/**
 * The Gemini switch.
 *
 * On: Google's model reads the handwriting and marks against the rubric.
 * Off: the pipeline we built does both - OpenCV preprocessing and line
 * segmentation, the TrOCR handwriting model, and criterion-by-criterion
 * concept matching for the marks.
 *
 * The panel says what each side actually runs, and says plainly that the
 * local marker is a baseline rather than a language model. Presenting the
 * two as interchangeable would be the one dishonest thing this screen could
 * do: an examiner has to know which of them produced a number before they
 * decide how much to trust it.
 */
export function EngineToggle({ state }: { state: EngineState }) {
  const { engine, setEngine, option, geminiAvailable, options } = state;
  const on = engine === "gemini";
  const gemini = options?.find((e) => e.id === "gemini");

  return (
    <section className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow">Engine</p>
          <h2 className="mt-1 font-display text-base font-bold tracking-tight">
            {on ? "Gemini (cloud)" : "EvalNova local engine"}
          </h2>
          <p className="mt-1 max-w-[70ch] text-sm text-ink2">
            {on
              ? "Google's model reads the page and marks against the rubric. Page images and transcribed text leave this machine."
              : "Our own pipeline, start to finish, with nothing leaving this machine: OpenCV preprocessing, the TrOCR handwriting model, and concept matching against each rubric criterion."}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <span
            className={`font-display text-xs font-bold uppercase tracking-label ${
              on ? "text-ink3" : "text-accent"
            }`}
          >
            Local
          </span>

          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-label="Use Gemini"
            disabled={!geminiAvailable}
            onClick={() => setEngine(on ? "local" : "gemini")}
            title={
              geminiAvailable
                ? "Switch between the cloud model and the local engine"
                : (gemini?.unavailable_reason ?? "Gemini is not configured.")
            }
            className={`relative h-7 w-14 shrink-0 border transition-colors duration-200
                        disabled:cursor-not-allowed disabled:opacity-45
                        ${
                          on
                            ? "border-transparent bg-nova-grad shadow-accent"
                            : "border-line bg-surface2"
                        }`}
            style={{ borderRadius: 100 }}
          >
            <span
              className={`absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow-sm
                          transition-[left] duration-200 ease-nova ${on ? "left-8" : "left-1"}`}
            />
          </button>

          <span
            className={`font-display text-xs font-bold uppercase tracking-label ${
              on ? "text-energyInk" : "text-ink3"
            }`}
          >
            Gemini
          </span>
        </div>
      </div>

      {!geminiAvailable && gemini?.unavailable_reason && (
        <p className="mt-3 rounded-md border border-line bg-surface2 px-3 py-2 text-xs text-ink2">
          <span className="font-semibold">Gemini is unavailable.</span>{" "}
          {gemini.unavailable_reason}
        </p>
      )}

      <dl className="mt-3 grid gap-x-6 gap-y-1 border-t border-line pt-3 text-xs sm:grid-cols-2">
        <div className="flex gap-2">
          <dt className="text-ink3">Reads handwriting with</dt>
          <dd className="font-mono text-ink2">{option?.transcription ?? "…"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-ink3">Awards marks with</dt>
          <dd className="font-mono text-ink2">{option?.marking ?? "…"}</dd>
        </div>
      </dl>

      {!on && (
        <p className="mt-3 text-xs leading-relaxed text-ink3">
          The local marker decides by concept overlap against each criterion,
          not by reading the answer. It walks the same rubric and awards the
          same partial credit, and every score it produces is labelled with
          that — it is the baseline the cloud model is measured against, not a
          result to report to a student.
        </p>
      )}
    </section>
  );
}

/** The compact form, for the header. */
export function EngineBadge({ state }: { state: EngineState }) {
  const on = state.engine === "gemini";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1
                  font-display text-[0.68rem] font-bold uppercase tracking-wider ${
                    on
                      ? "border-energy text-energyInk"
                      : "border-line text-ink2"
                  }`}
      title={state.option?.detail ?? ""}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${on ? "bg-energy" : "bg-ink3"}`}
      />
      {on ? "Gemini" : "Local"}
    </span>
  );
}
