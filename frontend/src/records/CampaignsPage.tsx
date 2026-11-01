import { Plus } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import {
  type Campaign,
  type CampaignStatus,
  type Step,
  useCampaigns,
  useCampaignStep,
  useCreateCampaign,
  useRejectCampaign,
  useUpdateCampaign,
} from "../api/campaigns";
import { ApiError } from "../api/client";
import { useAccess } from "../api/queries";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { stageLabel } from "./parts";

/*
 * Campaigns (decision P7-C): drafts with a subject, a plain-text body and
 * an audience segment; validation shows how many contacts may receive it
 * and why the others may not; Owners and Admins approve or reject what was
 * submitted; any edit withdraws an approval. Sending is not available
 * (SaaS-OS cannot set List-Unsubscribe headers yet, and production email
 * is not authorized), and the screen says so instead of offering it.
 */

const STAGES = ["lead", "prospect", "customer", "inactive"] as const;
const TONE: Record<CampaignStatus, Tone> = {
  draft: "neutral",
  validated: "info",
  awaiting_approval: "pending",
  approved: "success",
  queued: "info",
  processing: "info",
  completed: "success",
  partially_completed: "pending",
  failed: "risk",
  rejected: "risk",
  cancelled: "neutral",
};
const EDITABLE: CampaignStatus[] = [
  "draft",
  "validated",
  "awaiting_approval",
  "approved",
  "rejected",
];

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "stale_version") return "campaigns.error.stale";
    if (error.code === "campaign_sending_unavailable")
      return "campaigns.error.sending";
    if (error.code === "approval_outdated") return "campaigns.error.outdated";
    if (error.code === "invalid_campaign") return "campaigns.error.invalid";
    if (error.code === "campaign_state") return "campaigns.error.state";
    if (error.status === 403) return "campaigns.error.forbidden";
  }
  return "campaigns.error.generic";
}

export function CampaignsPage({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const access = useAccess(workspaceId);
  const actions = access.data?.actions;
  const canManage = actions?.manage_campaigns === true;
  const canApprove = actions?.approve_campaigns === true;
  const list = useCampaigns(workspaceId);
  const [editing, setEditing] = useState<Campaign | "new" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const items = list.data?.items ?? [];
  const current = items.find((item) => item.id === selected) ?? null;

  return (
    <div className="records-page campaigns-page">
      <div className="records-head">
        <div className="records-head-text">
          <h1 className="records-title">{t("nav.campaigns")}</h1>
          <p className="muted">{t("campaigns.intro")}</p>
        </div>
        {canManage ? (
          <div className="records-actions">
            <Button
              variant="primary"
              onPress={() => {
                setEditing("new");
              }}
            >
              <Plus size={14} aria-hidden="true" />
              {t("campaigns.new")}
            </Button>
          </div>
        ) : null}
      </div>
      {list.data && !list.data.sending_available ? (
        <p className="notice" role="note">
          {t("campaigns.sendingUnavailable")}
        </p>
      ) : null}
      {list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState
          title={t("campaigns.empty")}
          body={t("campaigns.emptyBody")}
        />
      ) : (
        <div className="campaigns">
          <ul className="campaign-items" aria-label={t("campaigns.listLabel")}>
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`campaign-item${item.id === selected ? " active" : ""}`}
                  aria-current={item.id === selected ? "true" : undefined}
                  onClick={() => {
                    setSelected(item.id);
                  }}
                >
                  <span className="campaign-item-name">{item.name}</span>
                  <Badge tone={TONE[item.status]}>
                    {t(`campaigns.status.${item.status}` as MessageId)}
                  </Badge>
                  <span className="muted">{item.subject}</span>
                </button>
              </li>
            ))}
          </ul>
          {current ? (
            <Detail
              key={`${current.id}:${String(current.version)}`}
              workspaceId={workspaceId}
              campaign={current}
              canManage={canManage}
              canApprove={canApprove}
              onEdit={() => {
                setEditing(current);
              }}
            />
          ) : (
            <p className="muted campaign-pick">{t("campaigns.pick")}</p>
          )}
        </div>
      )}
      {editing ? (
        <Editor
          workspaceId={workspaceId}
          campaign={editing === "new" ? null : editing}
          onClose={(saved) => {
            setEditing(null);
            if (saved) setSelected(saved);
          }}
        />
      ) : null}
    </div>
  );
}

