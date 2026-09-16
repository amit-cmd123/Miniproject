import type { ReactNode } from "react";
import type { ProviderInfo } from "../lib/types";

export type View = "transcribe" | "library" | "rubrics" | "evaluation" | "review" | "validation";

interface NavItem {
  id: View;
  label: string;
  part: string;
  ready: boolean;
}

const NAV: NavItem[] = [
  { id: "transcribe", label: "Transcribe", part: "Part 1", ready: true },
  { id: "library", label: "Answer library", part: "Part 1", ready: true },
  { id: "rubrics", label: "Questions & rubrics", part: "Part 2", ready: false },
  { id: "evaluation", label: "Evaluation", part: "Part 3", ready: false },
  { id: "review", label: "Examiner review", part: "Part 4", ready: false },
  { id: "validation", label: "Validation", part: "Part 4", ready: false },
];

export function Shell({
  view,
  onNavigate,
  provider,
  children,
}: {
  view: View;
  onNavigate: (view: View) => void;
  provider: ProviderInfo | null;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
          <div className="flex items-baseline gap-2.5">
            <span className="font-display text-lg font-bold tracking-tight">EvalNova</span>
            <span className="font-display text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-accent">
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
                      ? "bg-accentSoft text-accent font-semibold"
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

          {provider && <EngineBadge provider={provider} />}
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-7">{children}</main>
    </div>
  );
}

function EngineBadge({ provider }: { provider: ProviderInfo }) {
  const tone = provider.is_mock
    ? "border-band3 text-band3"
    : provider.is_ready
      ? "border-band1 text-band1"
      : "border-line text-ink3";
  const label = provider.is_mock
    ? "Mock engine"
    : provider.is_ready
      ? "Model ready"
      : "Model loading";

  return (
    <div
      className={`ml-auto flex items-center gap-2 rounded-full border px-3 py-1 ${tone}`}
      title={`${provider.model_name} on ${provider.device} — ${provider.detail}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      <span className="font-display text-[0.7rem] font-semibold uppercase tracking-wider">
        {label}
      </span>
      <span className="font-mono text-[0.68rem] text-ink3">{provider.device}</span>
    </div>
  );
}
