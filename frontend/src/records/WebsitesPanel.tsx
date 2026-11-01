import { Code2, Globe, Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import type { Form } from "../api/forms";
import {
  useCreateWebsite,
  useDeleteWebsite,
  useUpdateWebsite,
  useWebsites,
  type Website,
} from "../api/websites";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { embedSnippet } from "./embedSnippet";

/*
 * Websites outside LeadStack (decision P12-W): where the workspace's
 * published forms may be embedded. A site's pages may submit forms only
 * from the addresses listed here; everything else is refused by the
 * server, whatever the embed code says.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_website") return "websites.error.invalid";
    if (error.code === "stale_version") return "websites.error.stale";
    if (error.code === "website_limit") return "websites.error.limit";
    if (error.status === 403) return "websites.error.forbidden";
  }
  return "websites.error.generic";
}

export function WebsitesPanel({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}) {
  const t = useT();
  const sites = useWebsites(workspaceId);
  const create = useCreateWebsite(workspaceId);
  const update = useUpdateWebsite(workspaceId);
  const remove = useDeleteWebsite(workspaceId);
  const [name, setName] = useState("");
  const [origins, setOrigins] = useState("");
  const problem = create.error ?? update.error ?? remove.error;

  const add = (event: SyntheticEvent) => {
    event.preventDefault();
    create.mutate(
      {
        name,
        origins: origins
          .split(/[\s,]+/)
          .map((value) => value.trim())
          .filter(Boolean),
      },
      {
        onSuccess: () => {
          setName("");
          setOrigins("");
        },
      },
    );
  };

  return (
    <section className="records-card websites" aria-label={t("websites.title")}>
      <h2 className="websites-title">
        <Globe size={16} aria-hidden="true" /> {t("websites.title")}
      </h2>
      <p className="muted">{t("websites.intro")}</p>
      {sites.isPending ? (
        <Loading />
      ) : sites.isError ? (
        <LoadError error={sites.error} onRetry={() => void sites.refetch()} />
      ) : sites.data.items.length === 0 ? (
        <p className="muted">{t("websites.empty")}</p>
      ) : (
        <ul className="website-items">
          {sites.data.items.map((site: Website) => (
            <li key={site.id} className="website-item">
              <span className="website-name">{site.name}</span>
              <Badge tone={site.status === "active" ? "success" : "neutral"}>
                {t(
                  site.status === "active"
                    ? "websites.active"
                    : "websites.disabled",
                )}
              </Badge>
              <span className="muted website-origins">
                {site.origins.join(", ")}
              </span>
              {canManage ? (
                <span className="website-actions">
                  <Button
                    size="sm"
                    isDisabled={update.isPending}
                    onPress={() => {
                      update.mutate({
                        id: site.id,
                        version: site.version,
                        changes: {
                          status:
                            site.status === "active" ? "disabled" : "active",
                        },
                      });
                    }}
                  >
                    {t(
                      site.status === "active"
                        ? "websites.disable"
                        : "websites.enable",
                    )}
                  </Button>
                  <Button
                    size="sm"
                    aria-label={t("websites.remove", { name: site.name })}
                    isDisabled={remove.isPending}
                    onPress={() => {
                      remove.mutate({ id: site.id });
                    }}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canManage ? (
        <form className="website-form" onSubmit={add}>
          <label className="field">
            <span className="field-label">{t("websites.name")}</span>
            <input
              className="form-input"
              value={name}
              maxLength={120}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          <label className="field">
            <span className="field-label">{t("websites.origins")}</span>
            <input
              className="form-input"
              value={origins}
              placeholder="https://www.example.com"
              onChange={(event) => {
                setOrigins(event.target.value);
              }}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={create.isPending || !name.trim() || !origins.trim()}
          >
            {t("websites.add")}
          </Button>
        </form>
      ) : null}
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </section>
  );
}

export function EmbedButton({
  workspaceId,
  form,
}: {
  workspaceId: string;
  form: Form;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const code = embedSnippet(
    {
      key: form.public_key,
      name: form.name,
      fields: form.fields.map((field) => ({
        key: field.key,
        label: field.label,
        type: field.type,
        required: field.required,
        options: field.options ?? null,
      })),
      consent_text: form.consent_text ?? null,
      thank_you: form.thank_you,
    },
    window.location.origin,
    workspaceId,
  );
  return (
    <>
      <Button
        size="sm"
        onPress={() => {
          setOpen(true);
        }}
      >
        <Code2 size={14} aria-hidden="true" />
        {t("websites.embed")}
      </Button>
      {open ? (
        <Dialog
          isOpen
          title={t("websites.embedTitle")}
          onClose={() => {
            setOpen(false);
          }}
          actions={
            <>
              <Button
                onPress={() => {
                  void navigator.clipboard.writeText(code);
                }}
              >
                {t("websites.copyCode")}
              </Button>
              <Button
                variant="primary"
                onPress={() => {
                  setOpen(false);
                }}
              >
                {t("websites.close")}
              </Button>
            </>
          }
        >
          <p>{t("websites.embedIntro")}</p>
          <label className="field">
            <span className="field-label">{t("websites.code")}</span>
            <textarea
              className="form-input mono embed-code"
              readOnly
              value={code}
              rows={12}
            />
          </label>
        </Dialog>
      ) : null}
    </>
  );
}
