import { Pencil, Plus, Trash2 } from "lucide-react";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { DuplicateError, FieldErrors } from "../api/records";
import { type Tag, useCreateTag, useDeleteTag, useRenameTag, useTags } from "../api/tags";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Settings › Tags (decision P3-C). The design creates tags inline only (the
 * drawer's "+ Add tag"); this section adds a place to rename and delete
 * them, the design notes' "Central Settings" option. Everyone sees the
 * list; Owners and Admins (`update_workspace`) change it, and the server
 * enforces that. Deleting a tag removes it from every record.
 */

function failure(error: unknown): MessageId {
  if (error instanceof DuplicateError) return "tags.error.duplicate";
  if (error instanceof FieldErrors) return "tags.error.name";
  if (error instanceof ApiError) {
    if (error.code === "stale_version") return "tagSettings.error.stale";
    if (error.code === "tag_limit_reached") return "tags.error.vocabularyFull";
    if (error.code === "tag_not_found") return "tagSettings.error.gone";
    if (error.status === 403) return "tags.error.forbidden";
  }
  return "tags.error.failed";
}

export function TagSettings({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const t = useT();
  const toast = useToast();
  const tags = useTags(workspaceId);
  const create = useCreateTag(workspaceId);
  const remove = useDeleteTag(workspaceId);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<MessageId | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Tag | null>(null);

  if (tags.isPending) return <Loading />;
  if (tags.isError) return <LoadError error={tags.error} onRetry={() => void tags.refetch()} />;
  const { items, max_tags: max } = tags.data;

  const add = (event: SyntheticEvent) => {
    event.preventDefault();
    const name = draft.trim();
    if (!name) return;
    setError(null);
    create.mutate(
      { name },
      {
        onSuccess: (tag) => {
          setDraft("");
          toast(t("tagSettings.created", { name: tag.name }));
        },
        onError: (problem) => {
          setError(failure(problem));
        },
      },
    );
  };

  const confirmDelete = () => {
    if (!deleting) return;
    const tag = deleting;
    setDeleting(null);
    setError(null);
    remove.mutate(
      { id: tag.id },
      {
        onSuccess: () => {
          toast(t("tagSettings.deleted", { name: tag.name }));
        },
        onError: (problem) => {
          setError(failure(problem));
        },
      },
    );
  };

  return (
    <section className="business-card tag-settings" aria-label={t("settings.tags")}>
      <p className="profile-note">{t("tagSettings.count", { count: items.length, max })}</p>
      {canEdit ? null : <p className="profile-note">{t("tagSettings.readOnly")}</p>}
      {error ? (
        <p className="notice error" role="alert">
          {t(error)}
        </p>
      ) : null}
      {canEdit ? (
        <form className="tag-new" onSubmit={add}>
          <div className="form-field">
            <label htmlFor="tag-settings-new" className="form-label">
              {t("tags.newName")}
            </label>
            <input
              id="tag-settings-new"
              className="form-input"
              value={draft}
              maxLength={50}
              onChange={(event) => {
                setDraft(event.target.value);
              }}
            />
          </div>
          <Button type="submit" isDisabled={!draft.trim() || create.isPending || items.length >= max}>
            <Plus size={14} aria-hidden="true" />
            {t("tags.add")}
          </Button>
        </form>
      ) : null}
      {items.length === 0 ? (
        <p className="muted">{canEdit ? t("tagSettings.emptyEdit") : t("tags.emptyAsk")}</p>
      ) : (
        <ul className="tag-rows" aria-label={t("settings.tags")}>
          {items.map((tag) =>
            editing === tag.id ? (
              <RenameRow
                key={tag.id}
                workspaceId={workspaceId}
                tag={tag}
                onDone={() => {
                  setEditing(null);
                }}
                onError={setError}
              />
            ) : (
              <li key={tag.id} className="tag-row">
                <span className="tag-pill">{tag.name}</span>
                {canEdit ? (
                  <span className="tag-row-actions">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={t("tagSettings.rename", { name: tag.name })}
                      onPress={() => {
                        setError(null);
                        setEditing(tag.id);
                      }}
                    >
                      <Pencil size={13} aria-hidden="true" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={t("tagSettings.delete", { name: tag.name })}
                      isDisabled={remove.isPending}
                      onPress={() => {
                        setDeleting(tag);
                      }}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </Button>
                  </span>
                ) : null}
              </li>
            ),
          )}
        </ul>
      )}
      <ConfirmDialog
        isOpen={deleting !== null}
        title={t("tagSettings.deleteTitle")}
        confirmLabel={t("tagSettings.deleteConfirm")}
        message={t("tagSettings.deleteMessage", { name: deleting?.name ?? "" })}
        onConfirm={confirmDelete}
        onCancel={() => {
          setDeleting(null);
        }}
      />
    </section>
  );
}

function RenameRow({
  workspaceId,
  tag,
  onDone,
  onError,
}: {
  workspaceId: string;
  tag: Tag;
  onDone: () => void;
  onError: (error: MessageId | null) => void;
}) {
  const t = useT();
  const toast = useToast();
  const rename = useRenameTag(workspaceId);
  const [name, setName] = useState(tag.name);
  const input = useRef<HTMLInputElement>(null);
  const inputId = `tag-rename-${tag.id}`;
  // The rename was just asked for: its field takes focus.
  useEffect(() => {
    input.current?.focus();
  }, []);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const next = name.trim();
    if (!next || next === tag.name) {
      onDone();
      return;
    }
    onError(null);
    rename.mutate(
      { id: tag.id, version: tag.version, name: next },
      {
        onSuccess: () => {
          toast(t("tagSettings.renamed"));
          onDone();
        },
        onError: (problem) => {
          onError(failure(problem));
        },
      },
    );
  };

  return (
    <li className="tag-row editing">
      <form className="tag-new" onSubmit={submit}>
        <div className="form-field">
          <label htmlFor={inputId} className="form-label">
            {t("tagSettings.renameLabel", { name: tag.name })}
          </label>
          <input
            ref={input}
            id={inputId}
            className="form-input"
            value={name}
            maxLength={50}
            onChange={(event) => {
              setName(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") onDone();
            }}
          />
        </div>
        <Button type="submit" variant="primary" isDisabled={rename.isPending}>
          {t("tagSettings.save")}
        </Button>
        <Button onPress={onDone}>{t("confirm.cancel")}</Button>
      </form>
    </li>
  );
}
