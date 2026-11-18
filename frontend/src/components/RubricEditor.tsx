/**
 * Editing a question's rubric.
 *
 * The one thing this screen must never let through is a rubric whose criteria
 * do not sum to the question's marks. Such a rubric caps every student
 * silently - a paper worth 5 whose criteria total 4.5 gives every candidate
 * at most 90%, with a breakdown that looks entirely reasonable. So the sum is
 * shown live, in large type, next to the target, and the save button is
 * disabled until they agree. The backend refuses it too; this is the version
 * the examiner can see and fix.
 *
 * Saving writes a NEW rubric version rather than editing the current one. The
 * previous version is kept and deactivated, so a score awarded last week
 * still resolves to the rubric it was marked against. The interface says so
 * on the button, because "save" implying overwrite would be a lie.
 */

import { useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { CriterionDraft, Question, RubricVersion } from "../lib/types";

const TOLERANCE = 0.001;

/** A fresh criterion. Zero marks so it cannot accidentally balance a rubric. */
function blankCriterion(position: number): CriterionDraft {
  return {
    position,
    description: "",
    max_marks: 0,
    essential_concepts: [],
    acceptable_alternatives: [],
    common_mistakes: [],
    allows_partial: true,
    load_bearing: false,
  };
}

function fromQuestion(question: Question): CriterionDraft[] {
  if (!question.rubric?.criteria.length) return [blankCriterion(1)];
  return question.rubric.criteria
    .slice()
    .sort((a, b) => a.position - b.position)
    .map((c) => ({
      position: c.position,
      description: c.description,
      max_marks: c.max_marks,
      essential_concepts: [...c.essential_concepts],
      acceptable_alternatives: [...c.acceptable_alternatives],
      common_mistakes: [...c.common_mistakes],
      allows_partial: c.allows_partial,
      load_bearing: c.load_bearing,
    }));
}

export function RubricEditor({
  question,
  onSaved,
  onCancel,
}: {
  question: Question;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [criteria, setCriteria] = useState<CriterionDraft[]>(() =>
    fromQuestion(question),
  );
  const [scheme, setScheme] = useState(question.rubric?.marking_scheme ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<RubricVersion[] | null>(null);

  const total = useMemo(
    () => criteria.reduce((sum, c) => sum + (Number(c.max_marks) || 0), 0),
    [criteria],
  );
  const target = question.max_marks;
  const sums = Math.abs(total - target) <= TOLERANCE;
  const blank = criteria.filter((c) => c.description.trim().length < 3);
  const canSave = sums && blank.length === 0 && criteria.length > 0;

  function patch(index: number, change: Partial<CriterionDraft>) {
    setCriteria((list) =>
      list.map((c, i) => (i === index ? { ...c, ...change } : c)),
    );
  }

  function add() {
    setCriteria((list) => [...list, blankCriterion(list.length + 1)]);
  }

  function remove(index: number) {
    setCriteria((list) =>
      list
        .filter((_, i) => i !== index)
        .map((c, i) => ({ ...c, position: i + 1 })),
    );
  }

  function move(index: number, delta: number) {
    const next = index + delta;
    if (next < 0 || next >= criteria.length) return;
    setCriteria((list) => {
      const copy = [...list];
      [copy[index], copy[next]] = [copy[next], copy[index]];
      return copy.map((c, i) => ({ ...c, position: i + 1 }));
    });
  }

  /** Spread the question's marks evenly, rounded to half marks. */
  function distribute() {
    const count = criteria.length;
    if (!count) return;
    const step = 0.5;
    const each = Math.max(step, Math.round((target / count) / step) * step);
    const values = Array.from({ length: count }, () => each);
    // Put whatever the rounding left over onto the first criterion, so the
    // total is exact rather than nearly right.
    const drift = Math.round((target - each * count) / step) * step;
    values[0] = Math.max(0, values[0] + drift);
    setCriteria((list) =>
      list.map((c, i) => ({ ...c, max_marks: Number(values[i].toFixed(2)) })),
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.saveRubric(question.id, {
        marking_scheme: scheme.trim() || null,
        criteria: criteria.map((c, i) => ({
          ...c,
          position: i + 1,
          max_marks: Number(c.max_marks) || 0,
          description: c.description.trim(),
        })),
        scoring_rules: question.rubric?.scoring_rules ?? {},
      });
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "The rubric could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function loadVersions() {
    try {
      setVersions(await api.rubricVersions(question.id));
    } catch {
      setVersions([]);
    }
  }

  return (
    <div className="flex flex-col gap-4 border-t border-line pt-4">
      {/* The sum check. The most important thing on the screen. */}
      <section
        className={`flex flex-wrap items-center justify-between gap-4 rounded-md border px-4 py-3 ${
          sums ? "border-band1 bg-surface" : "border-band4 bg-surface"
        }`}
      >
        <div>
          <p className="eyebrow">Criteria total</p>
          <p className="mt-0.5 font-mono text-xl font-semibold tabular-nums">
            <span className={sums ? "text-band1" : "text-band4"}>
              {total.toFixed(2).replace(/\.00$/, "")}
            </span>
            <span className="text-ink3"> / {target}</span>
          </p>
        </div>
        <p className="max-w-[48ch] text-sm text-ink2">
          {sums ? (
            <>These criteria sum to the question&apos;s marks, so it can be marked.</>
          ) : (
            <>
              <strong className="text-band4">
                This rubric would cap every student.
              </strong>{" "}
              Criteria summing to {total.toFixed(2).replace(/\.00$/, "")} out of{" "}
              {target} means no candidate can score more than{" "}
              {target > 0 ? Math.round((total / target) * 100) : 0}%, with a
              breakdown that looks perfectly reasonable. Marking is refused
              until they agree.
            </>
          )}
        </p>
        <button type="button" className="btn-ghost text-sm" onClick={distribute}>
          Spread {target} evenly
        </button>
      </section>

      {/* Criteria */}
      <div className="flex flex-col gap-3">
        {criteria.map((criterion, index) => (
          <article key={index} className="rounded-md border border-line p-3">
            <div className="flex flex-wrap items-start gap-3">
              <span className="mt-2 font-mono text-sm text-ink3">{index + 1}.</span>

              <div className="min-w-[18rem] flex-1">
                <label className="eyebrow" htmlFor={`desc-${index}`}>
                  What this criterion tests
                </label>
                <textarea
                  id={`desc-${index}`}
                  className="input mt-1 min-h-[3.5rem] w-full"
                  value={criterion.description}
                  placeholder="States that a pointer stores the address of another variable"
                  onChange={(e) => patch(index, { description: e.target.value })}
                />
              </div>

              <div className="w-24">
                <label className="eyebrow" htmlFor={`marks-${index}`}>
                  Marks
                </label>
                <input
                  id={`marks-${index}`}
                  type="number"
                  min={0}
                  step={0.5}
                  className="input mt-1 w-full font-mono tabular-nums"
                  value={criterion.max_marks}
                  onChange={(e) =>
                    patch(index, { max_marks: Number(e.target.value) })
                  }
                />
              </div>

              <div className="flex flex-col gap-1 pt-5">
                <button
                  type="button"
                  className="btn-ghost px-2 py-0.5 text-xs"
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  aria-label="Move up"
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="btn-ghost px-2 py-0.5 text-xs"
                  onClick={() => move(index, 1)}
                  disabled={index === criteria.length - 1}
                  aria-label="Move down"
                >
                  ↓
                </button>
              </div>

              <button
                type="button"
                className="btn-ghost mt-5 px-2 py-1 text-xs text-band4"
                onClick={() => remove(index)}
                disabled={criteria.length === 1}
              >
                Remove
              </button>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <ListField
                label="Must convey"
                hint="The ideas required. Not words to match."
                items={criterion.essential_concepts}
                onChange={(items) => patch(index, { essential_concepts: items })}
              />
              <ListField
                label="Also acceptable"
                hint="Different wording that still earns the mark."
                items={criterion.acceptable_alternatives}
                onChange={(items) =>
                  patch(index, { acceptable_alternatives: items })
                }
              />
              <ListField
                label="Known mistakes"
                hint="Errors to watch for, e.g. int max = 0."
                items={criterion.common_mistakes}
                onChange={(items) => patch(index, { common_mistakes: items })}
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-5 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={criterion.allows_partial}
                  onChange={(e) =>
                    patch(index, { allows_partial: e.target.checked })
                  }
                />
                <span>
                  Partial credit
                  <span className="ml-1 text-ink3">
                    (off = all or nothing)
                  </span>
                </span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={criterion.load_bearing}
                  onChange={(e) =>
                    patch(index, { load_bearing: e.target.checked })
                  }
                />
                <span>
                  Load-bearing
                  <span className="ml-1 text-ink3">
                    (getting it wrong costs confidence, not marks)
                  </span>
                </span>
              </label>
            </div>
          </article>
        ))}
      </div>

      <button type="button" className="btn-ghost self-start text-sm" onClick={add}>
        + Add a criterion
      </button>

      <div>
        <label className="eyebrow" htmlFor="scheme">
          Marking scheme note (optional)
        </label>
        <textarea
          id="scheme"
          className="input mt-1 min-h-[3rem] w-full"
          value={scheme}
          placeholder="Guidance for whoever marks this by hand."
          onChange={(e) => setScheme(e.target.value)}
        />
      </div>

      {blank.length > 0 && (
        <p className="text-sm text-band3">
          {blank.length} criterion/criteria still need a description of at least
          three characters.
        </p>
      )}

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
          disabled={!canSave || busy}
        >
          {busy
            ? "Saving…"
            : `Save as version ${(question.rubric?.version ?? 0) + 1}`}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className="btn-ghost text-sm"
          onClick={loadVersions}
        >
          History
        </button>
        <span className="text-sm text-ink3">
          The current version is kept, not overwritten.
        </span>
      </div>

      {versions && (
        <section className="rounded-md border border-line p-3">
          <p className="eyebrow">Rubric history</p>
          {versions.length === 0 ? (
            <p className="mt-1 text-sm text-ink3">No versions recorded.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {versions.map((version) => (
                <li key={version.id} className="flex flex-wrap gap-3">
                  <span className="font-mono tabular-nums">v{version.version}</span>
                  <span className="text-ink2">
                    {version.criteria_count} criteria ·{" "}
                    {version.total_criterion_marks} marks
                  </span>
                  <span className="text-ink3">
                    {new Date(version.created_at).toLocaleString()}
                  </span>
                  {version.is_active && (
                    <span className="text-band1">active</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

/**
 * A list of short strings, edited one per line.
 *
 * A textarea rather than tag chips on purpose: these lists are written by
 * someone transcribing a marking scheme, and typing four lines is faster than
 * four click-and-confirm interactions.
 */
function ListField({
  label,
  hint,
  items,
  onChange,
}: {
  label: string;
  hint: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <div>
      <label className="eyebrow">{label}</label>
      <textarea
        className="input mt-1 min-h-[4.5rem] w-full text-sm"
        value={items.join("\n")}
        placeholder="One per line"
        onChange={(e) =>
          onChange(
            e.target.value
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean),
          )
        }
      />
      <p className="mt-1 text-xs text-ink3">{hint}</p>
    </div>
  );
}
