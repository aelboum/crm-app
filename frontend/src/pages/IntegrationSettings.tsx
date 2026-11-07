import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  EXPIRY_DAYS,
  type Integration,
  type IntegrationRole,
  type IssuedKey,
  MAX_KEYS,
  useCreateIntegration,
  useDisableIntegration,
  useIntegrations,
  useIssueKey,
  useRevokeKey,
} from "../api/integrations";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { When } from "../records/parts";

/*
 * Settings › Integrations (decision P12-K). An integration lets another
 * tool read, create and update contacts, companies, deals and tasks with an
 * API key, as a Member or Read-only, never more. A key is shown once, right
 * after it is issued; LeadStack keeps only a fingerprint of it. Disabling an
 * integration revokes its keys and cannot be undone.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "duplicate_integration")
      return "integrations.error.duplicate";
    if (error.code === "integration_limit") return "integrations.error.limit";
    if (error.code === "integrations_unavailable")
      return "integrations.error.unavailable";
    if (error.code === "invalid_integration")
      return "integrations.error.invalid";
    if (error.status === 403) return "integrations.error.forbidden";
  }
  return "integrations.error.generic";
}

const ROLE_LABEL: Record<IntegrationRole, MessageId> = {
  Member: "integrations.role.member",
  "Read-only": "integrations.role.readOnly",
};

function IssuedSecret({
  issued,
  onDone,
}: {
  issued: IssuedKey;
  onDone: () => void;
}) {
  const t = useT();
  return (
    <div className="notice integration-secret" role="status">
      <p>{t("integrations.secretOnce", { name: issued.key.name })}</p>
      <p className="mono integration-secret-value">{issued.secret}</p>
      <p className="muted">{t("integrations.secretHow")}</p>
      <Button size="sm" onPress={onDone}>
        {t("integrations.secretDone")}
      </Button>
    </div>
  );
}

function IntegrationItem({
  workspaceId,
  integration,
}: {
  workspaceId: string;
  integration: Integration;
}) {
  const t = useT();
  const issue = useIssueKey(workspaceId);
  const revoke = useRevokeKey(workspaceId);
  const disable = useDisableIntegration(workspaceId);
  const [keyName, setKeyName] = useState("");
  const [expiry, setExpiry] = useState("90");
  const [issued, setIssued] = useState<IssuedKey | null>(null);
  const [confirming, setConfirming] = useState(false);
  const active = integration.status === "active";
  const problem = issue.error ?? revoke.error ?? disable.error;
  const keys = integration.keys.filter((key) => key.revoked_at === null);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    issue.mutate(
      {
        id: integration.id,
        name: keyName,
        expires_in_days: expiry === "never" ? null : Number(expiry),
      },
      {
        onSuccess: (result) => {
          setIssued(result);
          setKeyName("");
        },
      },
    );
  };

  return (
    <li className="domain-item">
      <div className="domain-head">
        <span className="domain-host">{integration.name}</span>
        <Badge tone={active ? "success" : "neutral"}>
          {t(
            active
              ? "integrations.status.active"
              : "integrations.status.disabled",
          )}
        </Badge>
        <span className="muted">
          {integration.role
            ? t(ROLE_LABEL[integration.role])
            : t("integrations.noRole")}
        </span>
      </div>
      {issued ? (
        <IssuedSecret
          issued={issued}
          onDone={() => {
            setIssued(null);
          }}
        />
      ) : null}
      {keys.length ? (
        <ul
          className="integration-keys"
          aria-label={t("integrations.keysOf", { name: integration.name })}
        >
          {keys.map((key) => (
            <li key={key.id} className="integration-key">
              <span>{key.name}</span>
              <span className="muted">
                {key.expires_at ? (
                  <>
                    {t("integrations.expires")} <When value={key.expires_at} />
                  </>
                ) : (
                  t("integrations.neverExpires")
                )}
              </span>
              <Button
                size="sm"
                aria-label={t("integrations.revoke", { name: key.name })}
                isDisabled={revoke.isPending}
                onPress={() => {
                  revoke.mutate({ id: integration.id, keyId: key.id });
                }}
              >
                {t("integrations.revokeShort")}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("integrations.noKeys")}</p>
      )}
      {active ? (
        <form className="domain-form" onSubmit={submit}>
          <label className="field">
            <span className="field-label">{t("integrations.keyName")}</span>
            <input
              className="form-input"
              value={keyName}
              maxLength={100}
              placeholder={t("integrations.keyPlaceholder")}
              onChange={(event) => {
                setKeyName(event.target.value);
              }}
            />
          </label>
          <label className="field">
            <span className="field-label">{t("integrations.expiry")}</span>
            <select
              className="form-input"
              value={expiry}
              onChange={(event) => {
                setExpiry(event.target.value);
              }}
            >
              {EXPIRY_DAYS.map((days) => (
                <option key={days} value={String(days)}>
                  {t("integrations.days", { count: days })}
                </option>
              ))}
              <option value="never">{t("integrations.neverExpires")}</option>
            </select>
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={
              issue.isPending || !keyName.trim() || keys.length >= MAX_KEYS
            }
          >
            {t("integrations.issue")}
          </Button>
          {confirming ? (
            <Button
              size="sm"
              variant="destructive"
              isDisabled={disable.isPending}
              onPress={() => {
                disable.mutate({ id: integration.id });
              }}
            >
              {t("integrations.disableConfirm", { name: integration.name })}
            </Button>
          ) : (
            <Button
              size="sm"
              onPress={() => {
                setConfirming(true);
              }}
            >
              {t("integrations.disable")}
            </Button>
          )}
        </form>
      ) : null}
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </li>
  );
}

export function IntegrationSettings({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}) {
  const t = useT();
  const integrations = useIntegrations(workspaceId, canManage);
  const create = useCreateIntegration(workspaceId);
  const [name, setName] = useState("");
  const [role, setRole] = useState<IntegrationRole>("Member");

  if (!canManage) {
    return (
      <section className="records-card" aria-label={t("settings.integrations")}>
        <p className="muted">{t("integrations.forbidden")}</p>
      </section>
    );
  }

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    create.mutate(
      { name, role },
      {
        onSuccess: () => {
          setName("");
        },
      },
    );
  };

  return (
    <section
      className="records-card domains"
      aria-label={t("settings.integrations")}
    >
      <p className="muted">{t("integrations.intro")}</p>
      {integrations.isPending ? (
        <Loading />
      ) : integrations.isError ? (
        <LoadError
          error={integrations.error}
          onRetry={() => void integrations.refetch()}
        />
      ) : integrations.data.items.length === 0 ? (
        <p className="muted">{t("integrations.empty")}</p>
      ) : (
        <ul className="domain-items">
          {integrations.data.items.map((integration) => (
            <IntegrationItem
              key={integration.id}
              workspaceId={workspaceId}
              integration={integration}
            />
          ))}
        </ul>
      )}
      <form className="domain-form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">{t("integrations.name")}</span>
          <input
            className="form-input"
            value={name}
            maxLength={100}
            placeholder={t("integrations.namePlaceholder")}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </label>
        <label className="field">
          <span className="field-label">{t("integrations.role")}</span>
          <select
            className="form-input"
            value={role}
            onChange={(event) => {
              setRole(event.target.value as IntegrationRole);
            }}
          >
            <option value="Member">{t("integrations.role.member")}</option>
            <option value="Read-only">{t("integrations.role.readOnly")}</option>
          </select>
        </label>
        <Button
          type="submit"
          size="sm"
          variant="primary"
          isDisabled={create.isPending || !name.trim()}
        >
          {t("integrations.add")}
        </Button>
      </form>
      {create.error ? (
        <p className="notice error" role="alert">
          {t(failure(create.error))}
        </p>
      ) : null}
    </section>
  );
}
