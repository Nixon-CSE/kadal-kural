import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { BADGES, RANKS, type BadgeId } from "./data";

const KEY = "kk-harbour-shift-v1";

interface Progress {
  xp: number;
  badges: BadgeId[];
  best: number;
}

const EMPTY: Progress = { xp: 0, badges: [], best: 0 };

function load(): Progress {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Progress) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function rankOf(xp: number) {
  const idx = RANKS.reduce((acc, r, i) => (xp >= r.min ? i : acc), 0);
  const next = RANKS[idx + 1];
  const into = xp - RANKS[idx].min;
  const span = next ? next.min - RANKS[idx].min : 1;
  return { rank: RANKS[idx].name, next: next?.name ?? null, pct: next ? Math.min(1, into / span) : 1, toNext: next ? next.min - xp : 0 };
}

/** XP, badges and best score, kept in this browser only. */
export function useProgress() {
  const [p, setP] = useState<Progress>(load);
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* storage unavailable */ }
  }, [p]);

  const addXp = useCallback((n: number) => setP((s) => ({ ...s, xp: s.xp + n })), []);
  const award = useCallback((id: BadgeId) => {
    setP((s) => {
      if (s.badges.includes(id)) return s;
      toast.success(`Badge unlocked: ${BADGES[id].title}`, { description: BADGES[id].body });
      return { ...s, badges: [...s.badges, id], xp: s.xp + 50 };
    });
  }, []);
  const recordBest = useCallback((score: number) => setP((s) => (score > s.best ? { ...s, best: score } : s)), []);
  const reset = useCallback(() => setP(EMPTY), []);
  return { ...p, addXp, award, recordBest, reset };
}

export type ProgressApi = ReturnType<typeof useProgress>;
