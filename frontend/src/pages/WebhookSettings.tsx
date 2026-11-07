import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  type AddedEndpoint,
  type Endpoint,
  useAddWebhook,
  useRemoveWebhook,
  useWebhooks,
} from "../api/webhooks";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { When } from "../records/parts";

/*
 * Settings › Integrations › Webhooks (decision P12-H). An endpoint gets
 * every event the list names, signed with its own key, shown once when it
 * is added. Recent deliveries show their status and attempts, never what
 * was sent.
 */

const TONE: Record<string, Tone> = {
  pending: "pending",
  published: "success",
  dead_lettered: "risk",
};

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_webhook_url") return "webhooks.error.url";
    if (error.code === "webhook_limit") return "webhooks.error.limit";
    if (error.code === "webhooks_not_configured")
      return "webhooks.error.notConfigured";
    if (error.code === "integrations_unavailable")
      return "integrations.error.unavailable";
    if (error.status === 403) return "integrations.error.forbidden";
  }
  return "integrations.error.generic";
}

function status(value: string): MessageId {
  if (value === "published") return "webhooks.status.published";
  if (value === "dead_lettered") return "webhooks.status.failed";
  return "webhooks.status.pending";
}

function EndpointItem({
  endpoint,
  onRemove,
  removing,
}: {
  endpoint: Endpoint;
  onRemove: () => void;
  removing: boolean;
}) {
  const t = useT();
  return (
    <li className="domain-item">
      <div className="domain-head">
        <span className="domain-host mono">{endpoint.url}</span>
        <Button
          size="sm"
          aria-label={t("webhooks.remove", { url: endpoint.url })}
          isDisabled={removing}
          onPress={onRemove}
        >
          {t("webhooks.removeShort")}
        </Button>
      </div>
      {endpoint.deliveries.length ? (
        <ul
          className="integration-keys"
          aria-label={t("webhooks.deliveriesOf", { url: endpoint.url })}
        >
          {endpoint.deliveries.map((delivery) => (
            <li key={delivery.id} className="integration-key">
              <span className="mono">{delivery.event}</span>
              <Badge tone={TONE[delivery.status] ?? "neutral"}>
                {t(status(delivery.status))}
              </Badge>
              <span className="muted">
                {t("webhooks.attempts", { count: delivery.attempts })} ·{" "}
                <When value={delivery.created_at} />
              </span>
              {delivery.last_error ? (
                <span className="muted">{delivery.last_error}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("webhooks.noDeliveries")}</p>
      )}
    </li>
  );
}

export function WebhookSettings({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const webhooks = useWebhooks(workspaceId);
  const add = useAddWebhook(workspaceId);
  const remove = useRemoveWebhook(workspaceId);
  const [url, setUrl] = useState("");
  const [added, setAdded] = useState<AddedEndpoint | null>(null);
  const problem = add.error ?? remove.error;

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    add.mutate(
      { url },
      {
        onSuccess: (result) => {
          setAdded(result);
          setUrl("");
        },
      },
    );
  };

  return (
    <section className="records-card domains" aria-label={t("webhooks.title")}>
      <h2 className="settings-card-title">{t("webhooks.title")}</h2>
      <p className="muted">{t("webhooks.intro")}</p>
      {webhooks.data ? (
        <p className="muted">
          {t("webhooks.events")}{" "}
          <span className="mono">{webhooks.data.events.join(", ")}</span>
        </p>
      ) : null}
      {added ? (
        <div className="notice integration-secret" role="status">
          <p>{t("webhooks.shownOnce", { url: added.endpoint.url })}</p>
          <p className="mono integration-secret-value">
            {added.signing_secret}
          </p>
          <p className="muted">{t("webhooks.howToVerify")}</p>
          <Button
            size="sm"
            onPress={() => {
              setAdded(null);
            }}
          >
            {t("integrations.copiedIt")}
          </Button>
        </div>
      ) : null}
      {webhooks.isPending ? (
        <Loading />
      ) : webhooks.isError ? (
        <LoadError
          error={webhooks.error}
          onRetry={() => void webhooks.refetch()}
        />
      ) : webhooks.data.items.length === 0 ? (
        <p className="muted">{t("webhooks.empty")}</p>
      ) : (
        <ul className="domain-items">
          {webhooks.data.items.map((endpoint) => (
            <EndpointItem
              key={endpoint.id}
              endpoint={endpoint}
              removing={remove.isPending}
              onRemove={() => {
                remove.mutate({ id: endpoint.id });
              }}
            />
          ))}
        </ul>
      )}
      <form className="domain-form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">{t("webhooks.url")}</span>
          <input
            className="form-input"
            type="url"
            value={url}
            maxLength={2000}
            placeholder="https://hooks.example.com/leadstack"
            onChange={(event) => {
              setUrl(event.target.value);
            }}
          />
        </label>
        <Button
          type="submit"
          size="sm"
          variant="primary"
          isDisabled={add.isPending || !url.trim()}
        >
          {t("webhooks.add")}
        </Button>
      </form>
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </section>
  );
}
