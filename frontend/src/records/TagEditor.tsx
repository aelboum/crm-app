import { Pencil, Plus } from "lucide-react";
import { type SyntheticEvent, useId, useState } from "react";

import { ApiError } from "../api/client";
import { DuplicateError, FieldErrors, type RecordKind, useSetTags } from "../api/records";
import { type TagRef, useCreateTag, useTags } from "../api/tags";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Tags on a contact or company (decision P3-C; ScreenContacts.dc.html, the
 * drawer's Tags card and the list's tag pills). Tags show as the design's
 * neutral pills. Editing happens in a dialog that saves the whole set in one
 * versioned request, so two quick changes can never race each other; Owners
 * and Admins can also create a tag there (the design's "+ Add tag").
 */

export const MAX_RECORD_TAGS = 20;
const SHOWN_IN_LISTS = 3;

/** A record's tags as pills; lists show the first few and a count. */
export function TagPills({ tags, limit }: { tags: TagRef[]; limit?: number }) {
  const t = useT();
  if (tags.length === 0) return null;
  const shown = limit === undefined ? tags : tags.slice(0, limit);
  const more = tags.length - shown.length;
  return (
    <ul className="tag-pills" aria-label={t("tags.label")}>
      {shown.map((tag) => (
        <li key={tag.id} className="tag-pill">
          {tag.name}
        </li>
      ))}
      {more > 0 ? (
        <li className="tag-pill more" aria-label={t("tags.more", { count: more })}>
          +{more}
        </li>
      ) : null}
    </ul>
  );
}

/** A list row's tags: the first few, or a dash. */
export function ListTags({ tags }: { tags: TagRef[] }) {
  return tags.length ? <TagPills tags={tags} limit={SHOWN_IN_LISTS} /> : <span className="muted">—</span>;
}

/** The drawer's Tags section, with "Edit tags" for those who may change the record. */
export function TagSection({
  workspaceId,
  kind,
  record,
  canEdit,
  canCreate,
}: {
  workspaceId: string;
  kind: RecordKind;
  record: { id: string; version: number; tags: TagRef[] };
  canEdit: boolean;
  canCreate: boolean;
}) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const headingId = useId();
  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <div className="drawer-section-head">
        <h2 id={headingId} className="drawer-section-title">
          {t("tags.label")}
        </h2>
        {canEdit ? (
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              setEditing(true);
            }}
          >
            <Pencil size={13} aria-hidden="true" />
            {t("tags.edit")}
          </Button>
        ) : null}
      </div>
      {record.tags.length ? <TagPills tags={record.tags} /> : <p className="muted">{t("tags.none")}</p>}
      {editing ? (
        <TagDialog
          workspaceId={workspaceId}
          kind={kind}
          record={record}
          canCreate={canCreate}
          onClose={() => {
            setEditing(false);
          }}
        />
      ) : null}
    </section>
  );
}

const FAILURES: Partial<Record<string, MessageId>> = {
  stale_version: "tags.error.stale",
  tag_not_found: "tags.error.gone",
  tag_limit_reached: "tags.error.vocabularyFull",
};

function failure(error: unknown): MessageId {
  if (error instanceof DuplicateError) return "tags.error.duplicate";
  if (error instanceof FieldErrors) return "tags.error.name";
  if (error instanceof ApiError) {
    const known = error.code ? FAILURES[error.code] : undefined;
    if (known) return known;
    if (error.status === 403) return "tags.error.forbidden";
  }
  return "tags.error.failed";
}

function TagDialog({
  workspaceId,
  kind,
  record,
  canCreate,
  onClose,
}: {
  workspaceId: string;
  kind: RecordKind;
  record: { id: string; version: number; tags: TagRef[] };
  canCreate: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const tags = useTags(workspaceId);
  const save = useSetTags(workspaceId, kind);
  const create = useCreateTag(workspaceId);
  const [chosen, setChosen] = useState<string[]>(record.tags.map((tag) => tag.id));
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<MessageId | null>(null);
  const filterId = useId();
  const draftId = useId();
  const full = chosen.length >= MAX_RECORD_TAGS;
  const needle = filter.trim().toLowerCase();
  const items = (tags.data?.items ?? []).filter((tag) => !needle || tag.name.toLowerCase().includes(needle));

  const toggle = (id: string, on: boolean) => {
    setChosen((current) => (on ? [...new Set([...current, id])] : current.filter((other) => other !== id)));
  };

  const add = (event: SyntheticEvent) => {
    event.preventDefault();
    const name = draft.trim();
    if (!name || create.isPending) return;
    setError(null);
    create.mutate(
      { name },
      {
        onSuccess: (tag) => {
          setDraft("");
          if (!full) toggle(tag.id, true);
        },
        onError: (problem) => {
          // A tag of that name already exists: choose it instead.
          if (problem instanceof DuplicateError && problem.existingId) {
            setDraft("");
            if (!full) toggle(problem.existingId, true);
            return;
          }
          setError(failure(problem));
        },
      },
    );
  };

  const submit = () => {
    setError(null);
    save.mutate(
      { id: record.id, version: record.version, tagIds: chosen },
      {
        onSuccess: () => {
          toast(t("tags.saved"));
          onClose();
        },
        onError: (problem) => {
          setError(failure(problem));
        },
      },
    );
  };

  return (
    <Dialog
      isOpen
      title={t("tags.editTitle")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" onPress={submit} isDisabled={save.isPending || !tags.data}>
            {t("tags.save")}
          </Button>
        </>
      }
    >
      {error ? (
        <p className="notice error" role="alert">
          {t(error)}
        </p>
      ) : null}
      {tags.isPending ? <Loading /> : null}
      {tags.isError ? <LoadError error={tags.error} onRetry={() => void tags.refetch()} /> : null}
      {tags.data ? (
        <div className="tag-editor">
          {tags.data.items.length > 0 ? (
            <div className="form-field">
              <label htmlFor={filterId} className="form-label">
                {t("tags.filter")}
              </label>
              <input
                id={filterId}
                type="search"
                className="form-input"
                value={filter}
                maxLength={50}
                onChange={(event) => {
                  setFilter(event.target.value);
                }}
              />
            </div>
          ) : null}
          <p className="tag-count" aria-live="polite">
            {t("tags.chosen", { count: chosen.length, max: MAX_RECORD_TAGS })}
          </p>
          {tags.data.items.length === 0 ? (
            <p className="muted">{canCreate ? t("tags.emptyCreate") : t("tags.emptyAsk")}</p>
          ) : items.length === 0 ? (
            <p className="muted">{t("tags.noMatch")}</p>
          ) : (
            <fieldset className="tag-options">
              <legend className="sr-only">{t("tags.label")}</legend>
              {items.map((tag) => {
                const on = chosen.includes(tag.id);
                return (
                  <label key={tag.id} className="tag-option">
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={!on && full}
                      onChange={(event) => {
                        toggle(tag.id, event.target.checked);
                      }}
                    />
                    <span>{tag.name}</span>
                  </label>
                );
              })}
            </fieldset>
          )}
          {canCreate ? (
            <form className="tag-new" onSubmit={add}>
              <div className="form-field">
                <label htmlFor={draftId} className="form-label">
                  {t("tags.newName")}
                </label>
                <input
                  id={draftId}
                  className="form-input"
                  value={draft}
                  maxLength={50}
                  onChange={(event) => {
                    setDraft(event.target.value);
                  }}
                />
              </div>
              <Button type="submit" isDisabled={!draft.trim() || create.isPending}>
                <Plus size={14} aria-hidden="true" />
                {t("tags.add")}
              </Button>
            </form>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
