import { Pause, Pencil, Play, Plus, Trash2, X } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import {
  type Action,
  type Automation,
  type AutomationRun,
  type Condition,
  DAILY_LIMIT_DEFAULT,
  DAILY_LIMIT_MAX,
  type Definition,
  EMPTY_DEFINITION,
  MAX_ACTIONS,
  NOTICE_MAX,
  ROTATION_MAX,
  ROTATION_MIN,
  type Source,
  type Trigger,
  TRIGGER_SOURCES,
  TRIGGER_TYPES,
  type TriggerType,
  useAutomationRuns,
  useAutomations,
  useCreateAutomation,
  useDeleteAutomation,
  useSwitchAutomation,
  useUpdateAutomation,
} from "../api/automations";
import { useBookingPages } from "../api/bookingPages";
import { useCampaign, useCampaigns } from "../api/campaigns";
import { ApiError } from "../api/client";
import {
  activeFields,
  type FieldDefinition,
  useFieldDefinitions,
} from "../api/customFields";
import { useEmailTemplates } from "../api/emailTemplates";
import { useForms } from "../api/forms";
import { usePipelines } from "../api/pipelines";
import {
  useAccess,
  useMe,
  useMembers,
  useWorkspaceSettings,
} from "../api/queries";
import { useTags } from "../api/tags";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { type Option, ownerOptions, When } from "./parts";

/*
 * Automations (decision P8-A): a list of workflows with their status, an
 * editor for the design's shape (one trigger, an optional condition, a yes
 * and a no branch of actions), activation and pausing, and each one's
 * latest runs with their steps. Only the actions the engine runs are
 * offered: one marketing email from a template (P8-E), not yet the
 * design's SMS and AI actions. The server checks every definition again.
 */

const STATUS_TONE: Record<Automation["status"], Tone> = {
  draft: "neutral",
  active: "success",
  paused: "pending",
};
const RUN_TONE: Record<AutomationRun["status"], Tone> = {
  running: "info",
  waiting: "pending",
  completed: "success",
  failed: "risk",
  cancelled: "neutral",
};
const STAGES = ["lead", "prospect", "customer", "inactive"] as const;
const SOURCES = [
  "manual",
  "import",
  "form",
  "referral",
  "other",
  "booking",
] as const;
const OUTCOMES = ["open", "won", "lost"] as const;
const WAITS = [15, 60, 240, 1440, 4320, 10080];
const DUES = [null, 15, 60, 1440, 4320];

type ConditionKind =
  | "none"
  | "source"
  | "lifecycle_stage"
  | "email"
  | "tag"
  | "custom_field"
  | "deal"
  | "deal_stage";
type FieldValue = string | number | boolean;
type T = ReturnType<typeof useT>;

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_automation") return "automations.error.invalid";
    if (error.code === "automation_limit") return "automations.error.limit";
    if (error.code === "automation_active") return "automations.error.active";
    if (error.code === "campaign_approval_required")
      return "automations.error.approval";
    if (error.code === "stale_version") return "automations.error.stale";
    if (error.status === 403) return "automations.error.forbidden";
  }
  return "automations.error.failed";
}

function minutesLabel(t: T, minutes: number): string {
  if (minutes % 1440 === 0)
    return t("automations.days", { count: minutes / 1440 });
  if (minutes % 60 === 0)
    return t("automations.hours", { count: minutes / 60 });
  return t("automations.minutes", { count: minutes });
}

export function AutomationsPage({
  workspaceId,
  onOpenContact,
  newForForm = null,
  newForCampaign = null,
  onNewDone = () => undefined,
}: {
  workspaceId: string;
  onOpenContact: (id: string) => void;
  /** Opens a new automation started by this form (`?create=automation&form=`). */
  newForForm?: string | null;
  /** Opens a new automation started by this campaign's emails (`&campaign=`). */
  newForCampaign?: string | null;
  /** Called when that editor closes, to clear the request. */
  onNewDone?: () => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const list = useAutomations(workspaceId);
  const [editing, setEditing] = useState<Automation | "new" | null>(
    newForForm || newForCampaign ? "new" : null,
  );
  const [preset] = useState<Definition | null>(() =>
    newForForm
      ? {
          ...EMPTY_DEFINITION,
          trigger: { type: "form_submitted", form_id: newForForm },
        }
      : newForCampaign
        ? {
            ...EMPTY_DEFINITION,
            trigger: { type: "campaign_sent", campaign_id: newForCampaign },
          }
        : null,
  );
  const [runsOf, setRunsOf] = useState<string | null>(null);
  const canManage = access.data?.actions.manage_automations === true;
  const items = list.data?.items ?? [];
  return (
    <div className="records-page automations-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.marketing")}</p>
          <h1 className="records-title">{t("nav.automations")}</h1>
          <p className="muted automations-intro">{t("automations.intro")}</p>
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
              {t("automations.new")}
            </Button>
          </div>
        ) : null}
      </div>
      {list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : list.isPending ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState
          title={t("automations.empty")}
          body={t("automations.emptyBody")}
        />
      ) : (
        <ul className="automation-list">
          {items.map((item) => (
            <AutomationCard
              key={item.id}
              workspaceId={workspaceId}
              automation={item}
              canManage={canManage}
              showingRuns={runsOf === item.id}
              onEdit={() => {
                setEditing(item);
              }}
              onRuns={() => {
                setRunsOf(runsOf === item.id ? null : item.id);
              }}
              onOpenContact={onOpenContact}
            />
          ))}
        </ul>
      )}
      {editing ? (
        <AutomationEditor
          workspaceId={workspaceId}
          automation={editing === "new" ? null : editing}
          initial={editing === "new" ? preset : null}
          onClose={() => {
            setEditing(null);
            if (newForForm || newForCampaign) onNewDone();
          }}
        />
      ) : null}
    </div>
  );
}

function summary(t: T, definition: Definition): string {
  const trigger = definition.trigger;
  const count = definition.yes.length + definition.no.length;
  if (trigger.type !== "contact_created") {
    return t("automations.summaryEvent", {
      trigger: t(`automations.triggerType.${trigger.type}` as MessageId),
      count,
    });
  }
  const sources = trigger.sources;
  const from = sources.length
    ? sources.map((s) => t(`source.${s}` as MessageId)).join(", ")
    : t("automations.anySource");
  return t("automations.summary", { from, count });
}

/*
 * A campaign trigger's summary names its campaign (decision P8-C
 * follow-up), when the member may read campaigns; otherwise, or while it
 * loads, "a campaign".
 */
