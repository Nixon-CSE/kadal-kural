import { Command, Phone, RotateCcw, Waves } from "lucide-react";
import { motion } from "motion/react";

import GradientText from "@/components/GradientText";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DeskState } from "@/lib/api";
import { cn } from "@/lib/utils";

function Pill({ on, label, hint, icon }: { on: boolean | null; label: string; hint: string; icon?: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="surface inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-sm text-muted-foreground">
          <span className="relative flex size-2.5">
            {on && <span className="absolute inline-flex size-full animate-ping rounded-full bg-lime opacity-70" />}
            <span className={cn("relative inline-flex size-2.5 rounded-full", on ? "bg-lime ring-2 ring-lime-deep/30" : on === false ? "border-[1.5px] border-undone" : "bg-undone")} />
          </span>
          {icon}
          <span className="font-medium text-foreground">{label}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  );
}

export function Header({ desk, onCommand, onReset }: { desk: DeskState | null; onCommand: () => void; onReset: () => void }) {
  const gate = desk ? Math.round(desk.confidence_threshold * 100) : null;
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/75 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <div className="mr-auto flex items-center gap-3">
          <motion.div
            initial={{ rotateY: -90, opacity: 0 }}
            animate={{ rotateY: 0, opacity: 1 }}
            transition={{ type: "spring", stiffness: 120, damping: 14 }}
            className="ink-key grid size-11 place-items-center rounded-xl"
            style={{ transformPerspective: 600 }}
          >
            <Waves className="size-6 text-lime" strokeWidth={2.4} />
          </motion.div>
          <div className="leading-tight">
            <div className="flex items-baseline gap-2">
              <GradientText colors={["#0f1d14", "#4d7c0f", "#84cc16", "#0f1d14"]} animationSpeed={6} className="text-xl font-extrabold tracking-tight [font-stretch:115%]">
                Kadal Kural
              </GradientText>
              <span lang="ta" className="tamil text-base font-medium text-muted-foreground">கடல் குரல்</span>
            </div>
            <p className="text-xs text-muted-foreground">{desk?.domain_title ?? "Credit desk"}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Pill
            on={desk ? desk.gnani_live_key_configured : null}
            label={desk?.gnani_live_key_configured ? "Gnani speech live" : "Add a Gnani key"}
            hint="Prisma speech-to-text and Timbre voice replies"
          />
          <Pill
            on={desk ? desk.phone_channel_enabled : null}
            icon={<Phone className="size-3.5" />}
            label={desk?.phone_channel_enabled ? "Phone line on" : "Phone line off"}
            hint="Orders by phone through Gnani Agent Builder"
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="surface inline-flex h-9 items-center gap-2 rounded-full px-3.5 text-sm text-muted-foreground">
                Confidence gate <strong className="text-foreground">{gate === null ? "–" : `${gate}%`}</strong>
              </span>
            </TooltipTrigger>
            <TooltipContent>Orders below this confidence are held and the trader is asked again</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" className="surface h-9 gap-2 rounded-full" onClick={onCommand}>
            <Command className="size-4" /> Commands <Kbd>⌘K</Kbd>
          </Button>
          <Button variant="outline" className="surface h-9 gap-2 rounded-full" onClick={onReset}>
            <RotateCcw className="size-4" /> Reset balances
          </Button>
        </div>
      </div>
    </header>
  );
}
