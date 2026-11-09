import { ArrowRight, AudioLines, Check, Gamepad2, Gauge, Mic, Phone, ShieldCheck, Timer, Waves } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { lazy, Suspense } from "react";
import { Link, useNavigate } from "react-router";

import { useDeskContext } from "@/app/desk-context";
import CircularText from "@/components/CircularText";
import CountUp from "@/components/CountUp";
import { TiltCard } from "@/components/desk/TiltCard";
import { WordRotator } from "@/components/desk/WordRotator";
import { TRY_ORDERS } from "@/lib/format";
import { loadHeroScene } from "@/pages/loaders";

const HeroScene = lazy(loadHeroScene);

const reveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { type: "spring" as const, stiffness: 90, damping: 18 },
};

const STEPS = [
  { icon: AudioLines, title: "Hear", body: "Prisma transcribes Tamil and Tanglish from an 8 kHz stream, paced in 64 ms frames." },
  { icon: Waves, title: "Understand", body: "Tamil number words and case endings are normalised; buyer, item, unit and rate are matched." },
  { icon: Gauge, title: "Gate", body: "Unsure or implausible? The trader is asked again instead of the desk guessing." },
  { icon: ShieldCheck, title: "Credit check", body: "Over the buyer's limit means the fish stays on the dock until the trader decides." },
  { icon: Check, title: "Record and reply", body: "An append-only ledger entry, then the answer spoken back in Tamil in under half a second." },
];

const PROOF = [
  { value: 0, suffix: "", of: " of 560", label: "silent financial errors", note: "noisy trades at 10 and 5 dB SNR" },
  { value: 392, suffix: " ms", label: "reply speed", note: "first STT segment to first reply audio, P50" },
  { value: 52, suffix: " ms", label: "barge-in stop", note: "trader interrupts, voice stops, P50 of 24 live trials" },
  { value: 95.7, suffix: "%", decimals: 1, label: "rates read correctly", note: "under harbour, market, traffic and ice-crusher noise" },
];

