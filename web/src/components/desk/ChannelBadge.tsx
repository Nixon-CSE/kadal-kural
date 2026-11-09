import type { Channel } from "@/lib/api";
import { CHANNELS } from "@/lib/channel";
import { cn } from "@/lib/utils";

/** How an entry arrived. Phone entries are highlighted: they came from the Gnani agent, not the desk. */
export function ChannelBadge({ channel, compact = false, className }: { channel: Channel | null | undefined; compact?: boolean; className?: string }) {
  if (!channel) return null;
  const meta = CHANNELS[channel];
  const Icon = meta.icon;
  const phone = channel === "phone";
  return (
    <span
      title={meta.label}
      aria-label={compact ? meta.label : undefined}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full font-semibold whitespace-nowrap",
        compact ? "size-6 justify-center" : "px-2 py-0.5 text-xs",
        phone ? "bg-ink text-lime" : "bg-secondary text-muted-foreground",
        className,
      )}
    >
      <Icon className={compact ? "size-3.5" : "size-3"} aria-hidden />
      {!compact && meta.short}
    </span>
  );
}