function Detail({
  workspaceId,
  campaign,
  canManage,
  canApprove,
  onEdit,
}: {
  workspaceId: string;
  campaign: Campaign;
  canManage: boolean;
  canApprove: boolean;
  onEdit: () => void;
}) {
  const t = useT();
  const step = useCampaignStep(workspaceId);
  const reject = useRejectCampaign(workspaceId);
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const problem = step.error ?? reject.error;
  const run = (name: Step) => {
    step.mutate({ id: campaign.id, version: campaign.version, step: name });
  };
  const status = campaign.status;
  const segment = campaign.segment;
  const audience = segment.all_contacts
    ? t("campaigns.audience.all")
    : segment.stages.map((stage) => stageLabel(t, stage)).join(", ") ||
      t("campaigns.audience.filtered");

  return (
    <section
      className="campaign-detail"
      aria-label={t("campaigns.detailLabel")}
    >
      <h2 className="campaign-detail-title">{campaign.name}</h2>
      <dl className="campaign-facts">
        <dt>{t("campaigns.field.status")}</dt>
        <dd>
          <Badge tone={TONE[status]}>
            {t(`campaigns.status.${status}` as MessageId)}
          </Badge>
        </dd>
        <dt>{t("campaigns.field.audience")}</dt>
        <dd>{audience}</dd>
        {campaign.estimate ? (
          <>
            <dt>{t("campaigns.field.estimate")}</dt>
            <dd>
              {t("campaigns.eligible", { count: campaign.estimate.eligible })}
              {Object.entries(campaign.estimate.excluded).map(
                ([reason, count]) => (
                  <span key={reason} className="muted campaign-excluded">
                    {t(`campaigns.excluded.${reason}` as MessageId, { count })}
                  </span>
                ),
              )}
            </dd>
          </>
        ) : null}
        {campaign.decision_note ? (
          <>
            <dt>{t("campaigns.field.note")}</dt>
            <dd>{campaign.decision_note}</dd>
          </>
        ) : null}
      </dl>
      <div
        className="campaign-preview"
        aria-label={t("campaigns.previewLabel")}
      >
        <p className="campaign-preview-subject">{campaign.subject}</p>
        <p className="inbox-message-text">{campaign.body}</p>
        <p className="muted">{t("campaigns.footerNote")}</p>
      </div>
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
      <div className="campaign-actions">
        {canManage && EDITABLE.includes(status) ? (
          <Button size="sm" onPress={onEdit}>
            {t("campaigns.edit")}
          </Button>
        ) : null}
        {canManage && (status === "draft" || status === "rejected") ? (
          <Button
            size="sm"
            variant="primary"
            isDisabled={step.isPending}
            onPress={() => {
              run("validate");
            }}
          >
            {t("campaigns.validate")}
          </Button>
        ) : null}
        {canManage && status === "validated" ? (
          <Button
            size="sm"
            variant="primary"
            isDisabled={step.isPending}
            onPress={() => {
              run("submit");
            }}
          >
            {t("campaigns.submit")}
          </Button>
        ) : null}
        {canApprove && status === "awaiting_approval" ? (
          <>
            <Button
              size="sm"
              variant="primary"
              isDisabled={step.isPending}
              onPress={() => {
                run("approve");
              }}
            >
              {t("campaigns.approve")}
            </Button>
            <Button
              size="sm"
              onPress={() => {
                setRejecting(true);
              }}
            >
              {t("campaigns.reject")}
            </Button>
          </>
        ) : null}
        {canManage && EDITABLE.includes(status) ? (
          <Button
            size="sm"
            isDisabled={step.isPending}
            onPress={() => {
              run("cancel");
            }}
          >
            {t("campaigns.cancel")}
          </Button>
        ) : null}
      </div>
      {rejecting ? (
        <form
          className="campaign-reject"
          onSubmit={(event: SyntheticEvent) => {
            event.preventDefault();
            reject.mutate(
              { id: campaign.id, version: campaign.version, note },
              {
                onSuccess: () => {
                  setRejecting(false);
                },
              },
            );
          }}
        >
          <label className="field">
            <span className="field-label">{t("campaigns.rejectNote")}</span>
            <textarea
              className="form-input"
              value={note}
              maxLength={500}
              required
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </label>
          <Button
            size="sm"
            type="submit"
            variant="primary"
            isDisabled={!note.trim()}
          >
            {t("campaigns.rejectSend")}
          </Button>
        </form>
      ) : null}
    </section>
  );
}

