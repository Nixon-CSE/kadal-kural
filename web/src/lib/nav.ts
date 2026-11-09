import { ChartColumn, Gamepad2, House, Mic, Phone, ScrollText, Users, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Short marker shown next to the link, as a small badge. */
  badge?: string;
}

export const NAV: readonly NavItem[] = [
  { to: "/", label: "Home", icon: House },
  { to: "/play", label: "Play", icon: Gamepad2, badge: "New" },
  { to: "/desk", label: "Desk", icon: Mic },
  { to: "/ledger", label: "Ledger", icon: ScrollText },
  { to: "/buyers", label: "Buyers", icon: Users },
  { to: "/insights", label: "Insights", icon: ChartColumn },
  { to: "/phone", label: "Phone line", icon: Phone, badge: "New" },
];

/** Phones and tablets: four tabs in the bottom bar, the rest behind "More". */
export const TAB_BAR = ["/", "/play", "/desk", "/ledger"] as const;

export const isActive = (to: string, pathname: string) => (to === "/" ? pathname === "/" : pathname.startsWith(to));
