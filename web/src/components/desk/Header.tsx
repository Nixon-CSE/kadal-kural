import { Command, Mic, Phone, Waves } from "lucide-react";
import { motion, useScroll, useSpring } from "motion/react";
import { NavLink, useLocation } from "react-router";

import GradientText from "@/components/GradientText";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DeskState } from "@/lib/api";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

function Dot({ on }: { on: boolean | null }) {
  return (
    <span className="relative flex size-2.5">
      {on && <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime opacity-70" />}
      <span className={cn("relative inline-flex size-2.5 rounded-full", on ? "bg-lime ring-2 ring-lime-deep/30" : "border-[1.5px] border-undone")} />
    </span>
  );
}

export function Header({ desk, listening, onCommand }: { desk: DeskState | null; listening: boolean; onCommand: () => void }) {
  const { pathname } = useLocation();
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 140, damping: 24 });

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1480px] items-center gap-4 px-4 py-2.5 sm:px-6">
        <NavLink to="/" className="flex shrink-0 items-center gap-2.5" aria-label="Kadal Kural home">
          <motion.span
            initial={{ rotateY: -90, opacity: 0 }}
            animate={{ rotateY: 0, opacity: 1 }}
            whileHover={{ rotateY: 180 }}
            transition={{ type: "spring", stiffness: 120, damping: 14 }}
            className="ink-key grid size-10 place-items-center rounded-xl"
            style={{ transformPerspective: 600 }}
          >
            <Waves className="size-5.5 text-lime" strokeWidth={2.4} />
          </motion.span>
          <span className="hidden leading-tight sm:block">
            <GradientText colors={["#0f1d14", "#4d7c0f", "#84cc16", "#0f1d14"]} animationSpeed={6} className="text-lg font-extrabold tracking-tight [font-stretch:115%]">
              Kadal Kural
            </GradientText>
            <span className="block text-[11px] text-muted-foreground">{desk?.domain_title ?? "Credit desk"}</span>
          </span>
        </NavLink>

        <nav aria-label="Main" className="mx-auto -my-1 flex min-w-0 overflow-x-auto py-1 [scrollbar-width:none]">
          <ul className="surface flex items-center gap-0.5 rounded-full p-1">
            {NAV.map((n) => {
              const active = n.to === "/" ? pathname === "/" : pathname.startsWith(n.to);
              return (
                <li key={n.to} className="relative">
                  <NavLink
                    to={n.to}
                    className={cn("relative z-10 block rounded-full px-3.5 py-1.5 text-sm font-semibold whitespace-nowrap transition-colors", active ? "text-ink" : "text-muted-foreground hover:text-foreground")}
                  >
                    {n.label}
                    {n.to === "/desk" && listening && <span className="ml-1.5 inline-block size-1.5 animate-pulse rounded-full bg-hold align-middle" aria-label="listening" />}
                  </NavLink>
                  {active && (
                    <motion.span layoutId="nav-pill" className="lime-key absolute inset-0 rounded-full" transition={{ type: "spring", stiffness: 380, damping: 30 }} />
                  )}
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="hidden shrink-0 items-center gap-2 lg:flex">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="surface inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold">
                <Dot on={desk ? desk.gnani_live_key_configured : null} /> <Mic className="size-3.5" />
                <span className="text-muted-foreground">|</span>
                <Dot on={desk ? desk.phone_channel_enabled : null} /> <Phone className="size-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent>
              Speech {desk?.gnani_live_key_configured ? "live" : "off"} · phone line {desk?.phone_channel_enabled ? "on" : "off"} · gate {desk ? Math.round(desk.confidence_threshold * 100) : "–"}%
            </TooltipContent>
          </Tooltip>
          <Button variant="outline" className="surface h-9 gap-2 rounded-full" onClick={onCommand}>
            <Command className="size-4" /> <Kbd>⌘K</Kbd>
          </Button>
        </div>
        <Button variant="outline" size="icon" className="surface size-9 shrink-0 rounded-full lg:hidden" onClick={onCommand} aria-label="Commands">
          <Command className="size-4" />
        </Button>
      </div>
      <motion.div className="absolute bottom-0 left-0 h-0.5 w-full origin-left bg-gradient-to-r from-lime to-lime-deep" style={{ scaleX: progress }} />
    </header>
  );
}
