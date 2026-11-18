import { MailX } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";

/*
 * Unsubscribing from a campaign email's link (decisions P7-C, E-H1):
 * /app/u/<workspace>#<token>. The token stays in the fragment, which browsers
 * never send with the page request. Nothing changes until the person
 * presses the button, so an email scanner that opens links cannot
 * unsubscribe them. The same public route also serves mail clients'
 * one-click unsubscribe (`List-Unsubscribe-Post`). It answers alike for
 * known and unknown links, so the page cannot tell anyone whether an
 * address was on a list.
 */

const TOKEN = /^[0-9a-f]{32}$/;

type State = "ready" | "busy" | "done" | "invalid" | "failed";

export function UnsubscribePage({
  workspaceId,
  token,
}: {
  workspaceId: string;
  token: string;
}) {
  const t = useT();
  const [state, setState] = useState<State>(
    TOKEN.test(token) ? "ready" : "invalid",
  );

  const unsubscribe = () => {
    setState("busy");
    api
      .POST("/v1/public/unsubscribe/{workspace_id}/{token}", {
        params: { path: { workspace_id: workspaceId, token } },
      })
      .then(({ response }) => {
        setState(response.ok ? "done" : "failed");
      })
      .catch(() => {
        setState("failed");
      });
  };

  return (
    <main id="main" className="public-form-page">
      <div className="public-form-card">
        <MailX size={26} aria-hidden="true" className="visitor-booking-icon" />
        <h1 className="public-form-title">{t("unsubscribe.title")}</h1>
        {state === "done" ? (
          <p className="notice" role="status">
            {t("unsubscribe.done")}
          </p>
        ) : state === "invalid" ? (
          <p className="notice error" role="alert">
            {t("unsubscribe.invalid")}
          </p>
        ) : (
          <>
            <p>{t("unsubscribe.body")}</p>
            <Button
              variant="primary"
              isDisabled={state === "busy"}
              onPress={unsubscribe}
            >
              {t("unsubscribe.button")}
            </Button>
            {state === "failed" ? (
              <p className="notice error" role="alert">
                {t("unsubscribe.failed")}
              </p>
            ) : null}
          </>
        )}
      </div>
      <p className="public-form-foot">{t("publicBooking.footer")}</p>
    </main>
  );
}
