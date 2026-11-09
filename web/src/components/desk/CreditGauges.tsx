import { motion, useReducedMotion } from "motion/react";

import CountUp from "@/components/CountUp";
import type { Buyer } from "@/lib/api";
import { inr } from "@/lib/format";
import { cn } from "@/lib/utils";

const R = 42;
const C = 2 * Math.PI * R;
const ARC = 0.75; // a 270° dial

export function Dial({ used, level, flash, className = "size-28" }: { used: number; level: "ok" | "tight" | "critical"; flash: boolean; className?: string }) {
  const reduced = useReducedMotion();
  const stroke = level === "critical" ? "url(#g-hold)" : level === "tight" ? "url(#g-ask)" : "url(#g-lime)";
  const shown = Math.min(1, used);
  return (
    <svg viewBox="0 0 100 100" className={cn(className, "shrink-0 -rotate-[225deg] drop-shadow-[0_6px_10px_rgba(15,29,20,0.18)]")} aria-hidden>
      <defs>
        <linearGradient id="g-lime" x1="0" x2="1"><stop offset="0" stopColor="#d9f99d" /><stop offset="1" stopColor="#65a30d" /></linearGradient>
        <linearGradient id="g-ask" x1="0" x2="1"><stop offset="0" stopColor="#fde68a" /><stop offset="1" stopColor="#d97706" /></linearGradient>
        <linearGradient id="g-hold" x1="0" x2="1"><stop offset="0" stopColor="#fca5a5" /><stop offset="1" stopColor="#dc2626" /></linearGradient>
        <radialGradient id="g-face" cx="0.35" cy="0.3" r="0.8"><stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#eef3e6" /></radialGradient>
      </defs>
      <circle cx="50" cy="50" r="34" fill="url(#g-face)" stroke="#e1e8da" />
      <circle cx="50" cy="50" r={R} fill="none" stroke="#e6ece0" strokeWidth="9" strokeLinecap="round" strokeDasharray={`${C * ARC} ${C}`} />
      <motion.circle
        cx="50" cy="50" r={R} fill="none" stroke={stroke} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={`${C * ARC} ${C}`}
        initial={{ strokeDashoffset: C * ARC }}
        animate={{ strokeDashoffset: C * ARC * (1 - shown) }}
        transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 60, damping: 16 }}
      />
      {flash && !reduced && (
        <motion.circle cx="50" cy="50" r={R} fill="none" stroke="#84cc16" strokeWidth="2"
          initial={{ opacity: 0.9, scale: 1 }} animate={{ opacity: 0, scale: 1.18 }} transition={{ duration: 1.1 }}
          style={{ transformOrigin: "50% 50%" }} />
      )}
    </svg>
  );
}

export function CreditGauges({ buyers, touched }: { buyers: Buyer[]; touched: Set<string> }) {
  const owed = buyers.reduce((s, b) => s + b.running_balance_inr, 0);
  const limit = buyers.reduce((s, b) => s + b.credit_limit_inr, 0);
  return (
    <section aria-labelledby="credit-title" className="surface rounded-3xl p-5">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id="credit-title" className="text-lg font-extrabold tracking-tight">Credit headroom</h2>
        <p className="text-xs text-muted-foreground">{inr(owed)} owed of {inr(limit)}</p>
      </div>
      <ul className="grid gap-3">
        {buyers.map((b) => {
          const used = b.credit_limit_inr ? b.running_balance_inr / b.credit_limit_inr : 1;
          const left = Math.max(0, b.credit_limit_inr - b.running_balance_inr);
          const level = used >= 0.95 ? "critical" : used >= 0.8 ? "tight" : "ok";
          const flash = touched.has(b.buyer_id);
          return (
            <motion.li
              key={b.buyer_id + (flash ? "-f" : "")}
              initial={flash ? { scale: 0.98 } : false}
              animate={{ scale: 1 }}
              className={cn("relative flex items-center gap-4 rounded-2xl bg-white/70 p-2 pr-4", flash && "ring-2 ring-lime")}
              aria-label={`${b.canonical_name}: ${inr(left)} of credit left, ${inr(b.running_balance_inr)} of ${inr(b.credit_limit_inr)} used`}
            >
              <div className="relative">
                <Dial used={used} level={level} flash={flash} />
                <div className="absolute inset-0 grid place-items-center text-center">
                  <span className="text-lg leading-none font-extrabold">{Math.round(used * 100)}%</span>
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{b.canonical_name}</p>
                <p lang="ta" className="tamil truncate text-sm text-muted-foreground">{b.tamil_speak_name}</p>
                <p className="mt-1.5 text-xl font-extrabold tracking-tight">
                  ₹<CountUp to={left} separator="," duration={0.8} trigger="load" /> <span className="text-sm font-medium text-muted-foreground">left</span>
                </p>
                <p className="text-xs text-muted-foreground">{inr(b.running_balance_inr)} of {inr(b.credit_limit_inr)}</p>
              </div>
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}
