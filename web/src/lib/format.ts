import type { Decision, Status } from "@/lib/api";

export type Kind = "booked" | "hold" | "ask" | "undone";

export const STATUS: Record<Status, { kind: Kind; label: string }> = {
  BOOKED: { kind: "booked", label: "Booked" },
  BOOKED_AFTER_BARGE_IN: { kind: "booked", label: "Booked, corrected" },
  CREDIT_HOLD_BREACH: { kind: "hold", label: "Credit hold" },
  PENDING_CLARIFICATION: { kind: "ask", label: "Ask again" },
  VOIDED_BY_UNDO: { kind: "undone", label: "Undone" },
};

export const statusOf = (s: Status | string) =>
  STATUS[s as Status] ?? { kind: "undone" as Kind, label: String(s || "Unknown") };

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const inr = (n: number | null | undefined) => "₹" + INR.format(Number(n || 0));
export const ms = (n: number | null | undefined) =>
  n && n > 0 ? `${INR.format(Math.round(n))} ms` : "–";
export const pct = (x: number | null | undefined) => `${Math.round((x || 0) * 100)}%`;

export const KIND_CLASSES: Record<Kind, { chip: string; edge: string; tint: string; dot: string }> = {
  booked: { chip: "bg-booked-soft text-booked", edge: "border-l-booked", tint: "bg-booked-soft/60", dot: "bg-lime" },
  hold: { chip: "bg-hold-soft text-hold", edge: "border-l-hold", tint: "bg-hold-soft/60", dot: "bg-hold" },
  ask: { chip: "bg-ask-soft text-ask", edge: "border-l-ask", tint: "bg-ask-soft/60", dot: "bg-ask" },
  undone: { chip: "bg-undone-soft text-undone", edge: "border-l-undone", tint: "bg-undone-soft/60", dot: "bg-undone" },
};

/** Plain-language reason for a decision, shown under its stamp. */
export function decisionReason(d: Decision, gate: number): string {
  const kind = statusOf(d.status).kind;
  if (d.status === "VOIDED_BY_UNDO") return "Reversed the last booked order. The original entry stays in the ledger, struck through.";
  if (kind === "booked") return `Within credit. Balance now ${inr(d.projected_balance_inr)} of ${inr(d.credit_limit_inr)}.`;
  if (kind === "hold") return `${inr(d.excess_amount_inr)} over the credit limit. Not dispatched.`;
  if (d.confidence !== undefined && d.confidence < gate)
    return `Confidence ${pct(d.confidence)} is below the ${pct(gate)} gate, so the trader is asked to repeat.`;
  return "Could not read a complete order, so the trader is asked to repeat.";
}

export const TRY_ORDERS = [
  { text: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு", why: "Within credit, so it books ₹10,000", kind: "booked" as Kind },
  { text: "செந்திலுக்கு 40 கிலோ வஞ்சரம் 740 ரேட்டு", why: "Goes over Senthil's limit, so it is held", kind: "hold" as Kind },
  { text: "செந்திலுக்கு 25 கிலோ மட்டும் போடு", why: "Correction after a hold: books the smaller order", kind: "booked" as Kind },
  { text: "கடைசி ஆர்டர் கேன்சல்", why: "Voice undo: reverses the last booking", kind: "undone" as Kind },
  { text: "செந்திலுக்கு 10 கிலோ வஞ்சரம் 700 குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு", why: "Two orders in one breath", kind: "booked" as Kind },
  { text: "குமரனுக்கு 20 கிலோ டைகர் பிரான் 60 ரேட்டு", why: "₹60/kg is not a prawn price, so it asks again", kind: "ask" as Kind },
];