function Editor({
  workspaceId,
  campaign,
  onClose,
}: {
  workspaceId: string;
  campaign: Campaign | null;
  onClose: (saved: string | null) => void;
}) {
  const t = useT();
  const create = useCreateCampaign(workspaceId);
  const update = useUpdateCampaign(workspaceId);
  const [name, setName] = useState(campaign?.name ?? "");
  const [subject, setSubject] = useState(campaign?.subject ?? "");
  const [body, setBody] = useState(campaign?.body ?? "");
  const [stages, setStages] = useState<string[]>(
    campaign?.segment.stages ?? [],
  );
  const [all, setAll] = useState(campaign?.segment.all_contacts ?? false);
  const problem = create.error ?? update.error;
  const segment = {
    ...(campaign?.segment ?? { tag_ids: [], owner_ids: [], company_ids: [] }),
    stages: all ? [] : stages,
    all_contacts: all,
  };
  const save = () => {
    if (campaign) {
      update.mutate(
        {
          id: campaign.id,
          version: campaign.version,
          changes: { name, subject, body, segment },
        },
        {
          onSuccess: (saved) => {
            onClose(saved.id);
          },
        },
      );
    } else {
      create.mutate(
        { name, subject, body, segment },
        {
          onSuccess: (saved) => {
            onClose(saved.id);
          },
        },
      );
    }
  };
  const approvedOrWaiting =
    campaign?.status === "approved" || campaign?.status === "awaiting_approval";

  return (
    <Dialog
      isOpen
      title={campaign ? t("campaigns.editTitle") : t("campaigns.newTitle")}
      onClose={() => {
        onClose(null);
      }}
      actions={
        <>
          <Button
            onPress={() => {
              onClose(null);
            }}
          >
            {t("campaigns.close")}
          </Button>
          <Button
            variant="primary"
            isDisabled={
              create.isPending ||
              update.isPending ||
              !name.trim() ||
              !subject.trim() ||
              !body.trim() ||
              (!all && stages.length === 0)
            }
            onPress={save}
          >
            {t("campaigns.save")}
          </Button>
        </>
      }
    >
      {approvedOrWaiting ? (
        <p className="notice" role="note">
          {t("campaigns.editWithdraws")}
        </p>
      ) : null}
      <label className="field">
        <span className="field-label">{t("campaigns.field.name")}</span>
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
        <span className="field-label">{t("campaigns.field.subject")}</span>
        <input
          className="form-input"
          value={subject}
          maxLength={200}
          onChange={(event) => {
            setSubject(event.target.value);
          }}
        />
      </label>
      <label className="field">
        <span className="field-label">{t("campaigns.field.body")}</span>
        <textarea
          className="form-input campaign-body"
          value={body}
          maxLength={18000}
          rows={8}
          onChange={(event) => {
            setBody(event.target.value);
          }}
        />
      </label>
      <p className="muted">
        {t("campaigns.placeholders", {
          first: "{{first_name}}",
          last: "{{last_name}}",
        })}
      </p>
      <fieldset className="campaign-segment">
        <legend>{t("campaigns.field.audience")}</legend>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={all}
            onChange={(event) => {
              setAll(event.target.checked);
            }}
          />
          {t("campaigns.audience.all")}
        </label>
        {all ? null : (
          <div className="campaign-stages">
            {STAGES.map((stage) => (
              <label key={stage} className="checkbox">
                <input
                  type="checkbox"
                  checked={stages.includes(stage)}
                  onChange={(event) => {
                    setStages(
                      event.target.checked
                        ? [...stages, stage]
                        : stages.filter((s) => s !== stage),
                    );
                  }}
                />
                {stageLabel(t, stage)}
              </label>
            ))}
          </div>
        )}
      </fieldset>
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </Dialog>
  );
}
