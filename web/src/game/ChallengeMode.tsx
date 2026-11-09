import { Flame, Heart, HelpCircle, PackageCheck, RotateCcw, ShieldAlert, Timer, Trophy } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { sandbox, type Buyer, type Decision } from "@/lib/api";
import { inr, KIND_CLASSES, statusOf } from "@/lib/format";
import { cn } from "@/lib/utils";

import { nextChallengeOrder, type ChallengeOrder } from "./data";
import type { ProgressApi } from "./progress";
import { Confetti, GameKey } from "./ui";

export type Difficulty = "calm" | "rush";
type Answer = "book" | "hold" | "ask";

const SECONDS: Record<Difficulty, number> = { calm: 10, rush: 5 };
const LIVES = 3;

const ANSWERS: { id: Answer; label: string; hint: string; tone: "lime" | "hold" | "white"; icon: typeof PackageCheck }[] = [
  { id: "book", label: "Book it", hint: "clean and within credit", tone: "lime", icon: PackageCheck },
  { id: "hold", label: "Credit hold", hint: "over the buyer's limit", tone: "hold", icon: ShieldAlert },
  { id: "ask", label: "Ask again", hint: "unknown buyer or odd price", tone: "white", icon: HelpCircle },
];

const toAnswer = (d?: Decision): Answer => {
  const k = d ? statusOf(d.status).kind : "ask";
  return k === "booked" ? "book" : k === "hold" ? "hold" : "ask";
};

function Hint({ order, buyers }: { order: ChallengeOrder; buyers: Buyer[] }) {
  const b = buyers.find((x) => x.canonical_name === order.buyer);
  const [lo, hi] = order.band;
  return (
    <ul className="mt-3 grid gap-1 rounded-xl bg-secondary/70 p-3 text-sm">
      <li>Buyer: {b ? <b>{b.canonical_name}</b> : <b className="text-ask">not a known buyer</b>}</li>
      <li>Price: ₹{order.rate}/kg {order.rate < lo || order.rate > hi ? <b className="text-ask">outside ₹{lo}–₹{hi}</b> : <span className="text-muted-foreground">inside ₹{lo}–₹{hi}</span>}</li>
      {b && <li>Credit after: <b className={b.running_balance_inr + order.value > b.credit_limit_inr ? "text-hold" : "text-booked"}>{inr(b.running_balance_inr + order.value)}</b> of {inr(b.credit_limit_inr)}</li>}
    </ul>
  );
}

