import { useCallback, useEffect, useState } from "react";

import { api, type CallLog } from "@/lib/api";

const POLL_MS = 4000;

/** The phone line's call log, refreshed while the page is visible. Nothing is fetched when disabled. */
export function usePhoneCalls(limit = 20, enabled = true) {
  const [log, setLog] = useState<CallLog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLog(await api.calls(limit));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [limit]);

  useEffect(() => {
    if (!enabled) return;
    void load();
    const id = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { window.clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, [load, enabled]);

  return { log, error, reload: load };
}
