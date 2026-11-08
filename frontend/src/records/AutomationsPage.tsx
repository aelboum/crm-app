import { Pause, Pencil, Play, Plus, Trash2, X } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import {
  type Action,
  type Automation,
  type AutomationRun,
  type Condition,
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
import { ApiError } from "../api/client";
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
 * offered; the design's email, SMS, notification and AI actions are not.
 * The server checks every definition again.
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
const WAITS = [15, 60, 240, 1440, 4320, 10080];
const DUES = [null, 15, 60, 1440, 4320];

type ConditionKind = "none" | "source" | "lifecycle_stage" | "email" | "tag";
type T = ReturnType<typeof useT>;

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "invalid_automation") return "automations.error.invalid";
    if (error.code === "automation_limit") return "automations.error.limit";
    if (error.code === "automation_active") return "automations.error.active";
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
  onNewDone = () => undefined,
}: {
  workspaceId: string;
  onOpenContact: (id: string) => void;
  /** Opens a new automation started by this form (`?create=automation&form=`). */
  newForForm?: string | null;
  /** Called when that editor closes, to clear the request. */
  onNewDone?: () => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const list = useAutomations(workspaceId);
  const [editing, setEditing] = useState<Automation | "new" | null>(
    newForForm ? "new" : null,
  );
  const [preset] = useState<Definition | null>(() =>
    newForForm
      ? {
          ...EMPTY_DEFINITION,
          trigger: { type: "form_submitted", form_id: newForForm },
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
            if (newForForm) onNewDone();
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
            {summary(t, definition)}
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
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function newAction(
  type: Action["type"],
  tags: Option[],
  members: Option[],
): Action {
  if (type === "add_tag" || type === "remove_tag")
    return { type, tag_id: tags[0]?.id ?? "" };
  if (type === "set_lifecycle_stage") return { type, stage: "customer" };
  if (type === "assign_owner") return { type, user_id: members[0]?.id ?? "" };
  if (type === "wait") return { type, minutes: 60 };
  if (type === "wait_for_business_hours") return { type };
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
): Trigger {
  if (type === "tag_added") return { type, tag_id: tags[0]?.id ?? "" };
  if (type === "form_submitted") return { type, form_id: null };
  if (type === "appointment_booked") return { type, booking_page_id: null };
  if (type === "deal_stage_changed")
    return { type, stage_id: stages[0]?.id ?? "" };
  return { type: "contact_created", sources: [] };
}

/** The trigger (P8-B): its type, then what it is limited to. */
function TriggerFields({
  workspaceId,
  trigger,
  tags,
  onChange,
}: {
  workspaceId: string;
  trigger: Trigger;
  tags: Option[];
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
          onChange(newTrigger(event.target.value as TriggerType, tags, stages));
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
    </fieldset>
  );
}

function startingCondition(
  kind: ConditionKind,
  tags: Option[],
): Condition | null {
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
          </select>
          {definition.condition ? (
            <ConditionEditor
              condition={definition.condition}
              tags={tags}
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
  onChange,
}: {
  condition: Condition;
  tags: Option[];
  onChange: (condition: Condition) => void;
}) {
  const t = useT();
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
  const isTag = condition.field === "tag";
  const choices: Option[] = isTag
    ? tags
    : condition.field === "source"
      ? SOURCES.map((s) => ({ id: s, label: t(`source.${s}` as MessageId) }))
      : STAGES.map((s) => ({ id: s, label: t(`stage.${s}` as MessageId) }));
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
              checked={condition.values.includes(choice.id)}
              onChange={(event) => {
                const values = event.target.checked
                  ? [...condition.values, choice.id]
                  : condition.values.filter((v) => v !== choice.id);
                onChange({ ...condition, values });
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
  hoursSet,
  onChange,
}: {
  label: string;
  actions: Action[];
  tags: Option[];
  members: Option[];
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
            <option value="wait">{t("automations.action.wait")}</option>
            <option value="wait_for_business_hours">
              {t("automations.action.wait_for_business_hours")}
            </option>
          </select>
          <Button
            size="sm"
            aria-label={t("automations.addStepTo", { branch: label })}
            onPress={() => {
              onChange([...actions, newAction(adding, tags, members)]);
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
  hoursSet,
  onChange,
}: {
  action: Action;
  index: number;
  branch: string;
  tags: Option[];
  members: Option[];
  hoursSet: boolean | undefined;
  onChange: (action: Action) => void;
}) {
  const t = useT();
  const kind = t(`automations.action.${action.type}` as MessageId);
  const label = (field: MessageId) =>
    t("automations.fieldOf", { field: t(field), branch, number: index + 1 });
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
