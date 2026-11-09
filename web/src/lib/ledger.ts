import type { LedgerEvent } from "@/lib/api";
import { statusOf } from "@/lib/format";

/** Counts for the stats row and filters; entries reversed by an undo are excluded. */
export function tally(events: LedgerEvent[]) {
  const voided = new Set(events.filter((e) => e.voids_event_id).map((e) => Number(e.voids_event_id)));
  const live = events.filter((e) => !voided.has(e.event_id));
  const of = (k: string) => live.filter((e) => statusOf(e.status).kind === k);
  return {
    voided,
    booked: of("booked").length,
    value: of("booked").reduce((s, e) => s + e.trade_value_inr, 0),
    held: of("hold").length,
    ask: of("ask").length,
  };
}
