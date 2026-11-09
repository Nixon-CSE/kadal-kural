import { motion } from "motion/react";
import type { ReactNode } from "react";

export function PageHeading({ title, lead, children }: { title: string; lead: string; children?: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 110, damping: 18 }} className="flex flex-wrap items-end justify-between gap-4 pt-4">
      <div className="max-w-3xl">
        <h1 className="text-[clamp(2.2rem,4.5vw,3.4rem)] leading-none font-extrabold tracking-tight [font-stretch:112%]">{title}</h1>
        <p className="mt-3 text-lg text-muted-foreground">{lead}</p>
      </div>
      {children}
    </motion.div>
  );
}
