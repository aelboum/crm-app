import { Pencil, Plus, Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  type EmailTemplate,
  renderTemplate,
  useDeleteTemplate,
  useEmailTemplates,
  useSaveTemplate,
} from "../api/emailTemplates";
import { LoadError, Loading } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Email templates (decision P7-T): the list under Campaigns, its editor, and
 * the pickers that copy a template into a campaign draft or fill it in for
 * a conversation's contact in the reply composer. Nothing here sends.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_template") return "templates.error.invalid";
    if (error.code === "template_name_taken") return "templates.error.taken";
    if (error.code === "template_limit") return "templates.error.limit";
    if (error.code === "stale_version") return "templates.error.stale";
    if (error.status === 403) return "templates.error.forbidden";
  }
  return "templates.error.generic";
}

function TemplateEditor({
  workspaceId,
  template,
  onClose,
}: {
  workspaceId: string;
  template: EmailTemplate | null;
  onClose: () => void;
}) {
  const t = useT();
  const save = useSaveTemplate(workspaceId);
  const [name, setName] = useState(template?.name ?? "");
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    save.mutate(
      { template, body: { name, subject, body } },
      { onSuccess: onClose },
    );
  };
  return (
    <Dialog
      isOpen
      title={t(template ? "templates.edit" : "templates.new")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button
            variant="primary"
            type="submit"
            form="template-form"
            isDisabled={
              save.isPending || !name.trim() || !subject.trim() || !body.trim()
            }
          >
            {t("templates.save")}
          </Button>
        </>
      }
    >
      <form id="template-form" className="form-grid" onSubmit={submit}>
        <label className="field wide">
          <span className="field-label">{t("templates.field.name")}</span>
          <input
            className="form-input"
            value={name}
            maxLength={120}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </label>
        <label className="field wide">
          <span className="field-label">{t("templates.field.subject")}</span>
          <input
            className="form-input"
            value={subject}
            maxLength={200}
            onChange={(event) => {
              setSubject(event.target.value);
            }}
          />
        </label>
        <label className="field wide">
          <span className="field-label">{t("templates.field.body")}</span>
          <textarea
            className="form-input campaign-body"
            rows={8}
            maxLength={18000}
            value={body}
            onChange={(event) => {
              setBody(event.target.value);
            }}
          />
        </label>
        <p className="muted wide">
          {t("campaigns.placeholders", {
            first: "{{first_name}}",
            last: "{{last_name}}",
          })}
        </p>
        {save.error ? (
          <p className="notice error wide" role="alert">
            {t(failure(save.error))}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

/** Campaigns › Templates: every role reads; managers add, edit, delete. */
export function TemplatesPanel({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}) {
  const t = useT();
  const templates = useEmailTemplates(workspaceId);
  const remove = useDeleteTemplate(workspaceId);
  const [editing, setEditing] = useState<EmailTemplate | "new" | null>(null);
  return (
    <section
      className="records-card templates-card"
      aria-labelledby="templates-title"
    >
      <div className="home-card-head">
        <h2 id="templates-title" className="home-card-title">
          {t("templates.title")}
        </h2>
        {canManage ? (
          <Button
            size="sm"
            onPress={() => {
              setEditing("new");
            }}
          >
            <Plus size={13} aria-hidden="true" />
            {t("templates.new")}
          </Button>
        ) : null}
      </div>
      <p className="muted">{t("templates.intro")}</p>
      {templates.isPending ? (
        <Loading />
      ) : templates.isError ? (
        <LoadError
          error={templates.error}
          onRetry={() => void templates.refetch()}
        />
      ) : templates.data.items.length === 0 ? (
        <p className="muted">{t("templates.empty")}</p>
      ) : (
        <ul className="template-list">
          {templates.data.items.map((template) => (
            <li key={template.id} className="template-item">
              <span className="template-name">{template.name}</span>
              <span className="muted">{template.subject}</span>
              {canManage ? (
                <span className="template-actions">
                  <Button
                    size="sm"
                    aria-label={t("templates.editNamed", {
                      name: template.name,
                    })}
                    onPress={() => {
                      setEditing(template);
                    }}
                  >
                    <Pencil size={13} aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    aria-label={t("templates.deleteNamed", {
                      name: template.name,
                    })}
                    isDisabled={remove.isPending}
                    onPress={() => {
                      remove.mutate({ id: template.id });
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {remove.error ? (
        <p className="notice error" role="alert">
          {t(failure(remove.error))}
        </p>
      ) : null}
      {editing ? (
        <TemplateEditor
          workspaceId={workspaceId}
          template={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
    </section>
  );
}

/**
 * A select that hands over the chosen template: as stored (campaign
 * drafts) or filled in for `contactId` (the reply composer).
 */
export function TemplatePicker({
  workspaceId,
  contactId,
  onPick,
}: {
  workspaceId: string;
  contactId?: string;
  onPick: (subject: string, body: string) => void;
}) {
  const t = useT();
  const templates = useEmailTemplates(workspaceId);
  const [problem, setProblem] = useState(false);
  const items = templates.data?.items ?? [];
  if (!items.length) return null;
  return (
    <span className="template-picker">
      <select
        className="form-input"
        aria-label={t("templates.use")}
        value=""
        onChange={(event) => {
          const chosen = items.find((item) => item.id === event.target.value);
          if (!chosen) return;
          setProblem(false);
          if (!contactId) {
            onPick(chosen.subject, chosen.body);
            return;
          }
          renderTemplate(workspaceId, chosen.id, contactId)
            .then((filled) => {
              onPick(filled.subject, filled.body);
            })
            .catch(() => {
              setProblem(true);
            });
        }}
      >
        <option value="">{t("templates.use")}</option>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      {problem ? (
        <span className="notice error" role="alert">
          {t("templates.error.render")}
        </span>
      ) : null}
    </span>
  );
}
