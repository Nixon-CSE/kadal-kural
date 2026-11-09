import { ArrowRight, Phone } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { lazy, Suspense } from "react";
import { Link, useNavigate } from "react-router";

import { useDeskContext } from "@/app/desk-context";
import { inr, KIND_CLASSES, statusOf, TRY_ORDERS } from "@/lib/format";
import { cn } from "@/lib/utils";
import { loadHeroScene } from "@/pages/loaders";

const HeroScene = lazy(loadHeroScene);

const REPO = "https://github.com/Nixon-CSE/kadal-kural";

// Every figure comes from benchmark/REPORT.md or the live trials described in the README.
const MEASURED = [
  { figure: "0 of 560", label: "noisy trades booked wrongly without a hold" },
  { figure: "392 ms", label: "from the trader's last word to the first spoken reply (P50)" },
  { figure: "52 ms", label: "for the reply to stop when the trader talks over it (P50, 24 live trials)" },
  { figure: "95.7%", label: "of rates read correctly under harbour, market, traffic and ice-crusher noise" },
];

const STEPS = [
  { title: "Hear", body: "Gnani Prisma turns the trader's Tamil or Tanglish into text, live, from an 8 kHz stream." },
  { title: "Understand", body: "Tamil number words and case endings are normalised; buyer, item, quantity and rate are matched." },
  { title: "Gate", body: "If any part is unsure, or the price is not a real price, the trader is asked again." },
  { title: "Credit check", body: "If the order takes the buyer past their limit, it is held and the fish stays on the dock." },
  { title: "Record and reply", body: "A new ledger line is written, never edited, and the answer is spoken back in Tamil." },
];

// From the git history of this repository.
const LOG = [
  { date: "9 Nov 2026", tag: "Phone line", title: "First live call through Gnani Agent Builder", body: "An order cut off before the rate was held; two seconds later the full sentence booked ₹10,000." },
  { date: "2 Nov 2026", tag: "Payments", title: "UPI link on every booked order", body: "The ledger drawer shows a QR code for the exact amount; undone orders lose it." },
  { date: "1 Nov 2026", tag: "Latency", title: "Barge-in measured on live audio", body: "A voice-activity threshold sweep, and reply latency before and after it." },
  { date: "31 Oct 2026", tag: "Benchmark", title: "405 transcripts through four kinds of noise", body: "45 spoken orders, clean and at 10 and 5 dB of harbour, market, traffic and ice-crusher noise." },
  { date: "26 Oct 2026", tag: "Speech", title: "Tamil numbers checked against live Prisma output", body: "Lakh amounts, ₹ and comma decoration, and words like எழுநூற்றி நாற்பது." },
  { date: "23 Oct 2026", tag: "Ledger", title: "Append-only ledger and the live microphone bridge", body: "SQLite in WAL mode; an undo adds a reversing line instead of deleting one." },
];

const BUILT_WITH = [
  { name: "Gnani Prisma", role: "Speech to text" },
  { name: "Gnani Timbre", role: "Text to speech" },
  { name: "Agent Builder", role: "Phone calls" },
  { name: "FastAPI", role: "API and live audio" },
  { name: "SQLite", role: "The ledger" },
  { name: "React", role: "This app" },
  { name: "three.js", role: "3D scenes" },
  { name: "Cloudflare Tunnel", role: "Phone webhook" },
];

function SectionHead({ id, title, link }: { id: string; title: string; link?: { to: string; label: string } }) {
  return (
    <div className="mb-6 flex items-baseline justify-between gap-4">
      <h2 id={id} className="text-[clamp(1.6rem,3vw,2.1rem)] font-bold tracking-tight">{title}</h2>
      {link && (
        <Link to={link.to} className="shrink-0 text-sm font-semibold text-lime-deep underline-offset-4 hover:underline">
          {link.label}
        </Link>
      )}
    </div>
  );
}

