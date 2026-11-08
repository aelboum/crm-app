import { ArrowUpRight } from "lucide-react";

import { useContact } from "../api/records";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import { useMemberNames } from "../members/names";
import { AppointmentsSection } from "./AppointmentsSection";
import { DealsSection } from "./DealsSection";
import { Avatar, FieldRow, initials, ownerLabel, StagePill } from "./parts";
import { TagPills } from "./TagEditor";

/*
 * The Inbox's contact panel (ScreenConversations.dc.html, "Contact
 * details"; decision P6-CX): who the conversation is with, their deals,
 * upcoming appointments and tags, next to the thread. It reads the same
 * routes as the contact drawer, so it shows only what the member may read,
 * and links to the full record. The design's lead score is not shown: the
 * product has no score.
 */
export function ContactContext({
  workspaceId,
  contactId,
  meId,
  onOpenContact,
  onOpenDeal,
  onOpenAppointment,
}: {
  workspaceId: string;
  contactId: string;
  meId: string | undefined;
  onOpenContact: (id: string) => void;
  onOpenDeal: (id: string) => void;
  onOpenAppointment: (id: string) => void;
}) {
  const t = useT();
  const names = useMemberNames();
  const contact = useContact(workspaceId, contactId);
  if (contact.isPending) return <Loading />;
  if (contact.isError) {
    return (
      <LoadError
        error={contact.error}
        onRetry={() => void contact.refetch()}
        notFound={t("contact.notFound")}
      />
    );
  }
  const record = contact.data;
  const name = [record.first_name, record.last_name].filter(Boolean).join(" ");
  const headline =
    [record.job_title, record.company?.name]
      .filter(Boolean)
      .join(t("records.at")) ||
    record.city ||
    "";
  return (
    <div className="inbox-context-body">
      <div className="inbox-context-identity">
        <Avatar
          id={record.id}
          label={initials(record.first_name, record.last_name)}
          large
        />
        <p className="drawer-name">{name}</p>
        {headline ? <p className="drawer-headline">{headline}</p> : null}
        <StagePill stage={record.lifecycle_stage} />
        <Button
          size="sm"
          onPress={() => {
            onOpenContact(record.id);
          }}
        >
          {t("inbox.context.fullRecord")}
          <ArrowUpRight size={13} aria-hidden="true" />
        </Button>
      </div>
      {record.archived_at ? (
        <p className="notice info">{t("records.archivedNote")}</p>
      ) : null}
      <dl className="field-list">
        <FieldRow label={t("contact.field.email")}>{record.email}</FieldRow>
        <FieldRow label={t("contact.field.phone")}>{record.phone}</FieldRow>
        <FieldRow label={t("contact.field.city")}>{record.city}</FieldRow>
        <FieldRow label={t("records.field.owner")}>
          {ownerLabel(t, record.owner_user_id, meId, names)}
        </FieldRow>
      </dl>
      <DealsSection
        workspaceId={workspaceId}
        link={{
          kind: "contact",
          contact: { id: record.id, name },
          company: record.company ?? null,
        }}
        onOpen={onOpenDeal}
      />
      <AppointmentsSection
        workspaceId={workspaceId}
        contact={{ id: record.id, name }}
        onOpen={onOpenAppointment}
      />
      <section aria-labelledby={`context-tags-${record.id}`}>
        <h3 className="drawer-section-title" id={`context-tags-${record.id}`}>
          {t("inbox.context.tags")}
        </h3>
        {record.tags.length ? (
          <TagPills tags={record.tags} />
        ) : (
          <p className="muted">{t("inbox.context.noTags")}</p>
        )}
      </section>
    </div>
  );
}
