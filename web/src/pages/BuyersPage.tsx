import { Calculator, Phone } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useDeskContext } from "@/app/desk-context";
import CountUp from "@/components/CountUp";
import { ChannelBadge } from "@/components/desk/ChannelBadge";
import { Dial } from "@/components/desk/CreditGauges";
import { TiltCard } from "@/components/desk/TiltCard";
import { Slider } from "@/components/ui/slider";
import { usePhoneCalls } from "@/hooks/usePhoneCalls";
import type { Buyer, LedgerEvent } from "@/lib/api";
import { inr, KIND_CLASSES, statusOf } from "@/lib/format";
import { tally } from "@/lib/ledger";
import { cn } from "@/lib/utils";

import { PageHeading } from "./PageHeading";

function initials(name: string) {
  return name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
}

function WhatIf({ buyer }: { buyer: Buyer }) {
  const [qty, setQty] = useState(20);
  const [rate, setRate] = useState(500);
  const value = qty * rate;
  const projected = buyer.running_balance_inr + value;
  const over = projected - buyer.credit_limit_inr;
  const ok = over <= 0;
  return (
    <div className="rounded-2xl bg-secondary/70 p-4">
      <p className="mb-3 inline-flex items-center gap-2 text-sm font-bold"><Calculator className="size-4" /> What if the next order is…</p>
      <div className="grid gap-4">
        <label className="grid gap-2 text-sm">
          <span className="flex justify-between"><span className="text-muted-foreground">Quantity</span><b>{qty} kg</b></span>
          <Slider value={[qty]} min={1} max={150} step={1} onValueChange={([v]) => setQty(v)} aria-label="Quantity in kg" />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="flex justify-between"><span className="text-muted-foreground">Rate</span><b>{inr(rate)}/kg</b></span>
          <Slider value={[rate]} min={100} max={1600} step={10} onValueChange={([v]) => setRate(v)} aria-label="Rate in rupees per kg" />
        </label>
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={ok ? "ok" : "hold"}
          initial={{ opacity: 0, y: 6, rotateX: -20 }}
          animate={{ opacity: 1, y: 0, rotateX: 0 }}
          exit={{ opacity: 0, y: -6 }}
          style={{ transformPerspective: 600 }}
          className={cn("mt-4 rounded-xl p-3 text-sm", ok ? "bg-booked-soft" : "bg-hold-soft")}
        >
          <p className={cn("font-extrabold", ok ? "text-booked" : "text-hold")}>{ok ? "Would book" : `Would be held: ${inr(over)} over the limit`}</p>
          <p className="text-muted-foreground">{inr(value)} order · balance {inr(projected)} of {inr(buyer.credit_limit_inr)}</p>
        </motion.div>
      </AnimatePresence>
      <p className="mt-2 text-xs text-muted-foreground">Estimate only. The firewall makes the real decision, including confidence and price-band checks.</p>
    </div>
  );
}

function BuyerCard({ buyer, events, index, phoneOrders }: { buyer: Buyer; events: LedgerEvent[]; index: number; phoneOrders: number | null }) {
  const mine = events.filter((e) => e.buyer_id === buyer.buyer_id);
  const t = tally(mine);
  const used = buyer.credit_limit_inr ? buyer.running_balance_inr / buyer.credit_limit_inr : 1;
  const level = used >= 0.95 ? "critical" : used >= 0.8 ? "tight" : "ok";
  const left = Math.max(0, buyer.credit_limit_inr - buyer.running_balance_inr);
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 90, damping: 18, delay: index * 0.08 }}>
      <TiltCard max={4}>
        <div className="grid gap-6 p-6">
          <div className="flex items-center gap-4">
            <span className="ink-key grid size-14 place-items-center rounded-2xl text-lg font-extrabold text-lime">{initials(buyer.canonical_name)}</span>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-2xl font-extrabold">{buyer.canonical_name}</h2>
              <p lang="ta" className="tamil text-muted-foreground">{buyer.tamil_speak_name}</p>
            </div>
            {phoneOrders !== null && (
              <Link
                to="/phone"
                className={cn("inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-semibold", phoneOrders > 0 ? "ink-key" : "surface text-muted-foreground hover:border-lime")}
                title="Orders this buyer placed through the Gnani phone agent"
              >
                <Phone className={cn("size-4", phoneOrders > 0 && "text-lime")} aria-hidden />
                {phoneOrders > 0 ? `${phoneOrders} by phone` : "No phone orders"}
              </Link>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <div className="relative">
              <Dial used={used} level={level} flash={false} className="size-40" />
              <div className="absolute inset-0 grid place-items-center text-center">
                <span><span className="block text-3xl font-extrabold">{Math.round(used * 100)}%</span><span className="text-xs text-muted-foreground">of limit used</span></span>
              </div>
            </div>
            <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-4">
              <div><dt className="text-xs text-muted-foreground">Credit left</dt><dd className="text-2xl font-extrabold">₹<CountUp to={left} separator="," duration={0.9} /></dd></div>
              <div><dt className="text-xs text-muted-foreground">Owed</dt><dd className="text-2xl font-extrabold">{inr(buyer.running_balance_inr)}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Booked today</dt><dd className="text-lg font-bold">{t.booked} · {inr(t.value)}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Held / asked again</dt><dd className="text-lg font-bold">{t.held} / {t.ask}</dd></div>
            </dl>
          </div>

          <WhatIf buyer={buyer} />

          <div>
            <p className="mb-2 text-sm font-bold">Recent entries</p>
            {mine.length === 0 ? (
              <p className="text-sm text-muted-foreground">No orders for this buyer yet.</p>
            ) : (
              <ul className="grid gap-1.5">
                {mine.slice(0, 5).map((e) => {
                  const st = statusOf(e.status);
                  return (
                    <li key={e.event_id} className={cn("flex items-center gap-3 rounded-xl px-3 py-2 text-sm", t.voided.has(e.event_id) ? "opacity-50 line-through" : "bg-white/70")}>
                      <span className="text-muted-foreground">{e.created_at}</span>
                      <ChannelBadge channel={e.channel} compact />
                      <span className="min-w-0 flex-1 truncate">{e.quantity} {e.unit} {e.sku_name}</span>
                      <b>{inr(e.trade_value_inr)}</b>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold", KIND_CLASSES[st.kind].chip)}>{st.label}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </TiltCard>
    </motion.div>
  );
}

export default function BuyersPage() {
  const desk = useDeskContext();
  const buyers = desk.desk?.buyers ?? [];
  const events = desk.desk?.events ?? [];
  const phoneOn = !!desk.desk?.phone_channel_enabled;
  const { log } = usePhoneCalls(100, phoneOn);
  // Orders each buyer placed through the phone agent, over the whole call log (not just recent entries).
  const phoneOrders = useMemo(() => {
    const counts = new Map<string, number>();
    for (const call of log?.calls ?? []) {
      for (const t of call.turns) {
        if (t.status !== "VOIDED_BY_UNDO") counts.set(t.buyer_id, (counts.get(t.buyer_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [log]);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeading title="Buyers" lead="Credit exposure for each account, with their recent orders and a what-if check before you quote a big order." />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        {buyers.map((b, i) => (
          <BuyerCard key={b.buyer_id} buyer={b} events={events} index={i} phoneOrders={phoneOn && log ? phoneOrders.get(b.buyer_id) ?? 0 : null} />
        ))}
      </div>
    </div>
  );
}