export default function HomePage() {
  const reduced = !!useReducedMotion();
  const desk = useDeskContext();
  const navigate = useNavigate();
  const events = desk.desk?.events ?? [];
  const recent = events.slice(0, 5);
  const runSample = () => { navigate("/desk"); setTimeout(() => void desk.sendTranscript(TRY_ORDERS[0].text), 350); };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-20 pb-6 sm:gap-28">
      {/* Hero */}
      <section className="grid grid-cols-[minmax(0,1fr)] items-center gap-8 pt-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:pt-14">
        <div>
          <h1 className="text-[clamp(2.6rem,5.6vw,4.75rem)] leading-[1.02] font-bold tracking-[-0.025em]">
            Every spoken order,
            <br />
            checked before
            <br />
            it ships.
          </h1>
          <p className="mt-6 max-w-[46ch] text-lg leading-relaxed text-muted-foreground sm:text-xl">
            A voice credit desk for wholesale fish markets. Traders speak orders in Tamil; the desk books them, holds anything over a
            buyer's credit limit, and asks again when it is unsure.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link to="/desk" className="ink-key inline-flex h-12 items-center gap-2 rounded-xl px-6 text-base font-semibold">
              Open the desk <ArrowRight className="size-4" />
            </Link>
            <Link to="/play" className="text-base font-semibold underline decoration-lime-deep/40 decoration-2 underline-offset-4 hover:decoration-lime-deep">
              Learn it by playing Harbour Shift
            </Link>
          </div>
        </div>
        <div className="relative aspect-[5/4] w-full">
          <Suspense fallback={<div className="absolute inset-[25%] animate-pulse rounded-full bg-lime/30" />}>
            <HeroScene reduced={reduced} />
          </Suspense>
        </div>
      </section>

      {/* Featured */}
      <section aria-labelledby="featured-title">
        <h2 id="featured-title" className="mb-4 text-sm font-semibold text-muted-foreground">Featured</h2>
        <article className="grid overflow-hidden rounded-2xl border bg-white md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="flex min-h-56 flex-col justify-between gap-6 bg-ink p-6 text-[#f4ffe0] sm:p-8">
            <span className="inline-flex items-center gap-2 text-sm text-[#f4ffe0]/70"><Phone className="size-4" /> Live call, 9 Nov 2026, 11:50:26</span>
            <p lang="ta" className="tamil text-[clamp(1.5rem,3.2vw,2.4rem)] leading-snug font-semibold">“குமரனுக்கு இருபது கிலோ டைகர் பிரான் ஐநூறு ரேட்”</p>
            <span className="text-sm text-lime">Booked ₹10,000 for Kumaran Stores. இருபது read as 20, ஐநூறு as 500.</span>
          </div>
          <div className="flex flex-col gap-4 p-6 sm:p-8">
            <p className="text-sm text-muted-foreground">Phone line · Gnani Agent Builder</p>
            <h3 className="text-2xl font-bold tracking-tight">Orders by phone, checked by the same firewall</h3>
            <p className="text-muted-foreground">
              Gnani's agent answers the call and passes each sentence to Kadal Kural. On the first live call the agent sent the order before
              the rate was spoken, so the desk held it; two seconds later the full sentence arrived and was booked.
            </p>
            <Link to="/phone" className="ink-key mt-auto inline-flex h-11 items-center gap-2 self-start rounded-xl px-5 font-semibold">
              See how the phone line works
            </Link>
          </div>
        </article>
      </section>

      {/* Live ledger */}
      <section aria-labelledby="recent-title">
        <SectionHead id="recent-title" title="On the desk right now" link={{ to: "/ledger", label: "View the ledger" }} />
        {recent.length ? (
          <ul className="divide-y rounded-2xl border bg-white">
            {recent.map((e) => {
              const st = statusOf(e.status);
              return (
                <li key={e.event_id}>
                  <Link to="/ledger" className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3.5 hover:bg-lime-soft/50 sm:grid-cols-[5rem_minmax(0,1fr)_10rem_7rem_8rem] sm:px-6">
                    <span className="text-sm text-muted-foreground tabular-nums">{e.created_at.slice(-8, -3) || e.created_at}</span>
                    <span lang="ta" className="tamil truncate font-semibold">{e.raw_utterance}</span>
                    <span className="hidden truncate text-sm text-muted-foreground sm:block">{e.buyer_name}</span>
                    <span className="hidden text-right font-semibold tabular-nums sm:block">{inr(e.trade_value_inr)}</span>
                    <span className={cn("justify-self-end rounded-full px-2.5 py-0.5 text-xs font-bold whitespace-nowrap", KIND_CLASSES[st.kind].chip)}>{st.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="flex flex-col items-start gap-4 rounded-2xl border border-dashed bg-white/60 p-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-muted-foreground">Nothing on the ledger yet. A sample order takes one click and shows the whole check.</p>
            <button type="button" onClick={runSample} className="ink-key h-11 shrink-0 rounded-xl px-5 font-semibold">Run a sample order</button>
          </div>
        )}
      </section>

      {/* Measured */}
      <section aria-labelledby="measured-title">
        <SectionHead id="measured-title" title="What we measured" link={{ to: "/insights", label: "See the benchmark" }} />
        <dl className="grid grid-cols-2 gap-x-6 gap-y-10 sm:gap-x-10 lg:grid-cols-4">
          {MEASURED.map((m) => (
            <div key={m.label}>
              <dt className="sr-only">{m.label}</dt>
              <dd className="text-[clamp(1.9rem,4.5vw,3.5rem)] leading-none font-bold tracking-tight tabular-nums">{m.figure}</dd>
              <dd className="mt-3 max-w-[28ch] text-muted-foreground">{m.label}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-title">
        <SectionHead id="how-title" title="How an order is checked" link={{ to: "/desk", label: "Watch it on the desk" }} />
        <ol className="grid gap-8 md:grid-cols-5 md:gap-6">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-t-2 border-ink/80 pt-4">
              <p className="text-sm font-semibold text-lime-deep tabular-nums">Step {i + 1}</p>
              <h3 className="mt-1 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Build log */}
      <section aria-labelledby="log-title">
        <SectionHead id="log-title" title="Build log" />
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {LOG.map((l) => (
            <li key={l.title} className="flex flex-col gap-2 rounded-2xl border bg-white p-5">
              <p className="flex items-center justify-between text-sm text-muted-foreground">
                <time>{l.date}</time>
                <span className="rounded-md bg-secondary px-2 py-0.5 text-xs font-semibold text-foreground">{l.tag}</span>
              </p>
              <h3 className="text-lg leading-snug font-bold">{l.title}</h3>
              <p className="text-[15px] text-muted-foreground">{l.body}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* Built with */}
      <section aria-labelledby="built-title">
        <SectionHead id="built-title" title="Built with" />
        <ul className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-4">
          {BUILT_WITH.map((b) => (
            <li key={b.name} className="flex flex-col justify-center gap-1 bg-white px-5 py-6">
              <span className="text-lg font-bold tracking-tight">{b.name}</span>
              <span className="text-sm text-muted-foreground">{b.role}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-muted-foreground">
          Every amount is worked out by plain Python, never by an AI model.{" "}
          <a href={REPO} className="font-semibold text-foreground underline underline-offset-4">Read the source on GitHub</a>
        </p>
      </section>

      {/* Closing */}
      <section className="flex flex-col gap-6 rounded-2xl border bg-white p-6 sm:p-10 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-[clamp(1.6rem,3vw,2.1rem)] font-bold tracking-tight">Try it in thirty seconds</h2>
          <p className="mt-2 max-w-[52ch] text-muted-foreground">Open the desk and say an order, or type one. Every check lands in the ledger as you speak.</p>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <Link to="/desk" className="ink-key inline-flex h-12 items-center gap-2 rounded-xl px-6 font-semibold">Open the desk <ArrowRight className="size-4" /></Link>
          <button type="button" onClick={runSample} className="font-semibold underline decoration-lime-deep/40 decoration-2 underline-offset-4 hover:decoration-lime-deep">
            Run a sample order
          </button>
        </div>
      </section>
    </div>
  );
}
