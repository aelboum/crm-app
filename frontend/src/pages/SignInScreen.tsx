import { ArrowRight } from "lucide-react";
import { type MouseEvent, type ReactNode, useEffect, useState } from "react";

import type { useMe } from "../api/queries";
import { clearSignedOut, LOGIN_PATH, shouldRedirectToSignIn, signInNavigation } from "../api/signInRedirect";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";

/*
 * The signed-out screen, after the account step of the design's
 * LeadStack Signup.dc.html (L23-50, L118-125): a dark brand column beside a
 * centred panel. Only its sign-in parts are used. The step rail, the
 * Google/Microsoft buttons and the name and email fields belong to
 * self-service signup, which decision P2-C excludes; credentials are never
 * entered here (SaaS-OS ADR-0026 was rejected), so the one action starts the
 * existing OIDC flow at /auth/login and ZITADEL's own pages take over.
 * With `redirect` (the start page, decision S-2) the screen leaves for the
 * sign-in page by itself when there is no session, unless
 * shouldRedirectToSignIn() says otherwise.
 */

const LOGIN = LOGIN_PATH;

function isPlainClick(event: MouseEvent) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

/** The sign-in link; once followed it says so and ignores further clicks. */
function SignInLink() {
  const t = useT();
  const [leaving, setLeaving] = useState(false);
  // Coming back from the provider with the browser's Back button can restore
  // this page from the back/forward cache, still marked as leaving.
  useEffect(() => {
    const reset = (event: PageTransitionEvent) => {
      if (event.persisted) setLeaving(false);
    };
    window.addEventListener("pageshow", reset);
    return () => {
      window.removeEventListener("pageshow", reset);
    };
  }, []);
  return (
    <>
      <a
        className="signin-button"
        href={LOGIN}
        aria-disabled={leaving || undefined}
        onClick={(event) => {
          if (leaving) {
            event.preventDefault();
            return;
          }
          clearSignedOut();
          if (isPlainClick(event)) setLeaving(true);
        }}
      >
        {leaving ? <span className="spinner signin-spinner" aria-hidden="true" /> : null}
        {t("home.signIn")}
        {leaving ? null : <ArrowRight size={15} aria-hidden="true" />}
      </a>
      <p className="visually-hidden" role="status">
        {leaving ? t("signin.leaving") : ""}
      </p>
    </>
  );
}

export function SignInScreen({
  me,
  title,
  body,
  notice,
  redirect = false,
}: {
  /** The session check; while it runs or fails the screen says so. */
  me: ReturnType<typeof useMe>;
  title: string;
  body?: string | undefined;
  /** Shown above the sign-in action, e.g. why a link cannot be used. */
  notice?: ReactNode;
  /** Leave for the sign-in page by itself when there is no session. */
  redirect?: boolean;
}) {
  const t = useT();
  const signedOut = me.isSuccess && me.data === null;
  useEffect(() => {
    if (redirect && signedOut && shouldRedirectToSignIn()) signInNavigation.leave(LOGIN);
  }, [redirect, signedOut]);
  let content;
  if (me.isPending) {
    content = (
      <p role="status" className="state-loading">
        <span className="spinner" aria-hidden="true" />
        {t("signin.checking")}
      </p>
    );
  } else {
    content = (
      <>
        {me.isError ? (
          <div className="notice error signin-notice" role="alert">
            <p>{t("signin.checkFailed")}</p>
            <Button size="sm" onPress={() => void me.refetch()}>
              {t("state.retry")}
            </Button>
          </div>
        ) : null}
        {notice}
        <SignInLink />
        <p className="signin-help">{t("signin.provider")}</p>
      </>
    );
  }
  return (
    <div className="signin">
      <aside className="signin-aside" aria-label={t("app.brand")}>
        <div className="signin-brand">
          <span className="brand-tile signin-tile" data-mark="LS" aria-hidden="true" />
          <span className="signin-brand-name">{t("app.brand")}</span>
        </div>
        <p className="signin-tagline">{t("signin.tagline")}</p>
        <span className="signin-aside-fill" />
        <p className="signin-aside-note">{t("signin.asideNote")}</p>
      </aside>
      <div className="signin-panel">
        <div className="signin-body">
          <div className="signin-head">
            <p className="signin-kicker">{t("app.name")}</p>
            <h1>{title}</h1>
            {body ? <p className="signin-sub">{body}</p> : null}
          </div>
          {content}
          <p className="signin-footer">{t("signin.noAccount")}</p>
        </div>
      </div>
    </div>
  );
}
