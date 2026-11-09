import { ArrowRight, BookOpen, Brain, Check, Ear, Gauge, Phone, QrCode, RotateCcw, ShieldCheck, Timer, Users, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import { sandbox, type Decision } from "@/lib/api";
import { inr, KIND_CLASSES, statusOf } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AFTER, CHECKPOINTS, OPENING_CREDIT, STAKES, STORY_ORDERS, VERDICT_STOP, type CheckpointId, type Choice } from "./data";
import type { ProgressApi } from "./progress";
import { ChapterHeader, Confetti, GameKey } from "./ui";

const ICONS = { ear: Ear, brain: Brain, gauge: Gauge, shield: ShieldCheck, check: Check, book: BookOpen, qr: QrCode, users: Users, phone: Phone } as const;
const TOTAL = 5;
const ORDER_SECONDS = 9;

interface ShiftResult { choices: Choice[]; seconds: number }

/* ---------------- Chapter 1: the problem ---------------- */

function NoiseMeter() {
  return (
    <div className="flex h-8 items-end gap-[3px]" aria-hidden>
      {Array.from({ length: 22 }, (_, i) => (
        <span key={i} className="noise-bar w-1.5 rounded-full bg-gradient-to-t from-lime-deep to-lime" style={{ animationDelay: `${(i * 97) % 600}ms`, animationDuration: `${420 + ((i * 53) % 380)}ms` }} />
      ))}
    </div>
  );
}

