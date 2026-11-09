import { Activity, CircleCheck, HelpCircle, IndianRupee, ShieldAlert } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import CountUp from "@/components/CountUp";
import type { Turn } from "@/hooks/useDesk";
import type { LedgerEvent } from "@/lib/api";
import { tally } from "@/lib/ledger";
import { cn } from "@/lib/utils";

import { TiltCard } from "./TiltCard";

function Stat({ icon, label, children, accent, foot }: { icon: ReactNode; label: string; children: ReactNode; accent?: boolean; foot?: ReactNode }) {
  return (
    <TiltCard>
      <div className="flex h-full flex-col gap-2 p-5">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">{label}</span>
          <span className={cn("grid size-9 place-items-center rounded-xl", accent ? "lime-key" : "bg-secondary text-foreground")}>{icon}</span>
        </div>
        <div className="text-[2rem] leading-none font-extrabold tracking-tight [font-stretch:90%]">{children}</div>
        {foot && <div className="mt-auto text-xs text-muted-foreground">{foot}</div>}
      </div>
    </TiltCard>
  );
}

function Spark({ history }: { history: Turn[] }) {
  const pts = history.filter((t) => t.ttfbMs > 0 || t.sttMs > 0).slice(-20);
  if (pts.length < 2) return <p className="text-xs text-muted-foreground">Appears after two spoken replies</p>;
  const values = pts.map((t) => t.sttMs + t.ttfbMs);
  const max = Math.max(...values, 1);
  const w = 180, h = 44;
  const xy = values.map((v, i) => [(i / (values.length - 1)) * w, h - (v / max) * (h - 6) - 3] as const);
  const line = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-11 w-full" role="img" aria-label={`Last ${values.length} replies, latest ${Math.round(values.at(-1)!)} ms`}>
      <defs>
        <linearGradient id="spark" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#84cc16" stopOpacity="0.45" />
          <stop offset="1" stopColor="#84cc16" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${w},${h} L0,${h} Z`} fill="url(#spark)" />
      <motion.path d={line} fill="none" stroke="#4d7c0f" strokeWidth={2} strokeLinecap="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.8 }} />
      <circle cx={xy.at(-1)![0]} cy={xy.at(-1)![1]} r={3.5} fill="#b5f23d" stroke="#0f1d14" strokeWidth={1.5} />
    </svg>
  );
}

export function Stats({ events, history }: { events: LedgerEvent[]; history: Turn[] }) {
  const t = tally(events);
  const last = history.at(-1);
  return (
    <section aria-label="Today at the desk" className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <Stat icon={<IndianRupee className="size-4.5" />} label="Booked value" accent foot="Undone orders excluded">
        ₹<CountUp to={t.value} separator="," duration={1} trigger="load" />
      </Stat>
      <Stat icon={<CircleCheck className="size-4.5" />} label="Orders booked">
        <CountUp to={t.booked} duration={0.8} trigger="load" />
      </Stat>
      <Stat icon={<ShieldAlert className="size-4.5" />} label="Credit holds" foot="Not dispatched">
        <CountUp to={t.held} duration={0.8} trigger="load" />
      </Stat>
      <Stat icon={<HelpCircle className="size-4.5" />} label="Asked again" foot="Below the gate or incomplete">
        <CountUp to={t.ask} duration={0.8} trigger="load" />
      </Stat>
      <div className="col-span-2 lg:col-span-1">
        <Stat
          icon={<Activity className="size-4.5" />}
          label="Reply speed"
          foot={<Spark history={history} />}
        >
          {last && last.sttMs + last.ttfbMs > 0 ? (
            <><CountUp to={Math.round(last.sttMs + last.ttfbMs)} duration={0.6} trigger="load" /><span className="ml-1 text-base font-semibold text-muted-foreground">ms</span></>
          ) : (
            <span className="text-muted-foreground">–</span>
          )}
        </Stat>
      </div>
    </section>
  );
}
