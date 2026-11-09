// Typed client for the Kadal Kural FastAPI gateway (same origin in production, proxied by Vite in dev).

export type Status =
  | "BOOKED"
  | "BOOKED_AFTER_BARGE_IN"
  | "CREDIT_HOLD_BREACH"
  | "PENDING_CLARIFICATION"
  | "VOIDED_BY_UNDO";

export interface Buyer {
  buyer_id: string;
  canonical_name: string;
  tamil_speak_name: string;
  credit_limit_inr: number;
  running_balance_inr: number;
  phone_e164: string;
}

export interface LedgerEvent {
  event_id: number;
  created_at: string;
  buyer_id: string;
  buyer_name: string;
  sku_name: string;
  quantity: number;
  unit: string;
  rate_inr: number;
  trade_value_inr: number;
  previous_balance_inr: number;
  projected_balance_inr: number;
  credit_limit_inr: number;
  status: Status;
  confidence: number;
  raw_utterance: string;
  normalized_clause: string;
  upi_payment_uri: string;
  upi_link_visible: boolean;
  voids_event_id: number | null;
  buyer_guess: string | null;
  buyer_guess_confidence: number | null;
  sku_guess: string | null;
  sku_guess_confidence: number | null;
}

export interface Snapshot {
  buyers: Buyer[];
  events: LedgerEvent[];
}

export interface DeskState extends Snapshot {
  domain_title: string;
  confidence_threshold: number;
  gnani_live_key_configured: boolean;
  phone_channel_enabled: boolean;
}

/** One firewall decision as returned by /api/v1/ingest and the live socket. */
export interface Decision {
  event_id?: number;
  status: Status;
  buyer_id?: string;
  buyer_name?: string;
  sku_name?: string;
  quantity?: number;
  unit?: string;
  rate_inr?: number;
  trade_value_inr?: number;
  previous_balance_inr?: number;
  projected_balance_inr?: number;
  credit_limit_inr?: number;
  excess_amount_inr?: number;
  confidence?: number;
  tts_response_tamil: string;
  stt_latency_ms?: number;
  timbre_ttfb_ms?: number;
  audio_wav_b64?: string;
}

export interface TurnResult {
  decisions: Decision[];
  snapshot: Snapshot;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`the server answered ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  state: () => fetch("/api/v1/state").then((r) => json<DeskState>(r)),
  ingest: (transcript: string) =>
    fetch("/api/v1/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, synthesize_tts: true }),
    }).then((r) => json<TurnResult>(r)),
  reset: () => fetch("/api/v1/reset", { method: "POST" }).then((r) => json<{ snapshot: Snapshot }>(r)),
};

/** Messages the live-audio socket sends. */
export type LiveMessage =
  | { type: "error"; message: string }
  | { type: "prisma_connected"; session_id: string }
  | { type: "barge_in_and_segment"; segment_text: string; stt_latency_ms: number }
  | {
      type: "credit_decisions";
      assembled_transcript: string;
      stt_latency_ms: number;
      decisions: Decision[];
      snapshot: Snapshot;
    };

/** The game's sandbox firewall: the same engine on an isolated ledger. */
export const sandbox = {
  reset: () => fetch("/api/v1/sandbox/reset", { method: "POST" }).then((r) => json<{ buyers: Buyer[] }>(r)),
  evaluate: (transcript: string) =>
    fetch("/api/v1/sandbox/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript }),
    }).then((r) => json<{ decisions: Decision[]; buyers: Buyer[] }>(r)),
};
