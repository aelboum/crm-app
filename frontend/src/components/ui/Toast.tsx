import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

/**
 * The design's toast (LeadStack CRM.dc.html, `hasToast`): a dark pill at the
 * bottom centre, dismissed after 2.6 s. Announced politely to screen readers.
 */
const ToastContext = createContext<(message: string) => void>(() => undefined);

export function useToast(): (message: string) => void {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const show = useCallback((next: string) => {
    setMessage(next);
  }, []);
  useEffect(() => {
    if (message === null) return undefined;
    const timer = window.setTimeout(() => {
      setMessage(null);
    }, 2600);
    return () => {
      window.clearTimeout(timer);
    };
  }, [message]);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {message ? <div className="toast">{message}</div> : null}
      </div>
    </ToastContext.Provider>
  );
}
