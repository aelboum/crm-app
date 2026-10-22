import { Button } from "react-aria-components";

import { ApiError } from "../api/client";
import { useT } from "../i18n/useT";

export function Loading() {
  const t = useT();
  return (
    <p role="status" className="muted">
      {t("state.loading")}
    </p>
  );
}

/** The failure state of a read. 401, 403 and 404 each get their own message; nothing else is shown. */
export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useT();
  const status = error instanceof ApiError ? error.status : undefined;
  if (status === 401) {
    return (
      <div className="notice error" role="alert">
        <p>{t("state.signedOut")}</p>
        <a className="button primary" href="/auth/login">
          {t("home.signIn")}
        </a>
      </div>
    );
  }
  const message =
    status === 404 ? t("state.notFound") : status === 403 ? t("state.denied") : t("state.error");
  return (
    <div className="notice error row" role="alert">
      <p>{message}</p>
      {status === 404 || status === 403 ? null : (
        <Button className="button" onPress={onRetry}>
          {t("state.retry")}
        </Button>
      )}
    </div>
  );
}
