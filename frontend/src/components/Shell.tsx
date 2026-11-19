import type { ReactNode } from "react";
import { Logo } from "./Logo";
import { EngineBadge } from "./EngineToggle";
import type { EngineState } from "../lib/engine";
import type { ProviderInfo } from "../lib/types";

export type View = "transcribe" | "library" | "rubrics" | "evaluation" | "review" | "validation";

interface NavItem {
  id: View;
  label: string;
  part: string;
  ready: boolean;
}

// Ordered as the work happens: read the page, define the standard, mark
// against it, confirm the mark, then measure whether the marking was any good.
const NAV: NavItem[] = [
  { id: "transcribe", label: "Transcribe", part: "Part 1", ready: true },
  { id: "library", label: "Answer library", part: "Part 1", ready: true },
  { id: "rubrics", label: "Questions & rubrics", part: "Part 2", ready: true },
  { id: "evaluation", label: "Evaluation", part: "Part 3", ready: true },
  { id: "review", label: "Examiner review", part: "Part 4", ready: true },
  { id: "validation", label: "Validation", part: "Part 4", ready: true },
];

export function Shell({
  view,
  onNavigate,
  provider,
  engine,
  children,
}: {
  view: View;
  onNavigate: (view: View) => void;
  provider: ProviderInfo | null;
  engine: EngineState;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
          <div className="flex items-center gap-2.5">
            <Logo size={28} className="text-ink" />
            <span className="font-display text-lg font-extrabold tracking-tightest">
              EvalNova
            </span>
            <span className="font-display text-[0.68rem] font-bold uppercase tracking-label text-energyInk">
              Core
            </span>
          </div>

          <nav className="flex flex-wrap gap-1" aria-label="Sections">
            {NAV.map((item) => {
              const active = item.id === view;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-md px-3 py-1.5 font-display text-sm transition-colors ${
                    active
                      ? "bg-accentSoft font-bold text-accent"
                      : "text-ink2 hover:bg-surface2"
                  }`}
                >
                  {item.label}
                  {!item.ready && (
                    <span className="ml-1.5 font-mono text-[0.6rem] uppercase text-ink3">
                      soon
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <EngineBadge state={engine} />
            {provider && <ModelBadge provider={provider} />}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-7">{children}</main>
    </div>
  );
}

/** Whether the selected engine's model is loaded and ready to read a page. */
function ModelBadge({ provider }: { provider: ProviderInfo }) {
  const tone = provider.is_mock
    ? "border-band3 text-band3"
    : provider.is_ready
      ? "border-band1 text-band1"
      : "border-line text-ink3";
  const label = provider.is_mock
    ? "Stand-in engine"
    : provider.is_ready
      ? "Model ready"
      : "Model loading";

  return (
    <div
      className={`flex items-center gap-2 rounded-full border px-3 py-1 ${tone}`}
      title={`${provider.model_name} on ${provider.device} — ${provider.detail}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      <span className="font-display text-[0.68rem] font-bold uppercase tracking-wider">
        {label}
      </span>
      <span className="font-mono text-[0.68rem] text-ink3">{provider.device}</span>
    </div>
  );
}
