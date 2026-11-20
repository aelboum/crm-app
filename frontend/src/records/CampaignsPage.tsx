import { Download, Plus, Search, Tag, User, X } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { useIntl } from "react-intl";

import {
  type Campaign,
  type CampaignOrder,
  type CampaignStatus,
  exportCampaignResults,
  type Outcome,
  type Step,
  useCampaignReport,
  useCampaigns,
  useCampaignPreview,
  useCampaignStep,
  useCreateCampaign,
  useDeleteCampaign,
  useDuplicateCampaign,
  useRejectCampaign,
  useScheduleCampaign,
  useUpdateCampaign,
} from "../api/campaigns";
import { type Definition, useAutomations } from "../api/automations";
import { ApiError } from "../api/client";
import { ExportError, fileDownload } from "../api/exportContacts";
import { useAccess, useMe, useMembers } from "../api/queries";
import { useCompany } from "../api/records";
import { useTags } from "../api/tags";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { TemplatePicker, TemplatesPanel } from "./EmailTemplates";
import { CompanyPicker, type PickedCompany } from "./CompanyPicker";
import { FilterMenu, ownerOptions, stageLabel } from "./parts";
import { useDebounced } from "./useDebounced";

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

// Those never queued, which may be deleted (decision P7-DL).
const DELETABLE: CampaignStatus[] = ["draft", "validated", "rejected", "cancelled"];

// Every status, in workflow order, for the list's filter (decision P7-CL).
const STATUSES: CampaignStatus[] = [
  "draft",
  "validated",
  "awaiting_approval",
  "approved",
  "queued",
  "processing",
  "completed",
  "partially_completed",
  "failed",
  "rejected",
  "cancelled",
];

// Statuses after queuing: the campaign has recipients and results.
const STARTED: CampaignStatus[] = [
  "queued",
  "processing",
  "completed",
  "partially_completed",
  "failed",
];

// Finished campaigns, which may be archived (decision P7-AR).
const FINISHED: CampaignStatus[] = [
  "completed",
  "partially_completed",
  "failed",
  "cancelled",
];

// The list's orders (decision P7-SO).
const ORDERS: CampaignOrder[] = ["created_at", "updated_at", "name"];

const OUTCOMES: Outcome[] = [
  "waiting",
  "sent",
  "delivered",
  "bounced",
  "complained",
  "suppressed",
  "not_sent",
  "unknown",
  "rehearsed",
];

