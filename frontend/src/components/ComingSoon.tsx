import type { ReactNode } from "react";

/**
 * A prototype of a screen that is not built yet.
 *
 * Deliberately not an empty "coming soon" placeholder: it shows the real
 * layout, greyed out, next to the specific work that has to happen and the
 * endpoints that will back it. The point is that a panel can see what Part 2,
 * 3 and 4 will look like, and the team can see exactly what they are building.
 */
export function ComingSoon({
  part,
  title,
  question,
  phase,
  owner,
  scope,
  endpoints,
  children,
}: {
  part: string;
  title: string;
  question: string;
  phase: string;
  owner: string;
  scope: string[];
  endpoints: string[];
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3 border-b border-line pb-5">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded bg-accentSoft px-2 py-0.5 font-mono text-xs font-semibold text-accent">
            {part}
          </span>
          <span className="rounded-full border border-band3 px-2.5 py-0.5 font-display text-[0.68rem] font-semibold uppercase tracking-wider text-band3">
            Not built yet
          </span>
          <span className="font-mono text-xs text-ink3">{phase}</span>
        </div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="max-w-[60ch] text-ink2 italic">{question}</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* The prototype of the real screen, dimmed and inert.
            The notice sits above it rather than floating over it - an overlay
            in the middle of the layout hides exactly the content a viewer is
            trying to read. */}
        <section aria-label={`${title} prototype`} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-md border border-dashed border-line bg-surface2 px-4 py-2.5">
            <p className="font-display text-sm font-semibold">Interface prototype</p>
            <p className="text-sm text-ink2">
              The layout is designed; the logic behind it is {phase.toLowerCase()} work.
            </p>
          </div>
          <div className="pointer-events-none select-none opacity-55 grayscale">{children}</div>
        </section>

        <aside className="flex flex-col gap-5">
          <div className="card p-5">
            <p className="eyebrow">Owned by</p>
            <p className="mt-1 font-display text-sm font-semibold">{owner}</p>
          </div>

          <div className="card p-5">
            <p className="eyebrow">What this screen will do</p>
            <ul className="mt-2.5 flex flex-col gap-2">
              {scope.map((item) => (
                <li key={item} className="flex gap-2.5 text-sm text-ink2">
                  <span className="mt-[7px] h-1 w-1 flex-none rounded-full bg-accent" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="card p-5">
            <p className="eyebrow">Endpoints it will call</p>
            <ul className="mt-2.5 flex flex-col gap-1.5">
              {endpoints.map((endpoint) => (
                <li key={endpoint} className="font-mono text-xs text-ink2">
                  {endpoint}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-ink3">
              These are registered on the API now and return 501 with the workstream
              that owns them, so the contract is fixed before the code exists.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
