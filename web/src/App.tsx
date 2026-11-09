import { useEffect, useRef, useState } from "react";
import { Toaster } from "sonner";

import { CommandMenu } from "@/components/desk/CommandMenu";
import { CreditGauges } from "@/components/desk/CreditGauges";
import { Header } from "@/components/desk/Header";
import { Ledger } from "@/components/desk/Ledger";
import { LiveTurn } from "@/components/desk/LiveTurn";
import { Pipeline } from "@/components/desk/Pipeline";
import { Stats } from "@/components/desk/Stats";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useDesk } from "@/hooks/useDesk";

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(t.tagName));

export default function App() {
  const desk = useDesk();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const gate = desk.desk?.confidence_threshold ?? 0.82;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPaletteOpen((o) => !o); return; }
      if (paletteOpen || isTyping(e.target) || e.repeat) return;
      if (e.code === "Space") { e.preventDefault(); desk.toggleMic(); }
      else if (e.key === "/") { e.preventDefault(); inputRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desk, paletteOpen]);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="stage-bg" aria-hidden />
      <a href="#ledger" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-3 focus:py-2 focus:text-lime">
        Skip to ledger
      </a>
      <Header desk={desk.desk} onCommand={() => setPaletteOpen(true)} onReset={() => void desk.reset()} />

      <main className="mx-auto grid max-w-[1480px] grid-cols-[minmax(0,1fr)] gap-5 px-4 py-6 sm:px-6">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <LiveTurn desk={desk} inputRef={inputRef} />
          <aside className="grid content-start gap-5">
            <CreditGauges buyers={desk.desk?.buyers ?? []} touched={desk.touched} />
            <Pipeline stage={desk.stage} gate={gate} />
          </aside>
        </div>
        <Stats events={desk.desk?.events ?? []} history={desk.history} />
        <Ledger events={desk.desk?.events ?? []} gate={gate} newIds={desk.newIds} />
        <footer className="pb-6 text-center text-xs text-muted-foreground">
          Kadal Kural · speech by Gnani Prisma and Timbre · every amount is computed by deterministic code, never by an AI model
        </footer>
      </main>

      <CommandMenu
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        listening={desk.listening}
        onToggleMic={desk.toggleMic}
        onType={() => setTimeout(() => inputRef.current?.focus(), 50)}
        onReset={() => void desk.reset()}
        onTry={(t) => void desk.sendTranscript(t)}
      />
      <Toaster position="bottom-right" richColors closeButton toastOptions={{ className: "!font-sans" }} />
    </TooltipProvider>
  );
}
