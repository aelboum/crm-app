import { useEffect, useState } from "react";

/** The search box's delay before a query is sent (ScreenContacts.dc.html: debounced search). */
export const SEARCH_DELAY_MS = 250;

/** `value`, once it has stopped changing for `SEARCH_DELAY_MS`. */
export function useDebounced(value: string): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(value);
    }, SEARCH_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value]);
  return debounced;
}
