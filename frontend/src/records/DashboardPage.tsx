import { ChevronRight, ClockAlert, Hourglass } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { useIntl } from "react-intl";
import { Button as AriaButton } from "react-aria-components";

import { useAppointments } from "../api/appointments";
import { ApiError } from "../api/client";
import {
  type RecentEntry,
  TODAY_TASKS,
  useContactTotal,
  useRecentActivity,
  useTasksDueBy,
} from "../api/dashboard";
import {
  type DealFilters,
  minorDigits,
  useDealSummary,
} from "../api/opportunities";
import { usePipelines } from "../api/pipelines";
import {
  useAccess,
  useMe,
  useWorkspace,
  useWorkspaceSettings,
} from "../api/queries";
import { type Task, useTaskCounts, useUpdateTask } from "../api/tasks";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { STATUS_LABEL, STATUS_TONE } from "./appointmentParts";
import {
  addDecimals,
  formatMoney,
  moneyTotal,
  stageShade,
  totalsOf,
} from "./dealParts";
import { ACTIVITY_ICONS, useDescribe } from "./NotesSection";
import { ownerLabel, When } from "./parts";
import { DueText, taskRefusal } from "./taskParts";

/*
 * A workspace's Home page (decision P4-D): what needs attention, four
 * headline numbers, the pipeline by stage, today's appointments and tasks,
 * and recent activity on contacts and companies. Every number has a written
 * definition (P4-D 3) and comes from the same endpoint as the page it links
 * to; each card loads and fails on its own. The design's conversations,
 * campaigns and AI cards, its trend charts and its agency view are not
 * shown: their data does not exist yet.
 */

export interface HomeTarget {
  section: "contacts" | "companies" | "opportunities" | "tasks" | "calendar";
  record?: string;
  view?: "overdue" | "idle";
}

const OPEN: DealFilters = {
  q: "",
  outcomes: ["open"],
  stageIds: [],
  owners: [],
  idle: false,
  sort: "updated_at",
  direction: "desc",
};
const IDLE: DealFilters = { ...OPEN, idle: true };

function startOfToday(): Date {
  const day = new Date();
  day.setHours(0, 0, 0, 0);
  return day;
}

function endOfToday(): Date {
  const day = startOfToday();
  day.setDate(day.getDate() + 1);
  return day;
}

function greeting(hour: number): MessageId {
  if (hour < 12) return "dash.morning";
  if (hour < 18) return "dash.afternoon";
  return "dash.evening";
}

type Go = (target: HomeTarget) => void;

export function DashboardPage({
  workspaceId,
  onGo,
}: {
  workspaceId: string;
  onGo: Go;
}) {
  const t = useT();
  const intl = useIntl();
  const workspace = useWorkspace(workspaceId);
  // Fixed for the page's life, so the day's queries keep one key.
  const signedOut =
    workspace.error instanceof ApiError && workspace.error.status === 401;
  const [day] = useState(() => ({
    start: startOfToday(),
    end: endOfToday(),
    now: new Date(),
  }));

  return (
    <div className="records-page home-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">
            {intl.formatDate(day.now, { dateStyle: "full" })}
          </p>
          <h1 className="records-title">{t(greeting(day.now.getHours()))}</h1>
          <p className="home-subline">
            {workspace.data
              ? t("dash.subline", { name: workspace.data.name })
              : " "}
          </p>
        </div>
      </div>
      {signedOut ? (
        // One notice for the page, not one per card.
        <LoadError
          error={workspace.error}
          onRetry={() => void workspace.refetch()}
        />
      ) : (
        <>
          <Attention workspaceId={workspaceId} onGo={onGo} />
          <Headlines workspaceId={workspaceId} onGo={onGo} />
          <div className="home-grid">
            <PipelineCard workspaceId={workspaceId} onGo={onGo} />
            <AppointmentsCard
              workspaceId={workspaceId}
              start={day.start}
              end={day.end}
              onGo={onGo}
            />
            <TasksCard
              workspaceId={workspaceId}
              now={day.now}
              end={day.end}
              onGo={onGo}
            />
            <ActivityCard workspaceId={workspaceId} onGo={onGo} />
          </div>
        </>
      )}
    </div>
  );
}

