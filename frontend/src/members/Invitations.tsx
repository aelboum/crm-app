import { Copy, Mail } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import type { Access } from "../api/client";
import {
  type CreatedInvitation,
  type Invitation,
  type InvitationRole,
  useCreateInvitation,
  useRevokeInvitation,
} from "../api/invitations";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { When } from "../records/parts";

/*
 * Inviting members (PHASE2-PLAN.md §8.2; decisions Q4, Q5, P2-F). In manual
 * mode the link is shown once, in the dialog that created it, labelled as
 * not sent; it is never stored or shown again. In email mode the product
 * says only that the email provider accepted it, never that it arrived.
 */

const ROLE_CHOICES: readonly InvitationRole[] = ["Member", "Read-only", "Admin", "Owner"];

const REFUSAL: Partial<Record<string, MessageId>> = {
  duplicate_invitation: "invite.error.duplicate",
  role_not_allowed: "invite.error.ownerOnly",
  too_many_pending: "invite.error.tooMany",
  delivery_failed: "invite.error.delivery",
  delivery_not_configured: "invite.error.delivery",
  invalid_email: "invite.error.email",
};

export function InviteDialog({
  workspaceId,
  access,
  onClose,
}: {
  workspaceId: string;
  access: Access;
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const create = useCreateInvitation(workspaceId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitationRole>("Member");
  const [created, setCreated] = useState<CreatedInvitation | null>(null);
  const [error, setError] = useState<MessageId | null>(null);
  const roles = ROLE_CHOICES.filter((choice) => choice !== "Owner" || access.actions.manage_owners === true);

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (!email.trim()) {
      setError("invite.error.email");
      return;
    }
    create.mutate(
      { email, role },
      {
        onSuccess: (result) => {
          if (result.link) setCreated(result);
          else {
            toast(t("invite.emailed"));
            onClose();
          }
        },
        onError: (failure) => {
          const known = failure.code ? REFUSAL[failure.code] : undefined;
          setError(known ?? (failure.status === 422 ? "invite.error.email" : "records.error.generic"));
        },
      },
    );
  }

  if (created?.link) {
    const link = created.link;
    return (
      <Dialog
        isOpen
        title={t("invite.linkTitle")}
        onClose={onClose}
        actions={
          <Button variant="primary" onPress={onClose}>
            {t("invite.done")}
          </Button>
        }
      >
        <p className="notice info">{t("invite.notSent")}</p>
        <p className="form-hint">
          {t("invite.linkFor", { email: created.invitation.email, role: created.invitation.role ?? "" })}
        </p>
        <div className="invite-link">
          <label className="sr-only" htmlFor="invite-link">
            {t("invite.linkLabel")}
          </label>
          <input id="invite-link" className="form-input mono" readOnly value={link} />
          <Button
            size="sm"
            onPress={() => {
              navigator.clipboard.writeText(link).then(
                () => {
                  toast(t("invite.copied"));
                },
                () => {
                  toast(t("invite.copyFailed"));
                },
              );
            }}
          >
            <Copy size={13} aria-hidden="true" />
            {t("invite.copy")}
          </Button>
        </div>
        <p className="form-hint">{t("invite.linkRules")}</p>
      </Dialog>
    );
  }

  return (
    <Dialog
      isOpen
      title={t("invite.title")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" form="invite-form" isDisabled={create.isPending}>
            <Mail size={13} aria-hidden="true" />
            {t("invite.submit")}
          </Button>
        </>
      }
    >
      <form id="invite-form" className="record-form" onSubmit={submit} noValidate>
        <div className="form-field wide">
          <label className="form-label" htmlFor="invite-email">
            {t("invite.email")}
            <span className="required"> *</span>
          </label>
          <input
            id="invite-email"
            type="email"
            className={error === "invite.error.email" ? "form-input invalid" : "form-input"}
            value={email}
            autoComplete="off"
            aria-invalid={error === "invite.error.email" ? true : undefined}
            onChange={(event) => {
              setEmail(event.target.value);
              setError(null);
            }}
          />
        </div>
        <div className="form-field wide">
          <label className="form-label" htmlFor="invite-role">
            {t("invite.role")}
          </label>
          <select
            id="invite-role"
            className="form-input form-select"
            value={role}
            onChange={(event) => {
              setRole(event.target.value as InvitationRole);
            }}
          >
            {roles.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        </div>
        <p className="form-hint wide">{t("invite.hint")}</p>
        {error ? (
          <p className="notice error wide" role="alert">
            {t(error)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

const STATUS: Record<Invitation["status"], { label: MessageId; tone: Tone }> = {
  pending: { label: "invite.status.pending", tone: "pending" },
  accepted: { label: "invite.status.accepted", tone: "success" },
  expired: { label: "invite.status.expired", tone: "neutral" },
  revoked: { label: "invite.status.revoked", tone: "neutral" },
};

/** Invitations not yet turned into members: pending, expired or revoked. */
export function InvitationsCard({
  workspaceId,
  invitations,
  canRevoke,
}: {
  workspaceId: string;
  invitations: Invitation[];
  canRevoke: boolean;
}) {
  const t = useT();
  const toast = useToast();
  const revoke = useRevokeInvitation(workspaceId);
  const [confirming, setConfirming] = useState<Invitation | null>(null);
  const open = invitations.filter((invitation) => invitation.status !== "accepted");
  if (open.length === 0) return null;
  return (
    <section className="settings-card" aria-labelledby="invitations-title">
      <div className="settings-card-head">
        <h2 id="invitations-title" className="settings-card-title">
          {t("invite.listTitle")}
        </h2>
      </div>
      <ul className="member-list" aria-labelledby="invitations-title">
        {open.map((invitation) => {
          const status = STATUS[invitation.status];
          return (
            <li key={invitation.id} className="member-row">
              <div className="member-text">
                <div className="member-name">{invitation.email}</div>
                <div className="member-sub">
                  <Badge tone={status.tone}>{t(status.label)}</Badge>{" "}
                  {invitation.delivery === "manual" ? t("invite.deliveredManual") : null}
                  {invitation.delivery === "email" ? t("invite.deliveredEmail") : null}
                  {invitation.status === "pending" ? (
                    <>
                      {" · "}
                      {t("invite.expires")} <When value={invitation.expires_at} />
                    </>
                  ) : null}
                </div>
              </div>
              <span className="member-roles">
                {invitation.role ? <span className="scope-pill">{invitation.role}</span> : null}
              </span>
              {canRevoke && invitation.status === "pending" ? (
                <Button
                  size="sm"
                  isDisabled={revoke.isPending}
                  onPress={() => {
                    setConfirming(invitation);
                  }}
                >
                  {t("invite.revoke")}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        isOpen={confirming !== null}
        title={t("invite.revokeTitle")}
        confirmLabel={t("invite.revoke")}
        message={t("invite.revokeConfirm", { email: confirming?.email ?? "" })}
        onCancel={() => {
          setConfirming(null);
        }}
        onConfirm={() => {
          const target = confirming;
          setConfirming(null);
          if (target) {
            revoke.mutate(
              { invitationId: target.id },
              {
                onSuccess: () => {
                  toast(t("invite.revoked"));
                },
                onError: () => {
                  toast(t("records.error.generic"));
                },
              },
            );
          }
        }}
      />
    </section>
  );
}
