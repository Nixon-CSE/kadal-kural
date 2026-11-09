import { Move3d } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { lazy, Suspense, useMemo } from "react";

import { useDeskContext } from "@/app/desk-context";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { LedgerEvent } from "@/lib/api";
import { inr, statusOf } from "@/lib/format";
import { tally } from "@/lib/ledger";

import { PageHeading } from "./PageHeading";

const Bars3D = lazy(() => import("@/components/three/Bars3D"));

// benchmark/REPORT.md, 405 cached Prisma transcripts (45 utterances × 9 conditions).
const BENCH = [
  { c: "Clean", wer: 10.2, sku: 97.1, rate: 97.1, p50: 266 },
  { c: "Harbour 10 dB", wer: 11.8, sku: 97.1, rate: 95.7, p50: 214 },
  { c: "Harbour 5 dB", wer: 12.1, sku: 97.1, rate: 95.7, p50: 218 },
  { c: "Market 10 dB", wer: 12.8, sku: 97.1, rate: 97.1, p50: 208 },
  { c: "Market 5 dB", wer: 17.6, sku: 97.1, rate: 92.9, p50: 209 },
  { c: "Traffic 10 dB", wer: 11.1, sku: 97.1, rate: 95.7, p50: 223 },
  { c: "Traffic 5 dB", wer: 11.4, sku: 97.1, rate: 95.7, p50: 202 },
  { c: "Ice crusher 10 dB", wer: 12.3, sku: 95.7, rate: 95.7, p50: 204 },
  { c: "Ice crusher 5 dB", wer: 13.6, sku: 97.1, rate: 97.1, p50: 217 },
];

const KIND_COLOR = { booked: "#a3e635", hold: "#ef6b6b", ask: "#f0b93a", undone: "#94a3b8" } as const;

