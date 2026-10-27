import { useState } from "react";

import { useAccess, useMe, useMembers } from "../api/queries";
import { dueGroup, NO_TASK_FILTERS, type Task, useTaskList } from "../api/tasks";
import { LoadError } from "../components/StateNotice";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ownerOptions } from "./parts";
import { QuickAdd, TaskDialog, TaskRow } from "./taskParts";

/*
 * A record drawer's open tasks (decision P4-C 7): the contact's, company's
 * or deal's open tasks, soonest due first, and a quick-add row whose tasks
 * are linked to the record. Who may add, change or delete follows `/access`.
 */

export function TasksSection({
  workspaceId,
  link,
}: {
  workspaceId: string;
  link: { kind: "contact" | "company" | "opportunity"; id: string };
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const [editing, setEditing] = useState<Task | null>(null);
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const can = (action: string) => access.data?.actions[action] === true;
  const filters = {
    ...NO_TASK_FILTERS,
    contactIds: link.kind === "contact" ? [link.id] : [],
    companyIds: link.kind === "company" ? [link.id] : [],
    opportunityIds: link.kind === "opportunity" ? [link.id] : [],
  };
  const list = useTaskList(workspaceId, filters);
  const tasks = (list.data?.pages ?? []).flatMap((page) => page.items);
  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const choices = owners.length ? owners : meId ? [{ id: meId, label: t("records.owner.me") }] : [];
  const headingId = `${link.kind}-tasks-title`;
  const now = new Date();
  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="drawer-section-title">
        {t("tasks.section", { count: tasks.length })}
      </h2>
      {list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} /> : null}
      {refusal ? (
        <p className="notice error" role="alert">
          {t(refusal)}
        </p>
      ) : null}
      {tasks.length ? (
        <ul className="task-list compact">
          {tasks.map((task) => (
            <TaskRow
              key={task.id}
              workspaceId={workspaceId}
              task={task}
              meId={meId}
              overdue={dueGroup(task, now) === "overdue"}
              canUpdate={can("update_task")}
              canDelete={can("delete_task")}
              onEdit={setEditing}
              onError={setRefusal}
            />
          ))}
        </ul>
      ) : list.isPending ? null : (
        <p className="muted">{t("tasks.sectionEmpty")}</p>
      )}
      {can("create_task") ? (
        <QuickAdd
          workspaceId={workspaceId}
          owners={choices}
          meId={meId}
          links={{ [`${link.kind}_id`]: link.id }}
          idPrefix={`${link.kind}-task-new`}
          onError={setRefusal}
        />
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
    </section>
  );
}
