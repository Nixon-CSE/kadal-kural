import { FileAudio, Keyboard, Mic, Phone, type LucideIcon } from "lucide-react";

import type { Channel } from "@/lib/api";

export const CHANNELS: Record<Channel, { label: string; short: string; icon: LucideIcon }> = {
  voice: { label: "Spoken at the desk", short: "Desk", icon: Mic },
  typed: { label: "Typed at the desk", short: "Typed", icon: Keyboard },
  phone: { label: "Phone call", short: "Phone", icon: Phone },
  file: { label: "Audio file", short: "File", icon: FileAudio },
};

export const CHANNEL_ORDER: Channel[] = ["voice", "phone", "typed", "file"];

/** Local wall-clock time of an ISO timestamp, e.g. 11:50:26, with the date when it is not today. */
export function callTime(iso: string | null | undefined, fallback = ""): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const today = new Date().toDateString() === d.toDateString();
  return today ? time : `${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${time}`;
}