function Panel({ title, note, children, className = "" }: { title: string; note?: string; children: React.ReactNode; className?: string }) {
  return (
    <motion.section initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className={`surface rounded-3xl p-5 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-extrabold tracking-tight">{title}</h2>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </div>
      {children}
    </motion.section>
  );
}

function Donut({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  const R = 40, C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 100 100" className="size-44 -rotate-90 drop-shadow-[0_8px_14px_rgba(15,29,20,0.15)]" role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")}>
        <circle cx="50" cy="50" r={R} fill="none" stroke="#eef2e9" strokeWidth="14" />
        {total > 0 && parts.map((p) => {
          const len = (p.value / total) * C;
          const el = (
            <motion.circle key={p.label} cx="50" cy="50" r={R} fill="none" stroke={p.color} strokeWidth="14"
              strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }} />
          );
          offset += len;
          return el;
        })}
      </svg>
      <ul className="grid gap-2 text-sm">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-2"><span className="size-3 rounded" style={{ background: p.color }} /> {p.label} <b className="ml-auto pl-6">{p.value}</b></li>
        ))}
        <li className="border-t pt-2 text-muted-foreground">Total <b className="float-right text-foreground">{total}</b></li>
      </ul>
    </div>
  );
}

function Histogram({ events, gate }: { events: LedgerEvent[]; gate: number }) {
  const bins = [0, 0.5, 0.7, gate, 0.9, 1.0001];
  const counts = bins.slice(0, -1).map((lo, i) => events.filter((e) => e.confidence >= lo && e.confidence < bins[i + 1]).length);
  const max = Math.max(1, ...counts);
  const labels = ["< 50%", "50–70%", `70–${Math.round(gate * 100)}%`, `${Math.round(gate * 100)}–90%`, "≥ 90%"];
  return (
    <div className="flex h-48 items-end gap-3">
      {counts.map((c, i) => (
        <div key={labels[i]} className="flex flex-1 flex-col items-center gap-2">
          <span className="text-sm font-bold">{c}</span>
          <motion.div
            initial={{ height: 0 }} animate={{ height: `${(c / max) * 120 + 4}px` }} transition={{ type: "spring", stiffness: 80, damping: 16, delay: i * 0.05 }}
            className={i >= 3 ? "w-full rounded-t-lg bg-gradient-to-t from-lime-deep to-lime" : "w-full rounded-t-lg bg-gradient-to-t from-ask to-amber-200"}
          />
          <span className="text-center text-[11px] text-muted-foreground">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

export default function InsightsPage() {
  const desk = useDeskContext();
  const reduced = !!useReducedMotion();
  const events = useMemo(() => desk.desk?.events ?? [], [desk.desk?.events]);
  const gate = desk.desk?.confidence_threshold ?? 0.82;
  const t = tally(events);
  const undone = events.filter((e) => statusOf(e.status).kind === "undone").length;
  const bars = [
    { label: "Booked", value: t.booked, color: KIND_COLOR.booked, display: String(t.booked) },
    { label: "Held", value: t.held, color: KIND_COLOR.hold, display: String(t.held) },
    { label: "Asked again", value: t.ask, color: KIND_COLOR.ask, display: String(t.ask) },
    { label: "Undone", value: undone, color: KIND_COLOR.undone, display: String(undone) },
  ];
  const byBuyer = (desk.desk?.buyers ?? []).map((b) => ({
    name: b.canonical_name,
    value: events.filter((e) => e.buyer_id === b.buyer_id && statusOf(e.status).kind === "booked" && !t.voided.has(e.event_id)).reduce((s, e) => s + e.trade_value_inr, 0),
  }));
  const maxBuyer = Math.max(1, ...byBuyer.map((b) => b.value));

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeading title="Insights" lead="What this session's ledger says, next to the offline noise benchmark. Session numbers reset with the balances." />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Decisions this session" note="Drag to rotate">
          <div className="relative h-80">
            <Suspense fallback={<div className="h-full animate-pulse rounded-2xl bg-secondary" />}>
              <Bars3D bars={bars} reduced={reduced} />
            </Suspense>
            <Move3d className="pointer-events-none absolute right-2 bottom-2 size-5 text-muted-foreground" />
          </div>
        </Panel>
        <div className="grid gap-6">
          <Panel title="Decision mix">
            <Donut parts={bars.map((b) => ({ label: b.label, value: b.value, color: b.color }))} />
          </Panel>
          <Panel title="Booked value by buyer">
            <ul className="grid gap-3">
              {byBuyer.map((b) => (
                <li key={b.name}>
                  <div className="mb-1 flex justify-between text-sm"><span className="font-semibold">{b.name}</span><b>{inr(b.value)}</b></div>
                  <div className="h-3 overflow-hidden rounded-full bg-secondary">
                    <motion.div className="h-full rounded-full bg-gradient-to-r from-lime to-lime-deep" initial={{ width: 0 }} animate={{ width: `${(b.value / maxBuyer) * 100}%` }} transition={{ type: "spring", stiffness: 70, damping: 16 }} />
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel title="Confidence of every entry" note={`Lime bars clear the ${Math.round(gate * 100)}% gate`}>
        {events.length ? <Histogram events={events} gate={gate} /> : <p className="py-10 text-center text-muted-foreground">Run a few orders on the desk to fill this in.</p>}
      </Panel>

      <Panel title="Noise benchmark" note="benchmark/REPORT.md · 0 silent financial errors in all 560 noisy trades">
        <div className="-mx-5 overflow-x-auto px-5">
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow><TableHead>Condition</TableHead><TableHead className="text-right">Word error (norm.)</TableHead><TableHead className="text-right">Item correct</TableHead><TableHead className="text-right">Rate correct</TableHead><TableHead className="text-right">STT P50</TableHead><TableHead>Rate accuracy</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {BENCH.map((r) => (
                <TableRow key={r.c}>
                  <TableCell className="font-semibold">{r.c}</TableCell>
                  <TableCell className="text-right">{r.wer}%</TableCell>
                  <TableCell className="text-right">{r.sku}%</TableCell>
                  <TableCell className="text-right">{r.rate}%</TableCell>
                  <TableCell className="text-right">{r.p50} ms</TableCell>
                  <TableCell className="w-48">
                    <div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-lime-deep" style={{ width: `${(r.rate - 85) * (100 / 15)}%` }} /></div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Synthetic speaker and synthetic noise; the rate bar spans 85–100%.</p>
      </Panel>
    </div>
  );
}
