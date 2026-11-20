import { useContactBrief } from "../api/contactBrief";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * The contact brief (decision P9-B): on request, a short summary of where
 * the contact stands and up to three suggested next steps. It is a
 * suggestion to check, never a fact, and is gone when the drawer closes.
 * Only the allowlisted facts are sent (stage, source, tags, kinds of recent
 * activity, deal stages, counts); never names, contact details or notes.
 */

const STATE_MESSAGE: Record<string, MessageId> = {
  unavailable: "brief.unavailable",
  quota_reached: "brief.quotaReached",
  busy: "brief.busy",
  failed: "brief.failed",
};

export function BriefSection({
  workspaceId,
  contactId,
}: {
  workspaceId: string;
  contactId: string;
}) {
  const t = useT();
  const brief = useContactBrief(workspaceId, contactId);
  const answer = brief.data;
  const problem: MessageId | null = brief.isError
    ? "brief.failed"
    : answer && answer.state !== "ready"
      ? (STATE_MESSAGE[answer.state] ?? "brief.failed")
      : null;
  return (
    <section className="drawer-section" aria-labelledby="contact-brief-title">
      <h2 id="contact-brief-title" className="drawer-section-title">
        {t("brief.title")}
      </h2>
      <p className="form-hint">{t("brief.what")}</p>
      <Button
        size="sm"
        isDisabled={brief.isPending}
        onPress={() => {
          brief.mutate();
        }}
      >
        {t(
          brief.isPending
            ? "brief.writing"
            : answer?.state === "ready"
              ? "brief.again"
              : "brief.write",
        )}
      </Button>
      {answer?.state === "ready" && answer.text ? (
        <div className="brief-result" aria-live="polite">
          <p className="brief-label">{t("brief.suggestion")}</p>
          <p className="brief-text">{answer.text}</p>
        </div>
      ) : null}
      {problem ? (
        <p className="notice info" role="status">
          {t(problem)}
        </p>
      ) : null}
    </section>
  );
}
