import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Engine, EngineOption } from "./types";

const STORAGE_KEY = "evalnova.engine";

/**
 * Which engine the next request runs on.
 *
 * Held in the application rather than on the server because it is a property
 * of what the examiner is doing right now, not of the installation: during a
 * demo the same booklet goes through Gemini and then through the local model,
 * and a server-side setting would mean a restart between the two.
 *
 * It is remembered across reloads, because losing the choice on a refresh
 * mid-session is the kind of small betrayal that makes a tool feel unsafe.
 * It falls back to the local engine whenever Gemini turns out to be
 * unavailable, since an engine that cannot run is not a choice.
 */
export function useEngine() {
  const [engine, setEngineState] = useState<Engine>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "gemini" || saved === "local") return saved;
    } catch {
      /* private browsing, or storage disabled - the default is fine */
    }
    return "local";
  });

  const [options, setOptions] = useState<EngineOption[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await api.engines();
        if (cancelled) return;
        setOptions(body.engines);

        // A remembered choice that is no longer possible - the key was taken
        // out of .env since last time - must not sit there looking selected
        // and then fail on the first upload.
        const gemini = body.engines.find((e) => e.id === "gemini");
        if (gemini && !gemini.available) {
          setEngineState((current) => (current === "gemini" ? "local" : current));
        }
      } catch {
        /* the badge and switch degrade to the local engine on their own */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setEngine = useCallback((next: Engine) => {
    setEngineState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* not remembering the choice is survivable; failing to make it is not */
    }
  }, []);

  const option = options?.find((e) => e.id === engine) ?? null;
  const geminiAvailable =
    options?.find((e) => e.id === "gemini")?.available ?? false;

  return { engine, setEngine, options, option, geminiAvailable };
}

export type EngineState = ReturnType<typeof useEngine>;
