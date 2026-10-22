import {
  Bell,
  Building2,
  Check,
  ChevronDown,
  Eye,
  ListPlus,
  Minus,
  Palette,
  Plug,
  Sparkles,
  User,
  UserPlus,
  Users,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button as AriaButton, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";

import type { Access, Member } from "../api/client";
import { PAGE_SIZE, useAccess, useMemberChange, useMembers, useWorkspace } from "../api/queries";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import { en, type MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { availableActions, type MemberAction } from "../members/actions";

/*
 * Settings › Team & roles, reproduced from the design (ScreenSettings.dc.html:
 * settings nav L11-20, page header L22-26, Team & roles L54-68). Differences,
 * recorded in DESIGN-FIDELITY.md:
 * - names and e-mail addresses are not stored yet, so members show by ID;
 * - the design's per-row role <select> becomes the actions menu, because roles
 *   are added and removed individually and Owner changes need confirmation;
 * - the permissions matrix shows this product's four roles (decision Q6).
 */

const shortId = (id: string) => id.slice(0, 8);

function statusLabel(status: string): MessageId {
  const id = `status.${status}`;
  return id in en ? (id as MessageId) : "status.active";
}

const STATUS_TONE: Record<string, Tone> = { active: "success", suspended: "pending" };

function refusalLabel(code: string | undefined): MessageId {
  const id = `refusal.${code ?? ""}`;
  return id in en ? (id as MessageId) : "state.error";
}

interface Pending {
  member: Member;
  action: MemberAction;
}

function MemberActions({
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
  if (actions.length === 0) return null;
  return (
    <MenuTrigger>
      <AriaButton
        className="row-select"
        aria-label={t("members.actionsFor", { id: shortId(member.membership_id) })}
      >
        {t("members.actions")}
        <ChevronDown size={14} aria-hidden="true" />
      </AriaButton>
      <Popover className="menu-popover" placement="bottom end" offset={4}>
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
  );
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
  const isSelf = member.membership_id === access.membership_id;
  return (
    <li className="member-row">
      <span className="member-avatar" aria-hidden="true">
        <User size={15} />
      </span>
      <div className="member-text">
        <div className="member-name">
          <span className="mono">{t("members.id", { id: shortId(member.membership_id) })}</span>
          {isSelf ? <Badge tone="accent">{t("members.you")}</Badge> : null}
        </div>
        <div className="member-sub">
          {member.status === "active" ? (
            t(statusLabel(member.status))
          ) : (
            <Badge tone={STATUS_TONE[member.status] ?? "neutral"}>{t(statusLabel(member.status))}</Badge>
          )}
        </div>
      </div>
      <span className="member-roles">
        {member.roles.length === 0 ? (
          <span className="scope-pill">{t("members.noRole")}</span>
        ) : (
          member.roles.map((role) => (
            <span key={role} className="scope-pill">
              {role}
            </span>
          ))
        )}
      </span>
      <MemberActions member={member} access={access} onAction={onAction} />
    </li>
  );
}

function MembersCard({ workspaceId, access }: { workspaceId: string; access: Access }) {
  const t = useT();
  const toast = useToast();
  const [offset, setOffset] = useState(0);
  const canRead = access.actions.read_members === true;
  const members = useMembers(workspaceId, offset, canRead);
  const change = useMemberChange(workspaceId);
  const [pending, setPending] = useState<Pending | null>(null);
  const result = useRef<HTMLDivElement>(null);
  const settled = change.isSuccess || change.isError;

  // A removed member's row, and with it the focused Actions button, can
  // disappear after a change; keep keyboard focus on the page by moving it
  // to the result message.
  useEffect(() => {
    if (settled && members.isFetched && document.activeElement === document.body) {
      result.current?.focus();
    }
  }, [settled, members.isFetched, members.data]);

  const submit = ({ member, action }: Pending) => {
    setPending(null);
    change.mutate({
      membershipId: member.membership_id,
      change: action.change,
      confirmOwnerChange: action.confirm === "owner",
    });
  };

  let body: ReactNode;
  let count = "";
  if (!canRead) {
    body = <p className="card-pad notice error">{t("state.denied")}</p>;
  } else if (members.isPending) {
    body = (
      <div className="card-pad">
        <Loading />
      </div>
    );
  } else if (members.isError) {
    body = (
      <div className="card-pad">
        <LoadError error={members.error} onRetry={() => void members.refetch()} />
      </div>
    );
  } else {
    const page = members.data;
    count = t("members.count", { total: page.total });
    body = (
      <>
        {page.items.length === 0 ? (
          <div className="card-pad">
            <EmptyState title={t("members.empty")} />
          </div>
        ) : (
          <ul className="member-list" aria-label={count}>
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
          </ul>
        )}
        {page.total > PAGE_SIZE ? (
          <div className="card-footer">
            <Button
              size="sm"
              isDisabled={offset === 0}
              onPress={() => {
                setOffset(Math.max(0, offset - PAGE_SIZE));
              }}
            >
              {t("members.previous")}
            </Button>
            <span className="muted">
              {t("members.page", {
                from: offset + 1,
                to: Math.min(offset + PAGE_SIZE, page.total),
                total: page.total,
              })}
            </span>
            <Button
              size="sm"
              isDisabled={offset + PAGE_SIZE >= page.total}
              onPress={() => {
                setOffset(offset + PAGE_SIZE);
              }}
            >
              {t("members.next")}
            </Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="settings-card" aria-labelledby="members-card-title">
      <div className="settings-card-head">
        <h2 id="members-card-title" className="settings-card-title">
          {count || t("members.title")}
        </h2>
        <AriaButton
          className="invite-button"
          onPress={() => {
            toast(t("members.inviteUnavailable"));
          }}
        >
          <UserPlus size={14} aria-hidden="true" />
          {t("members.invite")}
        </AriaButton>
      </div>
      <div role="status" aria-live="polite" tabIndex={-1} ref={result} className="result-region">
        {change.isSuccess ? <p className="notice info">{t("action.done")}</p> : null}
        {change.isError ? <p className="notice error">{t(refusalLabel(change.error.code))}</p> : null}
      </div>
      {body}
      <p className="card-note">{t("members.namesUnavailable")}</p>
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
    </section>
  );
}

// The approved role matrix (decision Q6, src/crm_app/roles.py) in the
// design's "Role permissions" layout: 1 = full, 0.5 = read only, 0 = none.
const ROLE_COLUMNS = ["Owner", "Admin", "Member", "Read-only"] as const;
const CAPABILITIES: { label: MessageId; cells: [number, number, number, number] }[] = [
  { label: "perm.viewEdit", cells: [1, 1, 1, 0.5] },
  { label: "perm.deleteExport", cells: [1, 1, 0, 0] },
  { label: "perm.pipelines", cells: [1, 1, 0, 0] },
  { label: "perm.settings", cells: [1, 1, 0, 0] },
  { label: "perm.team", cells: [1, 1, 0, 0] },
  { label: "perm.owners", cells: [1, 0, 0, 0] },
];

function PermissionCell({ value }: { value: number }) {
  const t = useT();
  if (value === 1) {
    return (
      <span className="perm-cell perm-full">
        <Check size={15} aria-hidden="true" />
        <span className="visually-hidden">{t("perm.full")}</span>
      </span>
    );
  }
  if (value > 0) {
    return (
      <span className="perm-cell perm-partial">
        <Eye size={15} aria-hidden="true" />
        <span className="visually-hidden">{t("perm.readOnly")}</span>
      </span>
    );
  }
  return (
    <span className="perm-cell perm-none">
      <Minus size={15} aria-hidden="true" />
      <span className="visually-hidden">{t("perm.none")}</span>
    </span>
  );
}

function RolePermissions() {
  const t = useT();
  return (
    <section className="settings-card" aria-labelledby="perm-title">
      <div className="settings-card-head">
        <h2 id="perm-title" className="settings-card-title">
          {t("perm.title")}
        </h2>
        <span className="card-meta">{t("perm.summary")}</span>
      </div>
      <table className="perm-table">
        <thead>
          <tr>
            <th scope="col">{t("perm.capability")}</th>
            {ROLE_COLUMNS.map((role) => (
              <th key={role} scope="col">
                {role}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {CAPABILITIES.map((row) => (
            <tr key={row.label}>
              <th scope="row">{t(row.label)}</th>
              {row.cells.map((value, index) => (
                <td key={ROLE_COLUMNS[index]}>
                  <PermissionCell value={value} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// The design's settings sections (ScreenSettings.dc.html SECTIONS). Only Team
// & roles exists; the others are marked the way the design marks later ones.
const SETTINGS_NAV: { group: MessageId; items: { id: string; label: MessageId; icon: typeof User }[] }[] = [
  { group: "settings.account", items: [{ id: "profile", label: "settings.profile", icon: User }] },
  {
    group: "settings.workspace",
    items: [
      { id: "business", label: "settings.business", icon: Building2 },
      { id: "team", label: "settings.team", icon: Users },
      { id: "notifications", label: "settings.notifications", icon: Bell },
      { id: "fields", label: "settings.fields", icon: ListPlus },
      { id: "ai", label: "settings.ai", icon: Sparkles },
      { id: "integrations", label: "settings.integrations", icon: Plug },
      { id: "appearance", label: "settings.appearance", icon: Palette },
    ],
  },
];

export function MembersPage({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const toast = useToast();
  const access = useAccess(workspaceId);
  const workspace = useWorkspace(workspaceId);
  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label={t("settings.title")}>
        <p className="settings-nav-title">{t("settings.title")}</p>
        <p className="settings-nav-scope">{workspace.data?.name ?? ""}</p>
        {SETTINGS_NAV.map((group) => (
          <div key={group.group} className="settings-nav-group">
            <p className="settings-nav-label">{t(group.group)}</p>
            <ul className="settings-nav-list">
              {group.items.map((item) => {
                const Icon = item.icon;
                const current = item.id === "team";
                return (
                  <li key={item.id}>
                    <AriaButton
                      className={current ? "settings-nav-item active" : "settings-nav-item"}
                      aria-current={current ? "page" : false}
                      onPress={() => {
                        if (!current) toast(t("settings.unavailable", { name: t(item.label) }));
                      }}
                    >
                      <Icon size={15} className="settings-nav-icon" aria-hidden="true" />
                      <span className="settings-nav-text">{t(item.label)}</span>
                      {current ? null : <span className="nav-soon">{t("nav.soonLower")}</span>}
                    </AriaButton>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="settings-scroll">
      <div className="settings-content">
        <div className="settings-header">
          <h1 className="settings-title">{t("settings.team")}</h1>
          <p className="settings-desc">{t("settings.teamDesc")}</p>
        </div>
        {access.isPending ? <Loading /> : null}
        {access.isError ? (
          <LoadError error={access.error} onRetry={() => void access.refetch()} />
        ) : null}
        {access.data ? (
          <>
            <MembersCard workspaceId={workspaceId} access={access.data} />
            <RolePermissions />
          </>
        ) : null}
      </div>
      </div>
    </div>
  );
}
