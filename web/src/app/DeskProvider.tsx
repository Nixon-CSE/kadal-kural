import type { ReactNode } from "react";

import { useDesk } from "@/hooks/useDesk";

import { DeskContext } from "./desk-context";

export function DeskProvider({ children }: { children: ReactNode }) {
  const desk = useDesk();
  return <DeskContext.Provider value={desk}>{children}</DeskContext.Provider>;
}
