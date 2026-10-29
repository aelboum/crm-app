import { CircleCheckBig } from "lucide-react";
import { useMemo, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { useAccess, useMe, useMembers } from "../api/queries";
import { dueGroup, type DueGroup, NO_TASK_FILTERS, type Task, type TaskFilters, useTaskCounts, useTaskList } from "../api/tasks";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ownerOptions } from "./parts";
import { QuickAdd, TaskDialog, TaskRow } from "./taskParts";

/*
 * Tasks (ScreenTasks.dc.html, decision P4-C): the assignee filter, the tabs
 * Open, Assigned to me, Overdue and Completed with their counts, the
 * quick-add row, and the list grouped Overdue, Today, Upcoming (and No due
 * date, which the design does not have because its tasks always carry one).
 * "Today" is the viewer's own day. A row completes or reopens the task,
 * opens its linked record, and edits or deletes it for those `/access`
 * allows; Read-only members see the list only.
 */

type Tab = "open" | "mine" | "overdue" | "done";

const TABS: [Tab, MessageId][] = [
  ["open", "tasks.tab.open"],
  ["mine", "tasks.tab.mine"],
  ["overdue", "tasks.tab.overdue"],
  ["done", "tasks.tab.done"],
];

const GROUPS: [DueGroup, MessageId][] = [
  ["overdue", "tasks.group.overdue"],
  ["today", "tasks.group.today"],
  ["upcoming", "tasks.group.upcoming"],
  ["none", "tasks.group.none"],
];

export function TasksPage({
  workspaceId,
  onOpenLink,
  initialTab = "open",
}: {
  workspaceId: string;
  onOpenLink: (kind: "contact" | "company" | "opportunity", id: string) => void;
  /** The Home page opens the Overdue tab (P4-D 1). */
  initialTab?: Tab;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [assignee, setAssignee] = useState("");
  const [editing, setEditing] = useState<Task | null>(null);
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const can = (action: string) => access.data?.actions[action] === true;
  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const choices = owners.length ? owners : meId ? [{ id: meId, label: t("records.owner.me") }] : [];
  const assignees = assignee ? [assignee] : [];
  const counts = useTaskCounts(workspaceId, assignees);

  const filters: TaskFilters = useMemo(() => {
    if (tab === "done") {
      return { ...NO_TASK_FILTERS, status: "done", assignees, sort: "completed_at", direction: "desc" };
    }
    if (tab === "mine") return { ...NO_TASK_FILTERS, assignees: meId ? [meId] : ["me"] };
    return { ...NO_TASK_FILTERS, assignees, overdue: tab === "overdue" };
    // `assignees` is derived from `assignee`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, assignee, meId]);
  const list = useTaskList(workspaceId, filters);
  const tasks = (list.data?.pages ?? []).flatMap((page) => page.items);
  const now = new Date();
  const groups =
    tab === "done"
      ? [{ key: "done" as const, label: "tasks.group.done" as MessageId, items: tasks }]
      : GROUPS.map(([key, label]) => ({ key, label, items: tasks.filter((task) => dueGroup(task, now) === key) })).filter(
          (group) => group.items.length > 0,
        );

  return (
    <div className="records-page tasks-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.crm")}</p>
          <h1 className="records-title">{t("nav.tasks")}</h1>
        </div>
        <div className="records-actions">
          <label className="sr-only" htmlFor="tasks-assignee">
            {t("tasks.field.assignee")}
          </label>
          <select
            id="tasks-assignee"
            className="form-input form-select tasks-assignee"
            value={assignee}
            onChange={(event) => {
              setAssignee(event.target.value);
            }}
          >
            <option value="">{t("tasks.everyone")}</option>
            {choices.map((owner) => (
              <option key={owner.id} value={owner.id}>
                {owner.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="tabs tasks-tabs" role="group" aria-label={t("tasks.views")}>
        {TABS.map(([key, label]) => (
          <AriaButton
            key={key}
            className={tab === key ? "tab active" : "tab"}
            aria-pressed={tab === key}
            onPress={() => {
              setTab(key);
            }}
          >
            {t(label)}
            <span className={key === "overdue" ? "tab-count risk" : "tab-count"}>{counts.data?.[key] ?? ""}</span>
          </AriaButton>
        ))}
      </div>

      {can("create_task") ? (
        <QuickAdd workspaceId={workspaceId} owners={choices} meId={meId} idPrefix="tasks-new" onError={setRefusal} />
      ) : null}
      {refusal ? (
        <p className="notice error records-notice" role="alert">
          {t(refusal)}
        </p>
      ) : null}

      {list.isPending ? (
        <div className="records-card">
          <Loading />
        </div>
      ) : list.isError ? (
        <div className="records-card">
          <LoadError error={list.error} onRetry={() => void list.refetch()} />
        </div>
      ) : groups.length === 0 ? (
        <div className="records-card tasks-empty">
          <CircleCheckBig size={28} aria-hidden="true" />
          <p className="tasks-empty-title">{t("tasks.empty.title")}</p>
          <p className="muted">{t("tasks.empty.body")}</p>
        </div>
      ) : (
        groups.map((group) => (
          <section key={group.key} className="records-card task-group" aria-labelledby={`task-group-${group.key}`}>
            <h2 id={`task-group-${group.key}`} className={`task-group-title ${group.key}`}>
              {t(group.label)}
              <span className="tab-count">{group.items.length}</span>
            </h2>
            <ul className="task-list">
              {group.items.map((task) => (
                <TaskRow
                  key={task.id}
                  workspaceId={workspaceId}
                  task={task}
                  meId={meId}
                  overdue={dueGroup(task, now) === "overdue"}
                  canUpdate={can("update_task")}
                  canDelete={can("delete_task")}
                  onOpenLink={onOpenLink}
                  onEdit={setEditing}
                  onError={setRefusal}
                />
              ))}
            </ul>
          </section>
        ))
      )}
      {list.hasNextPage ? (
        <div className="records-footer">
          <Button size="sm" onPress={() => void list.fetchNextPage()} isDisabled={list.isFetchingNextPage}>
            {t("records.loadMore")}
          </Button>
        </div>
      ) : null}
      {editing ? (
        <TaskDialog
          workspaceId={workspaceId}
          task={editing}
          owners={choices}
          onClose={() => {
            setEditing(null);
          }}
        />
      ) : null}
    </div>
  );
}
