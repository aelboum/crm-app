import { BellRing } from "lucide-react";
import { useState } from "react";
import { useIntl } from "react-intl";

import { useReminders, useSendReminder } from "../api/appointments";
import { ApiError } from "../api/client";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * The appointment drawer's Reminders section (decision P5-D): the
 * workspace's setting, when this appointment's automatic reminder is due,
 * the latest reminders and why any were skipped, and "Send reminder" for
 * members who may update appointments. A reminder is an email queued for
 * the contact; it reaches them only once email sending is switched on.
 */

const LEAD_LABEL: Record<number, MessageId> = {
  60: "reminders.lead.60",
  120: "reminders.lead.120",
  1440: "reminders.lead.1440",
  2880: "reminders.lead.2880",
};

function refusal(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "reminder_too_soon") return "reminders.error.tooSoon";
    if (error.code === "reminder_unavailable")
      return "reminders.error.unavailable";
    if (error.status === 403) return "reminders.error.forbidden";
  }
  return "reminders.error.generic";
}

export function AppointmentReminders({
  workspaceId,
  id,
  canSend,
}: {
  workspaceId: string;
  id: string;
  canSend: boolean;
}) {
  const t = useT();
  const intl = useIntl();
  const toast = useToast();
  const status = useReminders(workspaceId, id);
  const send = useSendReminder(workspaceId);
  const [problem, setProblem] = useState<MessageId | null>(null);
  const when = (iso: string) =>
    intl.formatDate(new Date(iso), {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <section
      className="drawer-section"
      aria-labelledby="appointment-reminders-title"
    >
      <h2 id="appointment-reminders-title" className="drawer-section-title">
        {t("reminders.title")}
      </h2>
      {status.isPending ? (
        <Loading />
      ) : status.isError ? (
        <LoadError error={status.error} onRetry={() => void status.refetch()} />
      ) : (
        <>
          <p className="muted">
            {status.data.lead_minutes === null
              ? t("reminders.off")
              : t("reminders.setting", {
                  lead: t(
                    LEAD_LABEL[status.data.lead_minutes] ??
                      "reminders.lead.custom",
                  ),
                })}
            {status.data.next_at
              ? ` ${t("reminders.next", { when: when(status.data.next_at) })}`
              : null}
          </p>
          {status.data.recipient_problem ? (
            <p className="muted">
              {t(
                `reminders.problem.${status.data.recipient_problem}` as MessageId,
              )}
            </p>
          ) : null}
          {status.data.items.length ? (
            <ul className="reminder-list" aria-label={t("reminders.history")}>
              {status.data.items.map((item) => (
                <li key={item.id} className="reminder-item">
                  <span>{when(item.created_at)}</span>
                  <span className="muted">
                    {t(
                      item.kind === "manual"
                        ? "reminders.kind.manual"
                        : "reminders.kind.automatic",
                    )}
                  </span>
                  {item.outcome === "queued" ? (
                    <Badge tone="success">{t("reminders.queued")}</Badge>
                  ) : (
                    <Badge tone="neutral">
                      {t(
                        `reminders.skipped.${item.skip_reason ?? "no_contact"}` as MessageId,
                      )}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
          {canSend ? (
            <div className="drawer-actions">
              <Button
                size="sm"
                isDisabled={
                  send.isPending || status.data.recipient_problem !== null
                }
                onPress={() => {
                  setProblem(null);
                  send.mutate(
                    { id },
                    {
                      onSuccess: () => {
                        toast(t("reminders.sent"));
                      },
                      onError: (error) => {
                        setProblem(refusal(error));
                      },
                    },
                  );
                }}
              >
                <BellRing size={13} aria-hidden="true" />
                {t("reminders.send")}
              </Button>
            </div>
          ) : null}
          {problem ? (
            <p className="notice error" role="alert">
              {t(problem)}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
