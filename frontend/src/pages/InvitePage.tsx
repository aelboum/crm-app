import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "../api/client";
import {
  forgetInvitation,
  type PendingInvitation,
  pendingInvitation,
  rememberInvitation,
  useAcceptInvitation,
} from "../api/invitations";
import { useMe } from "../api/queries";
import { Button, buttonClass } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import { isWorkspaceId } from "./HomePage";
import { SignInScreen } from "./SignInScreen";

/*
 * Accepting an invitation (decisions Q4, Q5; SaaS-OS ADR-0046). The link is
 * /app/invite/<workspace>#<token>: the token rides in the fragment, which
 * browsers never send to a server. On arrival it is kept in this tab's
 * sessionStorage (so it survives the sign-in round trip, which always lands
 * on /app) and removed from the address bar. SaaS-OS accepts only for a
 * signed-in person whose verified email is the invited one, once; every
 * refusal is the same 404, so the page says only that it cannot be used.
 */

/** Reads the token from the fragment once, then clears the fragment. */
function takeFromLink(workspaceId: string): PendingInvitation | null {
  const token = globalThis.location.hash.replace(/^#/, "");
  if (token) {
    globalThis.history.replaceState(null, "", globalThis.location.pathname + globalThis.location.search);
    const pending = { workspaceId, token };
    rememberInvitation(pending);
    return pending;
  }
  const kept = pendingInvitation();
  return kept?.workspaceId === workspaceId ? kept : null;
}

export function InvitePage({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const me = useMe();
  const accept = useAcceptInvitation();
  const [pending] = useState(() => (isWorkspaceId(workspaceId) ? takeFromLink(workspaceId) : null));

  if (!me.data) {
    return (
      <SignInScreen
        me={me}
        title={t("accept.signInTitle")}
        body={pending ? t("accept.signedOut") : undefined}
        notice={pending ? undefined : <p className="notice error signin-notice">{t("accept.missing")}</p>}
      />
    );
  }

  let content;
  if (!pending) {
    content = <p className="notice error">{t("accept.missing")}</p>;
  } else if (accept.isSuccess) {
    content = (
      <>
        <p className="notice info" role="status">
          {t("accept.done")}
        </p>
        <div className="row">
          <Link className={buttonClass("primary")} to="/">
            {t("accept.home")}
          </Link>
        </div>
      </>
    );
  } else {
    const refused = accept.isError;
    content = (
      <>
        <p className="muted">{t("accept.body")}</p>
        {refused ? (
          <p className="notice error" role="alert">
            {accept.error instanceof ApiError && accept.error.status === 404
              ? t("accept.invalid")
              : t("state.error")}
          </p>
        ) : null}
        <div className="row">
          <Button
            variant="primary"
            isDisabled={accept.isPending}
            onPress={() => {
              accept.mutate(pending, {
                onSettled: () => {
                  // Used or refused, the token is no longer needed in this tab.
                  forgetInvitation();
                },
              });
            }}
          >
            {t("accept.submit")}
          </Button>
        </div>
      </>
    );
  }

  return (
    <section className="card" aria-labelledby="accept-heading">
      <h1 id="accept-heading">{t("accept.title")}</h1>
      {content}
    </section>
  );
}
