import { Check } from "lucide-react";
import { motion } from "motion/react";

import type { Stage } from "@/hooks/useDesk";
import { cn } from "@/lib/utils";

const STEPS = [
  { title: "Hear", body: "Gnani Prisma transcribes Tamil or Tanglish from the 8 kHz stream." },
  { title: "Understand", body: "Tamil numbers and case endings are normalised; buyer, item, quantity, unit and rate are matched." },
  { title: "Gate", body: "Below the confidence gate, or an implausible price or quantity, means ask again." },
  { title: "Credit check", body: "The value is added to the buyer's balance; over the limit is held, not dispatched." },
  { title: "Record and reply", body: "A new ledger entry (never an edit), then the answer in Tamil. No AI model does the arithmetic." },
];

export function Pipeline({ stage, gate }: { stage: Stage; gate: number }) {
  return (
    <section aria-labelledby="pipe-title" className="surface rounded-3xl p-5">
      <h2 id="pipe-title" className="mb-4 text-lg font-extrabold tracking-tight">How each order is checked</h2>
      <ol className="relative grid gap-4">
        {STEPS.map((s, i) => {
          const n = (i + 1) as Stage;
          const done = stage >= n;
          return (
            <li key={s.title} className="relative grid grid-cols-[32px_1fr] gap-3">
              {i < STEPS.length - 1 && (
                <span className="absolute top-8 left-[15px] h-[calc(100%-12px)] w-0.5 overflow-hidden rounded bg-border">
                  <motion.span className="block w-full bg-lime-deep" initial={false} animate={{ height: stage > n ? "100%" : "0%" }} transition={{ duration: 0.18 }} />
                </span>
              )}
              <motion.span
                initial={false}
                animate={done ? { scale: [1, 1.18, 1] } : { scale: 1 }}
                transition={{ duration: 0.3 }}
                className={cn(
                  "relative z-10 grid size-8 place-items-center rounded-full text-sm font-extrabold transition-colors",
                  done ? "lime-key" : "bg-secondary text-muted-foreground",
                )}
              >
                {done ? <Check className="size-4" strokeWidth={3} /> : n}
              </motion.span>
              <div>
                <p className={cn("font-bold", done ? "text-foreground" : "text-muted-foreground")}>{s.title}</p>
                <p className="text-sm text-muted-foreground">
                  {i === 2 ? s.body.replace("the confidence gate", `the ${Math.round(gate * 100)}% confidence gate`) : s.body}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
