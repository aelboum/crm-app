import { useContactConsent } from "../api/forms";
import { LoadError } from "../components/StateNotice";
import { useT } from "../i18n/useT";
import { When } from "./parts";

/*
 * A contact's consent records (decision P7-A 7, 10): the channel, how and
 * when it was given, the form, and the exact wording the person agreed to.
 * Read-only: records are evidence and never change. Single opt-in from a
 * web form is unverified, and the section says so rather than implying
 * more.
 */

export function ConsentSection({ workspaceId, contactId }: { workspaceId: string; contactId: string }) {
  const t = useT();
  const consent = useContactConsent(workspaceId, contactId);
  const items = consent.data?.items ?? [];
  return (
    <section className="drawer-section" aria-labelledby="contact-consent-title">
      <h2 id="contact-consent-title" className="drawer-section-title">
        {t("consent.title")}
      </h2>
      {consent.isError ? <LoadError error={consent.error} onRetry={() => void consent.refetch()} /> : null}
      {items.length ? (
        <ul className="consent-list">
          {items.map((record) => (
            <li key={record.id} className="consent-item">
              <span className="consent-head">
                {t("consent.granted")} · <When value={record.recorded_at} />
              </span>
              <span className="consent-source">
                {record.form_name ? t("consent.viaForm", { name: record.form_name }) : t("consent.viaDeletedForm")}
              </span>
              <q className="consent-wording">{record.wording}</q>
            </li>
          ))}
        </ul>
      ) : consent.isPending ? null : (
        <p className="muted">{t("consent.none")}</p>
      )}
      {items.length ? <p className="form-hint">{t("consent.unverified")}</p> : null}
    </section>
  );
}
