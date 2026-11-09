import { Keyboard, List, Mic, RotateCcw, Sparkles, Square } from "lucide-react";

import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut,
} from "@/components/ui/command";
import { TRY_ORDERS } from "@/lib/format";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listening: boolean;
  onToggleMic: () => void;
  onType: () => void;
  onReset: () => void;
  onTry: (text: string) => void;
}

export function CommandMenu({ open, onOpenChange, listening, onToggleMic, onType, onReset, onTry }: Props) {
  const run = (fn: () => void) => () => { onOpenChange(false); fn(); };
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Commands" description="Run a desk action or a sample order">
      <CommandInput placeholder="Type a command or search sample orders…" />
      <CommandList>
        <CommandEmpty>No command matches.</CommandEmpty>
        <CommandGroup heading="Desk">
          <CommandItem onSelect={run(onToggleMic)}>
            {listening ? <Square /> : <Mic />} {listening ? "Stop listening" : "Start listening"} <CommandShortcut>Space</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={run(onType)}>
            <Keyboard /> Type an order <CommandShortcut>/</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={run(() => document.getElementById("ledger")?.scrollIntoView({ behavior: "smooth" }))}>
            <List /> Go to the ledger
          </CommandItem>
          <CommandItem onSelect={run(onReset)}>
            <RotateCcw /> Reset balances
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Sample orders">
          {TRY_ORDERS.map((t) => (
            <CommandItem key={t.text} value={`${t.text} ${t.why}`} onSelect={run(() => onTry(t.text))}>
              <Sparkles />
              <span className="flex flex-col">
                <span lang="ta" className="tamil font-semibold">{t.text}</span>
                <span className="text-xs text-muted-foreground">{t.why}</span>
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
