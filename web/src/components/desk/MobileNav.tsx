import { Command, LayoutGrid } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { DeskState } from "@/lib/api";
import { isActive, NAV, TAB_BAR } from "@/lib/nav";
import { cn } from "@/lib/utils";

/**
 * Bottom tab bar for phones and tablets (below the lg breakpoint): thumb-reachable, always visible,
 * clear of the home indicator. The desk tab is the raised lime key, because talking is the main job.
 */
export function MobileNav({ desk, listening, onCommand }: { desk: DeskState | null; listening: boolean; onCommand: () => void }) {
  const { pathname } = useLocation();
  const [more, setMore] = useState(false);
  const tabs = TAB_BAR.map((to) => NAV.find((n) => n.to === to)!);
  const rest = NAV.filter((n) => !(TAB_BAR as readonly string[]).includes(n.to));
  const moreActive = rest.some((n) => isActive(n.to, pathname));

  return (
    <>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border/80 bg-background/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_-12px_rgba(15,29,20,0.18)] lg:hidden"
      >
        <ul className="mx-auto grid h-16 max-w-xl grid-cols-5 items-stretch px-1">
          {tabs.map((n) => {
            const active = isActive(n.to, pathname);
            const Icon = n.icon;
            if (n.to === "/desk") {
              return (
                <li key={n.to} className="grid place-items-center">
                  <NavLink to={n.to} aria-current={active ? "page" : undefined} className="flex flex-col items-center gap-0.5 text-[11px] font-bold">
                    <span className={cn("relative -mt-5 grid size-13 place-items-center rounded-2xl ring-4 ring-background", active || listening ? "lime-key" : "ink-key")}>
                      <Icon className={cn("size-6", !(active || listening) && "text-lime")} strokeWidth={2.4} />
                      {listening && <span className="absolute -top-0.5 -right-0.5 size-3 animate-pulse rounded-full bg-hold ring-2 ring-background" aria-label="listening" />}
                    </span>
                    <span className={active ? "text-ink" : "text-muted-foreground"}>{n.label}</span>
                  </NavLink>
                </li>
              );
            }
            return (
              <li key={n.to}>
                <NavLink to={n.to} aria-current={active ? "page" : undefined} className="flex h-full flex-col items-center justify-center gap-1 text-[11px] font-bold">
                  <span className={cn("grid h-7 w-12 place-items-center rounded-full transition-colors", active ? "bg-lime text-ink" : "text-muted-foreground")}>
                    <Icon className="size-5" />
                  </span>
                  <span className={active ? "text-ink" : "text-muted-foreground"}>{n.label}</span>
                </NavLink>
              </li>
            );
          })}
          <li>
            <button type="button" onClick={() => setMore(true)} aria-haspopup="dialog" className="flex h-full w-full flex-col items-center justify-center gap-1 text-[11px] font-bold">
              <span className={cn("grid h-7 w-12 place-items-center rounded-full transition-colors", moreActive ? "bg-lime text-ink" : "text-muted-foreground")}>
                <LayoutGrid className="size-5" />
              </span>
              <span className={moreActive ? "text-ink" : "text-muted-foreground"}>More</span>
            </button>
          </li>
        </ul>
      </nav>

      <Sheet open={more} onOpenChange={setMore}>
        <SheetContent side="bottom" className="rounded-t-3xl pb-[calc(env(safe-area-inset-bottom)+1rem)]">
          <SheetHeader>
            <SheetTitle className="text-xl">More pages</SheetTitle>
            <SheetDescription>
              Speech {desk?.gnani_live_key_configured ? "live" : "off"}, phone line {desk?.phone_channel_enabled ? "on" : "off"}, confidence gate{" "}
              {desk ? Math.round(desk.confidence_threshold * 100) : "–"}%.
            </SheetDescription>
          </SheetHeader>
          <ul className="grid gap-2 px-4 sm:grid-cols-3">
            {rest.map((n) => {
              const Icon = n.icon;
              const active = isActive(n.to, pathname);
              return (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    onClick={() => setMore(false)}
                    aria-current={active ? "page" : undefined}
                    className={cn("flex min-h-14 items-center gap-3 rounded-2xl border p-3 text-base font-bold", active ? "border-lime bg-lime-soft" : "bg-white")}
                  >
                    <span className="ink-key grid size-10 place-items-center rounded-xl"><Icon className="size-5 text-lime" /></span>
                    {n.label}
                  </NavLink>
                </li>
              );
            })}
          </ul>
          <div className="px-4">
            <button
              type="button"
              onClick={() => { setMore(false); onCommand(); }}
              className="flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-secondary text-sm font-bold"
            >
              <Command className="size-4" /> Search and commands
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