function ManualShift({ onDone, progress }: { onDone: (r: ShiftResult) => void; progress: ProgressApi }) {
  const [i, setI] = useState(0);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [revealed, setRevealed] = useState<Choice | null>(null);
  const [left, setLeft] = useState(ORDER_SECONDS);
  const started = useRef(performance.now());
  const order = STORY_ORDERS[i];

  const owed = useMemo(() => {
    const o = OPENING_CREDIT.map((b) => b.owed);
    choices.forEach((c, k) => { const so = STORY_ORDERS[k]; if (c === "dispatch" && so.buyer !== null) o[so.buyer] += so.value; });
    return o;
  }, [choices]);

  const decide = (c: Choice) => {
    if (revealed) return;
    setRevealed(c);
    if (c === order.right) progress.addXp(20);
  };

  useEffect(() => {
    if (revealed) return;
    if (left <= 0) { decide("dispatch"); return; } // in the rush, it ships
    const id = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left, revealed]);

  const next = () => {
    const all = [...choices, revealed!];
    setChoices(all);
    setRevealed(null);
    setLeft(ORDER_SECONDS);
    if (i + 1 < STORY_ORDERS.length) setI(i + 1);
    else { progress.award("first_shift"); onDone({ choices: all, seconds: Math.round((performance.now() - started.current) / 1000) }); }
  };

  const right = revealed === order.right;
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="surface relative overflow-hidden rounded-3xl p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3"><NoiseMeter /><span className="text-sm font-semibold text-muted-foreground">Harbour noise · order {i + 1} of {STORY_ORDERS.length}</span></div>
          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-extrabold tabular-nums", left <= 3 && !revealed ? "bg-hold-soft text-hold" : "bg-secondary")}>
            <Timer className="size-4" /> {revealed ? "–" : `${left}s`}
          </span>
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={i} initial={{ opacity: 0, x: 40, rotate: 2 }} animate={{ opacity: 1, x: 0, rotate: 0 }} exit={{ opacity: 0, x: -40, rotate: -2 }} transition={{ type: "spring", stiffness: 200, damping: 22 }} className="mt-6">
            <p className="text-sm text-muted-foreground">A trader shouts across the dock:</p>
            <p lang="ta" className="tamil mt-1 text-[clamp(1.6rem,3.2vw,2.4rem)] leading-tight font-extrabold">“{order.heard}”</p>
            <p className="mt-1 text-muted-foreground">{order.gloss}</p>
          </motion.div>
        </AnimatePresence>

        {!revealed ? (
          <div className="mt-8 flex flex-wrap gap-4">
            <GameKey tone="lime" className="flex-1 text-lg" onClick={() => decide("dispatch")}>Dispatch it</GameKey>
            <GameKey tone="ink" className="flex-1 text-lg" onClick={() => decide("hold")}>Hold it</GameKey>
          </div>
        ) : (
          <motion.div initial={{ rotateX: -90, opacity: 0 }} animate={{ rotateX: 0, opacity: 1 }} transition={{ type: "spring", stiffness: 160, damping: 18 }} style={{ transformPerspective: 800, transformOrigin: "top" }}
            className={cn("mt-8 rounded-2xl p-5", right ? "bg-booked-soft" : "bg-hold-soft")}>
            <p className={cn("flex items-center gap-2 text-lg font-extrabold", right ? "text-booked" : "text-hold")}>
              {right ? <Check className="size-5" /> : <X className="size-5" />}
              {right ? "Good call." : revealed === "dispatch" ? `Shipped. ${order.lossIfDispatched ? inr(order.lossIfDispatched) + " at risk." : ""}` : "Held a good order: a lost sale."}
            </p>
            <p className="mt-2">{order.truth}</p>
            <p className="mt-1 text-sm text-muted-foreground">{order.lesson}</p>
            <GameKey tone="ink" className="mt-4" onClick={next}>{i + 1 < STORY_ORDERS.length ? "Next order" : "End the shift"} <ArrowRight className="size-4" /></GameKey>
          </motion.div>
        )}
      </div>

      <aside className="surface rounded-3xl p-5" aria-label="Credit board">
        <p className="font-extrabold">Your credit board</p>
        <p className="text-sm text-muted-foreground">Chalk, memory and a calculator you have no time to use.</p>
        <ul className="mt-4 grid gap-4">
          {OPENING_CREDIT.map((b, k) => {
            const pct = owed[k] / b.limit;
            return (
              <li key={b.name}>
                <div className="flex justify-between text-sm"><b>{b.name}</b><span className={cn("font-bold", pct > 1 && "text-hold")}>{inr(owed[k])} / {inr(b.limit)}</span></div>
                <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-secondary">
                  <motion.div className={cn("h-full rounded-full", pct > 1 ? "bg-hold" : pct > 0.8 ? "bg-ask" : "bg-lime-deep")} animate={{ width: `${Math.min(100, pct * 100)}%` }} />
                </div>
                {pct > 1 && <p className="mt-1 text-xs font-bold text-hold">Over the limit by {inr(owed[k] - b.limit)}</p>}
              </li>
            );
          })}
        </ul>
      </aside>
    </div>
  );
}

function ShiftSummary({ r, onNext }: { r: ShiftResult; onNext: () => void }) {
  const correct = r.choices.filter((c, k) => c === STORY_ORDERS[k].right).length;
  const atRisk = r.choices.reduce((s, c, k) => s + (c === "dispatch" ? STORY_ORDERS[k].lossIfDispatched : 0), 0);
  return (
    <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="surface rounded-3xl p-8 text-center">
      <p className="text-sm font-semibold text-muted-foreground">Shift over</p>
      <p className="mt-2 text-6xl font-extrabold tracking-tight">{correct}/5</p>
      <p className="mt-1 text-lg">right calls in {r.seconds} seconds</p>
      <p className={cn("mt-4 text-2xl font-extrabold", atRisk ? "text-hold" : "text-booked")}>{atRisk ? `${inr(atRisk)} at risk` : "Nothing at risk. Impressive."}</p>
      <p className="mx-auto mt-3 max-w-[52ch] text-muted-foreground">
        That was five orders. A real auction morning is hundreds, shouted over each other, with the ledger written up later from memory. That is the problem Kadal Kural solves.
      </p>
      <GameKey className="mt-6" onClick={onNext}>Why it matters <ArrowRight className="size-4" /></GameKey>
    </motion.div>
  );
}

