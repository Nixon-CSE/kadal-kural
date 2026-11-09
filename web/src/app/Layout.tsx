import { Waves } from "lucide-react";
import { motion } from "motion/react";
import { cloneElement, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutlet } from "react-router";
import { Toaster } from "sonner";

import { CommandMenu } from "@/components/desk/CommandMenu";
import { Header } from "@/components/desk/Header";
import { MobileNav } from "@/components/desk/MobileNav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { NAV } from "@/lib/nav";
import type { LayoutOutlet } from "@/pages/layout-outlet";
import { PAGE_LOADERS } from "@/pages/loaders";

import { useDeskContext } from "./desk-context";

const REPO = "https://github.com/Nixon-CSE/kadal-kural";
const FOOTER: { title: string; links: ({ label: string; to: string } | { label: string; href: string })[] }[] = [
  { title: "Product", links: [{ label: "Desk", to: "/desk" }, { label: "Ledger", to: "/ledger" }, { label: "Buyers", to: "/buyers" }, { label: "Phone line", to: "/phone" }] },
  { title: "Learn", links: [{ label: "Harbour Shift", to: "/play" }, { label: "Insights", to: "/insights" }, { label: "Benchmark report", href: `${REPO}/blob/main/benchmark/REPORT.md` }] },
  { title: "Project", links: [{ label: "Source on GitHub", href: REPO }, { label: "Phone setup guide", href: `${REPO}/blob/main/docs/phone_channel.md` }, { label: "README", href: `${REPO}#readme` }] },
];

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(t.tagName));

export function Layout() {
  const desk = useDeskContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const outletContext: LayoutOutlet = { inputRef };
  const outlet = useOutlet(outletContext);
  const onDesk = location.pathname.startsWith("/desk");

  useEffect(() => { window.scrollTo({ top: 0 }); }, [location.pathname]);

  // Warm every page's code while the browser is idle, so navigation never waits for a download.
  useEffect(() => {
    const warm = () => { for (const load of PAGE_LOADERS) void load(); };
    const ric = (window as unknown as { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
    const id = ric ? ric(warm) : window.setTimeout(warm, 1500);
    return () => { if (!ric) window.clearTimeout(id); };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPaletteOpen((o) => !o); return; }
      if (paletteOpen || isTyping(e.target) || e.repeat || !onDesk) return;
      if (e.code === "Space") { e.preventDefault(); desk.toggleMic(); }
      else if (e.key === "/") { e.preventDefault(); inputRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desk, paletteOpen, onDesk]);

  const goDeskThen = (fn: () => void) => { if (!onDesk) navigate("/desk"); setTimeout(fn, onDesk ? 0 : 350); };

  return (
    <TooltipProvider delayDuration={200}>
      <>
        <div className="stage-bg" aria-hidden />
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-3 focus:py-2 focus:text-lime">Skip to content</a>
        <Header desk={desk.desk} listening={desk.listening} onCommand={() => setPaletteOpen(true)} />

        <main id="main" className="mx-auto max-w-[1480px] py-6 pr-[max(1rem,env(safe-area-inset-right))] pl-[max(1rem,env(safe-area-inset-left))] sm:px-6">
          {/* Instant swap, short fade-in: no waiting for the old page to leave. */}
          <motion.div key={location.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.16, ease: "easeOut" }}>
            {outlet && cloneElement(outlet, { key: location.pathname })}
          </motion.div>
        </main>

        <footer className="mt-16 border-t border-border/70 bg-white pb-[calc(env(safe-area-inset-bottom)+5rem)] lg:pb-0">
          <div className="mx-auto grid max-w-[1480px] gap-10 px-4 pt-12 pb-8 sm:px-6 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="ink-key grid size-9 place-items-center rounded-xl"><Waves className="size-5 text-lime" /></span>
                <span className="text-lg font-bold">Kadal Kural <span lang="ta" className="tamil font-medium text-muted-foreground">கடல் குரல்</span></span>
              </div>
              <p className="mt-3 max-w-sm text-sm text-muted-foreground">A voice credit desk for the wholesale fish market at Kasimedu harbour, Chennai. Speech by Gnani Prisma and Timbre.</p>
            </div>
            {FOOTER.map((col) => (
              <nav key={col.title} aria-label={col.title} className="grid content-start gap-2.5 text-sm">
                <p className="font-semibold">{col.title}</p>
                {col.links.map((l) =>
                  "href" in l ? (
                    <a key={l.label} href={l.href} className="text-muted-foreground hover:text-foreground pointer-coarse:py-1">{l.label}</a>
                  ) : (
                    <Link key={l.label} to={l.to} className="text-muted-foreground hover:text-foreground pointer-coarse:py-1">
                      {l.label}
                      {NAV.find((n) => n.to === l.to)?.badge && <span className="ml-1.5 rounded bg-lime-soft px-1 py-px text-[10px] font-bold text-lime-deep">New</span>}
                    </Link>
                  ),
                )}
              </nav>
            ))}
          </div>
          <div className="mx-auto flex max-w-[1480px] flex-wrap justify-between gap-2 border-t border-border/70 px-4 py-5 text-sm text-muted-foreground sm:px-6">
            <p>© 2026 Kadal Kural. Every amount is computed by plain code, never by an AI model.</p>
            <p className="pointer-coarse:hidden">⌘K for commands · Space to talk on the desk</p>
          </div>
        </footer>
      </>

      <MobileNav desk={desk.desk} listening={desk.listening} onCommand={() => setPaletteOpen(true)} />
      <CommandMenu
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        listening={desk.listening}
        onToggleMic={() => goDeskThen(desk.toggleMic)}
        onType={() => goDeskThen(() => inputRef.current?.focus())}
        onReset={() => void desk.reset()}
        onTry={(t) => goDeskThen(() => void desk.sendTranscript(t))}
        onNavigate={(to) => navigate(to)}
      />
      <Toaster position="bottom-right" mobileOffset={{ bottom: "calc(env(safe-area-inset-bottom) + 84px)" }} richColors closeButton toastOptions={{ className: "!font-sans" }} />
    </TooltipProvider>
  );
}
