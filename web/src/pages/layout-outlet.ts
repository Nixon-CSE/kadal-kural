import type { RefObject } from "react";

/** What the layout hands to every page through <Outlet context>. */
export interface LayoutOutlet {
  inputRef: RefObject<HTMLInputElement | null>;
}