export default function HomePage() {
  const reduced = !!useReducedMotion();
  const desk = useDeskContext();
  const navigate = useNavigate();
  const tryFirst = () => { navigate("/desk"); setTimeout(() => void desk.sendTranscript(TRY_ORDERS[0].text), 350); };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-24 pb-10">
      {/* Hero */}
      <section className="relative grid grid-cols-[minmax(0,1fr)] items-center gap-10 pt-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pt-12">
        <div className="relative z-10">
          <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="surface inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium">
            <span className="size-2 rounded-full bg-lime ring-2 ring-lime-deep/30" /> Built on Gnani Prisma and Timbre
          </motion.p>
          <h1 className="mt-6 text-[clamp(2.5rem,5.2vw,4.4rem)] text-balance leading-[0.98] font-extrabold tracking-tight [font-stretch:112%]">
            Every spoken order,
            <br />
            checked before it ships.
          </h1>
          <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-xl text-muted-foreground sm:text-2xl">
            <span>Say it</span>
            <WordRotator
              words={["in Tamil", "in Tanglish", "in one breath", "over harbour noise", "on a phone call"]}
              className="lime-key rounded-xl px-3 font-bold text-ink"
            />
          </div>
          <p className="mt-5 max-w-[54ch] text-lg text-muted-foreground">
            Kadal Kural is a voice credit desk for wholesale fish markets. Traders speak orders; the desk books them, holds
            anything over a buyer's credit limit, and asks again whenever it is unsure. No AI model ever does the arithmetic.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to="/desk" className="orbit-border ink-key inline-flex h-12 items-center gap-2 rounded-full px-6 text-base font-bold">
              Open the desk <ArrowRight className="size-4" />
            </Link>
            <Link to="/play" className="surface inline-flex h-12 items-center gap-2 rounded-full px-5 font-semibold hover:border-lime">
              <Gamepad2 className="size-4" /> Play Harbour Shift
            </Link>
            <button type="button" onClick={tryFirst} className="inline-flex h-12 items-center gap-2 rounded-full px-3 font-semibold text-muted-foreground hover:text-foreground">
              <Mic className="size-4" /> Run a sample order
            </button>
          </div>
        </div>

        <div className="relative aspect-[5/4] w-full">
          <div className="pointer-events-none absolute inset-[8%] rounded-full bg-lime/30 blur-3xl" />
          <Suspense fallback={<div className="absolute inset-[25%] animate-pulse rounded-full bg-lime/40" />}>
            <HeroScene reduced={reduced} />
          </Suspense>
          <div className="absolute right-2 bottom-2 hidden sm:block">
            <CircularText text="speak · check · dispatch · " spinDuration={18} size={120} fontSize={13} color="#0f1d14" />
          </div>
        </div>
      </section>

      {/* Marquee of real orders */}
      <section aria-label="Orders the desk understands" className="-mx-4 overflow-hidden border-y border-border/70 bg-white/60 py-5 sm:-mx-6">
        <div className="marquee" aria-hidden>
          {[0, 1].map((copy) => (
            <p key={copy} lang="ta" className="tamil flex shrink-0 items-center gap-10 pr-10 text-2xl font-bold whitespace-nowrap text-ink/80">
              {TRY_ORDERS.map((t) => <span key={t.text} className="inline-flex items-center gap-10">{t.text}<span className="text-lime-deep">✦</span></span>)}
            </p>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-title">
        <motion.div {...reveal} className="mb-8 max-w-2xl">
          <h2 id="how-title" className="text-4xl font-extrabold tracking-tight [font-stretch:110%]">How an order is checked</h2>
          <p className="mt-3 text-lg text-muted-foreground">Five steps, under half a second, every time. Watch them light up on the desk as you speak.</p>
        </motion.div>
        <ol className="grid gap-4 md:grid-cols-5">
          {STEPS.map((s, i) => (
            <motion.li key={s.title} {...reveal} transition={{ ...reveal.transition, delay: i * 0.06 }}>
              <TiltCard>
                <div className="flex h-full flex-col gap-3 p-5">
                  <div className="flex items-center justify-between">
                    <span className="lime-key grid size-11 place-items-center rounded-xl"><s.icon className="size-5" /></span>
                    <span className="text-3xl font-extrabold text-ink/10">{i + 1}</span>
                  </div>
                  <h3 className="text-lg font-extrabold">{s.title}</h3>
                  <p className="text-sm text-muted-foreground">{s.body}</p>
                </div>
              </TiltCard>
            </motion.li>
          ))}
        </ol>
      </section>

      {/* Proof */}
      <section aria-labelledby="proof-title" className="relative overflow-hidden rounded-[2rem] bg-ink p-8 text-white sm:p-12">
        <div className="pointer-events-none absolute -top-32 -right-24 size-96 rounded-full bg-lime/30 blur-3xl" />
        <motion.div {...reveal} className="relative max-w-2xl">
          <h2 id="proof-title" className="text-4xl font-extrabold tracking-tight [font-stretch:110%]">Measured, not claimed</h2>
          <p className="mt-3 text-lg text-white/70">405 recorded transcripts across four synthetic noise profiles, plus live trials. Every number comes from a script in the repository.</p>
        </motion.div>
        <div className="relative mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {PROOF.map((p, i) => (
            <motion.div key={p.label} {...reveal} transition={{ ...reveal.transition, delay: i * 0.08 }} className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
              <p className="text-5xl font-extrabold tracking-tight text-lime [font-stretch:90%]">
                <CountUp to={p.value} decimals={p.decimals ?? 0} duration={1.2} />
                {p.suffix}
                {p.of && <span className="text-2xl text-white/60">{p.of}</span>}
              </p>
              <p className="mt-2 font-bold">{p.label}</p>
              <p className="mt-1 text-sm text-white/60">{p.note}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Channels */}
      <section aria-labelledby="ways-title">
        <motion.h2 {...reveal} id="ways-title" className="mb-8 text-4xl font-extrabold tracking-tight [font-stretch:110%]">Two ways to place an order</motion.h2>
        <div className="grid gap-5 md:grid-cols-2">
          {[
            { icon: Mic, title: "At the desk", body: "Live microphone into our own pipeline: paced 8 kHz Prisma stream, multi-segment assembler, instant barge-in.", to: "/desk", cta: "Open the desk", on: desk.desk?.gnani_live_key_configured },
            { icon: Phone, title: "On a phone call", body: "Gnani Agent Builder takes the call and forwards each turn to the same firewall. Verified on a live call.", to: "/phone", cta: "See the phone line", on: desk.desk?.phone_channel_enabled },
          ].map((c, i) => (
            <motion.div key={c.title} {...reveal} transition={{ ...reveal.transition, delay: i * 0.08 }}>
              <TiltCard>
                <div className="flex h-full flex-col gap-4 p-7">
                  <div className="flex items-center justify-between">
                    <span className="ink-key grid size-14 place-items-center rounded-2xl"><c.icon className="size-6 text-lime" /></span>
                    <span className="inline-flex items-center gap-2 rounded-full bg-secondary px-3 py-1 text-xs font-bold">
                      <span className={c.on ? "size-2 rounded-full bg-lime" : "size-2 rounded-full border border-undone"} /> {c.on ? "Available now" : "Not configured"}
                    </span>
                  </div>
                  <h3 className="text-2xl font-extrabold">{c.title}</h3>
                  <p className="text-muted-foreground">{c.body}</p>
                  <Link to={c.to} className="mt-auto inline-flex items-center gap-2 font-bold text-lime-deep hover:gap-3">{c.cta} <ArrowRight className="size-4" /></Link>
                </div>
              </TiltCard>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Closing CTA */}
      <motion.section {...reveal} className="lime-key relative overflow-hidden rounded-[2rem] p-10 text-center sm:p-14">
        <Timer className="mx-auto size-10" />
        <h2 className="mt-4 text-4xl font-extrabold tracking-tight [font-stretch:110%]">Try it in thirty seconds</h2>
        <p className="mx-auto mt-3 max-w-xl text-lg text-ink/75">Open the desk, press the space bar and say an order. Or type one. The ledger updates as you speak.</p>
        <Link to="/desk" className="ink-key mt-8 inline-flex h-12 items-center gap-2 rounded-full px-6 font-bold">Open the desk <ArrowRight className="size-4" /></Link>
      </motion.section>
    </div>
  );
}
