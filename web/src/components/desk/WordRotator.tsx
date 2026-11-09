import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Cycles through phrases with a vertical spring slide; the pill resizes smoothly to each phrase. */
export function WordRotator({ words, interval = 2200, className }: { words: string[]; interval?: number; className?: string }) {
  const reduced = useReducedMotion();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => setI((n) => (n + 1) % words.length), interval);
    return () => window.clearInterval(id);
  }, [interval, reduced, words.length]);

  return (
    <span className={cn("relative inline-grid h-[1.6em] items-center overflow-hidden align-middle transition-[width]", className)}>
      <span className="sr-only" aria-live="polite">{words[i]}</span>
      {/* In-flow sizer: the pill's width always matches the current phrase. */}
      <span aria-hidden className="invisible col-start-1 row-start-1 whitespace-nowrap">{words[i]}</span>
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={words[i]}
          aria-hidden
          className="col-start-1 row-start-1 block whitespace-nowrap"
          initial={{ y: "110%", opacity: 0, rotateX: -60 }}
          animate={{ y: "0%", opacity: 1, rotateX: 0 }}
          exit={{ y: "-110%", opacity: 0, rotateX: 60 }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
        >
          {words[i]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
