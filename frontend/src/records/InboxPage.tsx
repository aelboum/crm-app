import { ArrowLeft, Plus, Search } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { useIntl } from "react-intl";

import { ApiError } from "../api/client";
import {
  type Assigned,
  type Channel,
  type Conversation,
  type ConversationSummary,
  type InboxFilter,
  type InboxStatus,
  SEARCH_MAX,
  type MessageKind,
  useAddMessage,
  useConversation,
  useConversations,
  useDecideReview,
  useReviews,
  type Review,
  useCreateConversation,
  useMarkRead,
  useUpdateConversation,
} from "../api/conversations";
import { useAccess, useMe, useMembers } from "../api/queries";
import { newIdempotencyKey } from "../api/records";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { type MemberNames, useMemberNames } from "../members/names";
import { CompanyPicker, type PickedCompany } from "./CompanyPicker";
import { TemplatePicker } from "./EmailTemplates";
import { type Option, ownerLabel, ownerOptions } from "./parts";
import { useDebounced } from "./useDebounced";

/*
 * The inbox (decision P6-C): threads with contacts, by status and
 * assignment, and one thread with its messages. Members log what a contact
 * sent, add internal notes and, on an email thread, write a reply. A reply
 * is queued and shows "Not sent yet" until the email leaves; while email
 * sending is off for the installation, nothing leaves. Read-only members
 * read and nothing more.
 */

type T = ReturnType<typeof useT>;
type Changes = { status?: "open" | "closed"; assignee_user_id?: string | null };

const ASSIGNED: [Assigned, MessageId][] = [
  ["all", "inbox.filter.all"],
  ["mine", "inbox.filter.mine"],
  ["unassigned", "inbox.filter.unassigned"],
];

const DELIVERY_TONE: Record<string, Tone> = {
  queued: "pending",
  sending: "pending",
  sent: "info",
  delivered: "success",
  bounced: "risk",
  complained: "risk",
  failed: "risk",
  suppressed: "neutral",
  delivery_delayed: "pending",
  rejected: "risk",
  outcome_unknown: "risk",
};

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "contact_has_no_email") return "inbox.error.noEmail";
    if (error.code === "invalid_conversation") return "inbox.error.invalid";
    if (error.code === "stale_version") return "inbox.error.stale";
    if (error.status === 403) return "inbox.error.forbidden";
  }
  return "inbox.error.failed";
}

function kinds(channel: Channel): MessageKind[] {
  return channel === "email"
    ? ["outbound", "inbound", "note"]
    : ["inbound", "note"];
}

