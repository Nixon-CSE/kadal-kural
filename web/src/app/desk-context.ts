import { createContext, useContext } from "react";

import type { DeskApi } from "@/hooks/useDesk";

export const DeskContext = createContext<DeskApi | null>(null);

/** The single shared desk session (mic, ledger, history) used by every page. */
export function useDeskContext(): DeskApi {
  const desk = useContext(DeskContext);
  if (!desk) throw new Error("useDeskContext must be used inside <DeskProvider>");
  return desk;
}
