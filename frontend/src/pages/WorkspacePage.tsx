import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Button, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";

import type { Access, Member } from "../api/client";
import {
  keys,
  PAGE_SIZE,
  useAccess,
  useMemberChange,
  useMembers,
  useWorkspace,
} from "../api/queries";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { en, type MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { availableActions, type MemberAction } from "../members/actions";

const shortId = (id: string) => id.slice(0, 8);

function statusLabel(status: string): MessageId {
  const id = `status.${status}`;
  return id in en ? (id as MessageId) : "status.active";
}

function refusalLabel(code: string | undefined): MessageId {
  const id = `refusal.${code ?? ""}`;
  return id in en ? (id as MessageId) : "state.error";
}

interface Pending {
  member: Member;
  action: MemberAction;
}

function MemberRow({
  member,
  access,
  onAction,
}: {
  member: Member;
  access: Access;
  onAction: (pending: Pending) => void;
}) {
  const t = useT();
  const actions = availableActions(member, access);
  const isSelf = member.membership_id === access.membership_id;
  return (
    <tr>
      <td>
        <span className="mono">{t("members.id", { id: shortId(member.membership_id) })}</span>{" "}
        {isSelf ? <span className="badge">{t("members.you")}</span> : null}
      </td>
      <td>
        {member.roles.length === 0 ? (
          <span className="muted">{t("members.noRole")}</span>
        ) : (
          member.roles.map((role) => (
            <span key={role} className="badge">
              {role}
            </span>
          ))
        )}
      </td>
      <td>
        <span className={`badge status-${member.status}`}>{t(statusLabel(member.status))}</span>
      </td>
      <td>
        {actions.length === 0 ? (
          <span className="muted" aria-hidden="true">
            —
          </span>
        ) : (
          <MenuTrigger>
            <Button
              className="button"
              aria-label={t("members.actionsFor", { id: shortId(member.membership_id) })}
            >
              {t("members.actions")}
            </Button>
            <Popover className="popover" placement="bottom end">
              <Menu
                className="menu"
                onAction={(key) => {
                  const action = actions.find((a) => a.key === key);
                  if (action) onAction({ member, action });
                }}
              >
                {actions.map((action) => (
                  <MenuItem key={action.key} id={action.key} className="menu-item">
                    {t(action.label, action.role ? { role: action.role } : undefined)}
                  </MenuItem>
                ))}
              </Menu>
            </Popover>
          </MenuTrigger>
        )}
      </td>
    </tr>
  );
}

function Members({ workspaceId, access }: { workspaceId: string; access: Access }) {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const canRead = access.actions.read_members === true;
  const members = useMembers(workspaceId, offset, canRead);
  const change = useMemberChange(workspaceId);
  const [pending, setPending] = useState<Pending | null>(null);

  const submit = ({ member, action }: Pending) => {
    setPending(null);
    change.mutate({
      membershipId: member.membership_id,
      change: action.change,
      confirmOwnerChange: action.confirm === "owner",
    });
  };

  if (!canRead) return <p className="notice error">{t("state.denied")}</p>;
  if (members.isPending) return <Loading />;
  if (members.isError) {
    return <LoadError error={members.error} onRetry={() => void members.refetch()} />;
  }
  const page = members.data;
  return (
    <>
      <div role="status" aria-live="polite">
        {change.isSuccess ? <p className="notice info">{t("action.done")}</p> : null}
        {change.isError ? (
          <p className="notice error">{t(refusalLabel(change.error.code))}</p>
        ) : null}
      </div>
      <p className="muted">{t("members.namesUnavailable")}</p>
      {page.items.length === 0 ? (
        <p>{t("members.empty")}</p>
      ) : (
        <table>
          <caption className="caption muted">{t("members.count", { total: page.total })}</caption>
          <thead>
            <tr>
              <th scope="col">{t("members.member")}</th>
              <th scope="col">{t("members.roles")}</th>
              <th scope="col">{t("members.status")}</th>
              <th scope="col">{t("members.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((member) => (
              <MemberRow
                key={member.membership_id}
                member={member}
                access={access}
                onAction={(next) => {
                  change.reset();
                  if (next.action.confirm) setPending(next);
                  else submit(next);
                }}
              />
            ))}
          </tbody>
        </table>
      )}
      {page.total > PAGE_SIZE ? (
        <div className="row">
          <Button
            className="button"
            isDisabled={offset === 0}
            onPress={() => {
              setOffset(Math.max(0, offset - PAGE_SIZE));
            }}
          >
            {t("members.previous")}
          </Button>
          <span>
            {t("members.page", {
              from: offset + 1,
              to: Math.min(offset + PAGE_SIZE, page.total),
              total: page.total,
            })}
          </span>
          <Button
            className="button"
            isDisabled={offset + PAGE_SIZE >= page.total}
            onPress={() => {
              setOffset(offset + PAGE_SIZE);
            }}
          >
            {t("members.next")}
          </Button>
        </div>
      ) : null}
      <ConfirmDialog
        isOpen={pending !== null}
        message={t(pending?.action.confirm === "revoke" ? "confirm.revoke" : "confirm.owner")}
        onCancel={() => {
          setPending(null);
        }}
        onConfirm={() => {
          if (pending) submit(pending);
        }}
      />
    </>
  );
}

export function WorkspacePage({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const client = useQueryClient();
  const workspace = useWorkspace(workspaceId);
  const access = useAccess(workspaceId);

  // No workspace's data outlives a switch to another one (PHASE2-PLAN.md §6.3).
  useEffect(
    () => () => {
      client.removeQueries({ queryKey: keys.workspace(workspaceId) });
    },
    [client, workspaceId],
  );

  if (workspace.isPending || access.isPending) return <Loading />;
  if (workspace.isError) {
    return <LoadError error={workspace.error} onRetry={() => void workspace.refetch()} />;
  }
  if (access.isError) {
    return <LoadError error={access.error} onRetry={() => void access.refetch()} />;
  }
  return (
    <div className="stack">
      <div className="row">
        <Link to="/" className="button">
          {t("workspace.back")}
        </Link>
      </div>
      <header className="title-block">
        <h1>{workspace.data.name}</h1>
        <p className="muted">{t("workspace.status", { status: workspace.data.status })}</p>
      </header>
      <section className="card" aria-labelledby="members-heading">
        <h2 id="members-heading">{t("members.title")}</h2>
        <Members workspaceId={workspaceId} access={access.data} />
      </section>
    </div>
  );
}
