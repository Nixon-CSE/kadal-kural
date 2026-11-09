import { Waves } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { cloneElement, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutlet } from "react-router";
import { Toaster } from "sonner";

import ClickSpark from "@/components/ClickSpark";
import { CommandMenu } from "@/components/desk/CommandMenu";
import { Header } from "@/components/desk/Header";
import { TooltipProvider } from "@/components/ui/tooltip";
import { NAV } from "@/lib/nav";
import type { LayoutOutlet } from "@/pages/layout-outlet";

import { useDeskContext } from "./desk-context";

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
      <ClickSpark sparkColor={["#84cc16", "#b5f23d", "#0f1d14"]} sparkSize={9} sparkRadius={18} sparkCount={9} duration={420}>
        <div className="stage-bg" aria-hidden />
        <div className="grain" aria-hidden />
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-3 focus:py-2 focus:text-lime">Skip to content</a>
        <Header desk={desk.desk} listening={desk.listening} onCommand={() => setPaletteOpen(true)} />

        <main id="main" className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 14, scale: 0.995 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.995 }}
              transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}
            >
              {outlet && cloneElement(outlet, { key: location.pathname })}
            </motion.div>
          </AnimatePresence>
        </main>

        <footer className="mt-10 border-t border-border/70 bg-white/50 backdrop-blur">
          <div className="mx-auto grid max-w-[1480px] gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="ink-key grid size-9 place-items-center rounded-xl"><Waves className="size-5 text-lime" /></span>
                <span className="text-lg font-extrabold">Kadal Kural <span lang="ta" className="tamil font-medium text-muted-foreground">கடல் குரல்</span></span>
              </div>
              <p className="mt-3 max-w-md text-sm text-muted-foreground">A voice credit desk for wholesale fish markets. Speech by Gnani Prisma and Timbre; every amount is computed by deterministic code, never by an AI model.</p>
            </div>
            <nav aria-label="Footer" className="grid content-start gap-2 text-sm">
              <p className="font-bold">Pages</p>
              {NAV.map((n) => <Link key={n.to} to={n.to} className="text-muted-foreground hover:text-foreground">{n.label}</Link>)}
            </nav>
            <div className="grid content-start gap-2 text-sm">
              <p className="font-bold">Shortcuts</p>
              <p className="text-muted-foreground">⌘K / Ctrl+K: commands</p>
              <p className="text-muted-foreground">Space: talk (on the desk)</p>
              <p className="text-muted-foreground">/: type an order (on the desk)</p>
            </div>
          </div>
        </footer>
      </ClickSpark>

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
      <Toaster position="bottom-right" richColors closeButton toastOptions={{ className: "!font-sans" }} />
    </TooltipProvider>
  );
}
