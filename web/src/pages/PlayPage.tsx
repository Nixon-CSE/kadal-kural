import { BookOpenText, Gamepad2, Lightbulb, Zap } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { ChallengeMode, type Difficulty } from "@/game/ChallengeMode";
import { useProgress } from "@/game/progress";
import { StoryMode } from "@/game/StoryMode";
import { GameKey, XpBar } from "@/game/ui";
import { cn } from "@/lib/utils";

const CHAPTER_LIST = ["The 4 AM shift: you vs the noise", "Why it matters: four flip cards", "Build the firewall: five checkpoints", "Same shift, new desk: watch it decide", "After the fix: what it connects to"];

export default function PlayPage() {
  const progress = useProgress();
  const [mode, setMode] = useState<"menu" | "story" | "challenge">("menu");
  const [difficulty, setDifficulty] = useState<Difficulty>("calm");
  const [hints, setHints] = useState(true);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 pt-4">
      <XpBar xp={progress.xp} badges={progress.badges} />

      {mode === "story" && <StoryMode progress={progress} onExit={() => setMode("menu")} />}
      {mode === "challenge" && <ChallengeMode difficulty={difficulty} hints={hints} progress={progress} onExit={() => setMode("menu")} />}

      {mode === "menu" && (
        <>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="max-w-3xl">
            <h1 className="text-[clamp(2.6rem,6vw,4.6rem)] leading-[0.95] font-extrabold tracking-tight [font-stretch:115%]">Harbour Shift</h1>
            <p className="mt-4 text-xl text-muted-foreground">
              Learn what Kadal Kural does by doing the job it was built for. Run a dispatch desk at 4 AM, feel why it goes wrong, then build and test the fix.
            </p>
          </motion.div>

          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-2">
            <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="surface flex flex-col gap-5 rounded-3xl p-7" aria-labelledby="story-title">
              <div className="flex items-center gap-3">
                <span className="lime-key grid size-14 place-items-center rounded-2xl"><BookOpenText className="size-7" /></span>
                <div>
                  <h2 id="story-title" className="text-2xl font-extrabold">Story mode</h2>
                  <p className="text-sm text-muted-foreground">5 chapters · about 4 minutes · the whole picture</p>
                </div>
              </div>
              <ol className="grid gap-2">
                {CHAPTER_LIST.map((c, k) => (
                  <li key={c} className="flex items-center gap-3 text-[15px]">
                    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-secondary text-sm font-extrabold">{k + 1}</span>{c}
                  </li>
                ))}
              </ol>
              <GameKey className="mt-auto self-start text-lg" onClick={() => setMode("story")}>Start the story</GameKey>
            </motion.section>

            <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="surface flex flex-col gap-5 rounded-3xl p-7" aria-labelledby="challenge-title">
              <div className="flex items-center gap-3">
                <span className="ink-key grid size-14 place-items-center rounded-2xl"><Gamepad2 className="size-7 text-lime" /></span>
                <div>
                  <h2 id="challenge-title" className="text-2xl font-extrabold">Beat the firewall</h2>
                  <p className="text-sm text-muted-foreground">Endless · predict each decision · three lives{progress.best ? ` · best ${progress.best}` : ""}</p>
                </div>
              </div>
              <p className="text-[15px] text-muted-foreground">Random orders arrive with traps: dropped digits, strangers, orders too big for the buyer's credit. Call it before the real firewall answers.</p>

              <fieldset>
                <legend className="mb-2 text-sm font-bold">Pace</legend>
                <div className="grid grid-cols-2 gap-2" role="radiogroup">
                  {([["calm", "Calm market", "10 seconds per order"], ["rush", "Rush hour", "5 seconds, more XP"]] as const).map(([id, label, sub]) => (
                    <button key={id} type="button" role="radio" aria-checked={difficulty === id} onClick={() => setDifficulty(id)}
                      className={cn("flex items-start gap-3 rounded-2xl border-2 p-3 text-left transition-colors", difficulty === id ? "border-lime bg-lime-soft" : "border-border bg-white hover:border-lime/60")}>
                      <Zap className={cn("mt-0.5 size-5", id === "rush" ? "text-ask" : "text-lime-deep")} />
                      <span><span className="block font-extrabold">{label}</span><span className="text-xs text-muted-foreground">{sub}</span></span>
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl bg-secondary/70 p-3">
                <span className="flex items-center gap-3"><Lightbulb className="size-5 text-ask" /><span><span className="block font-bold">Show hints</span><span className="text-xs text-muted-foreground">Buyer, price band and credit after the order</span></span></span>
                <input type="checkbox" checked={hints} onChange={(e) => setHints(e.target.checked)} className="peer sr-only" />
                <span aria-hidden className="relative h-7 w-12 rounded-full bg-border transition-colors peer-checked:bg-lime-deep peer-focus-visible:outline-3 peer-focus-visible:outline-ring after:absolute after:top-1 after:left-1 after:size-5 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:after:translate-x-5" />
              </label>

              <GameKey tone="ink" className="mt-auto self-start text-lg" onClick={() => setMode("challenge")}>Start a shift</GameKey>
            </motion.section>
          </div>

          <p className="text-sm text-muted-foreground">
            Every decision in the game comes from the real firewall running on a private sandbox ledger, so your desk is never touched. Progress is saved in this browser.{" "}
            <button type="button" className="font-semibold underline underline-offset-2 hover:text-foreground" onClick={progress.reset}>Reset progress</button>
          </p>
        </>
      )}
    </div>
  );
}