function CampaignSummary({
  workspaceId,
  sent,
  campaignId,
  count,
}: {
  workspaceId: string;
  sent: boolean;
  campaignId: string | null;
  count: number;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const canRead = access.data?.actions.read_campaigns === true;
  const campaign = useCampaign(workspaceId, canRead ? campaignId : null);
  const name =
    campaignId === null
      ? t("automations.campaignAny")
      : campaign.data
        ? campaign.data.name
        : campaign.error instanceof ApiError && campaign.error.status === 404
          ? t("automations.campaignGone")
          : t("automations.campaignSome");
  return t(sent ? "automations.summarySent" : "automations.summaryUnsubscribed", {
    campaign: name,
    count,
  });
}

function AutomationCard({
  workspaceId,
  automation,
  canManage,
  showingRuns,
  onEdit,
  onRuns,
  onOpenContact,
}: {
  workspaceId: string;
  automation: Automation;
  canManage: boolean;
  showingRuns: boolean;
  onEdit: () => void;
  onRuns: () => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const change = useSwitchAutomation(workspaceId);
  const remove = useDeleteAutomation(workspaceId);
  const [confirming, setConfirming] = useState(false);
  const [problem, setProblem] = useState<MessageId | null>(null);
  const definition = automation.definition as unknown as Definition;
  const toggle = (to: "activate" | "pause") => {
    setProblem(null);
    change.mutate(
      { id: automation.id, version: automation.version, to },
      {
        onSuccess: () => {
          toast(
            t(
              to === "activate"
                ? "automations.activated"
                : "automations.pausedToast",
            ),
          );
        },
        onError: (error) => {
          setProblem(failure(error));
        },
      },
    );
  };
  const headingId = `automation-${automation.id}`;
  return (
    <li className="automation-card" aria-labelledby={headingId}>
      <div className="automation-card-head">
        <div className="automation-card-text">
          <h2 id={headingId} className="automation-card-title">
            {automation.name}
          </h2>
          <p className="muted automation-card-summary">
            {definition.trigger.type === "campaign_sent" ||
            definition.trigger.type === "campaign_unsubscribed" ? (
              <CampaignSummary
                workspaceId={workspaceId}
                sent={definition.trigger.type === "campaign_sent"}
                campaignId={definition.trigger.campaign_id}
                count={definition.yes.length + definition.no.length}
              />
            ) : (
              summary(t, definition)
            )}
          </p>
        </div>
        <Badge tone={STATUS_TONE[automation.status]}>
          {t(`automations.status.${automation.status}` as MessageId)}
        </Badge>
      </div>
      {problem ? (
        <p className="notice error" role="alert">
          {t(problem)}
        </p>
      ) : null}
      <div className="automation-card-actions">
        <Button
          size="sm"
          variant="ghost"
          aria-expanded={showingRuns}
          onPress={onRuns}
        >
          {t(showingRuns ? "automations.hideRuns" : "automations.showRuns")}
        </Button>
        {canManage ? (
          <>
            {automation.status !== "active" ? (
              <Button size="sm" onPress={onEdit}>
                <Pencil size={13} aria-hidden="true" />
                {t("automations.edit")}
              </Button>
            ) : null}
            {automation.status === "active" ? (
              <Button
                size="sm"
                isDisabled={change.isPending}
                onPress={() => {
                  toggle("pause");
                }}
              >
                <Pause size={13} aria-hidden="true" />
                {t("automations.pause")}
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                isDisabled={change.isPending}
                onPress={() => {
                  toggle("activate");
                }}
              >
                <Play size={13} aria-hidden="true" />
                {t("automations.activate")}
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              aria-label={t("automations.deleteNamed", {
                name: automation.name,
              })}
              onPress={() => {
                setConfirming(true);
              }}
            >
              <Trash2 size={13} aria-hidden="true" />
            </Button>
          </>
        ) : null}
      </div>
      {showingRuns ? (
        <Runs
          workspaceId={workspaceId}
          id={automation.id}
          onOpenContact={onOpenContact}
        />
      ) : null}
      <ConfirmDialog
        isOpen={confirming}
        title={t("automations.deleteTitle")}
        message={t("automations.deleteMessage", { name: automation.name })}
        confirmLabel={t("automations.delete")}
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
          setConfirming(false);
          remove.mutate(
            { id: automation.id },
            {
              onSuccess: () => {
                toast(t("automations.deleted"));
              },
              onError: (error) => {
                setProblem(failure(error));
              },
            },
          );
        }}
      />
    </li>
  );
}

function Runs({
  workspaceId,
  id,
  onOpenContact,
}: {
  workspaceId: string;
  id: string;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const runs = useAutomationRuns(workspaceId, id);
  if (runs.isError)
    return <LoadError error={runs.error} onRetry={() => void runs.refetch()} />;
  if (runs.isPending) return <Loading />;
  const items = runs.data.items;
  if (!items.length) return <p className="muted">{t("automations.noRuns")}</p>;
  return (
    <div className="table-scroll">
      <table className="records-table automation-runs">
        <caption className="sr-only">{t("automations.runs")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("automations.run.started")}</th>
            <th scope="col">{t("automations.run.contact")}</th>
            <th scope="col">{t("automations.run.status")}</th>
            <th scope="col">{t("automations.run.steps")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((run) => (
            <tr key={run.id}>
              <td>
                <When value={run.created_at} />
              </td>
              <td>
                {run.contact_id ? (
                  <AriaButton
                    className="record-link"
                    onPress={() => {
                      if (run.contact_id) onOpenContact(run.contact_id);
                    }}
                  >
                    {t("automations.run.openContact")}
                  </AriaButton>
                ) : (
                  <span className="muted">
                    {t("automations.run.contactGone")}
                  </span>
                )}
              </td>
              <td>
                <Badge tone={RUN_TONE[run.status]}>
                  {t(`automations.runStatus.${run.status}` as MessageId)}
                </Badge>
                <RunWait run={run} />
                {run.last_error ? (
                  <span className="muted"> · {run.last_error}</span>
                ) : null}
              </td>
              <td className="secondary">
                {t("automations.run.done", {
                  done: run.steps.filter((s) => s.outcome === "done").length,
                  skipped: run.steps.filter((s) => s.outcome === "skipped")
                    .length,
                })}
                {run.branch
                  ? ` · ${t(run.branch === "yes" ? "automations.yes" : "automations.no")}`
                  : ""}
                <RunEmails run={run} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/*
 * How long a waiting run waits: until its time, or, waiting for a field
 * value (P8-J), until the wait gives up.
 */
function RunWait({ run }: { run: AutomationRun }) {
  const t = useT();
  if (run.status !== "waiting") return null;
  if (run.field_wait_until)
    return (
      <span className="muted">
        {" · "}
        {t("automations.run.fieldWaitUntil")}{" "}
        <When value={run.field_wait_until} />
      </span>
    );
  if (!run.resume_at) return null;
  return (
    <span className="muted">
      {" · "}
      {t("automations.run.waitUntil")} <When value={run.resume_at} />
    </span>
  );
}

/*
 * What each send-email step of a run did (P8-E): queued, recorded in a
 * rehearsal, or not sent and why. The reasons are the step's skip codes.
 */
const EMAIL_SKIPS = new Set([
  "no_content",
  "no_email",
  "sending_unavailable",
  "not_eligible",
  "daily_limit",
  "invalid_email",
]);

function emailResult(
  step: AutomationRun["steps"][number],
  t: ReturnType<typeof useT>,
): string {
  if (step.outcome === "done")
    return t(
      step.detail === "rehearsal"
        ? "automations.run.email.rehearsal"
        : "automations.run.email.queued",
    );
  const code =
    step.detail && EMAIL_SKIPS.has(step.detail) ? step.detail : "unknown";
  return t("automations.run.email.skipped", {
    reason: t(`automations.run.email.reason.${code}` as MessageId),
  });
}

function RunEmails({ run }: { run: AutomationRun }) {
  const t = useT();
  const sends = run.steps.filter((s) => s.action === "send_email");
  if (sends.length === 0) return null;
  return (
    <ul className="run-emails muted">
      {sends.map((step) => (
        <li key={`${step.branch}-${step.position}`}>{emailResult(step, t)}</li>
      ))}
    </ul>
  );
}

function fieldStart(field: FieldDefinition | undefined): string | boolean {
  if (field?.field_type === "select") return field.options?.[0] ?? "";
  if (field?.field_type === "boolean") return true;
  return "";
}

function newAction(
  type: Action["type"],
  tags: Option[],
  members: Option[],
  fields: FieldDefinition[],
  templates: Option[],
): Action {
  if (type === "send_email")
    return {
      type,
      template_id: templates[0]?.id ?? "",
      daily_limit: DAILY_LIMIT_DEFAULT,
    };
  if (type === "add_tag" || type === "remove_tag")
    return { type, tag_id: tags[0]?.id ?? "" };
  if (type === "set_lifecycle_stage") return { type, stage: "customer" };
  if (type === "assign_owner") return { type, user_id: members[0]?.id ?? "" };
  if (type === "wait") return { type, minutes: 60 };
  if (type === "wait_for_business_hours") return { type };
  if (type === "wait_until_date")
    return {
      type,
      field_key: fields.find((f) => f.field_type === "date")?.key ?? "",
      offset_days: 0,
      hour: 9,
    };
  if (type === "set_custom_field")
    return {
      type,
      field_key: fields[0]?.key ?? "",
      value: fieldStart(fields[0]),
    };
  if (type === "wait_for_field")
    return { type, field_key: fields[0]?.key ?? "", max_days: 7 };
  if (type === "notify_member")
    return { type, recipient: "contact_owner", message: "" };
  if (type === "assign_round_robin")
    return {
      type,
      user_ids: members.slice(0, ROTATION_MIN).map((member) => member.id),
    };
  return {
    type,
    title: "",
    priority: "medium",
    due_minutes: 60,
    assignee: "contact_owner",
  };
}

function newTrigger(
  type: TriggerType,
  tags: Option[],
  stages: Option[],
  dateKey: string,
): Trigger {
  if (type === "date_reached")
    return { type, field_key: dateKey, offset_days: 0, hour: 9 };
  if (type === "tag_added") return { type, tag_id: tags[0]?.id ?? "" };
  if (type === "form_submitted") return { type, form_id: null };
  if (type === "appointment_booked") return { type, booking_page_id: null };
  if (type === "deal_stage_changed")
    return { type, stage_id: stages[0]?.id ?? "" };
  if (type === "campaign_sent" || type === "campaign_unsubscribed")
    return { type, campaign_id: null };
  return { type: "contact_created", sources: [] };
}

/** The campaign a campaign trigger is limited to (P8-C), or any. */
function CampaignPick({
  workspaceId,
  value,
  onChange,
}: {
  workspaceId: string;
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const t = useT();
  const list = useCampaigns(workspaceId, {
    order: "created_at",
    archived: false,
    status: null,
    search: "",
  });
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <select
      className="form-input"
      aria-label={t("automations.triggerCampaign")}
      value={value ?? ""}
      onChange={(event) => {
        onChange(event.target.value || null);
      }}
    >
      <option value="">{t("automations.triggerAny")}</option>
      {value && !items.some((item) => item.id === value) ? (
        <option value={value}>{t("automations.triggerCampaignUnlisted")}</option>
      ) : null}
      {items.map((item) => (
        <option key={item.id} value={item.id}>
          {item.name}
        </option>
      ))}
    </select>
  );
}

/** The trigger (P8-B): its type, then what it is limited to. */
function TriggerFields({
  workspaceId,
  trigger,
  tags,
  fields,
  onChange,
}: {
  workspaceId: string;
  trigger: Trigger;
  tags: Option[];
  fields: FieldDefinition[];
  onChange: (trigger: Trigger) => void;
}) {
  const t = useT();
  const forms = useForms(workspaceId, trigger.type === "form_submitted");
  const pages = useBookingPages(
    workspaceId,
    trigger.type === "appointment_booked",
  );
  const pipelines = usePipelines(workspaceId);
  const stages: Option[] = (pipelines.data?.items[0]?.stages ?? []).map(
    (stage) => ({
      id: stage.id,
      label: stage.name,
    }),
  );
  const pick = (
    label: MessageId,
    value: string,
    options: Option[],
    any: boolean,
    apply: (id: string) => void,
  ) => (
    <select
      className="form-input"
      aria-label={t(label)}
      value={value}
      onChange={(event) => {
        apply(event.target.value);
      }}
    >
      {any ? <option value="">{t("automations.triggerAny")}</option> : null}
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
  return (
    <fieldset className="form-field wide automation-block">
      <legend className="form-label">{t("automations.trigger")}</legend>
      <select
        className="form-input"
        aria-label={t("automations.triggerKind")}
        value={trigger.type}
        onChange={(event) => {
          onChange(
            newTrigger(
              event.target.value as TriggerType,
              tags,
              stages,
              fields.find((f) => f.field_type === "date")?.key ?? "",
            ),
          );
        }}
      >
        {TRIGGER_TYPES.map((type) => (
          <option key={type} value={type}>
            {t(`automations.triggerType.${type}` as MessageId)}
          </option>
        ))}
      </select>
      <p className="form-hint">{t("automations.triggerOnce")}</p>
      {trigger.type === "contact_created" ? (
        <>
          <p className="form-hint">{t("automations.triggerHint")}</p>
          <div className="automation-checks">
            {TRIGGER_SOURCES.map((source: Source) => (
              <label key={source} className="public-check-label">
                <input
                  type="checkbox"
                  checked={trigger.sources.includes(source)}
                  onChange={(event) => {
                    const sources = event.target.checked
                      ? [...trigger.sources, source]
                      : trigger.sources.filter((s) => s !== source);
                    onChange({ type: "contact_created", sources });
                  }}
                />
                <span>{t(`source.${source}` as MessageId)}</span>
              </label>
            ))}
          </div>
        </>
      ) : null}
      {trigger.type === "tag_added"
        ? pick("automations.triggerTag", trigger.tag_id, tags, false, (id) => {
            onChange({ type: "tag_added", tag_id: id });
          })
        : null}
      {trigger.type === "form_submitted"
        ? pick(
            "automations.triggerForm",
            trigger.form_id ?? "",
            (forms.data?.items ?? []).map((form) => ({
              id: form.id,
              label: form.name,
            })),
            true,
            (id) => {
              onChange({ type: "form_submitted", form_id: id || null });
            },
          )
        : null}
      {trigger.type === "appointment_booked"
        ? pick(
            "automations.triggerPage",
            trigger.booking_page_id ?? "",
            (pages.data?.items ?? []).map((page) => ({
              id: page.id,
              label: page.name,
            })),
            true,
            (id) => {
              onChange({
                type: "appointment_booked",
                booking_page_id: id || null,
              });
            },
          )
        : null}
      {trigger.type === "deal_stage_changed"
        ? pick(
            "automations.triggerStage",
            trigger.stage_id,
            stages,
            false,
            (id) => {
              onChange({ type: "deal_stage_changed", stage_id: id });
            },
          )
        : null}
      {trigger.type === "campaign_sent" ||
      trigger.type === "campaign_unsubscribed" ? (
        <>
          <p className="form-hint">
            {t(
              trigger.type === "campaign_sent"
                ? "automations.triggerSentHint"
                : "automations.triggerUnsubscribedHint",
            )}
          </p>
          <CampaignPick
            workspaceId={workspaceId}
            value={trigger.campaign_id}
            onChange={(id) => {
              onChange({ type: trigger.type, campaign_id: id });
            }}
          />
        </>
      ) : null}
      {trigger.type === "date_reached" ? (
        <>
          <DateParts
            value={trigger}
            fields={fields}
            label={(field) => t(field)}
            onChange={(parts) => {
              onChange({ type: "date_reached", ...parts });
            }}
          />
          <p className="form-hint">{t("automations.triggerDateHint")}</p>
        </>
      ) : null}
    </fieldset>
  );
}

function startValues(field: FieldDefinition | undefined): FieldValue[] {
  const start = fieldStart(field);
  return start === "" ? [] : [start];
}

function fieldCondition(field: FieldDefinition | undefined): Condition {
  return {
    field: "custom_field",
    key: field?.key ?? "",
    op: "in",
    values: startValues(field),
  };
}

function startingCondition(
  kind: ConditionKind,
  tags: Option[],
  fields: FieldDefinition[],
  stages: Option[],
): Condition | null {
  if (kind === "custom_field") return fieldCondition(fields[0]);
  if (kind === "deal") return { field: "deal", op: "has", values: ["open"] };
  if (kind === "deal_stage")
    return {
      field: "deal_stage",
      op: "has",
      values: stages[0] ? [stages[0].id] : [],
    };
  if (kind === "source") return { field: "source", op: "in", values: ["form"] };
  if (kind === "lifecycle_stage")
    return { field: "lifecycle_stage", op: "in", values: ["lead"] };
  if (kind === "email") return { field: "email", op: "present" };
  if (kind === "tag")
    return { field: "tag", op: "has", values: tags[0] ? [tags[0].id] : [] };
  return null;
}

function AutomationEditor({
  workspaceId,
  automation,
  initial = null,
  onClose,
}: {
  workspaceId: string;
  automation: Automation | null;
  /** A new automation's starting definition (from a form, P7-FA). */
  initial?: Definition | null;
  onClose: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const me = useMe();
  const tagsQuery = useTags(workspaceId);
  const membersQuery = useMembers(workspaceId, 0, true);
  const fieldsQuery = useFieldDefinitions(workspaceId);
  const fields = activeFields(fieldsQuery.data?.items, "contact");
  const templatesQuery = useEmailTemplates(workspaceId);
  const templates: Option[] = (templatesQuery.data?.items ?? []).map(
    (template) => ({ id: template.id, label: template.name }),
  );
  const pipelinesQuery = usePipelines(workspaceId);
  const pipelines = pipelinesQuery.data?.items ?? [];
  // Every pipeline's stages; named with their pipeline when there are several.
  const stages: Option[] = pipelines.flatMap((pipeline) =>
    pipeline.stages.map((stage) => ({
      id: stage.id,
      label:
        pipelines.length > 1 ? `${pipeline.name} · ${stage.name}` : stage.name,
    })),
  );
  const settingsQuery = useWorkspaceSettings(workspaceId);
  // Unknown (undefined) while loading or unreadable: no warning is shown.
  const hoursSet =
    settingsQuery.data === undefined
      ? undefined
      : settingsQuery.data.business_hours !== null;
  const create = useCreateAutomation(workspaceId);
  const update = useUpdateAutomation(workspaceId);
  const [name, setName] = useState(automation?.name ?? "");
  const [definition, setDefinition] = useState<Definition>(
    (automation?.definition as unknown as Definition | undefined) ??
      initial ??
      EMPTY_DEFINITION,
  );
  const [problem, setProblem] = useState<MessageId | null>(null);
  const tags: Option[] = (tagsQuery.data?.items ?? []).map((tag) => ({
    id: tag.id,
    label: tag.name,
  }));
  const members = ownerOptions(
    t,
    membersQuery.data?.items ?? [],
    me.data?.user_id,
  );
  const busy = create.isPending || update.isPending;
  const set = (next: Partial<Definition>) => {
    setDefinition((current) => ({ ...current, ...next }));
  };
  const conditionKind: ConditionKind = definition.condition?.field ?? "none";

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setProblem("automations.error.name");
      return;
    }
    const done = () => {
      toast(t(automation ? "automations.saved" : "automations.created"));
      onClose();
    };
    const failed = (error: unknown) => {
      setProblem(failure(error));
    };
    if (automation) {
      update.mutate(
        {
          id: automation.id,
          version: automation.version,
          name: name.trim(),
          definition,
        },
        { onSuccess: done, onError: failed },
      );
    } else {
      create.mutate(
        { name: name.trim(), definition },
        { onSuccess: done, onError: failed },
      );
    }
  };

  return (
    <Dialog
      isOpen
      title={t(automation ? "automations.dialogEdit" : "automations.dialogNew")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button
            variant="primary"
            type="submit"
            form="automation-form"
            isDisabled={busy}
          >
            {t(automation ? "automations.save" : "automations.create")}
          </Button>
        </>
      }
    >
      <form
        id="automation-form"
        className="form-grid automation-form"
        onSubmit={submit}
      >
        <div className="form-field wide">
          <label htmlFor="automation-name" className="form-label">
            {t("automations.field.name")}
          </label>
          <input
            id="automation-name"
            className="form-input"
            value={name}
            maxLength={100}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </div>
        <TriggerFields
          workspaceId={workspaceId}
          trigger={definition.trigger}
          tags={tags}
          fields={fields}
          onChange={(trigger) => {
            set({ trigger });
          }}
        />
        <fieldset className="form-field wide automation-block">
          <legend className="form-label">{t("automations.condition")}</legend>
          <select
            className="form-input"
            aria-label={t("automations.conditionKind")}
            value={conditionKind}
            onChange={(event) => {
              const condition = startingCondition(
                event.target.value as ConditionKind,
                tags,
                fields,
                stages,
              );
              set({ condition, no: condition ? definition.no : [] });
            }}
          >
            <option value="none">{t("automations.condition.none")}</option>
            <option value="source">{t("automations.condition.source")}</option>
            <option value="lifecycle_stage">
              {t("automations.condition.stage")}
            </option>
            <option value="email">{t("automations.condition.email")}</option>
            <option value="tag">{t("automations.condition.tag")}</option>
            <option value="custom_field">
              {t("automations.condition.customField")}
            </option>
            <option value="deal">{t("automations.condition.deal")}</option>
            <option value="deal_stage" disabled={stages.length === 0}>
              {t("automations.condition.dealStage")}
            </option>
          </select>
          {definition.condition ? (
            <ConditionEditor
              condition={definition.condition}
              tags={tags}
              fields={fields}
              stages={stages}
              onChange={(condition) => {
                set({ condition });
              }}
            />
          ) : null}
        </fieldset>
        <Branch
          label={t(
            definition.condition
              ? "automations.yesBranch"
              : "automations.actions",
          )}
          actions={definition.yes}
          tags={tags}
          members={members}
          fields={fields}
          templates={templates}
          hoursSet={hoursSet}
          onChange={(yes) => {
            set({ yes });
          }}
        />
        {definition.condition ? (
          <Branch
            label={t("automations.noBranch")}
            actions={definition.no}
            tags={tags}
            members={members}
            fields={fields}
            templates={templates}
            hoursSet={hoursSet}
            onChange={(no) => {
              set({ no });
            }}
          />
        ) : null}
        <p className="form-hint wide">{t("automations.editorHint")}</p>
        {problem ? (
          <p className="notice error form-field wide" role="alert">
            {t(problem)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

function ConditionEditor({
  condition,
  tags,
  fields,
  stages,
  onChange,
}: {
  condition: Condition;
  tags: Option[];
  fields: FieldDefinition[];
  stages: Option[];
  onChange: (condition: Condition) => void;
}) {
  const t = useT();
  if (condition.field === "custom_field") {
    return (
      <FieldCondition condition={condition} fields={fields} onChange={onChange} />
    );
  }
  if (condition.field === "email") {
    return (
      <select
        className="form-input"
        aria-label={t("automations.conditionOp")}
        value={condition.op}
        onChange={(event) => {
          onChange({
            field: "email",
            op: event.target.value as "present" | "absent",
          });
        }}
      >
        <option value="present">{t("automations.op.present")}</option>
        <option value="absent">{t("automations.op.absent")}</option>
      </select>
    );
  }
  const isTag =
    condition.field === "tag" ||
    condition.field === "deal" ||
    condition.field === "deal_stage";
  const choices: Option[] =
    condition.field === "tag"
      ? tags
      : condition.field === "deal_stage"
        ? [
            ...stages,
            // A stage removed since it was chosen stays listed, so it can be
            // cleared; activation refuses it (P8-H).
            ...condition.values
              .filter((id) => !stages.some((stage) => stage.id === id))
              .map((id) => ({ id, label: t("automations.stageGone") })),
          ]
        : condition.field === "deal"
          ? OUTCOMES.map((o) => ({
              id: o,
              label: t(`automations.outcome.${o}` as MessageId),
            }))
          : condition.field === "source"
            ? SOURCES.map((s) => ({
                id: s,
                label: t(`source.${s}` as MessageId),
              }))
            : STAGES.map((s) => ({
                id: s,
                label: t(`stage.${s}` as MessageId),
              }));
  const values = condition.values as string[];
  return (
    <>
      <select
        className="form-input"
        aria-label={t("automations.conditionOp")}
        value={condition.op}
        onChange={(event) => {
          onChange({ ...condition, op: event.target.value } as Condition);
        }}
      >
        <option value={isTag ? "has" : "in"}>
          {t(isTag ? "automations.op.has" : "automations.op.in")}
        </option>
        <option value={isTag ? "has_not" : "not_in"}>
          {t(isTag ? "automations.op.hasNot" : "automations.op.notIn")}
        </option>
      </select>
      <div className="automation-checks">
        {choices.map((choice) => (
          <label key={choice.id} className="public-check-label">
            <input
              type="checkbox"
              checked={values.includes(choice.id)}
              onChange={(event) => {
                const next = event.target.checked
                  ? [...values, choice.id]
                  : values.filter((v) => v !== choice.id);
                onChange({ ...condition, values: next } as Condition);
              }}
            />
            <span>{choice.label}</span>
          </label>
        ))}
      </div>
    </>
  );
}

function Branch({
  label,
  actions,
  tags,
  members,
  fields,
  templates,
  hoursSet,
  onChange,
}: {
  label: string;
  actions: Action[];
  tags: Option[];
  members: Option[];
  fields: FieldDefinition[];
  templates: Option[];
  hoursSet: boolean | undefined;
  onChange: (actions: Action[]) => void;
}) {
  const t = useT();
  const [adding, setAdding] = useState<Action["type"]>("create_task");
  return (
    <fieldset className="form-field wide automation-block">
      <legend className="form-label">{label}</legend>
      {actions.length ? (
        <ol className="automation-steps">
          {actions.map((action, index) => (
            <li key={index} className="automation-step">
              <span className="automation-step-number" aria-hidden="true">
                {index + 1}
              </span>
              <ActionEditor
                action={action}
                index={index}
                branch={label}
                tags={tags}
                members={members}
                fields={fields}
                templates={templates}
                hoursSet={hoursSet}
                onChange={(next) => {
                  onChange(
                    actions.map((current, i) => (i === index ? next : current)),
                  );
                }}
              />
              <Button
                size="sm"
                variant="ghost"
                aria-label={t("automations.removeStep", {
                  branch: label,
                  number: index + 1,
                })}
                onPress={() => {
                  onChange(actions.filter((_, i) => i !== index));
                }}
              >
                <X size={13} aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">{t("automations.noSteps")}</p>
      )}
      {actions.length < MAX_ACTIONS ? (
        <div className="automation-add">
          <select
            className="form-input"
            aria-label={t("automations.addKind", { branch: label })}
            value={adding}
            onChange={(event) => {
              setAdding(event.target.value as Action["type"]);
            }}
          >
            <option value="create_task">
              {t("automations.action.create_task")}
            </option>
            <option value="add_tag">{t("automations.action.add_tag")}</option>
            <option value="remove_tag">
              {t("automations.action.remove_tag")}
            </option>
            <option value="assign_owner">
              {t("automations.action.assign_owner")}
            </option>
            <option value="assign_round_robin">
              {t("automations.action.assign_round_robin")}
            </option>
            <option value="set_lifecycle_stage">
              {t("automations.action.set_lifecycle_stage")}
            </option>
            <option value="notify_member">
              {t("automations.action.notify_member")}
            </option>
            <option value="set_custom_field">
              {t("automations.action.set_custom_field")}
            </option>
            <option value="wait">{t("automations.action.wait")}</option>
            <option value="wait_for_business_hours">
              {t("automations.action.wait_for_business_hours")}
            </option>
            <option value="wait_until_date">
              {t("automations.action.wait_until_date")}
            </option>
            <option value="wait_for_field">
              {t("automations.action.wait_for_field")}
            </option>
            <option value="send_email">
              {t("automations.action.send_email")}
            </option>
          </select>
          <Button
            size="sm"
            aria-label={t("automations.addStepTo", { branch: label })}
            onPress={() => {
              onChange([
                ...actions,
                newAction(adding, tags, members, fields, templates),
              ]);
            }}
          >
            <Plus size={13} aria-hidden="true" />
            {t("automations.addStep")}
          </Button>
        </div>
      ) : null}
    </fieldset>
  );
}

function ActionEditor({
  action,
  index,
  branch,
  tags,
  members,
  fields,
  templates,
  hoursSet,
  onChange,
}: {
  action: Action;
  index: number;
  branch: string;
  tags: Option[];
  members: Option[];
  fields: FieldDefinition[];
  templates: Option[];
  hoursSet: boolean | undefined;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  const kind = t(`automations.action.${action.type}` as MessageId);
  const label = (field: MessageId) =>
    t("automations.fieldOf", { field: t(field), branch, number: index + 1 });
  if (action.type === "send_email") {
    return (
      <EmailStep
        action={action}
        kind={kind}
        templates={templates}
        label={label}
        onChange={onChange}
      />
    );
  }
  if (action.type === "set_lifecycle_stage") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <select
          className="form-input"
          aria-label={label("automations.field.stage")}
          value={action.stage}
          onChange={(event) => {
            onChange({ ...action, stage: event.target.value });
          }}
        >
          {STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {t(`stage.${stage}` as MessageId)}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (action.type === "set_custom_field") {
    return (
      <FieldStep
        action={action}
        kind={kind}
        fields={fields}
        label={label}
        onChange={onChange}
      />
    );
  }
  if (action.type === "add_tag" || action.type === "remove_tag") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <select
          className="form-input"
          aria-label={label("automations.field.tag")}
          value={action.tag_id}
          onChange={(event) => {
            onChange({ ...action, tag_id: event.target.value });
          }}
        >
          {!tags.length ? (
            <option value="">{t("automations.noTags")}</option>
          ) : null}
          {tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (action.type === "assign_owner") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <select
          className="form-input"
          aria-label={label("automations.field.member")}
          value={action.user_id}
          onChange={(event) => {
            onChange({ ...action, user_id: event.target.value });
          }}
        >
          {members.map((member) => (
            <option key={member.id} value={member.id}>
              {member.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (action.type === "assign_round_robin") {
    // Members no longer listed (they left) stay in the step until unticked,
    // so an edit never silently drops them; the server passes them over.
    const known = new Set(members.map((member) => member.id));
    const gone = members.length
      ? action.user_ids.filter((id) => !known.has(id))
      : [];
    const toggle = (id: string, on: boolean) => {
      onChange({
        ...action,
        user_ids: on
          ? [...action.user_ids, id]
          : action.user_ids.filter((current) => current !== id),
      });
    };
    return (
      <fieldset className="automation-step-body automation-rotation">
        <legend className="automation-step-kind">
          {kind}
          <span className="visually-hidden">
            {` — ${t("automations.rotationMembers", { branch, number: index + 1 })}`}
          </span>
        </legend>
        <p className="form-hint">
          {t("automations.rotationHint", {
            min: ROTATION_MIN,
            max: ROTATION_MAX,
          })}
        </p>
        <div className="automation-checks">
          {[
            ...members,
            ...gone.map((id) => ({ id, label: t("automations.formerMember") })),
          ].map((member) => {
            const checked = action.user_ids.includes(member.id);
            return (
              <label key={member.id} className="public-check-label">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={!checked && action.user_ids.length >= ROTATION_MAX}
                  onChange={(event) => {
                    toggle(member.id, event.target.checked);
                  }}
                />
                <span>{member.label}</span>
              </label>
            );
          })}
        </div>
      </fieldset>
    );
  }
  if (action.type === "notify_member") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <select
          className="form-input"
          aria-label={label("automations.field.recipient")}
          value={action.recipient}
          onChange={(event) => {
            onChange({ ...action, recipient: event.target.value });
          }}
        >
          <option value="contact_owner">
            {t("automations.assignee.owner")}
          </option>
          {members.map((member) => (
            <option key={member.id} value={member.id}>
              {member.label}
            </option>
          ))}
        </select>
        <input
          className="form-input"
          aria-label={label("automations.field.message")}
          placeholder={t("automations.messagePlaceholder")}
          value={action.message}
          maxLength={NOTICE_MAX}
          onChange={(event) => {
            onChange({ ...action, message: event.target.value });
          }}
        />
      </div>
    );
  }
  if (action.type === "wait_for_field") {
    return (
      <FieldWaitStep
        action={action}
        kind={kind}
        fields={fields}
        label={label}
        onChange={onChange}
      />
    );
  }
  if (action.type === "wait_until_date") {
    return (
      <DateWaitStep
        action={action}
        kind={kind}
        fields={fields}
        label={label}
        onChange={onChange}
      />
    );
  }
  if (action.type === "wait_for_business_hours") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <p className="form-hint">{t("automations.businessHoursHint")}</p>
        {hoursSet === false ? (
          <p className="notice info">{t("automations.businessHoursUnset")}</p>
        ) : null}
      </div>
    );
  }
  if (action.type === "wait") {
    return (
      <div className="automation-step-body">
        <span className="automation-step-kind">{kind}</span>
        <select
          className="form-input"
          aria-label={label("automations.field.wait")}
          value={action.minutes}
          onChange={(event) => {
            onChange({ ...action, minutes: Number(event.target.value) });
          }}
        >
          {[...new Set([...WAITS, action.minutes])].map((minutes) => (
            <option key={minutes} value={minutes}>
              {minutesLabel(t, minutes)}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div className="automation-step-body">
      <span className="automation-step-kind">{kind}</span>
      <input
        className="form-input"
        aria-label={label("automations.field.title")}
        value={action.title}
        maxLength={200}
        onChange={(event) => {
          onChange({ ...action, title: event.target.value });
        }}
      />
      <select
        className="form-input"
        aria-label={label("automations.field.priority")}
        value={action.priority}
        onChange={(event) => {
          onChange({
            ...action,
            priority: event.target.value as "high" | "medium" | "low",
          });
        }}
      >
        <option value="high">{t("tasks.priority.high")}</option>
        <option value="medium">{t("tasks.priority.medium")}</option>
        <option value="low">{t("tasks.priority.low")}</option>
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.due")}
        value={action.due_minutes ?? ""}
        onChange={(event) => {
          onChange({
            ...action,
            due_minutes:
              event.target.value === "" ? null : Number(event.target.value),
          });
        }}
      >
        {DUES.map((minutes) => (
          <option key={minutes ?? "none"} value={minutes ?? ""}>
            {minutes === null
              ? t("automations.noDue")
              : t("automations.dueIn", { when: minutesLabel(t, minutes) })}
          </option>
        ))}
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.assignee")}
        value={action.assignee}
        onChange={(event) => {
          onChange({ ...action, assignee: event.target.value });
        }}
      >
        <option value="contact_owner">{t("automations.assignee.owner")}</option>
        <option value="none">{t("automations.assignee.none")}</option>
        {members.map((member) => (
          <option key={member.id} value={member.id}>
            {member.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/*
 * P8-F: which contact field, then a value in the control its type takes.
 * A field archived since (or never known) stays chosen until changed, so an
 * edit never silently swaps it; activation refuses it.
 */
function FieldStep({
  action,
  kind,
  fields,
  label,
  onChange,
}: {
  action: Extract<Action, { type: "set_custom_field" }>;
  kind: string;
  fields: FieldDefinition[];
  label: (field: MessageId) => string;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  const field = fields.find((candidate) => candidate.key === action.field_key);
  const valueLabel = label("automations.field.value");
  const setValue = (value: string | number | boolean) => {
    onChange({ ...action, value });
  };
  let control = null;
  if (field?.field_type === "select") {
    control = (
      <select
        className="form-input"
        aria-label={valueLabel}
        value={String(action.value)}
        onChange={(event) => {
          setValue(event.target.value);
        }}
      >
        {(field.options ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  } else if (field?.field_type === "boolean") {
    control = (
      <select
        className="form-input"
        aria-label={valueLabel}
        value={action.value === false ? "no" : "yes"}
        onChange={(event) => {
          setValue(event.target.value === "yes");
        }}
      >
        <option value="yes">{t("automations.valueYes")}</option>
        <option value="no">{t("automations.valueNo")}</option>
      </select>
    );
  } else if (field) {
    const numeric = field.field_type === "number";
    control = (
      <input
        className="form-input"
        aria-label={valueLabel}
        type={field.field_type}
        maxLength={field.field_type === "text" ? 500 : undefined}
        value={typeof action.value === "boolean" ? "" : action.value}
        onChange={(event) => {
          const raw = event.target.value;
          setValue(numeric && raw !== "" ? Number(raw) : raw);
        }}
      />
    );
  }
  return (
    <div className="automation-step-body">
      <span className="automation-step-kind">{kind}</span>
      <select
        className="form-input"
        aria-label={label("automations.field.customField")}
        value={action.field_key}
        onChange={(event) => {
          const next = fields.find((f) => f.key === event.target.value);
          onChange({
            ...action,
            field_key: event.target.value,
            value: fieldStart(next),
          });
        }}
      >
        {!fields.length && !action.field_key ? (
          <option value="">{t("automations.noFields")}</option>
        ) : null}
        {action.field_key && !field ? (
          <option value={action.field_key}>{t("automations.fieldGone")}</option>
        ) : null}
        {fields.map((option) => (
          <option key={option.id} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      {control}
      <p className="form-hint">{t("automations.fieldHint")}</p>
    </div>
  );
}

const WAIT_DAYS = [1, 2, 3, 7, 14, 30, 60, 90, 180, 365];

/*
 * P8-J: which contact custom field to wait for, and for how many days at
 * most. A field archived since stays chosen until changed.
 */
function FieldWaitStep({
  action,
  kind,
  fields,
  label,
  onChange,
}: {
  action: Extract<Action, { type: "wait_for_field" }>;
  kind: string;
  fields: FieldDefinition[];
  label: (field: MessageId) => string;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  const known = fields.some((f) => f.key === action.field_key);
  return (
    <div className="automation-step-body">
      <span className="automation-step-kind">{kind}</span>
      <select
        className="form-input"
        aria-label={label("automations.field.customField")}
        value={action.field_key}
        onChange={(event) => {
          onChange({ ...action, field_key: event.target.value });
        }}
      >
        {!fields.length && !action.field_key ? (
          <option value="">{t("automations.noFields")}</option>
        ) : null}
        {action.field_key && !known ? (
          <option value={action.field_key}>{t("automations.fieldGone")}</option>
        ) : null}
        {fields.map((option) => (
          <option key={option.id} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.maxDays")}
        value={action.max_days}
        onChange={(event) => {
          onChange({ ...action, max_days: Number(event.target.value) });
        }}
      >
        {[...new Set([...WAIT_DAYS, action.max_days])]
          .sort((x, y) => x - y)
          .map((days) => (
            <option key={days} value={days}>
              {days === 1
                ? t("automations.maxDay")
                : t("automations.maxDays", { count: days })}
            </option>
          ))}
      </select>
      <p className="form-hint">{t("automations.fieldWaitHint")}</p>
    </div>
  );
}

const DAILY_LIMITS = [
  10,
  25,
  50,
  100,
  DAILY_LIMIT_DEFAULT,
  500,
  DAILY_LIMIT_MAX,
];

/*
 * P8-E: which email template to send, and the automation's limit per 24
 * hours. A template deleted since stays chosen until changed; activation
 * then refuses it.
 */
function EmailStep({
  action,
  kind,
  templates,
  label,
  onChange,
}: {
  action: Extract<Action, { type: "send_email" }>;
  kind: string;
  templates: Option[];
  label: (field: MessageId) => string;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  const known = templates.some((option) => option.id === action.template_id);
  return (
    <div className="automation-step-body">
      <span className="automation-step-kind">{kind}</span>
      <select
        className="form-input"
        aria-label={label("automations.field.template")}
        value={action.template_id}
        onChange={(event) => {
          onChange({ ...action, template_id: event.target.value });
        }}
      >
        {!templates.length && !action.template_id ? (
          <option value="">{t("automations.noTemplates")}</option>
        ) : null}
        {action.template_id && !known ? (
          <option value={action.template_id}>
            {t("automations.templateGone")}
          </option>
        ) : null}
        {templates.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.dailyLimit")}
        value={action.daily_limit}
        onChange={(event) => {
          onChange({ ...action, daily_limit: Number(event.target.value) });
        }}
      >
        {[...new Set([...DAILY_LIMITS, action.daily_limit])]
          .sort((x, y) => x - y)
          .map((count) => (
            <option key={count} value={count}>
              {count}
            </option>
          ))}
      </select>
      <p className="form-hint">{t("automations.emailHint")}</p>
    </div>
  );
}

const DAY_OFFSETS = [-30, -14, -7, -3, -1, 0, 1, 3, 7, 14, 30];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function dayOffsetLabel(t: T, days: number): string {
  if (days === 0) return t("automations.onTheDay");
  if (days === -1) return t("automations.dayBefore");
  if (days === 1) return t("automations.dayAfter");
  return t(days < 0 ? "automations.daysBefore" : "automations.daysAfter", {
    count: Math.abs(days),
  });
}

/*
 * P8-D: which contact date field, how many days before or after, and the
 * hour in the workspace's time zone. A field archived since stays chosen
 * until changed, like the field step.
 */
interface DatePartsValue {
  field_key: string;
  offset_days: number;
  hour: number;
}

/*
 * A contact date field, the days before or after it and the hour: the
 * "Wait until a date" step (P8-D) and the date trigger (P8-I).
 */
function DateParts({
  value: action,
  fields,
  label,
  onChange,
}: {
  value: DatePartsValue;
  fields: FieldDefinition[];
  label: (field: MessageId) => string;
  onChange: (value: DatePartsValue) => void;
}) {
  const t = useT();
  const dates = fields.filter((f) => f.field_type === "date");
  const known = dates.some((f) => f.key === action.field_key);
  const parts = {
    field_key: action.field_key,
    offset_days: action.offset_days,
    hour: action.hour,
  };
  return (
    <>
      <select
        className="form-input"
        aria-label={label("automations.field.dateField")}
        value={action.field_key}
        onChange={(event) => {
          onChange({ ...parts, field_key: event.target.value });
        }}
      >
        {!dates.length && !action.field_key ? (
          <option value="">{t("automations.noDateFields")}</option>
        ) : null}
        {action.field_key && !known ? (
          <option value={action.field_key}>{t("automations.fieldGone")}</option>
        ) : null}
        {dates.map((option) => (
          <option key={option.id} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.offsetDays")}
        value={action.offset_days}
        onChange={(event) => {
          onChange({ ...parts, offset_days: Number(event.target.value) });
        }}
      >
        {[...new Set([...DAY_OFFSETS, action.offset_days])]
          .sort((x, y) => x - y)
          .map((days) => (
            <option key={days} value={days}>
              {dayOffsetLabel(t, days)}
            </option>
          ))}
      </select>
      <select
        className="form-input"
        aria-label={label("automations.field.hour")}
        value={action.hour}
        onChange={(event) => {
          onChange({ ...parts, hour: Number(event.target.value) });
        }}
      >
        {HOURS.map((hour) => (
          <option key={hour} value={hour}>
            {`${String(hour).padStart(2, "0")}:00`}
          </option>
        ))}
      </select>
    </>
  );
}

function DateWaitStep({
  action,
  kind,
  fields,
  label,
  onChange,
}: {
  action: Extract<Action, { type: "wait_until_date" }>;
  kind: string;
  fields: FieldDefinition[];
  label: (field: MessageId) => string;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  return (
    <div className="automation-step-body">
      <span className="automation-step-kind">{kind}</span>
      <DateParts
        value={action}
        fields={fields}
        label={label}
        onChange={(parts) => {
          onChange({ type: "wait_until_date", ...parts });
        }}
      />
      <p className="form-hint">{t("automations.dateWaitHint")}</p>
    </div>
  );
}

/*
 * P8-G: which contact field, the test, then the values in the control its
 * type takes. A field archived since stays chosen until changed.
 */
function FieldCondition({
  condition,
  fields,
  onChange,
}: {
  condition: Extract<Condition, { field: "custom_field" }>;
  fields: FieldDefinition[];
  onChange: (condition: Condition) => void;
}) {
  const t = useT();
  const field = fields.find((candidate) => candidate.key === condition.key);
  const values: FieldValue[] = "values" in condition ? condition.values : [];
  const valueLabel = t("automations.conditionValue");
  const setValues = (next: FieldValue[]) => {
    onChange({
      field: "custom_field",
      key: condition.key,
      op: condition.op === "not_in" ? "not_in" : "in",
      values: next,
    });
  };
  let control = null;
  if ("values" in condition && field?.field_type === "select") {
    control = (
      <div className="automation-checks">
        {(field.options ?? []).map((option) => (
          <label key={option} className="public-check-label">
            <input
              type="checkbox"
              checked={values.includes(option)}
              onChange={(event) => {
                setValues(
                  event.target.checked
                    ? [...values, option]
                    : values.filter((v) => v !== option),
                );
              }}
            />
            <span>{option}</span>
          </label>
        ))}
      </div>
    );
  } else if ("values" in condition && field?.field_type === "boolean") {
    control = (
      <select
        className="form-input"
        aria-label={valueLabel}
        value={values[0] === false ? "no" : "yes"}
        onChange={(event) => {
          setValues([event.target.value === "yes"]);
        }}
      >
        <option value="yes">{t("automations.valueYes")}</option>
        <option value="no">{t("automations.valueNo")}</option>
      </select>
    );
  } else if ("values" in condition && field) {
    const numeric = field.field_type === "number";
    const first = values[0];
    control = (
      <input
        className="form-input"
        aria-label={valueLabel}
        type={field.field_type}
        maxLength={field.field_type === "text" ? 500 : undefined}
        value={first === undefined || typeof first === "boolean" ? "" : first}
        onChange={(event) => {
          const raw = event.target.value;
          setValues(raw === "" ? [] : [numeric ? Number(raw) : raw]);
        }}
      />
    );
  }
  return (
    <>
      <select
        className="form-input"
        aria-label={t("automations.conditionField")}
        value={condition.key}
        onChange={(event) => {
          onChange(
            fieldCondition(fields.find((f) => f.key === event.target.value)),
          );
        }}
      >
        {!fields.length && !condition.key ? (
          <option value="">{t("automations.noFields")}</option>
        ) : null}
        {condition.key && !field ? (
          <option value={condition.key}>{t("automations.fieldGone")}</option>
        ) : null}
        {fields.map((option) => (
          <option key={option.id} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        className="form-input"
        aria-label={t("automations.conditionOp")}
        value={condition.op}
        onChange={(event) => {
          const op = event.target.value as Condition["op"];
          if (op === "present" || op === "absent") {
            onChange({ field: "custom_field", key: condition.key, op });
          } else {
            onChange({
              field: "custom_field",
              key: condition.key,
              op: op === "not_in" ? "not_in" : "in",
              values: "values" in condition ? condition.values : startValues(field),
            });
          }
        }}
      >
        <option value="in">{t("automations.op.in")}</option>
        <option value="not_in">{t("automations.op.notIn")}</option>
        <option value="present">{t("automations.op.present")}</option>
        <option value="absent">{t("automations.op.absent")}</option>
      </select>
      {control}
      <p className="form-hint">{t("automations.conditionFieldHint")}</p>
    </>
  );
}
