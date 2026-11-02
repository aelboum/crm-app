import { Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  type SendingDomain,
  useAddIdentity,
  useRegisterDomain,
  useRemoveIdentity,
  useRemoveSendingDomain,
  useSendingDomains,
  useVerifyDomain,
} from "../api/sendingDomains";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Settings › Sending domains (decision P6-D): domains the workspace owns
 * to send conversation and campaign email from, the DNS records Resend
 * gave for each (shown exactly), their verification state, and the sender
 * addresses on them. An address is used only while its domain is
 * verified; otherwise mail goes from LeadStack's own address.
 */

const TONE: Record<SendingDomain["status"], Tone> = {
  not_registered: "neutral",
  not_started: "pending",
  pending: "pending",
  verified: "success",
  failed: "risk",
  temporary_failure: "pending",
  unknown: "neutral",
  expired: "risk",
};

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_sending_domain") return "sending.error.invalid";
    if (error.code === "domain_in_use") return "sending.error.inUse";
    if (error.code === "identity_conflict")
      return "sending.error.identityConflict";
    if (error.code === "sending_domain_limit") return "sending.error.limit";
    if (error.code === "stale_version") return "sending.error.stale";
    if (error.status === 403) return "sending.error.forbidden";
  }
  return "sending.error.generic";
}

