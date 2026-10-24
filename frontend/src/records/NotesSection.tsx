import { Archive, ArchiveRestore, Building2, Flag, PenLine, Plus, StickyNote, Trash2, UserRound } from "lucide-react";
import { type SyntheticEvent, useCallback, useEffect, useRef, useState } from "react";
import { useIntl } from "react-intl";

import { ApiError } from "../api/client";
import {
  type Activity,
  type Note,
  NOTE_MAX,
  useActivity,
  useAddNote,
  useDeleteNote,
  useEditNote,
  useNotes,
} from "../api/notes";
import { newIdempotencyKey, type RecordKind } from "../api/records";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ownerLabel, When } from "./parts";

/*
 * Notes and history in the contact and company drawers (decision P3-B D1;
 * ScreenContacts.dc.html L181-187 for the note card, L155-164 for the
 * timeline). Note text is always rendered as text: React escapes it, and
 * `white-space: pre-wrap` keeps its line breaks. Nothing here inserts HTML.
 */

type T = ReturnType<typeof useT>;

/** Why a note change was refused, in words. */
function refusal(t: T, error: unknown): string {
  if (!(error instanceof ApiError)) return t("records.error.generic");
  if (error.code === "record_archived") return t("notes.error.archived");
  if (error.code === "stale_version") return t("notes.error.stale");
  if (error.code === "not_note_author" || error.status === 403) return t("notes.error.denied");
  if (error.code === "note_not_found") return t("notes.error.gone");
  if (error.status === 404) return t("notes.error.recordGone");
  if (error.status === 422) return t("notes.error.invalid");
  return t("records.error.generic");
}

export function NotesSection({
  workspaceId,
  kind,
  id,
  meId,
  canAdd,
  onDirtyChange,
}: {
  workspaceId: string;
  kind: RecordKind;
  id: string;
  meId: string | undefined;
  canAdd: boolean;
  /** Reports unsaved text (a new note or an edit), so the drawer can ask
   *  before closing. */
  onDirtyChange: (dirty: boolean) => void;
}) {
  const t = useT();
  const toast = useToast();
  const notes = useNotes(workspaceId, kind, id);
  const add = useAddNote(workspaceId, kind, id);
  const [draft, setDraft] = useState("");
  // One key per attempt: resending the same text reuses it, so a lost
  // response never makes a second note.
  const [key, setKey] = useState(newIdempotencyKey);
  const [error, setError] = useState<string | null>(null);
  const items = (notes.data?.pages ?? []).flatMap((page) => page.items);
  const archived = notes.data?.pages[0]?.record_archived ?? false;
  const headingId = `${kind}-${id}-notes`;
  // Notes with an unsaved edit, by ID; with the draft, what closing would lose.
  const [editsOpen, setEditsOpen] = useState<ReadonlySet<string>>(new Set());
  const dirty = draft.trim() !== "" || editsOpen.size > 0;
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const editChanged = useCallback((noteId: string, changed: boolean) => {
    setEditsOpen((open) => {
      if (open.has(noteId) === changed) return open;
      const next = new Set(open);
      if (changed) next.add(noteId);
      else next.delete(noteId);
      return next;
    });
  }, []);

  function change(value: string) {
    setDraft(value);
    setKey(newIdempotencyKey());
    setError(null);
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    add.mutate(
      { body: draft, key },
      {
        onSuccess: () => {
          setDraft("");
          setKey(newIdempotencyKey());
          toast(t("notes.added"));
        },
        onError: (failure) => {
          setError(refusal(t, failure));
        },
      },
    );
  }

  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="drawer-section-title">
        {t("notes.title")}
      </h2>
      {canAdd && !archived && notes.isSuccess ? (
        <form className="note-composer" onSubmit={submit}>
          <label className="sr-only" htmlFor={`${headingId}-draft`}>
            {t("notes.new")}
          </label>
          <textarea
            id={`${headingId}-draft`}
            value={draft}
            maxLength={NOTE_MAX}
            placeholder={t("notes.placeholder")}
            onChange={(event) => {
              change(event.target.value);
            }}
          />
          <div className="note-composer-bar">
            {error ? (
              <p className="note-error" role="alert">
                {error}
              </p>
            ) : null}
            <Button type="submit" variant="primary" size="sm" isDisabled={!draft.trim() || add.isPending}>
              <Plus size={13} aria-hidden="true" />
              {t("notes.add")}
            </Button>
          </div>
        </form>
      ) : null}
      {canAdd && archived ? <p className="drawer-note">{t(kind === "contacts" ? "notes.archivedContact" : "notes.archivedCompany")}</p> : null}
      {notes.isPending ? (
        <Loading />
      ) : notes.isError ? (
        <LoadError error={notes.error} onRetry={() => void notes.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("notes.empty")} />
      ) : (
        <ul className="note-list">
          {items.map((note) => (
            <NoteCard
              key={note.id}
              workspaceId={workspaceId}
              kind={kind}
              recordId={id}
              note={note}
              meId={meId}
              onEditChanged={editChanged}
            />
          ))}
        </ul>
      )}
      {notes.hasNextPage ? (
        <Button size="sm" isDisabled={notes.isFetchingNextPage} onPress={() => void notes.fetchNextPage()}>
          {t("notes.more")}
        </Button>
      ) : null}
    </section>
  );
}

