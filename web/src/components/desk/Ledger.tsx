import { ArrowRight, ChevronRight, Download, QrCode, Search } from "lucide-react";
import { motion } from "motion/react";
import { QRCodeSVG } from "qrcode.react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Buyer, LedgerEvent } from "@/lib/api";
import { inr, KIND_CLASSES, pct, statusOf, type Kind } from "@/lib/format";
import { cn } from "@/lib/utils";

import { tally } from "@/lib/ledger";

type Filter = "all" | Kind;
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "booked", label: "Booked" },
  { value: "hold", label: "Held" },
  { value: "ask", label: "Ask again" },
  { value: "undone", label: "Undone" },
];

function StatusChip({ status }: { status: string }) {
  const st = statusOf(status);
  return <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-xs font-bold whitespace-nowrap", KIND_CLASSES[st.kind].chip)}>{st.label}</span>;
}

function ConfidenceBar({ value, gate }: { value: number; gate: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-secondary">
        <span className={cn("block h-full rounded-full", value < gate ? "bg-ask" : "bg-lime-deep")} style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      {pct(value)}
    </span>
  );
}

function downloadCsv(rows: LedgerEvent[], voided: Set<number>) {
  const cols = ["event_id", "created_at", "status", "buyer_name", "sku_name", "quantity", "unit", "rate_inr", "trade_value_inr", "previous_balance_inr", "projected_balance_inr", "credit_limit_inr", "confidence", "raw_utterance"] as const;
  const cell = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  const lines = [[...cols, "undone"].join(","), ...rows.map((r) => [...cols.map((c) => cell(r[c])), voided.has(r.event_id) ? "yes" : ""].join(","))];
  const url = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `kadal-kural-ledger-${new Date().toISOString().slice(0, 10)}.csv` });
  a.click();
  URL.revokeObjectURL(url);
}

interface LedgerProps {
  events: LedgerEvent[];
  gate: number;
  newIds: Set<number>;
  /** Show at most this many rows, with a link to the full ledger page. */
  limit?: number;
  /** Full page: buyer filter and CSV export. */
  full?: boolean;
  buyers?: Buyer[];
}

export function Ledger({ events, gate, newIds, limit, full, buyers = [] }: LedgerProps) {
  const [query, setQuery] = useState("");
  const [buyer, setBuyer] = useState<string>("all");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<LedgerEvent | null>(null);
  const { voided } = tally(events);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: events.length, booked: 0, hold: 0, ask: 0, undone: 0 };
    events.forEach((e) => { c[statusOf(e.status).kind] += 1; });
    return c;
  }, [events]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter((e) => {
      if (filter !== "all" && statusOf(e.status).kind !== filter) return false;
      if (buyer !== "all" && e.buyer_id !== buyer) return false;
      if (!q) return true;
      return [e.raw_utterance, e.buyer_name, e.sku_name, statusOf(e.status).label].some((v) => String(v).toLowerCase().includes(q));
    });
  }, [events, filter, query, buyer]);
  const shown = limit ? rows.slice(0, limit) : rows;

  return (
    <section id="ledger" aria-labelledby="ledger-title" className="surface rounded-3xl p-5">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 id="ledger-title" className="mr-auto text-lg font-extrabold tracking-tight">Ledger</h2>
        <div className="relative w-full sm:w-auto">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search buyer, item or words" className="h-9 w-full rounded-full bg-white pl-9 sm:w-64" aria-label="Search the ledger" />
        </div>
        <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as Filter)} className="surface max-w-full flex-wrap rounded-full p-1" aria-label="Filter by decision">
          {FILTERS.map((f) => (
            <ToggleGroupItem key={f.value} value={f.value} className="h-7 rounded-full px-3 text-xs data-[state=on]:bg-lime data-[state=on]:text-ink">
              {f.label} <span className="ml-1 opacity-60">{counts[f.value]}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {full && (
          <button type="button" onClick={() => downloadCsv(rows, voided)} disabled={rows.length === 0} className="ink-key inline-flex h-9 items-center gap-2 rounded-full px-4 text-sm font-bold disabled:opacity-40">
            <Download className="size-4" /> Export CSV
          </button>
        )}
      </div>
      {full && buyers.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by buyer">
          {[{ buyer_id: "all", canonical_name: "All buyers" }, ...buyers].map((b) => (
            <button
              key={b.buyer_id}
              type="button"
              onClick={() => setBuyer(b.buyer_id)}
              aria-pressed={buyer === b.buyer_id}
              className={cn("rounded-full border px-3 py-1 text-sm font-semibold transition-colors", buyer === b.buyer_id ? "border-lime bg-lime-soft" : "bg-white hover:border-lime")}
            >
              {b.canonical_name}
            </button>
          ))}
        </div>
      )}

      <div className="-mx-5 overflow-x-auto px-5">
        <Table className="min-w-[900px]">
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead><TableHead>Heard</TableHead><TableHead>Buyer</TableHead><TableHead>Item</TableHead>
              <TableHead className="text-right">Qty × rate</TableHead><TableHead className="text-right">Value</TableHead>
              <TableHead>Decision</TableHead><TableHead>Confidence</TableHead><TableHead>Payment</TableHead><TableHead className="w-6" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((e) => {
              const isVoided = voided.has(e.event_id);
              return (
                <motion.tr
                  key={e.event_id}
                  layout
                  initial={newIds.has(e.event_id) ? { backgroundColor: "rgba(181,242,61,0.45)", y: -6, opacity: 0 } : false}
                  animate={{ backgroundColor: "rgba(181,242,61,0)", y: 0, opacity: 1 }}
                  transition={{ duration: 1.4 }}
                  onClick={() => setOpen(e)}
                  onKeyDown={(k) => (k.key === "Enter" || k.key === " ") && setOpen(e)}
                  tabIndex={0}
                  className="cursor-pointer border-b transition-colors hover:bg-lime-soft/60 focus-visible:bg-lime-soft"
                >
                  <TableCell className={cn(isVoided && "line-through opacity-60")}>{e.created_at}</TableCell>
                  <TableCell lang="ta" title={e.raw_utterance} className={cn("tamil max-w-[260px] truncate", isVoided && "line-through opacity-60")}>{e.raw_utterance}</TableCell>
                  <TableCell className={cn(isVoided && "line-through opacity-60")}>{e.buyer_name}</TableCell>
                  <TableCell className={cn(isVoided && "line-through opacity-60")}>{e.sku_name}</TableCell>
                  <TableCell className={cn("text-right", isVoided && "line-through opacity-60")}>{e.quantity} {e.unit} × {inr(e.rate_inr)}</TableCell>
                  <TableCell className={cn("text-right font-semibold", isVoided && "line-through opacity-60")}>{inr(e.trade_value_inr)}</TableCell>
                  <TableCell><StatusChip status={e.status} /></TableCell>
                  <TableCell><ConfidenceBar value={e.confidence} gate={gate} /></TableCell>
                  <TableCell>{e.upi_link_visible && !isVoided ? <span className="inline-flex items-center gap-1 font-semibold text-lime-deep"><QrCode className="size-4" /> UPI</span> : "–"}</TableCell>
                  <TableCell><ChevronRight className="size-4 text-muted-foreground" /></TableCell>
                </motion.tr>
              );
            })}
          </TableBody>
        </Table>
        {rows.length === 0 && (
          <p className="py-10 text-center text-muted-foreground">
            {events.length === 0 ? "No entries yet. Say an order, or pick one under “Try an order”." : "No entries match this search or filter."}
          </p>
        )}
      </div>
      {limit && rows.length > limit && (
        <Link to="/ledger" className="mt-3 inline-flex items-center gap-2 text-sm font-bold text-lime-deep hover:gap-3">
          View all {rows.length} entries <ArrowRight className="size-4" />
        </Link>
      )}
      <p className="mt-3 text-xs text-muted-foreground">Append-only: an undo adds a reversing entry and strikes through the original; nothing is deleted. Select a row for details.</p>

      <EntrySheet entry={open} voided={open ? voided.has(open.event_id) : false} gate={gate} onClose={() => setOpen(null)} />
    </section>
  );
}