function Card({
  id,
  title,
  action,
  children,
}: {
  id: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="home-card" aria-labelledby={id}>
      <div className="home-card-head">
        <h2 id={id} className="home-card-title">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function CardLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <AriaButton className="home-card-link" onPress={onPress}>
      {label}
      <ChevronRight size={14} aria-hidden="true" />
    </AriaButton>
  );
}

function Attention({ workspaceId, onGo }: { workspaceId: string; onGo: Go }) {
  const t = useT();
  const counts = useTaskCounts(workspaceId, []);
  const idle = useDealSummary(workspaceId, IDLE);
  const idleCount = idle.data
    ? idle.data.stages.reduce((sum, stage) => sum + stage.count, 0)
    : null;
  const items = [
    {
      key: "overdue",
      label: "dash.attention.overdue" as MessageId,
      count: counts.data?.overdue ?? null,
      failed: counts.isError,
      Icon: ClockAlert,
      go: () => {
        onGo({ section: "tasks", view: "overdue" });
      },
    },
    {
      key: "idle",
      label: "dash.attention.idle" as MessageId,
      count: idleCount,
      failed: idle.isError,
      Icon: Hourglass,
      go: () => {
        onGo({ section: "opportunities", view: "idle" });
      },
    },
  ];
  return (
    <section className="home-attention" aria-labelledby="home-attention-title">
      <h2 id="home-attention-title" className="home-section-title">
        {t("dash.attention")}
      </h2>
      <ul className="home-attention-list">
        {items.map(({ key, label, count, failed, Icon, go }) => (
          <li key={key}>
            <AriaButton
              className={`home-attention-item ${key}${count ? " active" : ""}`}
              onPress={go}
            >
              <span className="home-attention-icon" aria-hidden="true">
                <Icon size={16} />
              </span>
              <span className="home-attention-count">
                {failed ? "—" : (count ?? "…")}
              </span>{" "}
              <span className="home-attention-label">{t(label)}</span>
            </AriaButton>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Headlines({ workspaceId, onGo }: { workspaceId: string; onGo: Go }) {
  const t = useT();
  const intl = useIntl();
  const contacts = useContactTotal(workspaceId);
  const open = useDealSummary(workspaceId, OPEN);
  const counts = useTaskCounts(workspaceId, []);
  const settings = useWorkspaceSettings(workspaceId);
  const currency = settings.data?.currency ?? "EUR";
  const totals = open.data ? totalsOf(open.data, currency) : null;
  const number = (value: number) => intl.formatNumber(value);
  const money = (pick: "text" | "weightedText") =>
    totals
      ? moneyTotal(
          intl.formatNumber,
          totals.currencies,
          totals.sums,
          pick,
          currency,
        )
      : null;
  const tiles: {
    key: string;
    label: MessageId;
    value: string | null;
    note: string | null;
    failed: boolean;
    go: () => void;
  }[] = [
    {
      key: "contacts",
      label: "dash.kpi.contacts",
      value: contacts.data
        ? number(contacts.data.total) + (contacts.data.capped ? "+" : "")
        : null,
      note: null,
      failed: contacts.isError,
      go: () => {
        onGo({ section: "contacts" });
      },
    },
    {
      key: "deals",
      label: "dash.kpi.deals",
      value: totals ? number(totals.count) : null,
      note: null,
      failed: open.isError,
      go: () => {
        onGo({ section: "opportunities" });
      },
    },
    {
      key: "value",
      label: "dash.kpi.value",
      value: money("text"),
      note: totals
        ? t("dash.kpi.weighted", { amount: money("weightedText") ?? "" })
        : null,
      failed: open.isError,
      go: () => {
        onGo({ section: "opportunities" });
      },
    },
    {
      key: "tasks",
      label: "dash.kpi.tasks",
      value: counts.data ? number(counts.data.open) : null,
      note: counts.data
        ? t("dash.kpi.overdue", { count: counts.data.overdue })
        : null,
      failed: counts.isError,
      go: () => {
        onGo({ section: "tasks" });
      },
    },
  ];
  return (
    <section aria-label={t("dash.kpis")}>
      <ul className="home-kpis">
        {tiles.map((tile) => (
          <li key={tile.key}>
            <AriaButton className="home-kpi" onPress={tile.go}>
              <span className="home-kpi-label">{t(tile.label)}</span>
              <span className="home-kpi-value">
                {tile.failed ? "—" : (tile.value ?? "…")}
              </span>
              {tile.failed ? (
                <span className="home-kpi-note error">{t("dash.failed")}</span>
              ) : tile.note ? (
                <span className="home-kpi-note">{tile.note}</span>
              ) : null}
            </AriaButton>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PipelineCard({
  workspaceId,
  onGo,
}: {
  workspaceId: string;
  onGo: Go;
}) {
  const t = useT();
  const intl = useIntl();
  const pipelines = usePipelines(workspaceId);
  const summary = useDealSummary(workspaceId, OPEN);
  const settings = useWorkspaceSettings(workspaceId);
  const currency = settings.data?.currency ?? "EUR";
  const stages = pipelines.data?.items[0]?.stages ?? [];
  const digits = minorDigits(currency);
  const rows = stages.map((stage) => {
    const info = summary.data?.stages.find(
      (entry) => entry.stage_id === stage.id,
    );
    const own = info?.totals.find((total) => total.currency === currency);
    return {
      stage,
      count: info?.count ?? 0,
      amount: addDecimals([own?.amount ?? "0"], digits),
    };
  });
  // Bar widths are for display only; the amounts shown are the exact strings.
  const widest = Math.max(...rows.map((row) => Number(row.amount)), 0);
  const totals = summary.data ? totalsOf(summary.data, currency) : null;
  return (
    <Card
      id="home-pipeline"
      title={t("dash.pipeline")}
      action={
        <CardLink
          label={t("dash.open")}
          onPress={() => {
            onGo({ section: "opportunities" });
          }}
        />
      }
    >
      {pipelines.isPending || summary.isPending ? (
        <Loading />
      ) : pipelines.isError || summary.isError ? (
        <LoadError
          error={pipelines.error ?? summary.error}
          onRetry={() => {
            void pipelines.refetch();
            void summary.refetch();
          }}
        />
      ) : (
        <>
          <ol className="home-stages">
            {rows.map((row, index) => (
              <li key={row.stage.id} className="home-stage">
                <span className="home-stage-name">
                  {row.stage.name} · {intl.formatNumber(row.count)}
                </span>
                <span className="home-stage-value">
                  {formatMoney(intl.formatNumber, row.amount, currency)}
                </span>
                <span className="home-stage-bar" aria-hidden="true">
                  <span
                    style={{
                      width:
                        widest > 0
                          ? `${String((Number(row.amount) / widest) * 100)}%`
                          : "0%",
                      background: stageShade(index, rows.length),
                    }}
                  />
                </span>
              </li>
            ))}
          </ol>
          {totals ? (
            <p className="home-forecast">
              <span>{t("deals.summary.weighted")}</span>
              <strong>
                {moneyTotal(
                  intl.formatNumber,
                  totals.currencies,
                  totals.sums,
                  "weightedText",
                  currency,
                )}
              </strong>
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}

function AppointmentsCard({
  workspaceId,
  start,
  end,
  onGo,
}: {
  workspaceId: string;
  start: Date;
  end: Date;
  onGo: Go;
}) {
  const t = useT();
  const intl = useIntl();
  const range = useAppointments(workspaceId, start, end);
  const today = (range.data?.items ?? [])
    .filter(
      (item) =>
        item.status !== "cancelled" && new Date(item.starts_at) >= start,
    )
    .slice(0, TODAY_TASKS);
  return (
    <Card
      id="home-appointments"
      title={t("dash.appointments")}
      action={
        <CardLink
          label={t("nav.calendar")}
          onPress={() => {
            onGo({ section: "calendar" });
          }}
        />
      }
    >
      {range.isPending ? (
        <Loading />
      ) : range.isError ? (
        <LoadError error={range.error} onRetry={() => void range.refetch()} />
      ) : today.length === 0 ? (
        <EmptyState title={t("dash.appointments.none")} />
      ) : (
        <ul className="home-list">
          {today.map((item) => (
            <li key={item.id}>
              <AriaButton
                className="home-row"
                onPress={() => {
                  onGo({ section: "calendar", record: item.id });
                }}
              >
                <time className="home-row-time" dateTime={item.starts_at}>
                  {intl.formatTime(new Date(item.starts_at), {
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </time>
                <span className="home-row-main">
                  <span className="home-row-title">{item.title}</span>
                  {item.contact ? (
                    <span className="home-row-sub">{item.contact.name}</span>
                  ) : null}
                </span>
                <Badge tone={STATUS_TONE[item.status]}>
                  {t(STATUS_LABEL[item.status])}
                </Badge>
              </AriaButton>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TasksCard({
  workspaceId,
  now,
  end,
  onGo,
}: {
  workspaceId: string;
  now: Date;
  end: Date;
  onGo: Go;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const tasks = useTasksDueBy(workspaceId, end);
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const canUpdate = access.data?.actions.update_task === true;
  const items = tasks.data?.items ?? [];
  return (
    <Card
      id="home-tasks"
      title={t("dash.tasks")}
      action={
        <CardLink
          label={t("nav.tasks")}
          onPress={() => {
            onGo({ section: "tasks" });
          }}
        />
      }
    >
      {refusal ? (
        <p className="notice error" role="alert">
          {t(refusal)}
        </p>
      ) : null}
      {tasks.isPending ? (
        <Loading />
      ) : tasks.isError ? (
        <LoadError error={tasks.error} onRetry={() => void tasks.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("dash.tasks.none")} />
      ) : (
        <ul className="home-list">
          {items.map((task) => (
            <HomeTask
              key={task.id}
              workspaceId={workspaceId}
              task={task}
              now={now}
              meId={me.data?.user_id}
              canUpdate={canUpdate}
              onError={setRefusal}
            />
          ))}
        </ul>
      )}
      {tasks.data?.next_cursor ? (
        <p className="home-more muted">{t("dash.tasks.more")}</p>
      ) : null}
    </Card>
  );
}

function HomeTask({
  workspaceId,
  task,
  now,
  meId,
  canUpdate,
  onError,
}: {
  workspaceId: string;
  task: Task;
  now: Date;
  meId: string | undefined;
  canUpdate: boolean;
  onError: (message: MessageId) => void;
}) {
  const t = useT();
  const toast = useToast();
  const update = useUpdateTask(workspaceId);
  const overdue =
    task.due_at !== null && new Date(task.due_at).getTime() < now.getTime();
  return (
    <li className="home-task">
      <input
        type="checkbox"
        className="task-check"
        checked={false}
        disabled={!canUpdate || update.isPending}
        aria-label={t("tasks.complete", { title: task.title })}
        onChange={() => {
          update.mutate(
            { id: task.id, version: task.version, changes: { done: true } },
            {
              onSuccess: () => {
                toast(t("tasks.completed"));
              },
              onError: (error) => {
                onError(taskRefusal(error));
              },
            },
          );
        }}
      />
      <span className="home-row-main">
        <span className="home-row-title">{task.title}</span>
        <span className="home-row-sub">
          <DueText value={task.due_at} overdue={overdue} />
          {" · "}
          {ownerLabel(t, task.assignee_user_id, meId)}
        </span>
      </span>
    </li>
  );
}

function ActivityCard({
  workspaceId,
  onGo,
}: {
  workspaceId: string;
  onGo: Go;
}) {
  const t = useT();
  const me = useMe();
  const feed = useRecentActivity(workspaceId);
  const describe = useDescribe();
  const items = feed.data?.items ?? [];
  const meId = me.data?.user_id;
  const open = (entry: RecentEntry) => {
    onGo({
      section: entry.record_type === "contact" ? "contacts" : "companies",
      record: entry.record_id,
    });
  };
  return (
    <Card id="home-activity" title={t("history.title")}>
      {feed.isPending ? (
        <Loading />
      ) : feed.isError ? (
        <LoadError error={feed.error} onRetry={() => void feed.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={t("history.empty")} />
      ) : (
        <ol className="activity-list home-activity">
          {items.map((entry) => {
            const Icon = ACTIVITY_ICONS[entry.kind];
            return (
              <li
                key={entry.id}
                className={`activity-item activity-${entry.kind}`}
              >
                <span className="activity-icon" aria-hidden="true">
                  <Icon size={12} />
                </span>
                <div className="activity-text">
                  <p className="activity-what">
                    {entry.record_name ? (
                      <AriaButton
                        className="home-record-link"
                        onPress={() => {
                          open(entry);
                        }}
                      >
                        {entry.record_name}
                      </AriaButton>
                    ) : (
                      <span className="muted">{t("dash.deletedRecord")}</span>
                    )}
                    {": "}
                    {describe(entry, meId)}
                  </p>
                  <p className="activity-meta">
                    {entry.actor_user_id
                      ? ownerLabel(t, entry.actor_user_id, meId)
                      : t("history.system")}
                    {" · "}
                    <When value={entry.occurred_at} />
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
