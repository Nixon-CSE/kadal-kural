import { Play, Timer } from "lucide-react";
import { motion } from "motion/react";

import CountUp from "@/components/CountUp";
import SpotlightCard from "@/components/SpotlightCard";
import type { Decision } from "@/lib/api";
import { KIND_CLASSES, decisionReason, inr, ms, pct, statusOf } from "@/lib/format";
import { cn } from "@/lib/utils";

const SPOT: Record<string, string> = { booked: "#84cc16", hold: "#ef4444", ask: "#f0b93a", undone: "#94a3b8" };

export function DecisionCard({
  d, gate, sttMs, typed, index, onPlay,
}: { d: Decision; gate: number; sttMs: number; typed: boolean; index: number; onPlay: () => void }) {
  const st = statusOf(d.status);
  const k = KIND_CLASSES[st.kind];
  const hasTrade = d.buyer_name !== undefined && d.status !== "VOIDED_BY_UNDO" && (d.quantity ?? 0) > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, rotateX: -12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, rotateX: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 160, damping: 18, delay: index * 0.08 }}
      style={{ transformPerspective: 900 }}
    >
      <SpotlightCard theme="light" spotlightColor={SPOT[st.kind]} intensity={0.22} spotlightSize={300} className="!rounded-2xl !p-0">
        <div className={cn("border-l-[6px] p-5", k.edge)}>
          <div className={cn("pointer-events-none absolute inset-0 -z-10", k.tint)} />
          <div className="flex flex-wrap items-center gap-3">
            <motion.span
              initial={{ scale: 1.6, rotate: -8, opacity: 0 }}
              animate={{ scale: 1, rotate: 0, opacity: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.1 + index * 0.08 }}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold",
                st.kind === "booked" ? "lime-key" : k.chip,
              )}
            >
              {st.label}
            </motion.span>
            <span className="text-sm text-muted-foreground">{decisionReason(d, gate)}</span>
          </div>

          {hasTrade && (
            <dl className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(118px,1fr))] gap-x-6 gap-y-3">
              <Field label="Buyer" value={d.buyer_name} />
              <Field label="Item" value={d.sku_name} />
              <Field label="Quantity" value={`${d.quantity} ${d.unit}`} />
              <Field label="Rate" value={`${inr(d.rate_inr)}/${d.unit}`} />
              <div>
                <dt className="text-xs text-muted-foreground">Value</dt>
                <dd className="text-2xl font-extrabold tracking-tight [font-stretch:90%]">
                  ₹<CountUp to={d.trade_value_inr ?? 0} separator="," duration={0.9} trigger="load" />
                </dd>
              </div>
            </dl>
          )}

          <div className="mt-4 flex items-start gap-3">
            <button
              type="button"
              disabled={!d.audio_wav_b64}
              onClick={onPlay}
              aria-label="Play the spoken reply"
              className="ink-key grid size-10 shrink-0 place-items-center rounded-full transition-transform hover:scale-105 active:scale-95 disabled:opacity-30"
            >
              <Play className="size-4 fill-lime text-lime" />
            </button>
            <p lang="ta" className="tamil text-[1.05rem] leading-relaxed">{d.tts_response_tamil}</p>
          </div>

          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1"><Timer className="size-3.5" /> Speech to text <b className="text-foreground">{typed ? "typed order" : ms(sttMs)}</b></span>
            <span>Reply first audio <b className="text-foreground">{ms(d.timbre_ttfb_ms)}</b></span>
            {d.confidence !== undefined && <span>Confidence <b className="text-foreground">{pct(d.confidence)}</b></span>}
          </div>
        </div>
      </SpotlightCard>
    </motion.div>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-base leading-snug font-bold break-words">{value}</dd>
    </div>
  );
}