function Results({
  workspaceId,
  campaign,
  canExport,
}: {
  workspaceId: string;
  campaign: Campaign;
  canExport: boolean;
}) {
  const t = useT();
  const live = campaign.status === "queued" || campaign.status === "processing";
  const report = useCampaignReport(workspaceId, campaign.id, live);
  const data = report.data;
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<MessageId | null>(null);
  const download = () => {
    setBusy(true);
    setFailed(null);
    exportCampaignResults(workspaceId, campaign.id)
      .then(({ blob, fileName }) => {
        fileDownload.save(blob, fileName);
      })
      .catch((error: unknown) => {
        setFailed(
          error instanceof ExportError && error.status === 429
            ? "campaigns.results.csvLimit"
            : "campaigns.results.csvFailed",
        );
      })
      .finally(() => {
        setBusy(false);
      });
  };
  return (
    <section
      className="campaign-results"
      aria-label={t("campaigns.results.label")}
    >
      <h3 className="campaign-results-title">{t("campaigns.results.label")}</h3>
      {report.isPending ? (
        <Loading />
      ) : data === undefined ? (
        <LoadError
          error={report.error}
          onRetry={() => {
            void report.refetch();
          }}
        />
      ) : (
        <>
          <dl className="campaign-facts">
            {[
              ["recipients", data.recipients] as const,
              ...OUTCOMES.filter((name) => data.outcomes[name] > 0).map(
                (name) => [name, data.outcomes[name]] as const,
              ),
              ["unsubscribed", data.unsubscribed] as const,
            ].map(([name, count]) => (
              <div key={name} className="campaign-results-row">
                <dt>{t(`campaigns.results.${name}` as MessageId)}</dt>
                <dd>{count}</dd>
              </div>
            ))}
          </dl>
          <p className="muted">{t("campaigns.results.note")}</p>
          {canExport && data.recipients > 0 ? (
            <div className="campaign-results-csv">
              <Button size="sm" isDisabled={busy} onPress={download}>
                <Download size={13} aria-hidden="true" />
                {t("campaigns.results.csv")}
              </Button>
              <span className="sr-only" role="status">
                {busy ? t("campaigns.results.csvRunning") : ""}
              </span>
            </div>
          ) : null}
          {failed ? (
            <p className="notice error" role="alert">
              {t(failed)}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

// A started campaign's results in one line of the list (decision P7-RP,
// list summary): recipients and each outcome that occurred. It shares the
// detail's query, so opening the campaign needs no second request. Nothing
// is shown while loading or on an error; the detail reports those.
function ListResults({
  workspaceId,
  campaign,
}: {
  workspaceId: string;
  campaign: Campaign;
}) {
  const t = useT();
  const live = campaign.status === "queued" || campaign.status === "processing";
  const data = useCampaignReport(workspaceId, campaign.id, live).data;
  if (data === undefined) return null;
  const parts = [
    t("campaigns.results.count", { count: data.recipients }),
    ...OUTCOMES.filter((name) => data.outcomes[name] > 0).map(
      (name) =>
        `${t(`campaigns.results.${name}` as MessageId)} ${String(data.outcomes[name])}`,
    ),
  ];
  return <span className="muted campaign-item-results">{parts.join(" · ")}</span>;
}

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

export function CampaignsPage({
  workspaceId,
  onNewAutomation = () => undefined,
}: {
  workspaceId: string;
  /** Opens the automation editor started by this campaign (P8-C). */
  onNewAutomation?: (campaignId: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const actions = access.data?.actions;
  const canManage = actions?.manage_campaigns === true;
  const canApprove = actions?.approve_campaigns === true;
  const canExport = actions?.export_records === true;
  const [order, setOrder] = useState<CampaignOrder>("created_at");
  const [archived, setArchived] = useState(false);
  const [status, setStatus] = useState<CampaignStatus | null>(null);
  const [search, setSearch] = useState("");
  const query = useDebounced(search);
  const list = useCampaigns(workspaceId, {
    order,
    archived,
    status,
    search: query,
  });
  const [editing, setEditing] = useState<Campaign | "new" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const firstPage = list.data?.pages[0];
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = status !== null || query.trim() !== "";
  const current = items.find((item) => item.id === selected) ?? null;

  return (
    <div className="records-page campaigns-page">
      <div className="records-head">
        <div className="records-head-text">
          <h1 className="records-title">{t("nav.campaigns")}</h1>
          <p className="muted">{t("campaigns.intro")}</p>
        </div>
        <div className="records-actions">
          <Button
            aria-pressed={archived}
            onPress={() => {
              setArchived(!archived);
              setSelected(null);
            }}
          >
            {t(archived ? "campaigns.showCurrent" : "campaigns.showArchived")}
          </Button>
          {canManage ? (
            <Button
              variant="primary"
              onPress={() => {
                setEditing("new");
              }}
            >
              <Plus size={14} aria-hidden="true" />
              {t("campaigns.new")}
            </Button>
          ) : null}
        </div>
      </div>
      {archived ? (
        <p className="notice" role="note">
          {t("campaigns.archivedNote")}
        </p>
      ) : null}
      {firstPage?.rehearsal ? (
        <p className="notice" role="note">
          {t("campaigns.rehearsal")}
        </p>
      ) : firstPage && !firstPage.sending_available ? (
        <p className="notice" role="note">
          {t("campaigns.sendingUnavailable")}
        </p>
      ) : null}
      <div className="records-toolbar">
        <label className="search-box">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">{t("campaigns.search")}</span>
          <input
            type="search"
            value={search}
            placeholder={t("campaigns.search")}
            maxLength={120}
            onChange={(event) => {
              setSearch(event.target.value);
              setSelected(null);
            }}
          />
        </label>
        <label className="field campaign-status-filter">
          <span className="sr-only">{t("campaigns.field.status")}</span>
          <select
            className="form-input"
            value={status ?? ""}
            onChange={(event) => {
              setStatus(
                event.target.value === ""
                  ? null
                  : (event.target.value as CampaignStatus),
              );
              setSelected(null);
            }}
          >
            <option value="">{t("campaigns.allStatuses")}</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`campaigns.status.${value}` as MessageId)}
              </option>
            ))}
          </select>
        </label>
        <label className="field campaign-status-filter">
          <span className="sr-only">{t("campaigns.sort")}</span>
          <select
            className="form-input"
            value={order}
            onChange={(event) => {
              setOrder(event.target.value as CampaignOrder);
            }}
          >
            {ORDERS.map((value) => (
              <option key={value} value={value}>
                {t(`campaigns.order.${value}` as MessageId)}
              </option>
            ))}
          </select>
        </label>
        {firstPage && filtered ? (
          <span className="muted" role="status">
            {t("campaigns.matches", { count: firstPage.total })}
          </span>
        ) : null}
      </div>
      {list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <Loading />
      ) : items.length === 0 ? (
        filtered ? (
          <EmptyState
            title={t("campaigns.noMatch")}
            body={t("campaigns.noMatchBody")}
          />
        ) : archived ? (
          <EmptyState
            title={t("campaigns.archivedEmpty")}
            body={t("campaigns.archivedEmptyBody")}
          />
        ) : (
          <EmptyState
            title={t("campaigns.empty")}
            body={t("campaigns.emptyBody")}
          />
        )
      ) : (
        <div className="campaigns">
          <div className="campaign-list">
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
                  {STARTED.includes(item.status) ? (
                    <ListResults workspaceId={workspaceId} campaign={item} />
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
          {list.hasNextPage ? (
            <div className="records-footer">
              <Button
                size="sm"
                onPress={() => void list.fetchNextPage()}
                isDisabled={list.isFetchingNextPage}
              >
                {t("records.loadMore")}
              </Button>
            </div>
          ) : null}
          </div>
          {current ? (
            <Detail
              key={`${current.id}:${String(current.version)}`}
              workspaceId={workspaceId}
              campaign={current}
              canManage={canManage}
              canApprove={canApprove}
              canExport={canExport}
              canQueue={
                (firstPage?.sending_available ?? false) ||
                (firstPage?.rehearsal ?? false)
              }
              rehearsal={firstPage?.rehearsal ?? false}
              onEdit={() => {
                setEditing(current);
              }}
              onDuplicated={(copy) => {
                // The copy is a new draft: show the current list, unfiltered.
                setArchived(false);
                setStatus(null);
                setSearch("");
                setSelected(copy.id);
              }}
              onDeleted={() => {
                setSelected(null);
              }}
              onNewAutomation={() => {
                onNewAutomation(current.id);
              }}
            />
          ) : (
            <p className="muted campaign-pick">{t("campaigns.pick")}</p>
          )}
        </div>
      )}
      <TemplatesPanel workspaceId={workspaceId} canManage={canManage} />
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

// The campaign as one chosen contact would receive it (decision P7-PV).
function Preview({
  workspaceId,
  campaign,
}: {
  workspaceId: string;
  campaign: Campaign;
}) {
  const t = useT();
  const [picked, setPicked] = useState<PickedCompany | null>(null);
  const preview = useCampaignPreview(
    workspaceId,
    campaign.id,
    picked?.id ?? null,
    campaign.version,
  );
  const data = preview.data;
  return (
    <section
      className="campaign-results"
      aria-label={t("campaigns.preview.region")}
    >
      <CompanyPicker
        workspaceId={workspaceId}
        id={`campaign-preview-${campaign.id}`}
        kind="contacts"
        label={t("campaigns.preview.label")}
        selected={picked}
        onChange={setPicked}
        noneText={t("campaigns.preview.none")}
        chooseText={t("campaigns.preview.choose")}
      />
      {picked === null ? null : preview.isPending ? (
        <Loading />
      ) : data === undefined ? (
        <LoadError
          error={preview.error}
          onRetry={() => {
            void preview.refetch();
          }}
        />
      ) : (
        <>
          <p className="notice" role="status">
            {data.audience === "eligible"
              ? t("campaigns.preview.eligible")
              : data.audience === "outside"
                ? t("campaigns.preview.outside")
                : t("campaigns.preview.excluded", {
                    reason: t(
                      `campaigns.preview.reason.${data.reason ?? "no_email"}` as MessageId,
                    ),
                  })}
          </p>
          <div className="campaign-preview">
            <p className="campaign-preview-subject">{data.subject}</p>
            <p className="inbox-message-text">{data.body}</p>
          </div>
          <p className="muted">{t("campaigns.preview.note")}</p>
        </>
      )}
    </section>
  );
}

function Scheduler({
  workspaceId,
  campaign,
  onDone,
}: {
  workspaceId: string;
  campaign: Campaign;
  onDone: () => void;
}) {
  const t = useT();
  const schedule = useScheduleCampaign(workspaceId);
  const [at, setAt] = useState("");
  const inputId = `campaign-schedule-${campaign.id}`;
  return (
    <form
      className="campaign-reject"
      onSubmit={(event: SyntheticEvent) => {
        event.preventDefault();
        schedule.mutate(
          {
            id: campaign.id,
            version: campaign.version,
            at: new Date(at).toISOString(),
          },
          { onSuccess: onDone },
        );
      }}
    >
      <label className="field" htmlFor={inputId}>
        <span className="field-label">{t("campaigns.scheduleAt")}</span>
      </label>
      <input
        id={inputId}
        className="form-input"
        type="datetime-local"
        required
        value={at}
        aria-describedby={`${inputId}-hint`}
        onChange={(event) => {
          setAt(event.target.value);
        }}
      />
      <p id={`${inputId}-hint`} className="muted">
        {t("campaigns.scheduleHint")}
      </p>
      {schedule.error ? (
        <p className="notice error" role="alert">
          {t(
            schedule.error.code === "invalid_campaign"
              ? "campaigns.error.schedule"
              : failure(schedule.error),
          )}
        </p>
      ) : null}
      <Button
        size="sm"
        type="submit"
        variant="primary"
        isDisabled={!at || schedule.isPending}
      >
        {t("campaigns.scheduleSave")}
      </Button>
    </form>
  );
}

/** Whether anything but the deleted tags would still choose the audience. */
function keepsAFilter(campaign: Campaign): boolean {
  const segment = campaign.segment;
  const missing = campaign.missing_tag_ids?.length ?? 0;
  return (
    segment.stages.length > 0 ||
    segment.owner_ids.length > 0 ||
    segment.company_ids.length > 0 ||
    segment.tag_ids.length > missing
  );
}

function Detail({
  workspaceId,
  campaign,
  canManage,
  canApprove,
  canExport,
  canQueue,
  rehearsal,
  onEdit,
  onDuplicated,
  onDeleted,
  onNewAutomation,
}: {
  workspaceId: string;
  campaign: Campaign;
  canManage: boolean;
  canApprove: boolean;
  canExport: boolean;
  canQueue: boolean;
  rehearsal: boolean;
  onEdit: () => void;
  onDuplicated: (copy: Campaign) => void;
  onDeleted: () => void;
  onNewAutomation: () => void;
}) {
  const t = useT();
  const step = useCampaignStep(workspaceId);
  const reject = useRejectCampaign(workspaceId);
  const duplicate = useDuplicateCampaign(workspaceId);
  const remove = useDeleteCampaign(workspaceId);
  const intl = useIntl();
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [removingTags, setRemovingTags] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const problem = step.error ?? reject.error ?? duplicate.error ?? remove.error;
  const run = (name: Step) => {
    step.mutate({ id: campaign.id, version: campaign.version, step: name });
  };
  const status = campaign.status;
  const segment = campaign.segment;
  const audience = segment.all_contacts
    ? t("campaigns.audience.all")
    : [
        segment.stages.map((stage) => stageLabel(t, stage)).join(", "),
        segment.tag_ids.length
          ? t("campaigns.audience.tags", { count: segment.tag_ids.length })
          : "",
        segment.owner_ids.length
          ? t("campaigns.audience.owners", { count: segment.owner_ids.length })
          : "",
        segment.company_ids.length
          ? t("campaigns.audience.companies", { count: segment.company_ids.length })
          : "",
      ]
        .filter(Boolean)
        .join(" · ") || t("campaigns.audience.filtered");

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
        <dd>
          {audience}
          {campaign.missing_tag_ids?.length ? (
            <span className="notice error campaign-missing-tags" role="note">
              {t("campaigns.missingTags", {
                count: campaign.missing_tag_ids.length,
              })}
              {canManage &&
              EDITABLE.includes(status) &&
              keepsAFilter(campaign) ? (
                <Button
                  size="sm"
                  isDisabled={step.isPending}
                  onPress={() => {
                    setRemovingTags(true);
                  }}
                >
                  {t("campaigns.removeDeletedTags", {
                    count: campaign.missing_tag_ids.length,
                  })}
                </Button>
              ) : null}
            </span>
          ) : null}
        </dd>
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
        {campaign.scheduled_at ? (
          <>
            <dt>{t("campaigns.field.scheduled")}</dt>
            <dd>
              <time dateTime={campaign.scheduled_at}>
                {intl.formatDate(new Date(campaign.scheduled_at), {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </time>
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
        role="group"
        aria-label={t("campaigns.previewLabel")}
      >
        <p className="campaign-preview-subject">{campaign.subject}</p>
        <p className="inbox-message-text">{campaign.body}</p>
        <p className="muted">{t("campaigns.footerNote")}</p>
      </div>
      <Preview workspaceId={workspaceId} campaign={campaign} />
      <CampaignAutomations
        workspaceId={workspaceId}
        campaignId={campaign.id}
        onNew={onNewAutomation}
      />
      {STARTED.includes(status) ? (
        <Results
          workspaceId={workspaceId}
          campaign={campaign}
          canExport={canExport}
        />
      ) : null}
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
      <ConfirmDialog
        isOpen={removingTags}
        title={t("campaigns.removeDeletedTagsTitle")}
        confirmLabel={t("campaigns.removeDeletedTagsSubmit")}
        message={t("campaigns.removeDeletedTagsConfirm")}
        onCancel={() => {
          setRemovingTags(false);
        }}
        onConfirm={() => {
          setRemovingTags(false);
          run("remove_deleted_tags");
        }}
      />
      <ConfirmDialog
        isOpen={deleting}
        title={t("campaigns.deleteTitle")}
        confirmLabel={t("campaigns.deleteSubmit")}
        message={t("campaigns.deleteConfirm", { name: campaign.name })}
        onCancel={() => {
          setDeleting(false);
        }}
        onConfirm={() => {
          setDeleting(false);
          remove.mutate(
            { id: campaign.id, version: campaign.version },
            { onSuccess: onDeleted },
          );
        }}
      />
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
        {canApprove && canQueue && status === "approved" ? (
          <Button
            size="sm"
            variant="primary"
            isDisabled={step.isPending}
            onPress={() => {
              run("queue");
            }}
          >
            {t(rehearsal ? "campaigns.queueRehearsal" : "campaigns.queue")}
          </Button>
        ) : null}
        {canApprove && canQueue && status === "approved" ? (
          campaign.scheduled_at ? (
            <Button
              size="sm"
              isDisabled={step.isPending}
              onPress={() => {
                run("unschedule");
              }}
            >
              {t("campaigns.unschedule")}
            </Button>
          ) : (
            <Button
              size="sm"
              aria-expanded={scheduling}
              onPress={() => {
                setScheduling(!scheduling);
              }}
            >
              {t("campaigns.schedule")}
            </Button>
          )
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
        {canManage && FINISHED.includes(status) ? (
          <Button
            size="sm"
            isDisabled={step.isPending}
            onPress={() => {
              run(campaign.archived_at ? "unarchive" : "archive");
            }}
          >
            {t(campaign.archived_at ? "campaigns.unarchive" : "campaigns.archive")}
          </Button>
        ) : null}
        {canManage ? (
          <Button
            size="sm"
            isDisabled={duplicate.isPending}
            onPress={() => {
              duplicate.mutate(
                { id: campaign.id },
                { onSuccess: onDuplicated },
              );
            }}
          >
            {t("campaigns.duplicate")}
          </Button>
        ) : null}
        {canManage && DELETABLE.includes(status) ? (
          <Button
            size="sm"
            variant="destructive"
            isDisabled={remove.isPending}
            onPress={() => {
              setDeleting(true);
            }}
          >
            {t("campaigns.delete")}
          </Button>
        ) : null}
      </div>
      {scheduling && !campaign.scheduled_at && status === "approved" ? (
        <Scheduler
          workspaceId={workspaceId}
          campaign={campaign}
          onDone={() => {
            setScheduling(false);
          }}
        />
      ) : null}
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
  const [tagIds, setTagIds] = useState<string[]>(campaign?.segment.tag_ids ?? []);
  const [ownerIds, setOwnerIds] = useState<string[]>(campaign?.segment.owner_ids ?? []);
  const [companyIds, setCompanyIds] = useState<string[]>(campaign?.segment.company_ids ?? []);
  const tags = useTags(workspaceId);
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const problem = create.error ?? update.error;
  // Filters combine: a contact must match each kind used, and any one value
  // within it (the server's rule, decision P7-C); companies by the contact's
  // company (P7-CC).
  const segment = {
    company_ids: all ? [] : companyIds,
    stages: all ? [] : stages,
    tag_ids: all ? [] : tagIds,
    owner_ids: all ? [] : ownerIds,
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
      <TemplatePicker
        workspaceId={workspaceId}
        onPick={(chosenSubject, chosenBody) => {
          setSubject(chosenSubject);
          setBody(chosenBody);
        }}
      />
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
        {all ? null : (
          <div className="campaign-filters">
            {tags.data?.items.length ? (
              <FilterMenu
                label={t("tags.label")}
                icon={<Tag size={14} aria-hidden="true" />}
                options={tags.data.items.map((tag) => ({ id: tag.id, label: tag.name }))}
                selected={tagIds}
                onChange={setTagIds}
              />
            ) : null}
            <FilterMenu
              label={t("records.field.owner")}
              icon={<User size={14} aria-hidden="true" />}
              options={ownerOptions(t, members.data?.items ?? [], me.data?.user_id)}
              selected={ownerIds}
              onChange={setOwnerIds}
            />
          </div>
        )}
        {all ? null : (
          <CompanyFilter workspaceId={workspaceId} selected={companyIds} onChange={setCompanyIds} />
        )}
        {all ? null : <p className="muted">{t("campaigns.audience.combine")}</p>}
      </fieldset>
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </Dialog>
  );
}

/** The most companies one audience may name (the server's FILTER_MAX). */
const COMPANY_MAX = 50;

/*
 * Companies for a campaign's audience (decision P7-CC): search to add one,
 * remove it from its chip. A contact matches when their company is one of
 * them.
 */
function CompanyFilter({
  workspaceId,
  selected,
  onChange,
}: {
  workspaceId: string;
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const t = useT();
  return (
    <div className="campaign-companies">
      <CompanyPicker
        workspaceId={workspaceId}
        id="campaign-company"
        label={t("campaigns.companies.add")}
        noneText={t(selected.length ? "campaigns.companies.some" : "campaigns.companies.any")}
        chooseText={t("campaigns.companies.choose")}
        selected={null}
        onChange={(company) => {
          if (company && !selected.includes(company.id) && selected.length < COMPANY_MAX) {
            onChange([...selected, company.id]);
          }
        }}
      />
      {selected.length ? (
        <ul className="campaign-company-list" aria-label={t("campaigns.companies.chosen")}>
          {selected.map((id) => (
            <CompanyChip
              key={id}
              workspaceId={workspaceId}
              id={id}
              onRemove={() => {
                onChange(selected.filter((other) => other !== id));
              }}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function CompanyChip({ workspaceId, id, onRemove }: { workspaceId: string; id: string; onRemove: () => void }) {
  const t = useT();
  const company = useCompany(workspaceId, id);
  // A company that cannot be read (deleted, or no access) still shows, so it can be removed.
  const name = company.data?.name ?? (company.isPending ? "…" : t("campaigns.companies.unknown"));
  return (
    <li className="chip campaign-company">
      <span>{name}</span>
      <button
        type="button"
        className="chip-remove"
        aria-label={t("campaigns.companies.remove", { name })}
        onClick={onRemove}
      >
        <X size={12} aria-hidden="true" />
      </button>
    </li>
  );
}

/*
 * The automations this campaign starts (decision P8-C follow-up): those
 * whose trigger is a campaign email sent or an unsubscribe, for this
 * campaign or for any. A new one opens the automation editor with "sent"
 * and this campaign set. Nothing is stored on the campaign.
 */
function CampaignAutomations({
  workspaceId,
  campaignId,
  onNew,
}: {
  workspaceId: string;
  campaignId: string;
  onNew: () => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const canRead = access.data?.actions.read_automations === true;
  const canManage = access.data?.actions.manage_automations === true;
  const list = useAutomations(workspaceId, canRead);
  if (!canRead) return null;
  const started = (list.data?.items ?? []).flatMap((item) => {
    const trigger = (item.definition as unknown as Definition).trigger;
    return (trigger.type === "campaign_sent" ||
      trigger.type === "campaign_unsubscribed") &&
      (trigger.campaign_id === null || trigger.campaign_id === campaignId)
      ? [{ item, trigger }]
      : [];
  });
  return (
    <div
      className="form-field campaign-automations"
      role="group"
      aria-labelledby="campaign-automations"
    >
      <p id="campaign-automations" className="form-label">
        {t("campaigns.automations")}
      </p>
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : started.length === 0 ? (
        <p className="form-hint">{t("campaigns.automations.none")}</p>
      ) : (
        <ul className="form-automations">
          {started.map(({ item, trigger }) => (
            <li key={item.id}>
              <span>{item.name}</span>
              <Badge tone={item.status === "active" ? "success" : "neutral"}>
                {t(`automations.status.${item.status}` as MessageId)}
              </Badge>
              <span className="form-hint">
                {t(
                  trigger.type === "campaign_sent"
                    ? "campaigns.automations.onSent"
                    : "campaigns.automations.onUnsubscribed",
                )}
                {trigger.campaign_id === null
                  ? ` ${t("campaigns.automations.anyCampaign")}`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {canManage ? (
        <Button size="sm" onPress={onNew}>
          {t("campaigns.automations.new")}
        </Button>
      ) : null}
      <p className="form-hint">{t("campaigns.automations.hint")}</p>
    </div>
  );
}
