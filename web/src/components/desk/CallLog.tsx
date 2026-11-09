import { PhoneCall as PhoneIcon, PhoneOff, RefreshCw } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { usePhoneCalls } from "@/hooks/usePhoneCalls";
import type { CallTurn, PhoneCall } from "@/lib/api";
import { callTime } from "@/lib/channel";
import { inr, KIND_CLASSES, statusOf } from "@/lib/format";
import { cn } from "@/lib/utils";

/** "Kumaran Stores, 20 kg Tiger Prawn × ₹500 = ₹10,000", leaving out what was not heard. */
function detail(t: CallTurn): string {
  const parts = [t.buyer_name];
  if (t.quantity) parts.push(`${t.quantity} ${t.unit} ${t.sku_name}${t.rate_inr ? ` × ${inr(t.rate_inr)}` : ""}`);
  const priced = t.rate_inr > 0 && t.trade_value_inr > 0;
  return parts.join(", ") + (priced ? ` = ${inr(t.trade_value_inr)}` : "");
}

function CallCard({ call, index }: { call: PhoneCall; index: number }) {
  const { booked, held, asked_again: asked, undone } = call.counts;
  const outcome = [
    booked && `${booked} booked`, held && `${held} held`, asked && `${asked} asked again`, undone && `${undone} undone`,
  ].filter(Boolean).join(", ");
  return (
    <motion.li layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-2xl border bg-white">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-3">
        <span className="ink-key grid size-8 place-items-center rounded-lg"><PhoneIcon className="size-4 text-lime" aria-hidden /></span>
        <p className="font-bold">
          {index === 0 ? "Latest call" : "Call"} <span className="font-normal text-muted-foreground">at {callTime(call.started_at, call.turns[0]?.created_at)}</span>
        </p>
        {call.call_id && <code className="rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">{call.call_id}</code>}
        <p className="ml-auto text-sm text-muted-foreground">
          {outcome}{call.booked_value_inr > 0 && <> · <b className="text-foreground">{inr(call.booked_value_inr)}</b> booked</>}
        </p>
      </div>
      <ol className="divide-y">
        {call.turns.map((t) => {
          const st = statusOf(t.status);
          return (
            <li key={t.event_id} className="flex flex-wrap items-start gap-x-4 gap-y-1 px-4 py-3">
              <span className="order-1 text-sm text-muted-foreground tabular-nums sm:w-24 sm:pt-0.5">{callTime(t.recorded_at, t.created_at)}</span>
              <span className={cn("order-2 ml-auto rounded-full px-2.5 py-0.5 text-xs font-bold whitespace-nowrap sm:order-3", KIND_CLASSES[st.kind].chip)}>
                {t.voided ? "Booked, then undone" : st.label}
              </span>
              <div className="order-3 min-w-0 basis-full sm:order-2 sm:flex-1 sm:basis-0">
                <p lang="ta" className={cn("tamil font-semibold", t.voided && "line-through opacity-60")}>{t.raw_utterance}</p>
                {st.kind !== "undone" && <p className={cn("text-sm text-muted-foreground", t.voided && "line-through")}>{detail(t)}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </motion.li>
  );
}

/** Live log of calls placed through the Gnani Agent Builder agent, grouped from the ledger. */
export function CallLog() {
  const { log, error, reload } = usePhoneCalls();
  const on = log?.phone_channel_enabled ?? false;

  return (
    <section id="calls" aria-labelledby="calls-title" className="surface rounded-3xl p-6">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 id="calls-title" className="text-lg font-extrabold">Calls</h2>
        {log && log.summary.calls > 0 && (
          <p className="text-sm text-muted-foreground">
            {log.summary.calls} {log.summary.calls === 1 ? "call" : "calls"}, {log.summary.entries} ledger {log.summary.entries === 1 ? "entry" : "entries"}, {inr(log.summary.booked_value_inr)} booked by phone
          </p>
        )}
        <button type="button" onClick={() => void reload()} className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-sm font-semibold text-muted-foreground hover:text-foreground" aria-label="Refresh the call log">
          <RefreshCw className="size-3.5" aria-hidden /> Live
        </button>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">Every order the agent forwarded, as the firewall decided it. Updates every few seconds.</p>

      <div className="mt-4" aria-live="polite">
        {error && !log && <p className="rounded-2xl bg-hold-soft p-4 text-sm text-hold">Could not load the call log: {error}. Check that the server is running.</p>}
        {!log && !error && <div className="h-24 animate-pulse rounded-2xl bg-secondary" />}
        {log && log.calls.length === 0 && (
          <div className="flex items-start gap-3 rounded-2xl border border-dashed bg-white/60 p-5">
            {on ? <PhoneIcon className="mt-0.5 size-5 text-lime-deep" aria-hidden /> : <PhoneOff className="mt-0.5 size-5 text-muted-foreground" aria-hidden />}
            <p className="text-sm text-muted-foreground">
              {on
                ? "No calls yet. In the Gnani Agent Builder console, trigger a test call and say an order, for example “குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு”. It appears here within seconds."
                : "The phone line is off. Set KADAL_PHONE_WEBHOOK_TOKEN and connect the agent (docs/phone_channel.md), then calls appear here."}
            </p>
          </div>
        )}
        {log && log.calls.length > 0 && (
          <ul className="grid gap-3">
            <AnimatePresence initial={false}>
              {log.calls.map((c, i) => <CallCard key={c.key} call={c} index={i} />)}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </section>
  );
}