function NoteCard({
  workspaceId,
  kind,
  recordId,
  note,
  meId,
  onEditChanged,
}: {
  workspaceId: string;
  kind: RecordKind;
  recordId: string;
  note: Note;
  meId: string | undefined;
  /** Whether this note has an open edit that differs from the saved text. */
  onEditChanged: (noteId: string, changed: boolean) => void;
}) {
  const t = useT();
  const toast = useToast();
  const edit = useEditNote(workspaceId, kind, recordId);
  const remove = useDeleteNote(workspaceId, kind, recordId);
  const [editing, setEditing] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fieldId = `note-${note.id}-edit`;
  // Focus follows the edit: into the text (cursor at the end) on Edit, and
  // back to the Edit button on Cancel or Save, so keyboard users never land
  // on a control that no longer exists.
  const isEditing = editing !== null;
  const changed = editing !== null && editing !== note.body;
  useEffect(() => {
    onEditChanged(note.id, changed);
  }, [note.id, changed, onEditChanged]);
  useEffect(
    () => () => {
      onEditChanged(note.id, false);
    },
    [note.id, onEditChanged],
  );
  const field = useRef<HTMLTextAreaElement>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    if (isEditing) {
      const box = field.current;
      box?.focus();
      box?.setSelectionRange(box.value.length, box.value.length);
    } else if (wasEditing.current) {
      editButton.current?.focus();
    }
    wasEditing.current = isEditing;
  }, [isEditing]);

  function save(event: SyntheticEvent) {
    event.preventDefault();
    if (editing === null || !editing.trim()) return;
    edit.mutate(
      { noteId: note.id, version: note.version, body: editing },
      {
        onSuccess: () => {
          setEditing(null);
          setError(null);
          toast(t("notes.saved"));
        },
        onError: (failure) => {
          setError(refusal(t, failure));
        },
      },
    );
  }

  return (
    <li className="note-card">
      {editing === null ? (
        <p className="note-body">{note.body}</p>
      ) : (
        <form className="note-edit" onSubmit={save}>
          <label className="sr-only" htmlFor={fieldId}>
            {t("notes.editLabel")}
          </label>
          <textarea
            ref={field}
            id={fieldId}
            value={editing}
            maxLength={NOTE_MAX}
            onChange={(event) => {
              setEditing(event.target.value);
              setError(null);
            }}
          />
          <div className="note-actions">
            <Button
              size="sm"
              onPress={() => {
                setEditing(null);
                setError(null);
              }}
            >
              {t("confirm.cancel")}
            </Button>
            <Button type="submit" variant="primary" size="sm" isDisabled={!editing.trim() || edit.isPending}>
              {t("notes.save")}
            </Button>
          </div>
        </form>
      )}
      <p className="note-meta">
        {ownerLabel(t, note.author_user_id, meId)} · <When value={note.created_at} />
        {note.edited ? ` · ${t("notes.edited")}` : ""}
      </p>
      {error ? (
        <p className="note-error" role="alert">
          {error}
        </p>
      ) : null}
      {editing === null && (note.can_edit || note.can_delete) ? (
        <div className="note-actions">
          {note.can_edit ? (
            <Button
              ref={editButton}
              size="sm"
              variant="ghost"
              onPress={() => {
                setEditing(note.body);
              }}
            >
              <PenLine size={13} aria-hidden="true" />
              {t("notes.edit")}
            </Button>
          ) : null}
          {note.can_delete ? (
            <Button
              size="sm"
              variant="ghost"
              isDisabled={remove.isPending}
              onPress={() => {
                setConfirm(true);
              }}
            >
              <Trash2 size={13} aria-hidden="true" />
              {t("notes.delete")}
            </Button>
          ) : null}
        </div>
      ) : null}
      <ConfirmDialog
        isOpen={confirm}
        title={t("notes.deleteTitle")}
        confirmLabel={t("records.deleteSubmit")}
        message={t("notes.deleteConfirm")}
        onCancel={() => {
          setConfirm(false);
        }}
        onConfirm={() => {
          setConfirm(false);
          remove.mutate(
            { noteId: note.id },
            {
              onSuccess: () => {
                toast(t("notes.deleted"));
              },
              onError: (failure) => {
                setError(refusal(t, failure));
              },
            },
          );
        }}
      />
    </li>
  );
}