/* ---------------- Chapter 2: why it matters ---------------- */

function Stakes({ onNext, progress }: { onNext: () => void; progress: ProgressApi }) {
  const [flipped, setFlipped] = useState<boolean[]>(STAKES.map(() => false));
  const all = flipped.every(Boolean);
  const { award } = progress;
  useEffect(() => { if (all) award("stakes"); }, [all, award]);
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAKES.map((c, k) => (
          <button
            key={c.front}
            type="button"
            onClick={() => setFlipped((f) => f.map((v, j) => (j === k ? !v : v)))}
            aria-pressed={flipped[k]}
            aria-label={`${c.front}. ${flipped[k] ? c.back : "Select to reveal."}`}
            className="group h-64 [perspective:1000px]"
          >
            <motion.div className="relative size-full [transform-style:preserve-3d]" animate={{ rotateY: flipped[k] ? 180 : 0 }} transition={{ type: "spring", stiffness: 140, damping: 16 }}>
              <div className="lime-key absolute inset-0 flex flex-col justify-between rounded-3xl p-6 text-left [backface-visibility:hidden]">
                <span className="text-sm font-bold opacity-70">Card {k + 1}</span>
                <span className="text-2xl leading-tight font-extrabold">{c.front}</span>
                <span className="text-sm font-semibold opacity-70 group-hover:opacity-100">Tap to flip</span>
              </div>
              <div className="surface absolute inset-0 flex flex-col justify-between rounded-3xl p-6 text-left [backface-visibility:hidden] [transform:rotateY(180deg)]">
                <span><span className="block text-3xl font-extrabold text-lime-deep">{c.stat}</span><span className="text-xs text-muted-foreground">{c.statLabel}</span></span>
                <span className="text-[15px] leading-snug">{c.back}</span>
              </div>
            </motion.div>
          </button>
        ))}
      </div>
      <div className="mt-6 flex items-center gap-4">
        <GameKey disabled={!all} onClick={onNext}>Build the fix <ArrowRight className="size-4" /></GameKey>
        <span className="text-sm text-muted-foreground">{all ? "All four flipped." : `${flipped.filter(Boolean).length} of 4 flipped`}</span>
      </div>
    </div>
  );
}

/* ---------------- Chapter 3: build the firewall ---------------- */