export function InboxPage({
  workspaceId,
  openId = null,
  onOpenContact,
  startCreate = false,
  onCreateDone = () => undefined,
}: {
  workspaceId: string;
  /** A conversation to open first (`?record=`), e.g. from a contact's drawer. */
  openId?: string | null;
  onOpenContact: (id: string) => void;
  /** Open a new conversation (`?create=conversation`, "+ New"), if the caller may. */
  startCreate?: boolean;
  /** Called when that dialog closes, to clear the request. */
  onCreateDone?: () => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(
    workspaceId,
    0,
    access.data?.actions.read_members === true,
  );
  const people = ownerOptions(t, members.data?.items ?? [], meId);
  const canReply = access.data?.actions.reply_conversations === true;
  const [filter, setFilter] = useState<Omit<InboxFilter, "q">>({
    status: "open",
    assigned: "all",
  });
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [selected, setSelected] = useState<string | null>(openId);
  const [composing, setComposing] = useState(false);
  const list = useConversations(workspaceId, { ...filter, q });
  const markRead = useMarkRead(workspaceId);
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];

  const open = (item: ConversationSummary) => {
    setSelected(item.id);
    if (item.unread) markRead.mutate({ id: item.id });
  };

  return (
    <div className={`records-page inbox-page${selected ? " has-thread" : ""}`}>
      <div className="records-head">
        <div className="records-head-text">
          <h1 className="records-title">{t("nav.inbox")}</h1>
          <p className="muted inbox-intro">{t("inbox.intro")}</p>
        </div>
        {canReply ? (
          <div className="records-actions">
            <Button
              variant="primary"
              onPress={() => {
                setComposing(true);
              }}
            >
              <Plus size={14} aria-hidden="true" />
              {t("inbox.new")}
            </Button>
          </div>
        ) : null}
      </div>
      <div className="inbox">
        <section className="inbox-list" aria-label={t("inbox.listLabel")}>
          {canReply ? <Reviews workspaceId={workspaceId} /> : null}
          <label className="search-box inbox-search">
            <Search size={14} aria-hidden="true" />
            <span className="sr-only">{t("inbox.search")}</span>
            <input
              type="search"
              value={search}
              placeholder={t("inbox.search")}
              onChange={(event) => {
                setSearch(event.target.value);
              }}
              maxLength={SEARCH_MAX}
            />
          </label>
          <div className="inbox-filters">
            <div
              className="segmented"
              role="group"
              aria-label={t("inbox.statusLabel")}
            >
              {(
                [
                  "open",
                  "closed",
                  "all",
                ] as const satisfies readonly InboxStatus[]
              ).map((status) => (
                <button
                  key={status}
                  type="button"
                  className={
                    filter.status === status ? "segment active" : "segment"
                  }
                  aria-pressed={filter.status === status}
                  onClick={() => {
                    setFilter({ ...filter, status });
                  }}
                >
                  {t(`inbox.status.${status}`)}
                </button>
              ))}
            </div>
            <label className="sr-only" htmlFor="inbox-assigned">
              {t("inbox.assignedLabel")}
            </label>
            <select
              id="inbox-assigned"
              className="form-input form-select inbox-assigned"
              value={filter.assigned}
              onChange={(event) => {
                setFilter({
                  ...filter,
                  assigned: event.target.value as Assigned,
                });
              }}
            >
              {ASSIGNED.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </div>
          {list.isError ? (
            <LoadError error={list.error} onRetry={() => void list.refetch()} />
          ) : list.isPending ? (
            <Loading />
          ) : items.length === 0 ? (
            q ? (
              <EmptyState
                title={t("inbox.noResults")}
                body={t("inbox.noResultsBody")}
              />
            ) : (
              <EmptyState
                title={t("inbox.empty")}
                body={t("inbox.emptyBody")}
              />
            )
          ) : (
            <>
              <ul className="inbox-items">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`inbox-item${item.id === selected ? " active" : ""}${item.unread ? " unread" : ""}`}
                      aria-current={item.id === selected ? "true" : undefined}
                      onClick={() => {
                        open(item);
                      }}
                    >
                      <span className="inbox-item-top">
                        <span className="inbox-item-name">
                          {item.contact_name ?? t("inbox.noContact")}
                        </span>
                        <ShortTime value={item.last_message_at} />
                      </span>
                      <span className="inbox-item-subject">{item.subject}</span>
                      <span className="inbox-item-meta">
                        <span className="muted">
                          {t(`inbox.channel.${item.channel}`)}
                        </span>
                        {item.unread ? (
                          <span className="inbox-unread">
                            {t("inbox.unread")}
                          </span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {list.hasNextPage ? (
                <div className="inbox-more">
                  <Button
                    size="sm"
                    onPress={() => void list.fetchNextPage()}
                    isDisabled={list.isFetchingNextPage}
                  >
                    {list.isFetchingNextPage
                      ? t("state.loading")
                      : t("records.loadMore")}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
        <section className="inbox-thread" aria-label={t("inbox.threadLabel")}>
          {selected ? (
            <Thread
              key={selected}
              workspaceId={workspaceId}
              id={selected}
              canReply={canReply}
              people={people}
              meId={meId}
              onBack={() => {
                setSelected(null);
              }}
              onOpenContact={onOpenContact}
            />
          ) : (
            <p className="muted inbox-pick">{t("inbox.pick")}</p>
          )}
        </section>
      </div>
      {composing || (startCreate && canReply) ? (
        <NewConversationDialog
          workspaceId={workspaceId}
          onClose={(created) => {
            setComposing(false);
            if (startCreate) onCreateDone();
            if (created) {
              setFilter({ status: "open", assigned: filter.assigned });
              setSearch("");
              setSelected(created);
            }
          }}
        />
      ) : null}
    </div>
  );
}

function Reviews({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const reviews = useReviews(workspaceId, true);
  const decide = useDecideReview(workspaceId);
  const items = reviews.data?.items ?? [];
  if (items.length === 0) return null;
  return (
    <section className="inbox-reviews" aria-label={t("inbox.reviews.title")}>
      <h2 className="inbox-reviews-title">
        {t("inbox.reviews.title")}{" "}
        <span className="inbox-unread">{items.length}</span>
      </h2>
      <p className="muted">{t("inbox.reviews.intro")}</p>
      {decide.isError ? (
        <p className="notice error" role="alert">
          {t("inbox.reviews.error")}
        </p>
      ) : null}
      <ul className="inbox-review-items">
        {items.map((review: Review) => (
          <li key={review.id} className="inbox-review">
            <p className="inbox-review-reason">
              {t(`inbox.reviews.reason.${review.reason}` as MessageId)}
            </p>
            <p className="inbox-review-from">
              {t("inbox.reviews.from", { sender: review.sender })}
            </p>
            <p className="inbox-item-subject">{review.subject}</p>
            <p className="inbox-message-text">{review.body}</p>
            {review.truncated ? (
              <p className="muted">{t("inbox.reviews.truncated")}</p>
            ) : null}
            {review.attachments.length ? (
              <p className="muted">
                {t("inbox.attachments")}:{" "}
                {review.attachments.map((a) => a.filename).join(", ")}
              </p>
            ) : null}
            <div className="inbox-review-actions">
              <Button
                size="sm"
                variant="primary"
                isDisabled={decide.isPending || review.conversation_id === null}
                onPress={() => {
                  decide.mutate({
                    id: review.id,
                    version: review.version,
                    accept: true,
                  });
                }}
              >
                {t("inbox.reviews.accept")}
              </Button>
              <Button
                size="sm"
                isDisabled={decide.isPending}
                onPress={() => {
                  decide.mutate({
                    id: review.id,
                    version: review.version,
                    accept: false,
                  });
                }}
              >
                {t("inbox.reviews.discard")}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ShortTime({ value }: { value: string }) {
  const intl = useIntl();
  const date = new Date(value);
  const today = new Date().toDateString() === date.toDateString();
  return (
    <time
      className="inbox-time muted"
      dateTime={value}
      title={intl.formatDate(date, { dateStyle: "full", timeStyle: "short" })}
    >
      {today
        ? intl.formatTime(date, { hour: "numeric", minute: "2-digit" })
        : intl.formatDate(date, { day: "numeric", month: "short" })}
    </time>
  );
}

function author(
  t: T,
  kind: string,
  authorId: string | null,
  meId: string | undefined,
  names: MemberNames,
): string {
  if (kind === "inbound") return t("inbox.kind.inbound");
  return ownerLabel(t, authorId, meId, names);
}

function Thread({
  workspaceId,
  id,
  canReply,
  people,
  meId,
  onBack,
  onOpenContact,
}: {
  workspaceId: string;
  id: string;
  canReply: boolean;
  people: Option[];
  meId: string | undefined;
  onBack: () => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const names = useMemberNames();
  const toast = useToast();
  const thread = useConversation(workspaceId, id);
  const update = useUpdateConversation(workspaceId);
  const [problem, setProblem] = useState<MessageId | null>(null);
  if (thread.isError) {
    return (
      <LoadError error={thread.error} onRetry={() => void thread.refetch()} />
    );
  }
  if (thread.isPending) return <Loading />;
  const item = thread.data;
  const change = (changes: Changes) => {
    setProblem(null);
    update.mutate(
      { id: item.id, version: item.version, changes },
      {
        onSuccess: () => {
          if (changes.status) {
            toast(
              t(
                changes.status === "closed"
                  ? "inbox.closedToast"
                  : "inbox.reopenedToast",
              ),
            );
          }
        },
        onError: (error) => {
          setProblem(failure(error));
        },
      },
    );
  };
  const assignee = item.assignee_user_id ?? "";
  const choices =
    assignee && !people.some((p) => p.id === assignee)
      ? [...people, { id: assignee, label: ownerLabel(t, assignee, meId, names) }]
      : people;
  const contactId = item.contact_id;
  return (
    <div className="inbox-thread-body">
      <div className="inbox-thread-head">
        <Button
          size="sm"
          variant="ghost"
          className="inbox-back"
          onPress={onBack}
        >
          <ArrowLeft size={14} aria-hidden="true" />
          {t("inbox.back")}
        </Button>
        <div className="inbox-thread-title">
          <h2 className="inbox-subject">{item.subject}</h2>
          <p className="muted inbox-with">
            {contactId ? (
              <button
                type="button"
                className="inbox-contact-link"
                onClick={() => {
                  onOpenContact(contactId);
                }}
              >
                {item.contact_name}
              </button>
            ) : (
              t("inbox.noContact")
            )}
            {item.contact_email ? ` · ${item.contact_email}` : ""}
            {` · ${t(`inbox.channel.${item.channel}`)}`}
          </p>
        </div>
        <Badge tone={item.status === "open" ? "accent" : "neutral"}>
          {t(`inbox.status.${item.status}`)}
        </Badge>
      </div>
      {canReply ? (
        <div className="inbox-thread-actions">
          <label className="form-label" htmlFor={`assignee-${item.id}`}>
            {t("inbox.assignee")}
          </label>
          <select
            id={`assignee-${item.id}`}
            className="form-input form-select inbox-assignee"
            value={assignee}
            disabled={update.isPending}
            onChange={(event) => {
              change({ assignee_user_id: event.target.value || null });
            }}
          >
            <option value="">{t("records.owner.none")}</option>
            {choices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            isDisabled={update.isPending}
            onPress={() => {
              change({ status: item.status === "open" ? "closed" : "open" });
            }}
          >
            {t(item.status === "open" ? "inbox.close" : "inbox.reopen")}
          </Button>
        </div>
      ) : null}
      {problem ? (
        <p className="notice error" role="alert">
          {t(problem)}
        </p>
      ) : null}
      <ol className="inbox-messages" aria-label={t("inbox.messagesLabel")}>
        {item.messages.map((message) => (
          <li key={message.id} className={`inbox-message ${message.kind}`}>
            <div className="inbox-message-head">
              <span className="inbox-message-author">
                {message.kind === "note" ? `${t("inbox.kind.note")} · ` : ""}
                {author(t, message.kind, message.author_user_id, meId, names)}
              </span>
              <ShortTime value={message.created_at} />
            </div>
            <p className="inbox-message-text">{message.body}</p>
            {message.attachments?.length ? (
              <div className="inbox-attachments">
                <p className="muted">{t("inbox.attachments")}</p>
                <ul>
                  {message.attachments.map((attachment, index) => (
                    <li key={index}>
                      {attachment.filename}{" "}
                      <span className="muted">
                        ({attachment.content_type}
                        {attachment.size === null
                          ? ""
                          : `, ${String(attachment.size)} B`}
                        )
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="muted inbox-attachments-note">
                  {t("inbox.attachmentsNote")}
                </p>
              </div>
            ) : null}
            {message.delivery ? (
              <Badge tone={DELIVERY_TONE[message.delivery] ?? "neutral"}>
                {t(`inbox.delivery.${message.delivery}` as MessageId)}
              </Badge>
            ) : null}
          </li>
        ))}
      </ol>
      {canReply ? <Composer workspaceId={workspaceId} thread={item} /> : null}
    </div>
  );
}

function Composer({
  workspaceId,
  thread,
}: {
  workspaceId: string;
  thread: Conversation;
}) {
  const t = useT();
  const add = useAddMessage(workspaceId);
  const available = kinds(thread.channel);
  const [kind, setKind] = useState<MessageKind>(available[0] ?? "note");
  const [body, setBody] = useState("");
  const [key, setKey] = useState(newIdempotencyKey);
  const [problem, setProblem] = useState<MessageId | null>(null);
  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (!body.trim()) return;
    setProblem(null);
    add.mutate(
      { id: thread.id, kind, body, key },
      {
        onSuccess: () => {
          setBody("");
          setKey(newIdempotencyKey());
        },
        onError: (error) => {
          setProblem(failure(error));
        },
      },
    );
  };
  return (
    <form className="inbox-composer" onSubmit={submit}>
      <div className="segmented" role="group" aria-label={t("inbox.composeAs")}>
        {available.map((option) => (
          <button
            key={option}
            type="button"
            className={kind === option ? "segment active" : "segment"}
            aria-pressed={kind === option}
            onClick={() => {
              setKind(option);
            }}
          >
            {t(`inbox.mode.${option}`)}
          </button>
        ))}
      </div>
      {kind === "outbound" && thread.contact_id ? (
        <TemplatePicker
          workspaceId={workspaceId}
          contactId={thread.contact_id}
          onPick={(_subject, filled) => {
            setBody(filled);
          }}
        />
      ) : null}
      <label className="sr-only" htmlFor={`compose-${thread.id}`}>
        {t(`inbox.mode.${kind}`)}
      </label>
      <textarea
        id={`compose-${thread.id}`}
        className="form-input inbox-textarea"
        rows={3}
        maxLength={20000}
        value={body}
        placeholder={t(`inbox.placeholder.${kind}`)}
        onChange={(event) => {
          setBody(event.target.value);
        }}
      />
      {kind === "outbound" ? (
        <p className="muted inbox-hint">{t("inbox.queuedHint")}</p>
      ) : null}
      {problem ? (
        <p className="notice error" role="alert">
          {t(problem)}
        </p>
      ) : null}
      <div className="inbox-composer-actions">
        <Button
          type="submit"
          variant="primary"
          isDisabled={add.isPending || !body.trim()}
        >
          {t(`inbox.submit.${kind}`)}
        </Button>
      </div>
    </form>
  );
}

function NewConversationDialog({
  workspaceId,
  onClose,
}: {
  workspaceId: string;
  onClose: (created: string | null) => void;
}) {
  const t = useT();
  const create = useCreateConversation(workspaceId);
  const [contact, setContact] = useState<PickedCompany | null>(null);
  const [channel, setChannel] = useState<Channel>("email");
  const [subject, setSubject] = useState("");
  const [kind, setKind] = useState<MessageKind>("outbound");
  const [body, setBody] = useState("");
  const [key] = useState(newIdempotencyKey);
  const [problem, setProblem] = useState<MessageId | null>(null);
  const available = kinds(channel);
  const chosen = available.includes(kind) ? kind : (available[0] ?? "note");
  const valid = contact !== null && subject.trim() !== "" && body.trim() !== "";
  const submit = (event?: SyntheticEvent) => {
    event?.preventDefault();
    if (!contact || !valid) return;
    setProblem(null);
    create.mutate(
      {
        body: { contact_id: contact.id, channel, subject, kind: chosen, body },
        key,
      },
      {
        onSuccess: (made) => {
          onClose(made.id);
        },
        onError: (error) => {
          setProblem(failure(error));
        },
      },
    );
  };
  return (
    <Dialog
      isOpen
      title={t("inbox.new")}
      onClose={() => {
        onClose(null);
      }}
      actions={
        <>
          <Button
            onPress={() => {
              onClose(null);
            }}
          >
            {t("confirm.cancel")}
          </Button>
          <Button
            variant="primary"
            isDisabled={!valid || create.isPending}
            onPress={() => {
              submit();
            }}
          >
            {t(`inbox.submit.${chosen}`)}
          </Button>
        </>
      }
    >
      <form className="inbox-new" onSubmit={submit}>
        <CompanyPicker
          workspaceId={workspaceId}
          kind="contacts"
          id="conversation-contact"
          label={t("inbox.field.contact")}
          selected={contact}
          onChange={setContact}
        />
        <div className="form-field">
          <label className="form-label" htmlFor="conversation-channel">
            {t("inbox.field.channel")}
          </label>
          <select
            id="conversation-channel"
            className="form-input form-select"
            value={channel}
            onChange={(event) => {
              setChannel(event.target.value as Channel);
            }}
          >
            <option value="email">{t("inbox.channel.email")}</option>
            <option value="other">{t("inbox.channel.other")}</option>
          </select>
        </div>
        <div className="form-field">
          <label className="form-label" htmlFor="conversation-subject">
            {t("inbox.field.subject")}
          </label>
          <input
            id="conversation-subject"
            className="form-input"
            maxLength={200}
            value={subject}
            onChange={(event) => {
              setSubject(event.target.value);
            }}
          />
        </div>
        <div className="form-field">
          <label className="form-label" htmlFor="conversation-kind">
            {t("inbox.field.kind")}
          </label>
          <select
            id="conversation-kind"
            className="form-input form-select"
            value={chosen}
            onChange={(event) => {
              setKind(event.target.value as MessageKind);
            }}
          >
            {available.map((option) => (
              <option key={option} value={option}>
                {t(`inbox.mode.${option}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label className="form-label" htmlFor="conversation-body">
            {t("inbox.field.body")}
          </label>
          <textarea
            id="conversation-body"
            className="form-input inbox-textarea"
            rows={4}
            maxLength={20000}
            value={body}
            onChange={(event) => {
              setBody(event.target.value);
            }}
          />
        </div>
        {chosen === "outbound" ? (
          <p className="muted inbox-hint">{t("inbox.queuedHint")}</p>
        ) : null}
        {problem ? (
          <p className="notice error" role="alert">
            {t(problem)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