export function ChallengeMode({ difficulty, hints, progress, onExit }: { difficulty: Difficulty; hints: boolean; progress: ProgressApi; onExit: () => void }) {
  const [buyers, setBuyers] = useState<Buyer[]>([]);
  const [order, setOrder] = useState<ChallengeOrder>(() => nextChallengeOrder());
  const [left, setLeft] = useState(SECONDS[difficulty]);
  const [result, setResult] = useState<{ answer: Answer | null; actual: Answer; decision?: Decision } | null>(null);
  const [score, setScore] = useState(0);
  const [streak, setStreak] = useState(0);
  const [lives, setLives] = useState(LIVES);
  const [burst, setBurst] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);

  const start = useCallback(async () => {
    setScore(0); setStreak(0); setLives(LIVES); setResult(null); setOrder(nextChallengeOrder()); setLeft(SECONDS[difficulty]); setError(null);
    try { setBuyers((await sandbox.reset()).buyers); } catch { setError("The sandbox did not answer. Is the server running?"); }
  }, [difficulty]);

  useEffect(() => { void start(); }, [start]);

  const answer = useCallback(async (a: Answer | null) => {
    if (busy.current || result) return;
    busy.current = true;
    try {
      const out = await sandbox.evaluate(order.text);
      const d = out.decisions[0];
      const actual = toAnswer(d);
      setBuyers(out.buyers);
      setResult({ answer: a, actual, decision: d });
      if (a === actual) {
        const s = streak + 1;
        setScore((x) => x + 1); setStreak(s);
        progress.addXp(difficulty === "rush" ? 15 : 10);
        if (s === 5) { progress.award("streak5"); setBurst(Date.now()); }
        if (s === 10) { progress.award("streak10"); setBurst(Date.now()); }
        if (difficulty === "rush" && score + 1 === 10) progress.award("rush");
      } else {
        setStreak(0); setLives((l) => l - 1);
      }
    } catch {
      setError("The sandbox did not answer. Is the server running?");
    } finally { busy.current = false; }
  }, [difficulty, order.text, progress, result, score, streak]);

  useEffect(() => {
    if (result || lives <= 0 || error) return;
    if (left <= 0) { void answer(null); return; }
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
  }, [answer, error, left, lives, result]);

  const { recordBest } = progress;
  useEffect(() => { if (lives <= 0) recordBest(score); }, [lives, recordBest, score]);

  const next = () => { setResult(null); setOrder(nextChallengeOrder()); setLeft(SECONDS[difficulty]); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (lives <= 0) return;
      if (result && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); next(); return; }
      const map: Record<string, Answer> = { "1": "book", "2": "hold", "3": "ask" };
      if (!result && map[e.key]) void answer(map[e.key]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answer, lives, result]);

  const gameOver = lives <= 0;
  const right = result && result.answer === result.actual;

  return (
    <div>
      <Confetti burst={burst} />
      <button type="button" onClick={onExit} className="mb-4 text-sm font-semibold text-muted-foreground hover:text-foreground">← Back to the menu</button>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-[clamp(1.9rem,3.6vw,2.8rem)] leading-none font-extrabold tracking-tight [font-stretch:112%]">Beat the firewall</h2>
          <p className="mt-2 text-lg text-muted-foreground">Predict what Kadal Kural decides before the clock runs out. {difficulty === "rush" ? "Rush hour: 5 seconds." : "Calm market: 10 seconds."}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="surface inline-flex items-center gap-2 rounded-full px-4 py-2 font-extrabold"><Trophy className="size-4 text-lime-deep" /> {score}</span>
          <span className={cn("surface inline-flex items-center gap-2 rounded-full px-4 py-2 font-extrabold", streak >= 3 && "text-ask")}><Flame className={cn("size-4", streak >= 3 && "fill-ask")} /> {streak}</span>
          <span className="surface inline-flex items-center gap-1 rounded-full px-4 py-2" aria-label={`${lives} lives left`}>
            {Array.from({ length: LIVES }, (_, k) => <Heart key={k} className={cn("size-4", k < lives ? "fill-hold text-hold" : "text-muted-foreground/40")} />)}
          </span>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="surface relative overflow-hidden rounded-3xl p-6">
          {gameOver ? (
            <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="py-6 text-center">
              <p className="text-sm font-semibold text-muted-foreground">Shift over</p>
              <p className="mt-2 text-6xl font-extrabold">{score}</p>
              <p className="text-lg">right predictions · best {Math.max(progress.best, score)}</p>
              <p className="mx-auto mt-3 max-w-[48ch] text-muted-foreground">Every answer came from the real firewall. The rules you were guessing are the rules that protect the desk.</p>
              <GameKey className="mt-6" onClick={() => void start()}><RotateCcw className="size-4" /> Play again</GameKey>
            </motion.div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-muted-foreground">Incoming order</span>
                <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-extrabold tabular-nums", left <= 2 && !result ? "bg-hold-soft text-hold" : "bg-secondary")}><Timer className="size-4" /> {result ? "–" : `${left}s`}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
                <motion.div key={`${order.id}-${!!result}`} className="h-full bg-lime-deep" initial={{ width: "100%" }} animate={{ width: result ? "100%" : "0%" }} transition={{ duration: result ? 0 : SECONDS[difficulty], ease: "linear" }} />
              </div>
              <AnimatePresence mode="wait">
                <motion.div key={order.id} initial={{ opacity: 0, y: 16, rotateX: -25 }} animate={{ opacity: 1, y: 0, rotateX: 0 }} exit={{ opacity: 0, y: -12 }} style={{ transformPerspective: 800 }} transition={{ type: "spring", stiffness: 220, damping: 22 }} className="mt-5">
                  <p lang="ta" className="tamil text-[clamp(1.5rem,3vw,2.2rem)] leading-tight font-extrabold">“{order.text}”</p>
                  <p className="mt-1 text-muted-foreground">{order.gloss}</p>
                  {hints && <Hint order={order} buyers={buyers} />}
                </motion.div>
              </AnimatePresence>

              {!result ? (
                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  {ANSWERS.map((a, k) => (
                    <GameKey key={a.id} tone={a.tone} className="h-auto flex-col py-3" onClick={() => void answer(a.id)}>
                      <span className="inline-flex items-center gap-2 text-lg"><a.icon className="size-5" /> {a.label}</span>
                      <span className="text-xs font-semibold opacity-75">{a.hint} · key {k + 1}</span>
                    </GameKey>
                  ))}
                </div>
              ) : (
                <motion.div initial={{ rotateX: -90, opacity: 0 }} animate={{ rotateX: 0, opacity: 1 }} style={{ transformPerspective: 800, transformOrigin: "top" }} transition={{ type: "spring", stiffness: 170, damping: 18 }}
                  className={cn("mt-6 rounded-2xl p-5", right ? "bg-booked-soft" : "bg-hold-soft")} role="status">
                  <p className={cn("text-lg font-extrabold", right ? "text-booked" : "text-hold")}>
                    {result.answer === null ? "Too slow." : right ? `Right! +${difficulty === "rush" ? 15 : 10} XP` : "Not this time."}
                  </p>
                  {result.decision && (
                    <div className="mt-2 flex flex-wrap items-start gap-3">
                      <span className={cn("rounded-full px-3 py-1 text-sm font-extrabold", KIND_CLASSES[statusOf(result.decision.status).kind].chip)}>Firewall: {statusOf(result.decision.status).label}</span>
                      <p lang="ta" className="tamil min-w-0 flex-1 text-[15px]">{result.decision.tts_response_tamil}</p>
                    </div>
                  )}
                  <GameKey tone="ink" className="mt-4" onClick={next}>Next order <span className="text-xs opacity-60">Enter</span></GameKey>
                </motion.div>
              )}
              {error && <p className="mt-3 font-semibold text-hold">{error}</p>}
            </>
          )}
        </div>

        <aside className="surface rounded-3xl p-5" aria-label="Sandbox credit">
          <p className="font-extrabold">Credit this shift</p>
          <p className="text-sm text-muted-foreground">Bookings move these. Reset when the shift restarts.</p>
          <ul className="mt-4 grid gap-4">
            {buyers.map((b) => {
              const pct = b.running_balance_inr / b.credit_limit_inr;
              return (
                <li key={b.buyer_id}>
                  <div className="flex justify-between text-sm"><b>{b.canonical_name}</b><span className="font-bold">{inr(b.credit_limit_inr - b.running_balance_inr)} left</span></div>
                  <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-secondary">
                    <motion.div className={cn("h-full rounded-full", pct > 0.95 ? "bg-hold" : pct > 0.8 ? "bg-ask" : "bg-lime-deep")} animate={{ width: `${Math.min(100, pct * 100)}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="mt-6 rounded-2xl bg-secondary/70 p-4 text-sm">
            <p className="font-bold">The rules, in short</p>
            <ul className="mt-2 grid gap-1 text-muted-foreground">
              <li><b className="text-foreground">Book</b> when buyer, item and price are clear and credit allows.</li>
              <li><b className="text-foreground">Credit hold</b> when the order pushes the buyer over the limit.</li>
              <li><b className="text-foreground">Ask again</b> for an unknown buyer or a price that cannot be right.</li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
