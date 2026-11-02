import { MailCheck } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";

/*
 * Confirming consent from an email link (decision P7-V):
 * /app/c/<workspace>#<token>. The token stays in the fragment, which browsers
 * never send, and goes to the public route in a request body. Nothing is
 * confirmed until the person presses the button, so an email scanner that
 * opens links cannot confirm for them.
 */

type State = "ready" | "busy" | "confirmed" | "gone" | "failed";

export function ConsentConfirmPage({
  workspaceId,
  token,
}: {
  workspaceId: string;
  token: string;
}) {
  const t = useT();
  const [state, setState] = useState<State>(token ? "ready" : "gone");

  const confirm = () => {
    setState("busy");
    api
      .POST("/v1/public/consent/{workspace_id}/confirm", {
        params: { path: { workspace_id: workspaceId } },
        body: { token },
      })
      .then(({ response }) => {
        setState(
          response.ok
            ? "confirmed"
            : response.status === 404
              ? "gone"
              : "failed",
        );
      })
      .catch(() => {
        setState("failed");
      });
  };

  return (
    <main id="main" className="public-form-page">
      <div className="public-form-card">
        <MailCheck
          size={26}
          aria-hidden="true"
          className="visitor-booking-icon"
        />
        <h1 className="public-form-title">{t("consentConfirm.title")}</h1>
        {state === "confirmed" ? (
          <p className="notice" role="status">
            {t("consentConfirm.done")}
          </p>
        ) : state === "gone" ? (
          <p className="notice error" role="alert">
            {t("consentConfirm.gone")}
          </p>
        ) : (
          <>
            <p>{t("consentConfirm.body")}</p>
            <Button
              variant="primary"
              isDisabled={state === "busy"}
              onPress={confirm}
            >
              {t("consentConfirm.button")}
            </Button>
            {state === "failed" ? (
              <p className="notice error" role="alert">
                {t("consentConfirm.failed")}
              </p>
            ) : null}
          </>
        )}
      </div>
      <p className="public-form-foot">{t("publicBooking.footer")}</p>
    </main>
  );
}