function DomainCard({
  workspaceId,
  domain,
  canEdit,
}: {
  workspaceId: string;
  domain: SendingDomain;
  canEdit: boolean;
}) {
  const t = useT();
  const verify = useVerifyDomain(workspaceId);
  const remove = useRemoveSendingDomain(workspaceId);
  const addIdentity = useAddIdentity(workspaceId);
  const removeIdentity = useRemoveIdentity(workspaceId);
  const [local, setLocal] = useState("");
  const [conversation, setConversation] = useState(true);
  const [campaign, setCampaign] = useState(false);
  const problem =
    verify.error ?? remove.error ?? addIdentity.error ?? removeIdentity.error;

  const add = (event: SyntheticEvent) => {
    event.preventDefault();
    addIdentity.mutate(
      {
        domainId: domain.id,
        body: {
          local_part: local,
          for_conversation: conversation,
          for_campaign: campaign,
          default_conversation: conversation,
          default_campaign: campaign,
        },
      },
      {
        onSuccess: () => {
          setLocal("");
        },
      },
    );
  };

  return (
    <li className="sending-domain">
      <div className="domain-head">
        <span className="domain-host">{domain.domain}</span>
        <Badge tone={TONE[domain.status]}>
          {t(`sending.status.${domain.status}` as MessageId)}
        </Badge>
        {canEdit ? (
          <span className="domain-actions">
            {domain.status !== "verified" && domain.status !== "expired" ? (
              <Button
                size="sm"
                isDisabled={verify.isPending}
                onPress={() => {
                  verify.mutate({ id: domain.id, version: domain.version });
                }}
              >
                {t("sending.verify")}
              </Button>
            ) : null}
            <Button
              size="sm"
              aria-label={t("sending.remove", { domain: domain.domain })}
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
      {domain.claim_expires_at && domain.status !== "verified" ? (
        <p className="muted">
          {t("sending.claimExpires", {
            date: new Date(domain.claim_expires_at).toLocaleDateString(),
          })}
        </p>
      ) : null}
      {domain.last_error ? (
        <p className="muted">
          {t(`sending.lastError.${domain.last_error}` as MessageId)}
        </p>
      ) : null}
      {domain.records.length ? (
        <table className="sending-records">
          <caption className="sr-only">
            {t("sending.recordsCaption", { domain: domain.domain })}
          </caption>
          <thead>
            <tr>
              <th scope="col">{t("sending.record.type")}</th>
              <th scope="col">{t("sending.record.name")}</th>
              <th scope="col">{t("sending.record.value")}</th>
              <th scope="col">{t("sending.record.status")}</th>
            </tr>
          </thead>
          <tbody>
            {domain.records.map((record, index) => (
              <tr key={index}>
                <td>
                  {record.type}
                  {record.priority === null
                    ? ""
                    : ` ${String(record.priority)}`}
                </td>
                <td className="mono">{record.name}</td>
                <td className="mono">{record.value}</td>
                <td>{t(`sending.status.${record.status}` as MessageId)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {domain.identities.length ? (
        <ul className="sending-identities" aria-label={t("sending.identities")}>
          {domain.identities.map((identity) => (
            <li key={identity.id} className="sending-identity">
              <span className="mono">{identity.address}</span>
              <span className="muted">
                {[
                  identity.for_conversation
                    ? t("sending.forConversation")
                    : null,
                  identity.for_campaign ? t("sending.forCampaign") : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              <Badge tone={identity.usable ? "success" : "neutral"}>
                {t(identity.usable ? "sending.usable" : "sending.notUsable")}
              </Badge>
              {canEdit ? (
                <Button
                  size="sm"
                  aria-label={t("sending.removeIdentity", {
                    address: identity.address,
                  })}
                  isDisabled={removeIdentity.isPending}
                  onPress={() => {
                    removeIdentity.mutate({ id: identity.id });
                  }}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {canEdit ? (
        <form className="sending-identity-form" onSubmit={add}>
          <label className="field">
            <span className="field-label">
              {t("sending.localPart", { domain: domain.domain })}
            </span>
            <input
              className="form-input"
              value={local}
              maxLength={64}
              onChange={(event) => {
                setLocal(event.target.value);
              }}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={conversation}
              onChange={(event) => {
                setConversation(event.target.checked);
              }}
            />
            {t("sending.forConversation")}
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={campaign}
              onChange={(event) => {
                setCampaign(event.target.checked);
              }}
            />
            {t("sending.forCampaign")}
          </label>
          <Button
            type="submit"
            size="sm"
            isDisabled={
              addIdentity.isPending ||
              !local.trim() ||
              !(conversation || campaign)
            }
          >
            {t("sending.addIdentity")}
          </Button>
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

export function SendingDomainSettings({
  workspaceId,
  canEdit,
}: {
  workspaceId: string;
  canEdit: boolean;
}) {
  const t = useT();
  const domains = useSendingDomains(workspaceId);
  const register = useRegisterDomain(workspaceId);
  const [name, setName] = useState("");

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    register.mutate(
      { domain: name },
      {
        onSuccess: () => {
          setName("");
        },
      },
    );
  };

  return (
    <section className="records-card domains" aria-label={t("sending.title")}>
      <p className="muted">{t("sending.intro")}</p>
      {domains.data && !domains.data.provider_configured ? (
        <p className="notice" role="note">
          {t("sending.noProvider")}
        </p>
      ) : null}
      {domains.isPending ? (
        <Loading />
      ) : domains.isError ? (
        <LoadError
          error={domains.error}
          onRetry={() => void domains.refetch()}
        />
      ) : domains.data.items.length === 0 ? (
        <p className="muted">{t("sending.empty")}</p>
      ) : (
        <ul className="domain-items">
          {domains.data.items.map((domain) => (
            <DomainCard
              key={domain.id}
              workspaceId={workspaceId}
              domain={domain}
              canEdit={canEdit}
            />
          ))}
        </ul>
      )}
      {canEdit ? (
        <form className="domain-form" onSubmit={submit}>
          <label className="field">
            <span className="field-label">{t("sending.domain")}</span>
            <input
              className="form-input"
              value={name}
              placeholder="your-company.com"
              maxLength={253}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={register.isPending || !name.trim()}
          >
            {t("sending.add")}
          </Button>
        </form>
      ) : null}
      {register.error ? (
        <p className="notice error" role="alert">
          {t(failure(register.error))}
        </p>
      ) : null}
    </section>
  );
}
