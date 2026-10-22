import { useCallback, useEffect, useState } from "react";

/** The design's breakpoints: overlay sidebar below 760 px, collapsed below 1024 px. */
export const NARROW = "(max-width: 759px)";
export const MEDIUM = "(max-width: 1023px)";
const STORAGE_KEY = "crm-app.sidebar-collapsed";

function matches(query: string): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

function useMedia(query: string): boolean {
  const [value, setValue] = useState(() => matches(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const list = window.matchMedia(query);
    const update = () => {
      setValue(list.matches);
    };
    list.addEventListener("change", update);
    return () => {
      list.removeEventListener("change", update);
    };
  }, [query]);
  return value;
}

// A per-viewer convenience only; storage can be missing or blocked.
function readPreference(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writePreference(collapsed: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // Not remembered; the toggle still works for this page.
  }
}

export interface SidebarState {
  /** Below 760 px the sidebar is an overlay opened from the header. */
  narrow: boolean;
  /** Icon-only (60 px) rather than 232 px. */
  collapsed: boolean;
  overlayOpen: boolean;
  toggleCollapsed: () => void;
  setOverlayOpen: (open: boolean) => void;
}

export function useSidebar(): SidebarState {
  const narrow = useMedia(NARROW);
  const medium = useMedia(MEDIUM);
  // Wide screens remember the choice; between 760 and 1023 px the sidebar
  // starts collapsed and can be expanded for this page only.
  const [preference, setPreference] = useState(readPreference);
  const [mediumExpanded, setMediumExpanded] = useState(false);
  const [overlayOpen, setOverlayOpen] = useState(false);
  const toggleCollapsed = useCallback(() => {
    if (medium) {
      setMediumExpanded((current) => !current);
      return;
    }
    setPreference((current) => {
      writePreference(!current);
      return !current;
    });
  }, [medium]);
  return {
    narrow,
    collapsed: narrow ? false : medium ? !mediumExpanded : preference,
    // The overlay exists only on narrow screens; widening the window closes it.
    overlayOpen: narrow && overlayOpen,
    toggleCollapsed,
    setOverlayOpen,
  };
}