function EntrySheet({ entry, voided, gate, onClose }: { entry: LedgerEvent | null; voided: boolean; gate: number; onClose: () => void }) {
  const showUpi = !!entry && entry.upi_link_visible && !voided && entry.upi_payment_uri.startsWith("upi:");
  return (
    <Sheet open={!!entry} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        {entry && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2 text-xl">Entry #{entry.event_id} <StatusChip status={entry.status} /></SheetTitle>
              <SheetDescription>Recorded at {entry.created_at}{voided && " · later undone"}</SheetDescription>
            </SheetHeader>
            <div className="grid gap-5 px-4 pb-6">
              <div className="rounded-2xl bg-secondary p-4">
                <p className="text-xs text-muted-foreground">Heard</p>
                <p lang="ta" className="tamil text-lg font-semibold">{entry.raw_utterance}</p>
                {entry.normalized_clause && entry.normalized_clause !== entry.raw_utterance && (
                  <>
                    <p className="mt-2 text-xs text-muted-foreground">Understood as</p>
                    <p lang="ta" className="tamil">{entry.normalized_clause}</p>
                  </>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <Item k="Buyer" v={entry.buyer_name} sub={entry.buyer_guess_confidence != null ? `best match ${entry.buyer_guess ?? "–"} · ${pct(entry.buyer_guess_confidence)}` : undefined} />
                <Item k="Item" v={entry.sku_name} sub={entry.sku_guess_confidence != null ? `best match ${entry.sku_guess ?? "–"} · ${pct(entry.sku_guess_confidence)}` : undefined} />
                <Item k="Quantity" v={`${entry.quantity} ${entry.unit}`} />
                <Item k="Rate" v={`${inr(entry.rate_inr)}/${entry.unit}`} />
                <Item k="Value" v={inr(entry.trade_value_inr)} />
                <Item k="Confidence" v={pct(entry.confidence)} sub={`gate ${pct(gate)}`} />
                <Item k="Balance before" v={inr(entry.previous_balance_inr)} />
                <Item k="Balance after" v={inr(entry.projected_balance_inr)} sub={`limit ${inr(entry.credit_limit_inr)}`} />
              </dl>
              {showUpi ? (
                <div className="surface flex flex-col items-center gap-3 rounded-2xl p-5 text-center">
                  <div className="rounded-xl bg-white p-3 shadow-sm"><QRCodeSVG value={entry.upi_payment_uri} size={176} fgColor="#0f1d14" /></div>
                  <p className="text-sm text-muted-foreground">Scan with any UPI app to pay {inr(entry.trade_value_inr)}</p>
                  <a href={entry.upi_payment_uri} className="lime-key rounded-full px-4 py-2 text-sm font-bold">Open in UPI app</a>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No payment link: only booked orders that were not undone can be paid.</p>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Item({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="font-bold">{v}</dd>
      {sub && <dd className="text-xs text-muted-foreground">{sub}</dd>}
    </div>
  );
}
