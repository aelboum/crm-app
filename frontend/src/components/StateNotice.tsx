import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { useT } from "../i18n/useT";
import { Button, buttonClass } from "./ui/Button";

export function Loading() {
  const t = useT();
  return (
    <p role="status" className="state state-loading">
      <span className="spinner" aria-hidden="true" />
      {t("state.loading")}
    </p>
  );
}

/** Nothing to show yet; optionally with one way forward. */
export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="state state-empty">
      <p className="state-title">{title}</p>
      {body ? <p className="muted">{body}</p> : null}
      {action}
    </div>
  );
}

/**
 * A feature that does not exist yet. Says so plainly: no control on the page
 * pretends to work (CLAUDE.md §6).
 */
export function Unavailable({ title, body }: { title: string; body: string }) {
  const t = useT();
  return (
    <div className="state state-unavailable">
      <p className="state-kicker">{t("unavailable.kicker")}</p>
      <p className="state-title">{title}</p>
      <p className="muted">{body}</p>
    </div>
  );
}

/** The failure state of a read. 401, 403 and 404 each get their own message; nothing else is shown. */
/** `notFound` replaces the workspace-level 404 message when the missing thing is a single record. */
export function LoadError({ error, onRetry, notFound }: { error: unknown; onRetry: () => void; notFound?: string }) {
  const t = useT();
  const status = error instanceof ApiError ? error.status : undefined;
  if (status === 401) {
    return (
      <div className="notice error" role="alert">
        <p>{t("state.signedOut")}</p>
        <a className={buttonClass("primary")} href="/auth/login">
          {t("home.signIn")}
        </a>
      </div>
    );
  }
  const message =
    status === 404 ? (notFound ?? t("state.notFound")) : status === 403 ? t("state.denied") : t("state.error");
  return (
    <div className="notice error row" role="alert">
      <p>{message}</p>
      {status === 404 || status === 403 ? null : (
        <Button onPress={onRetry}>{t("state.retry")}</Button>
      )}
    </div>
  );
}
