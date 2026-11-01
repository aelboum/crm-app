import { Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  type Domain,
  useAddDomain,
  useCheckDomain,
  useDomains,
  useRemoveDomain,
} from "../api/domains";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { When } from "../records/parts";

/*
 * Settings › Domains (decision P12-D): hostnames the workspace owns for its
 * hosted forms and booking pages. Each claim shows the exact DNS TXT record
 * to publish; "Check now" looks it up. Serving pages on a verified domain
 * also needs the platform's web server to accept it, which is set up
 * separately; the screen says so.
 */

const TONE: Record<Domain["status"], Tone> = {
  pending: "pending",
  verified: "success",
  lapsed: "risk",
};

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_domain") return "domains.error.invalid";
    if (error.code === "domain_already_added") return "domains.error.duplicate";
    if (error.code === "domain_limit") return "domains.error.limit";
    if (error.code === "claim_expired") return "domains.error.expired";
    if (error.code === "stale_version") return "domains.error.stale";
    if (error.status === 403) return "domains.error.forbidden";
  }
  return "domains.error.generic";
}

export function DomainSettings({
  workspaceId,
  canEdit,
}: {
  workspaceId: string;
  canEdit: boolean;
}) {
  const t = useT();
  const domains = useDomains(workspaceId);
  const add = useAddDomain(workspaceId);
  const check = useCheckDomain(workspaceId);
  const remove = useRemoveDomain(workspaceId);
  const [hostname, setHostname] = useState("");
  const problem = add.error ?? check.error ?? remove.error;

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    add.mutate(
      { hostname },
      {
        onSuccess: () => {
          setHostname("");
        },
      },
    );
  };

  return (
    <section className="records-card domains" aria-label={t("domains.title")}>
      <p className="muted">{t("domains.intro")}</p>
      <p className="notice" role="note">
        {t("domains.serving")}
      </p>
      {domains.isPending ? (
        <Loading />
      ) : domains.isError ? (
        <LoadError
          error={domains.error}
          onRetry={() => void domains.refetch()}
        />
      ) : domains.data.items.length === 0 ? (
        <p className="muted">{t("domains.empty")}</p>
      ) : (
        <ul className="domain-items">
          {domains.data.items.map((domain) => (
            <li key={domain.id} className="domain-item">
              <div className="domain-head">
                <span className="domain-host">{domain.hostname}</span>
                <Badge tone={TONE[domain.status]}>
                  {t(`domains.status.${domain.status}` as MessageId)}
                </Badge>
                {canEdit ? (
                  <span className="domain-actions">
                    {domain.status !== "verified" ? (
                      <Button
                        size="sm"
                        isDisabled={check.isPending}
                        onPress={() => {
                          check.mutate({
                            id: domain.id,
                            version: domain.version,
                          });
                        }}
                      >
                        {t("domains.check")}
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      aria-label={t("domains.remove", {
                        hostname: domain.hostname,
                      })}
                      isDisabled={remove.isPending}
                      onPress={() => {
                        remove.mutate({ id: domain.id });
                      }}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </Button>
                  </span>
                ) : null}
              </div>
              {domain.status !== "verified" ? (
                <dl className="domain-record">
                  <dt>{t("domains.recordType")}</dt>
                  <dd className="mono">TXT</dd>
                  <dt>{t("domains.recordName")}</dt>
                  <dd className="mono">{domain.record_name}</dd>
                  <dt>{t("domains.recordValue")}</dt>
                  <dd className="mono">{domain.record_value}</dd>
                </dl>
              ) : null}
              {domain.last_error ? (
                <p className="muted">
                  {t(`domains.lastError.${domain.last_error}` as MessageId)}
                </p>
              ) : null}
              {domain.expires_at ? (
                <p className="muted">
                  {t("domains.expires")} <When value={domain.expires_at} />
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        <form className="domain-form" onSubmit={submit}>
          <label className="field">
            <span className="field-label">{t("domains.hostname")}</span>
            <input
              className="form-input"
              value={hostname}
              placeholder="forms.your-company.com"
              maxLength={253}
              onChange={(event) => {
                setHostname(event.target.value);
              }}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={add.isPending || !hostname.trim()}
          >
            {t("domains.add")}
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