const FIELD_LABELS: Partial<Record<string, MessageId>> = {
  first_name: "history.field.first_name",
  last_name: "history.field.last_name",
  email: "history.field.email",
  phone: "history.field.phone",
  job_title: "history.field.job_title",
  city: "history.field.city",
  source: "history.field.source",
  name: "history.field.name",
  domain: "history.field.domain",
  website: "history.field.website",
  industry: "history.field.industry",
  country_code: "history.field.country_code",
};

const STAGE_LABELS: Partial<Record<string, MessageId>> = {
  lead: "stage.lead",
  prospect: "stage.prospect",
  customer: "stage.customer",
  inactive: "stage.inactive",
};

function useDescribe() {
  const t = useT();
  const intl = useIntl();
  const label = (labels: Partial<Record<string, MessageId>>, value: string | null | undefined) => {
    const id = value ? labels[value] : undefined;
    return id ? t(id) : (value ?? "—");
  };
  return (entry: Activity, meId: string | undefined): string => {
    const company = entry.company_name ?? t("history.deletedCompany");
    switch (entry.kind) {
      case "created":
        return t("history.created");
      case "updated":
        return t("history.updated", {
          fields: intl.formatList(
            (entry.fields ?? []).map((name) => label(FIELD_LABELS, name)),
            { type: "conjunction" },
          ),
        });
      case "stage_changed":
        return t("history.stage", {
          from: label(STAGE_LABELS, entry.stage_from),
          to: label(STAGE_LABELS, entry.stage_to),
        });
      case "owner_changed":
        return t("history.owner", { to: ownerLabel(t, entry.owner_to, meId) });
      case "company_linked":
        return t("history.linked", { company });
      case "company_unlinked":
        return t("history.unlinked", { company });
      case "archived":
        return t("history.archived");
      case "restored":
        return t("history.restored");
      case "note_added":
        return t("history.noteAdded");
      case "note_deleted":
        return t("history.noteDeleted");
    }
  };
}

const ICONS = {
  created: Plus,
  updated: PenLine,
  stage_changed: Flag,
  owner_changed: UserRound,
  company_linked: Building2,
  company_unlinked: Building2,
  archived: Archive,
  restored: ArchiveRestore,
  note_added: StickyNote,
  note_deleted: Trash2,
} as const;

export function ActivitySection({
  workspaceId,
  kind,
  id,
  meId,
}: {
  workspaceId: string;
  kind: RecordKind;
  id: string;
  meId: string | undefined;
}) {
  const t = useT();
  const activity = useActivity(workspaceId, kind, id);
  const describe = useDescribe();
  const items = (activity.data?.pages ?? []).flatMap((page) => page.items);
  const headingId = `${kind}-${id}-activity`;

  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="drawer-section-title">
        {t("history.title")}
      </h2>
      {activity.isPending ? (
        <Loading />
      ) : activity.isError ? (
        <LoadError error={activity.error} onRetry={() => void activity.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("history.empty")} />
      ) : (
        <ol className="activity-list">
          {items.map((entry) => {
            const Icon = ICONS[entry.kind];
            return (
              <li key={entry.id} className={`activity-item activity-${entry.kind}`}>
                <span className="activity-icon" aria-hidden="true">
                  <Icon size={12} />
                </span>
                <div className="activity-text">
                  <p className="activity-what">{describe(entry, meId)}</p>
                  {entry.note_excerpt ? (
                    <p className="activity-excerpt">
                      {entry.note_excerpt}
                      {entry.note_truncated ? "…" : ""}
                    </p>
                  ) : null}
                  <p className="activity-meta">
                    {entry.actor_user_id ? ownerLabel(t, entry.actor_user_id, meId) : t("history.system")}
                    {" · "}
                    <When value={entry.occurred_at} />
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {activity.hasNextPage ? (
        <Button size="sm" isDisabled={activity.isFetchingNextPage} onPress={() => void activity.fetchNextPage()}>
          {t("history.more")}
        </Button>
      ) : null}
    </section>
  );
}