function BuildFirewall({ onNext, progress }: { onNext: () => void; progress: ProgressApi }) {
  const shuffled = useMemo(() => [...CHECKPOINTS].sort(() => Math.random() - 0.5), []);
  const [placed, setPlaced] = useState<CheckpointId[]>([]);
  const [shake, setShake] = useState<string | null>(null);
  const [mistakes, setMistakes] = useState(0);
  const done = placed.length === CHECKPOINTS.length;
  const last = placed.length ? CHECKPOINTS.find((c) => c.id === placed[placed.length - 1]) : null;

  const { award } = progress;
  useEffect(() => {
    if (!done) return;
    award("builder");
    if (mistakes === 0) award("flawless_build");
  }, [done, mistakes, award]);

  const tryPlace = (id: CheckpointId) => {
    if (CHECKPOINTS[placed.length].id === id) { setPlaced((p) => [...p, id]); progress.addXp(15); }
    else { setMistakes((m) => m + 1); setShake(id); window.setTimeout(() => setShake(null), 400); }
  };

  return (
    <div className="grid gap-6">
      <ol className="grid gap-3 md:grid-cols-5" aria-label="The firewall, in order">
        {CHECKPOINTS.map((c, k) => {
          const isPlaced = placed.includes(c.id);
          const Icon = ICONS[c.icon];
          return (
            <li key={c.id} className={cn("relative flex min-h-36 flex-col gap-2 rounded-2xl border-2 border-dashed p-4", isPlaced ? "border-transparent" : "border-border")}>
              <span className="text-xs font-bold text-muted-foreground">Slot {k + 1}</span>
              {isPlaced && (
                <motion.div layoutId={`cp-${c.id}`} className="lime-key absolute inset-0 flex flex-col gap-2 rounded-2xl p-4" transition={{ type: "spring", stiffness: 260, damping: 24 }}>
                  <Icon className="size-6" />
                  <span className="font-extrabold">{c.title}</span>
                </motion.div>
              )}
            </li>
          );
        })}
      </ol>

      <AnimatePresence mode="wait">
        {last && !done && (
          <motion.p key={last.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-2xl bg-booked-soft p-4">
            <b>{last.title}.</b> {last.body}
          </motion.p>
        )}
      </AnimatePresence>

      {!done ? (
        <div>
          <p className="mb-3 font-semibold">Which checkpoint comes {placed.length === 0 ? "first" : "next"}? <span className="text-muted-foreground">Tap it.</span></p>
          <div className="flex flex-wrap gap-3">
            {shuffled.filter((c) => !placed.includes(c.id)).map((c) => {
              const Icon = ICONS[c.icon];
              return (
                <motion.div key={c.id} layoutId={`cp-${c.id}`} animate={shake === c.id ? { x: [0, -10, 10, -6, 6, 0] } : {}} transition={{ duration: 0.35 }}>
                  <GameKey tone="white" onClick={() => tryPlace(c.id)}><Icon className="size-5" /> {c.title}</GameKey>
                </motion.div>
              );
            })}
          </div>
          {mistakes > 0 && <p className="mt-3 text-sm text-muted-foreground">Hint: an order has to be heard before it can be understood, and checked before it is recorded.</p>}
        </div>
      ) : (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="surface rounded-3xl p-6">
          <p className="text-xl font-extrabold">Firewall built{mistakes === 0 ? " without a wrong move" : ""}.</p>
          <ul className="mt-3 grid gap-2 text-sm">
            {CHECKPOINTS.map((c) => <li key={c.id}><b>{c.title}.</b> <span className="text-muted-foreground">{c.body}</span></li>)}
          </ul>
          <GameKey className="mt-5" onClick={onNext}>Run the same shift through it <ArrowRight className="size-4" /></GameKey>
        </motion.div>
      )}
    </div>
  );
}

/* ---------------- Chapter 4: the same shift, with the firewall ---------------- */

function FirewallRun({ choices, onNext, progress }: { choices: Choice[]; onNext: () => void; progress: ProgressApi }) {
  const reduced = useReducedMotion();
  const [k, setK] = useState(-1);
  const [stop, setStop] = useState<number>(-1);
  const [results, setResults] = useState<Decision[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void sandbox.reset().catch(() => setError("The sandbox did not answer. Is the server running?")); }, []);

  const run = async () => {
    const idx = k + 1;
    setBusy(true); setK(idx); setStop(-1);
    try {
      const out = await sandbox.evaluate(STORY_ORDERS[idx].heard);
      const d = out.decisions[0];
      const target = CHECKPOINTS.findIndex((c) => c.id === VERDICT_STOP[(d?.status ?? "PENDING_CLARIFICATION") as keyof typeof VERDICT_STOP]);
      for (let s = 0; s <= target; s++) { setStop(s); await new Promise((r) => setTimeout(r, reduced ? 0 : 320)); }
      setResults((r) => [...r, d]);
      progress.addXp(10);
      if (idx === STORY_ORDERS.length - 1) progress.award("witness");
    } catch {
      setError("The sandbox did not answer. Is the server running?");
    } finally { setBusy(false); }
  };

  const finished = results.length === STORY_ORDERS.length;
  const current = k >= 0 ? STORY_ORDERS[k] : null;
  const decision = results[k];
  return (
    <div className="grid gap-5">
      <div className="surface rounded-3xl p-6">
        <div className="relative grid grid-cols-5 gap-2">
          <div className="absolute top-7 right-[10%] left-[10%] h-1 rounded-full bg-secondary" />
          <motion.div className="absolute top-7 left-[10%] h-1 rounded-full bg-lime-deep" animate={{ width: stop < 0 ? "0%" : `${(stop / 4) * 80}%` }} transition={{ duration: reduced ? 0 : 0.28 }} />
          {CHECKPOINTS.map((c, s) => {
            const Icon = ICONS[c.icon];
            const lit = s <= stop;
            const isStop = s === stop && !busy && decision;
            return (
              <div key={c.id} className="relative z-10 flex flex-col items-center gap-2 text-center">
                <motion.span animate={lit ? { scale: [1, 1.15, 1] } : {}} className={cn("grid size-14 place-items-center rounded-2xl transition-colors", lit ? (isStop && statusOf(decision.status).kind !== "booked" ? "bg-hold text-white" : "lime-key") : "surface text-muted-foreground")}>
                  <Icon className="size-6" />
                </motion.span>
                <span className={cn("text-xs font-bold sm:text-sm", lit ? "text-foreground" : "text-muted-foreground")}>{c.title}</span>
              </div>
            );
          })}
        </div>

        <div className="mt-6 min-h-40">
          {current ? (
            <div>
              <p className="text-sm text-muted-foreground">Order {k + 1} of 5</p>
              <p lang="ta" className="tamil text-2xl font-extrabold">“{current.heard}”</p>
              {decision && !busy && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-3 flex flex-wrap items-start gap-3">
                  <span className={cn("rounded-full px-3 py-1 text-sm font-extrabold", KIND_CLASSES[statusOf(decision.status).kind].chip)}>{statusOf(decision.status).label}</span>
                  <p lang="ta" className="tamil min-w-0 flex-1 text-[15px]">{decision.tts_response_tamil}</p>
                  <span className={cn("rounded-full px-3 py-1 text-sm font-bold", choices[k] === current.right ? "bg-booked-soft text-booked" : "bg-hold-soft text-hold")}>
                    You {choices[k] === "dispatch" ? "dispatched" : "held"} it {choices[k] === current.right ? "✓" : "✗"}
                  </span>
                </motion.div>
              )}
            </div>
          ) : (
            <p className="text-muted-foreground">The firewall gets the exact same five orders you just handled. Watch where each one stops.</p>
          )}
          {error && <p className="mt-3 font-semibold text-hold">{error}</p>}
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          {!finished ? (
            <GameKey disabled={busy} onClick={() => void run()}>{k < 0 ? "Run the first order" : "Run the next order"} <ArrowRight className="size-4" /></GameKey>
          ) : (
            <GameKey onClick={onNext}>See what changed <ArrowRight className="size-4" /></GameKey>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">These are live answers from the real firewall, running on a private sandbox ledger: your desk's balances are not touched.</p>
    </div>
  );
}

/* ---------------- Chapter 5: after the fix ---------------- */

function After({ result, onRestart, progress }: { result: ShiftResult; onRestart: () => void; progress: ProgressApi }) {
  const [burst, setBurst] = useState(0);
  const { award } = progress;
  useEffect(() => { award("hero"); setBurst(Date.now()); }, [award]); // once: award is a stable callback
  const correct = result.choices.filter((c, k) => c === STORY_ORDERS[k].right).length;
  const atRisk = result.choices.reduce((s, c, k) => s + (c === "dispatch" ? STORY_ORDERS[k].lossIfDispatched : 0), 0);
  const rows = [
    { label: "Right decisions", you: `${correct} / 5`, kk: "5 / 5" },
    { label: "Money at risk", you: inr(atRisk), kk: inr(0) },
    { label: "Time per order", you: `~${Math.max(1, Math.round(result.seconds / 5))} s`, kk: "< 0.5 s" },
    { label: "Ledger", you: "Written later, from memory", kk: "Written as it happens" },
  ];
  return (
    <div className="grid gap-6">
      <Confetti burst={burst} />
      <div className="surface overflow-hidden rounded-3xl">
        <div className="grid grid-cols-[1.2fr_1fr_1fr] bg-secondary/70 px-5 py-3 text-sm font-extrabold">
          <span />
          <span>You, by hand</span>
          <span className="text-lime-deep">With Kadal Kural</span>
        </div>
        {rows.map((r, k) => (
          <motion.div key={r.label} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 * k }} className="grid grid-cols-[1.2fr_1fr_1fr] items-center border-t px-5 py-4">
            <span className="text-sm text-muted-foreground">{r.label}</span>
            <span className="font-bold">{r.you}</span>
            <span className="font-extrabold text-booked">{r.kk}</span>
          </motion.div>
        ))}
      </div>

      <div>
        <h3 className="mb-3 text-xl font-extrabold">And it connects to everything after the order</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {AFTER.map((a, k) => {
            const Icon = ICONS[a.icon];
            return (
              <motion.div key={a.title} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + k * 0.08 }}>
                <Link to={a.to} className="surface group flex h-full flex-col gap-2 rounded-2xl p-5 transition-transform hover:-translate-y-1">
                  <span className="ink-key grid size-11 place-items-center rounded-xl"><Icon className="size-5 text-lime" /></span>
                  <span className="font-extrabold">{a.title}</span>
                  <span className="text-sm text-muted-foreground">{a.body}</span>
                  <span className="mt-auto inline-flex items-center gap-1 text-sm font-bold text-lime-deep group-hover:gap-2">Open <ArrowRight className="size-3.5" /></span>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-4">
        <Link to="/desk"><GameKey tabIndex={-1}>Try it live on the desk <ArrowRight className="size-4" /></GameKey></Link>
        <GameKey tone="white" onClick={onRestart}><RotateCcw className="size-4" /> Play the story again</GameKey>
      </div>
    </div>
  );
}

/* ---------------- the story ---------------- */

const CHAPTERS = [
  { title: "The 4 AM shift", lead: "You run the dispatch desk at Kasimedu harbour. Orders come shouted over the noise; your board shows each buyer's credit. Dispatch or hold, before the clock runs out." },
  { title: "Why it matters", lead: "Your shift was five orders. Flip the cards to see what a real morning is up against." },
  { title: "Build the firewall", lead: "Kadal Kural puts five checkpoints between a shouted order and a dispatched crate. Put them in the right order." },
  { title: "Same shift, new desk", lead: "Now the firewall takes your five orders. A lime token travels the checkpoints and stops where the order is decided." },
  { title: "After the fix", lead: "What changed, and where the solution connects once an order is in." },
];

export function StoryMode({ progress, onExit }: { progress: ProgressApi; onExit: () => void }) {
  const [ch, setCh] = useState(0);
  const [result, setResult] = useState<ShiftResult | null>(null);
  const restart = () => { setResult(null); setCh(0); };
  return (
    <div>
      <button type="button" onClick={onExit} className="mb-4 text-sm font-semibold text-muted-foreground hover:text-foreground">← Back to the menu</button>
      <ChapterHeader index={ch} total={TOTAL} title={CHAPTERS[ch].title} lead={CHAPTERS[ch].lead} />
      <AnimatePresence mode="wait">
        <motion.div key={ch + (result ? "r" : "")} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
          {ch === 0 && !result && <ManualShift progress={progress} onDone={setResult} />}
          {ch === 0 && result && <ShiftSummary r={result} onNext={() => setCh(1)} />}
          {ch === 1 && <Stakes progress={progress} onNext={() => setCh(2)} />}
          {ch === 2 && <BuildFirewall progress={progress} onNext={() => setCh(3)} />}
          {ch === 3 && result && <FirewallRun choices={result.choices} progress={progress} onNext={() => setCh(4)} />}
          {ch === 4 && result && <After result={result} progress={progress} onRestart={restart} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
