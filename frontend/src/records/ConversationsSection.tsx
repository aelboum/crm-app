import { Button as AriaButton } from "react-aria-components";

import {
  CONTACT_CONVERSATIONS,
  useContactConversations,
} from "../api/conversations";
import { LoadError } from "../components/StateNotice";
import { useT } from "../i18n/useT";
import { When } from "./parts";

/*
 * A contact's conversations in its drawer: the most recent first, open or
 * closed, each opening in the Inbox. Every role reads conversations
 * (`read_conversations`, decision P6-C); calls are voice, which is parked.
 */

export function ConversationsSection({
  workspaceId,
  contactId,
  onOpen,
}: {
  workspaceId: string;
  contactId: string;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const list = useContactConversations(workspaceId, contactId);
  const items = list.data?.items ?? [];
  const more = Boolean(list.data?.next_cursor);
  const headingId = "contact-conversations-title";
  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="drawer-section-title">
        {t("contact.conversations")}
      </h2>
      {list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : null}
      {items.length ? (
        <ul className="deal-list">
          {items.map((item) => (
            <li key={item.id}>
              <AriaButton
                className="deal-row"
                onPress={() => {
                  onOpen(item.id);
                }}
              >
                <span className="deal-row-text">
                  <span className="deal-row-title">
                    {item.subject || t("contact.conversationNoSubject")}
                  </span>
                  <span className="deal-row-meta">
                    {t(item.status === "open" ? "inbox.status.open" : "inbox.status.closed")}
                    {item.unread ? ` · ${t("inbox.unread")}` : ""}
                    {" · "}
                    <When value={item.last_message_at} />
                  </span>
                </span>
              </AriaButton>
            </li>
          ))}
        </ul>
      ) : list.isPending || list.isError ? null : (
        <p className="muted">{t("contact.conversationsEmpty")}</p>
      )}
      {more ? (
        <p className="muted">
          {t("contact.conversationsMore", { shown: CONTACT_CONVERSATIONS })}
        </p>
      ) : null}
    </section>
  );
}
