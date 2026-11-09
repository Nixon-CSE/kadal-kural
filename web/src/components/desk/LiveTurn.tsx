import { CornerDownLeft, Mic, Sparkles, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { lazy, Suspense, useState, type FormEvent, type RefObject } from "react";

import Magnet from "@/components/Magnet";
import ShinyText from "@/components/ShinyText";
import SplitText from "@/components/SplitText";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import type { DeskApi } from "@/hooks/useDesk";
import { KIND_CLASSES, statusOf, TRY_ORDERS } from "@/lib/format";
import { cn } from "@/lib/utils";

import { DecisionCard } from "./DecisionCard";
import type { OrbTone } from "./VoiceOrb";

const VoiceOrb = lazy(() => import("./VoiceOrb").then((m) => ({ default: m.VoiceOrb })));

const MODE_HINT: Record<string, string> = {
  idle: "Press the microphone or the space bar, then say an order in Tamil or Tanglish.",
  connecting: "Opening a live 8 kHz stream to Gnani Prisma.",
  listening: "Speak naturally. Headphones stop the reply from being heard as speech.",
  thinking: "Normalising Tamil numbers, matching buyer and item, checking the gate and the credit limit.",
  speaking: "Talk over the reply to correct it: the voice stops at once.",
  error: "Fix the issue above, then press the microphone again.",
};

export function LiveTurn({ desk, inputRef }: { desk: DeskApi; inputRef: RefObject<HTMLInputElement | null> }) {
  const { mode, modeText, listening, turn, level, toggleMic, sendTranscript, play } = desk;
  const reduced = !!useReducedMotion();
  const [draft, setDraft] = useState("");
  const gate = desk.desk?.confidence_threshold ?? 0.82;
  const kinds = new Set((turn?.decisions ?? []).map((d) => statusOf(d.status).kind));
  const tone: OrbTone = kinds.has("hold") ? "hold" : kinds.has("ask") ? "ask" : "lime";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void sendTranscript(draft);
    setDraft("");
  };

  return (
    <section aria-labelledby="live-title" className="surface surface-lift relative overflow-hidden rounded-3xl">
      <h1 id="live-title" className="sr-only">Live order</h1>
      <div className="pointer-events-none absolute -top-24 -left-24 size-80 rounded-full bg-lime/25 blur-3xl" />

      <div className="relative grid grid-cols-[minmax(0,1fr)] gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]">
        {/* Orb + mic */}
        <div className="flex flex-col items-center">
          <div className="relative aspect-square w-full max-w-[340px]">
            <Suspense fallback={<div className="absolute inset-[18%] animate-pulse rounded-full bg-lime/40" />}>
              <VoiceOrb mode={mode} tone={tone} level={level} reduced={reduced} className="absolute inset-0" />
            </Suspense>
          </div>
          <Magnet padding={60} magnetStrength={4} disabled={reduced}>
            <button
              type="button"
              onClick={toggleMic}
              aria-pressed={listening}
              aria-label={listening ? "Stop listening" : "Start listening"}
              disabled={mode === "connecting"}
              className={cn(
                "group relative -mt-6 grid size-20 place-items-center rounded-full transition-transform active:scale-95 disabled:cursor-progress",
                listening ? "ink-key" : "lime-key",
              )}
            >
              {listening && <span className="absolute inset-0 animate-ping rounded-full bg-lime/40" />}
              {listening ? <Square className="relative size-7 fill-lime text-lime" /> : <Mic className="relative size-8" strokeWidth={2.4} />}
            </button>
          </Magnet>
          <p className="mt-3 text-xs text-muted-foreground">
            <Kbd>Space</Kbd> to talk · <Kbd>/</Kbd> to type · <Kbd>⌘K</Kbd> commands
          </p>
        </div>

        {/* Turn */}
        <div className="flex min-w-0 flex-col gap-5">
          <div role="status" aria-live="polite">
            <p className={cn("text-3xl font-extrabold tracking-tight [font-stretch:110%]", mode === "error" && "text-hold")}>
              {mode === "listening" || mode === "thinking" ? (
                <ShinyText text={modeText} color="#0f1d14" shineColor="#84cc16" speed={2.2} />
              ) : (
                modeText
              )}
            </p>
            <p className="mt-1 max-w-[62ch] text-sm text-muted-foreground">{MODE_HINT[mode]}</p>
          </div>

          <div className="border-t pt-4" aria-live="polite">
            <p className="text-xs font-medium text-muted-foreground">Heard</p>
            {turn ? (
              <div key={`${turn.id}-${turn.heard}`} lang="ta" className={cn("tamil mt-1 text-[clamp(1.5rem,3vw,2.35rem)] font-bold leading-snug", turn.partial && "text-muted-foreground")}>
                <SplitText text={turn.heard} tag="p" splitType="words" effect="rise" delay={45} duration={0.7} trigger="load" textAlign="left" />
              </div>
            ) : (
              <p className="mt-1 text-2xl text-muted-foreground">Waiting for the first order</p>
            )}
          </div>

          <div className="grid gap-3" aria-live="polite">
            <AnimatePresence mode="popLayout">
              {turn?.decisions.map((d, i) => (
                <DecisionCard
                  key={`${turn.id}-${i}`}
                  d={d}
                  gate={gate}
                  sttMs={turn.sttMs}
                  typed={turn.source === "typed"}
                  index={i}
                  onPlay={() => play([d.audio_wav_b64])}
                />
              ))}
            </AnimatePresence>
          </div>

          <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" autoComplete="off">
            <label htmlFor="type-order" className="sr-only">Type an order</label>
            <Input
              id="type-order"
              ref={inputRef}
              lang="ta"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Or type an order, e.g. குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"
              className="h-12 rounded-xl bg-white text-base"
            />
            <Button type="submit" className="ink-key h-12 gap-2 rounded-xl px-5 text-base">
              Check order <CornerDownLeft className="size-4" />
            </Button>
          </form>

          <div>
            <p className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="size-4 text-lime-deep" /> Try an order</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {TRY_ORDERS.map((t) => (
                <motion.button
                  key={t.text}
                  type="button"
                  whileHover={reduced ? undefined : { y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => void sendTranscript(t.text)}
                  className="group surface flex flex-col items-start gap-1 rounded-xl p-3 text-left hover:border-lime"
                >
                  <span lang="ta" className="tamil text-sm font-semibold leading-snug">{t.text}</span>
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className={cn("size-1.5 rounded-full", KIND_CLASSES[t.kind].dot)} /> {t.why}
                  </span>
                </motion.button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
