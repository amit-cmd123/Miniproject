import { useCallback, useEffect, useState } from "react";
import { Shell, type View } from "./components/Shell";
import { Transcribe } from "./views/Transcribe";
import { Library } from "./views/Library";
import { Evaluation, Review, Rubrics, Validation } from "./views/Planned";
import { api } from "./lib/api";
import type { ProviderInfo } from "./lib/types";

export default function App() {
  const [view, setView] = useState<View>("transcribe");
  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // The model loads in the background at startup, so poll until it is ready
  // and the badge in the header can stop saying "loading".
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const info = await api.providerInfo();
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
  }, []);

  const onSaved = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <Shell view={view} onNavigate={setView} provider={provider}>
      {view === "transcribe" && <Transcribe onSaved={onSaved} />}
      {view === "library" && <Library refreshKey={refreshKey} />}
      {view === "rubrics" && <Rubrics />}
      {view === "evaluation" && <Evaluation />}
      {view === "review" && <Review />}
      {view === "validation" && <Validation />}
    </Shell>
  );
}
