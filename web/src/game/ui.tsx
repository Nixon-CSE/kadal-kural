import { motion, useReducedMotion } from "motion/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

import { BADGES, type BadgeId } from "./data";
import { rankOf } from "./progress";

type Tone = "lime" | "ink" | "hold" | "white";
const TONES: Record<Tone, { face: string; edge: string; text: string }> = {
  lime: { face: "bg-gradient-to-b from-[#c8f75c] to-[#9be22d]", edge: "#5e9a0f", text: "text-ink" },
  ink: { face: "bg-gradient-to-b from-[#2a4232] to-[#0f1d14]", edge: "#05100a", text: "text-[#f4ffe0]" },
  hold: { face: "bg-gradient-to-b from-[#f37f72] to-[#d93a3a]", edge: "#992222", text: "text-white" },
  white: { face: "bg-gradient-to-b from-white to-[#eef3e6]", edge: "#c9d6bf", text: "text-ink" },
};

/** A chunky key that physically presses down: its bottom edge collapses on press. */
export function GameKey({ tone = "lime", className, children, style, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; children: ReactNode }) {
  const t = TONES[tone];
  return (
    <button
      type="button"
      {...rest}
      style={{ ...style, ["--edge" as string]: t.edge }}
      className={cn(
        "relative inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-6 font-extrabold tracking-tight select-none",
        "shadow-[0_6px_0_var(--edge),0_14px_24px_-10px_rgba(15,29,20,0.45)] transition-[transform,box-shadow] duration-75",
        "active:translate-y-[5px] active:shadow-[0_1px_0_var(--edge),0_4px_10px_-6px_rgba(15,29,20,0.4)] disabled:pointer-events-none disabled:opacity-40",
        t.face, t.text, className,
      )}
    >
      {children}
    </button>
  );
}

/** A one-off burst of confetti pieces animated on the GPU, removed after it settles. */
export function Confetti({ burst }: { burst: number }) {
  const reduced = useReducedMotion();
  if (!burst || reduced) return null;
  const colors = ["#b5f23d", "#84cc16", "#0f1d14", "#f0b93a", "#ffffff"];
  return (
    <div key={burst} className="pointer-events-none fixed inset-x-0 top-24 z-50 flex justify-center" aria-hidden>
      {Array.from({ length: 36 }, (_, i) => {
        const angle = (i / 36) * Math.PI * 2;
        const dist = 160 + (i % 5) * 40;
        return (
          <motion.span
            key={i}
            className="absolute size-2.5 rounded-[3px]"
            style={{ background: colors[i % colors.length] }}
            initial={{ x: 0, y: 0, rotate: 0, opacity: 1, scale: 1 }}
            animate={{ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist + 220, rotate: 540, opacity: 0, scale: 0.6 }}
            transition={{ duration: 1.3, ease: [0.15, 0.7, 0.3, 1] }}
          />
        );
      })}
    </div>
  );
}

export function XpBar({ xp, badges }: { xp: number; badges: BadgeId[] }) {
  const r = rankOf(xp);
  return (
    <div className="surface flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="ink-key grid size-10 place-items-center rounded-xl text-sm font-extrabold text-lime">{r.rank.split(" ").map((w) => w[0]).join("")}</span>
        <div className="leading-tight">
          <p className="text-sm font-extrabold">{r.rank}</p>
          <p className="text-xs text-muted-foreground">{xp} XP{r.next ? ` · ${r.toNext} to ${r.next}` : " · top rank"}</p>
        </div>
      </div>
      <div className="h-3 min-w-40 flex-1 overflow-hidden rounded-full bg-secondary shadow-[inset_0_1px_2px_rgba(15,29,20,0.15)]" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(r.pct * 100)} aria-label="Progress to next rank">
        <motion.div className="h-full rounded-full bg-gradient-to-r from-lime to-lime-deep" animate={{ width: `${r.pct * 100}%` }} transition={{ type: "spring", stiffness: 80, damping: 18 }} />
      </div>
      <ul className="flex flex-wrap gap-1.5" aria-label="Badges">
        {(Object.keys(BADGES) as BadgeId[]).map((id) => {
          const got = badges.includes(id);
          return (
            <li key={id} title={`${BADGES[id].title}: ${BADGES[id].body}`}>
              <motion.span
                initial={false}
                animate={got ? { scale: [1, 1.25, 1], rotate: [0, -8, 0] } : {}}
                className={cn("grid size-7 place-items-center rounded-lg text-[11px] font-extrabold", got ? "lime-key" : "bg-secondary text-muted-foreground/50")}
                aria-label={`${BADGES[id].title}${got ? "" : " (locked)"}`}
              >
                {got ? "★" : "·"}
              </motion.span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ChapterHeader({ index, total, title, lead }: { index: number; total: number; title: string; lead: string }) {
  return (
    <div className="mb-6">
      <div className="mb-3 flex items-center gap-2" aria-label={`Chapter ${index + 1} of ${total}`}>
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cn("h-1.5 rounded-full transition-all", i < index ? "w-8 bg-lime-deep" : i === index ? "w-12 bg-lime" : "w-8 bg-secondary")} />
        ))}
        <span className="ml-2 text-xs font-semibold text-muted-foreground">Chapter {index + 1} of {total}</span>
      </div>
      <h2 className="text-[clamp(1.9rem,3.6vw,2.8rem)] leading-none font-extrabold tracking-tight [font-stretch:112%]">{title}</h2>
      <p className="mt-2 max-w-[62ch] text-lg text-muted-foreground">{lead}</p>
    </div>
  );
}
