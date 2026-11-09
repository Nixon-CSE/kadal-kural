import { BookOpen, Bot, KeyRound, Lock, Phone, ShieldCheck, Smartphone } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Fragment } from "react";

import { useDeskContext } from "@/app/desk-context";
import { TiltCard } from "@/components/desk/TiltCard";
import { KIND_CLASSES } from "@/lib/format";
import { cn } from "@/lib/utils";

import { PageHeading } from "./PageHeading";

const NODES = [
  { icon: Smartphone, title: "Trader's phone", body: "Any phone. The agent calls a whitelisted number." },
  { icon: Bot, title: "Gnani Agent Builder", body: "Dialling, speech recognition, Tamil voice. Fires book_trade each turn." },
  { icon: ShieldCheck, title: "Kadal Kural firewall", body: "Same deterministic checks as the desk. Returns the Tamil reply." },
  { icon: BookOpen, title: "Ledger", body: "Append-only entry, live on the desk with what was heard." },
];

const CALL = [
  { time: "11:50:24", heard: "குமரனுக்கு இருபது கிலோ டைகர் பிரான்", kind: "ask" as const, decision: "Asked again: no rate yet" },
  { time: "11:50:26", heard: "குமரனுக்கு இருபது கிலோ டைகர் பிரான் ஐநூறு ரேட்", kind: "booked" as const, decision: "Booked ₹10,000 (இருபது → 20, ஐநூறு → 500)" },
];

function Connector({ reduced }: { reduced: boolean }) {
  return (
    <div className="relative hidden h-1 flex-1 self-center overflow-hidden rounded-full bg-border md:block" aria-hidden>
      {!reduced && (
        <motion.span
          className="absolute inset-y-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-lime to-transparent"
          animate={{ left: ["-35%", "100%"] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </div>
  );
}

export default function PhonePage() {
  const desk = useDeskContext();
  const reduced = !!useReducedMotion();
  const on = !!desk.desk?.phone_channel_enabled;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-8">
      <PageHeading title="Phone line" lead="Traders who are away from the desk place orders by phone. Gnani Agent Builder takes the call; the same firewall decides every order.">
        <span className={cn("surface inline-flex items-center gap-2 rounded-full px-4 py-2 font-bold", on ? "text-booked" : "text-muted-foreground")}>
          <span className="relative flex size-3">
            {on && <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime opacity-70" />}
            <span className={cn("relative inline-flex size-3 rounded-full", on ? "bg-lime" : "border-2 border-undone")} />
          </span>
          {on ? "Phone line on" : "Phone line off"}
        </span>
      </PageHeading>

      <section aria-label="How a call reaches the ledger" className="flex flex-col items-stretch gap-4 md:flex-row">
        {NODES.map((n, i) => (
          <Fragment key={n.title}>
            <motion.div className="md:w-56" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 90, damping: 16, delay: i * 0.1 }}>
              <TiltCard>
                <div className="flex h-full flex-col gap-3 p-5">
                  <span className={cn("grid size-12 place-items-center rounded-2xl", i === 2 ? "lime-key" : "ink-key")}><n.icon className={cn("size-5", i === 2 ? "" : "text-lime")} /></span>
                  <h2 className="font-extrabold">{n.title}</h2>
                  <p className="text-sm text-muted-foreground">{n.body}</p>
                </div>
              </TiltCard>
            </motion.div>
            {i < NODES.length - 1 && <Connector reduced={reduced} />}
          </Fragment>
        ))}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <section className="surface rounded-3xl p-6" aria-labelledby="call-title">
          <h2 id="call-title" className="text-lg font-extrabold">Verified on a live call</h2>
          <p className="mt-1 text-sm text-muted-foreground">9 Nov 2026. The caller said “குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு”. The agent fired twice.</p>
          <ol className="mt-4 grid gap-3">
            {CALL.map((c, i) => (
              <motion.li key={c.time} initial={{ opacity: 0, x: -12 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.15 }} className="rounded-2xl bg-white/80 p-4 shadow-sm">
                <div className="flex items-center gap-3 text-sm"><span className="text-muted-foreground">{c.time}</span><span className={cn("rounded-full px-2.5 py-0.5 text-xs font-bold", KIND_CLASSES[c.kind].chip)}>{c.decision}</span></div>
                <p lang="ta" className="tamil mt-2 text-lg font-semibold">{c.heard}</p>
              </motion.li>
            ))}
          </ol>
          <p className="mt-4 text-sm text-muted-foreground">The half sentence had no rate, so it was held instead of guessed. Tamil number words were normalised by the same code the desk uses.</p>
        </section>

        <section className="surface rounded-3xl p-6" aria-labelledby="safe-title">
          <h2 id="safe-title" className="text-lg font-extrabold">Safe to expose</h2>
          <ul className="mt-4 grid gap-4">
            {[
              { icon: KeyRound, t: "Shared secret on every request", d: "X-Kadal-Token, compared in constant time. No token configured means the endpoint stays off." },
              { icon: Lock, t: "Only the phone endpoint is public", d: "Through a tunnel or proxy, every other route returns 403 and live audio is refused, so the ledger and speech credits are safe." },
              { icon: ShieldCheck, t: "Fails closed", d: "An empty, partial or unfilled turn gets “please repeat” and writes nothing." },
              { icon: Phone, t: "Any request format", d: "JSON, form fields, query parameters or headers: what the platform sends is logged by field name, never by secret." },
            ].map((x) => (
              <li key={x.t} className="flex gap-3">
                <span className="lime-key grid size-10 shrink-0 place-items-center rounded-xl"><x.icon className="size-4.5" /></span>
                <div><p className="font-bold">{x.t}</p><p className="text-sm text-muted-foreground">{x.d}</p></div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
