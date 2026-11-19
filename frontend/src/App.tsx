import { useCallback, useEffect, useState } from "react";
import { Shell, type View } from "./components/Shell";
import { Transcribe } from "./views/Transcribe";
import { Library } from "./views/Library";
import { Rubrics } from "./views/Rubrics";
import { Evaluate } from "./views/Evaluate";
import { ReviewQueue } from "./views/ReviewQueue";
import { Validation } from "./views/Validation";
import { api } from "./lib/api";
import { useEngine } from "./lib/engine";
import type { ProviderInfo } from "./lib/types";

export default function App() {
  const [view, setView] = useState<View>("transcribe");
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // The engine switch lives here rather than in the upload screen, because
  // transcription and marking are on different screens and both obey it. One
  // choice, one place it is held.
  const engine = useEngine();
  const selected = engine.engine;

  // The model loads in the background at startup, so poll until it is ready
  // and the badge in the header can stop saying "loading". Re-runs when the
  // engine changes: the badge describes the engine that is selected, and the
  // local model's readiness is not the cloud model's.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const info = await api.providerInfo(selected);
        if (cancelled) return;
        setProvider(info);
        if (!info.is_ready && !info.is_mock) {
          timer = window.setTimeout(poll, 3000);
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(poll, 5000);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [selected]);

  // Bumped whenever work lands, so a screen opened afterwards shows it. Each
  // view reloads on its own rather than the app holding one shared cache -
  // the cost of a refetch is nothing next to the cost of showing stale marks.
  const onSaved = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <Shell view={view} onNavigate={setView} provider={provider} engine={engine}>
      {view === "transcribe" && <Transcribe onSaved={onSaved} engine={engine} />}
      {view === "library" && <Library refreshKey={refreshKey} />}
      {view === "rubrics" && <Rubrics engine={engine} />}
      {view === "evaluation" && <Evaluate refreshKey={refreshKey} engine={engine} />}
      {view === "review" && <ReviewQueue refreshKey={refreshKey} />}
      {view === "validation" && <Validation refreshKey={refreshKey} />}
    </Shell>
  );
}
