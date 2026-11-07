import {
  Bell,
  Building2,
  Check,
  ChevronDown,
  ExternalLink,
  Eye,
  Kanban,
  AtSign,
  Globe,
  MailX,
  ListPlus,
  Minus,
  Palette,
  Plug,
  Shield,
  Sparkles,
  Tag,
  User,
  UserPlus,
  Users,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button as AriaButton, Menu, MenuItem, MenuTrigger, Popover } from "react-aria-components";

import { type Access, ApiError, type Member } from "../api/client";
import {
  PAGE_SIZE,
  useAccess,
  useMemberChange,
  useMembers,
  useOwnProfile,
  useSetOwnProfile,
  useWorkspace,
  useWorkspaceSettings,
} from "../api/queries";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import { en, type MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { BusinessSettings } from "./BusinessSettings";
import { FieldSettings } from "./FieldSettings";
import { PipelineSettings } from "./PipelineSettings";
import { DomainSettings } from "./DomainSettings";
import { IntegrationSettings } from "./IntegrationSettings";
import { SendingDomainSettings } from "./SendingDomainSettings";
import { SuppressionSettings } from "./SuppressionSettings";
import { TagSettings } from "./TagSettings";
import { type Invitation, useInvitations } from "../api/invitations";
import { availableActions, highestRole, type MemberAction } from "../members/actions";
import { InvitationsCard, InviteDialog } from "../members/Invitations";

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
  invitation,
  onAction,
}: {
  member: Member;
  access: Access;
  /** The accepted invitation this member joined with, if the caller may see it. */
  invitation: Invitation | undefined;
  onAction: (pending: Pending) => void;
}) {
  const t = useT();
  const isSelf = member.membership_id === access.membership_id;
  // Decision Q5: a member who joined by invitation has no role until an
  // Owner or Admin confirms the intended one, in one action.
  const awaiting = member.status === "active" && member.roles.length === 0;
  const intended = awaiting && invitation?.role ? invitation.role : null;
  const confirm = intended
    ? availableActions(member, access).find((action) => action.key === `assign-${intended}`)
    : undefined;
  return (
    <li className="member-row">
      <span className="member-avatar" aria-hidden="true">
        <User size={15} />
      </span>
      <div className="member-text">
        <div className="member-name">
          {member.display_name ? (
            <span>{member.display_name}</span>
          ) : invitation ? (
            <span>{invitation.email}</span>
          ) : (
            <span className="mono">{t("members.id", { id: shortId(member.membership_id) })}</span>
          )}
          {isSelf ? <Badge tone="accent">{t("members.you")}</Badge> : null}
          {awaiting ? <Badge tone="pending">{t("members.awaitingRole")}</Badge> : null}
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
      {confirm ? (
        <Button
          size="sm"
          variant="primary"
          onPress={() => {
            onAction({ member, action: confirm });
          }}
        >
          {t("members.confirmRole", { role: intended ?? "" })}
        </Button>
      ) : null}
      <MemberActions member={member} access={access} onAction={onAction} />
    </li>
  );
}

function MembersCard({ workspaceId, access }: { workspaceId: string; access: Access }) {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const canRead = access.actions.read_members === true;
  const members = useMembers(workspaceId, offset, canRead);
  const canSeeInvitations = access.actions.read_invitations === true;
  const invitations = useInvitations(workspaceId, canSeeInvitations);
  const joinedBy = new Map(
    (invitations.data?.items ?? [])
      .filter((invitation) => invitation.status === "accepted" && invitation.accepted_by_user_id)
      .map((invitation) => [invitation.accepted_by_user_id, invitation]),
  );
  const [inviting, setInviting] = useState(false);
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
                invitation={joinedBy.get(member.user_id)}
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
    <>
    <section className="settings-card" aria-labelledby="members-card-title">
      <div className="settings-card-head">
        <h2 id="members-card-title" className="settings-card-title">
          {count || t("members.title")}
        </h2>
        {access.actions.create_invitation === true ? (
          <AriaButton
            className="invite-button"
            onPress={() => {
              setInviting(true);
            }}
          >
            <UserPlus size={14} aria-hidden="true" />
            {t("members.invite")}
          </AriaButton>
        ) : null}
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
      {inviting ? (
        <InviteDialog
          workspaceId={workspaceId}
          access={access}
          onClose={() => {
            setInviting(false);
          }}
        />
      ) : null}
    </section>
    {canSeeInvitations && invitations.data ? (
      <InvitationsCard
        workspaceId={workspaceId}
        invitations={invitations.data.items}
        canRevoke={access.actions.revoke_invitation === true}
      />
    ) : null}
    </>
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
      { id: "tags", label: "settings.tags", icon: Tag },
      { id: "notifications", label: "settings.notifications", icon: Bell },
      { id: "fields", label: "settings.fields", icon: ListPlus },
      { id: "pipeline", label: "settings.pipeline", icon: Kanban },
      { id: "suppression", label: "settings.suppression", icon: MailX },
      { id: "domains", label: "settings.domains", icon: Globe },
      { id: "sending", label: "settings.sending", icon: AtSign },
      { id: "ai", label: "settings.ai", icon: Sparkles },
      { id: "integrations", label: "settings.integrations", icon: Plug },
      { id: "appearance", label: "settings.appearance", icon: Palette },
    ],
  },
];

/** The settings sections that exist; every other one is marked "soon". */
export type SettingsSection =
  | "team"
  | "profile"
  | "business"
  | "tags"
  | "fields"
  | "pipeline"
  | "suppression"
  | "domains"
  | "sending"
  | "integrations";
const BUILT_SECTIONS: readonly string[] = [
  "team",
  "profile",
  "business",
  "tags",
  "fields",
  "pipeline",
  "suppression",
  "domains",
  "sending",
  "integrations",
];

const SECTION_TEXT: Record<SettingsSection, { title: MessageId; desc: MessageId }> = {
  team: { title: "settings.team", desc: "settings.teamDesc" },
  profile: { title: "settings.profile", desc: "settings.profileDesc" },
  business: { title: "settings.business", desc: "settings.businessDesc" },
  tags: { title: "settings.tags", desc: "settings.tagsDesc" },
  fields: { title: "settings.fields", desc: "settings.fieldsDesc" },
  pipeline: { title: "settings.pipeline", desc: "settings.pipelineDesc" },
  suppression: { title: "settings.suppression", desc: "settings.suppressionDesc" },
  domains: { title: "settings.domains", desc: "settings.domainsDesc" },
  sending: { title: "settings.sending", desc: "settings.sendingDesc" },
  integrations: { title: "settings.integrations", desc: "settings.integrationsDesc" },
};

/**
 * Settings › My profile (ScreenSettings.dc.html L43-52). The role line is
 * real and the display name is stored (decision M-P1). "Manage" is
 * unavailable because the identity provider has no self-service page that
 * keeps it invisible (SaaS-OS ADR-0023).
 */

/**
 * The time zone times are shown in (decision M-P2): this device's, because
 * every screen formats and computes times in it. There is no stored profile
 * zone, so the design's picker is replaced by a statement, with a warning
 * when the workspace's business time zone differs (business hours, booking
 * pages and reports use the workspace's).
 */
function TimeZoneNote({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const settings = useWorkspaceSettings(workspaceId);
  const device = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const workspace = settings.data?.time_zone;
  const differs = workspace !== undefined && !sameZone(device, workspace);
  return (
    <div className="field-stack">
      <p className="field-label profile-zone-label">{t("profileForm.zone")}</p>
      <p className="profile-zone">
        {t("profileForm.deviceZone", { zone: device.replaceAll("_", " ") })}
      </p>
      <p className="profile-note">{t("profileForm.zoneNote")}</p>
      {differs ? (
        <p className="notice" role="note">
          {t("profileForm.zoneDiffers", { zone: workspace.replaceAll("_", " ") })}
        </p>
      ) : null}
    </div>
  );
}

/** Two zone names that are the same zone (aliases such as "UTC" and "Etc/UTC"). */
function sameZone(a: string, b: string): boolean {
  if (a === b) return true;
  try {
    const canonical = (zone: string) =>
      new Intl.DateTimeFormat("en", { timeZone: zone }).resolvedOptions().timeZone;
    return canonical(a) === canonical(b);
  } catch {
    return false;
  }
}

/**
 * The member's own display name in this workspace (decision M-P1): shown
 * wherever they own, host or wrote something; empty clears it.
 */
function DisplayNameField({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const toast = useToast();
  const profile = useOwnProfile(workspaceId);
  const save = useSetOwnProfile(workspaceId);
  const [draft, setDraft] = useState<string | null>(null);
  const stored = profile.data?.display_name ?? "";
  const value = draft ?? stored;
  const changed = value.trim() !== stored;
  const invalid = save.error instanceof ApiError && save.error.status === 422;
  return (
    <form
      className="field-stack"
      onSubmit={(event) => {
        event.preventDefault();
        if (!changed) return;
        save.mutate(value, {
          onSuccess: () => {
            setDraft(null);
            toast(t("profileForm.saved"));
          },
        });
      }}
    >
      <label htmlFor="profile-name" className="field-label">
        {t("profileForm.name")}
      </label>
      <div className="profile-name-row">
        <input
          id="profile-name"
          className="field-input"
          value={value}
          maxLength={80}
          disabled={profile.isPending}
          placeholder={t("profileForm.namePlaceholder")}
          aria-describedby="profile-name-help"
          aria-invalid={invalid}
          onChange={(event) => {
            setDraft(event.target.value);
            save.reset();
          }}
        />
        <Button type="submit" isDisabled={!changed || save.isPending}>
          {save.isPending ? t("profileForm.saving") : t("profileForm.save")}
        </Button>
      </div>
      <p id="profile-name-help" className="profile-note">
        {t("profileForm.nameHelp")}
      </p>
      {save.isError ? (
        <p className="notice error" role="alert">
          {t(invalid ? "profileForm.nameInvalid" : "profileForm.saveFailed")}
        </p>
      ) : null}
      {profile.isError ? (
        <p className="notice error" role="alert">
          {t("profileForm.loadFailed")}
        </p>
      ) : null}
    </form>
  );
}

function ProfileSection({
  workspaceId,
  access,
  workspaceName,
}: {
  workspaceId: string;
  access: Access;
  workspaceName: string;
}) {
  const t = useT();
  const role = highestRole(access.roles);
  return (
    <section className="profile-card" aria-label={t("settings.profile")}>
      <div className="profile-identity">
        <span className="profile-avatar" aria-hidden="true">
          <User size={22} />
        </span>
        <div>
          <p className="profile-title">{t("profile.signedIn")}</p>
          <p className="profile-role-line">
            {role ? `${role} · ${workspaceName}` : workspaceName}
          </p>
        </div>
      </div>
      <div className="profile-fields">
        <DisplayNameField workspaceId={workspaceId} />
        <TimeZoneNote workspaceId={workspaceId} />
      </div>
      <div className="idp-card">
        <Shield size={16} className="idp-icon" aria-hidden="true" />
        <div className="idp-text">
          <p className="idp-title">{t("profileForm.idpTitle")}</p>
          <p className="idp-sub">{t("profileForm.idpSub")}</p>
        </div>
        <AriaButton className="idp-manage" isDisabled>
          {t("profileForm.manage")}
          <ExternalLink size={12} aria-hidden="true" />
          <span className="visually-hidden">{` (${t("nav.soon")})`}</span>
        </AriaButton>
      </div>
    </section>
  );
}

export function SettingsPage({
  workspaceId,
  section,
  onSelect,
}: {
  workspaceId: string;
  section: SettingsSection;
  onSelect: (section: SettingsSection) => void;
}) {
  const t = useT();
  const toast = useToast();
  const access = useAccess(workspaceId);
  const workspace = useWorkspace(workspaceId);
  const isProfile = section === "profile";
  const text = SECTION_TEXT[section];
  // Below 760 px the menu sits above the section, so a chosen section's
  // content would start below the fold: bring its heading into view and
  // move focus there. Wider screens keep focus on the menu item.
  const heading = useRef<HTMLHeadingElement>(null);
  const reveal = useRef(false);
  useEffect(() => {
    if (!reveal.current) return;
    reveal.current = false;
    const target = heading.current;
    if (!target) return;
    // focus() alone does not scroll a heading that is barely on screen.
    if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "start" });
    target.focus({ preventScroll: true });
  }, [section]);
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
                const built = BUILT_SECTIONS.includes(item.id);
                const current = item.id === section;
                return (
                  <li key={item.id}>
                    <AriaButton
                      className={current ? "settings-nav-item active" : "settings-nav-item"}
                      aria-current={current ? "page" : false}
                      onPress={() => {
                        if (built) {
                          reveal.current =
                            !current &&
                            typeof window.matchMedia === "function" &&
                            window.matchMedia("(max-width: 759px)").matches;
                          onSelect(item.id as SettingsSection);
                        } else toast(t("settings.unavailable", { name: t(item.label) }));
                      }}
                    >
                      <Icon size={15} className="settings-nav-icon" aria-hidden="true" />
                      <span className="settings-nav-text">{t(item.label)}</span>
                      {built ? null : <span className="nav-soon">{t("nav.soonLower")}</span>}
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
            <h1 className="settings-title" ref={heading} tabIndex={-1}>
              {t(text.title)}
            </h1>
            <p className="settings-desc">{t(text.desc)}</p>
          </div>
          {access.isPending ? <Loading /> : null}
          {access.isError ? (
            <LoadError error={access.error} onRetry={() => void access.refetch()} />
          ) : null}
          {access.data && isProfile ? (
            <ProfileSection
              workspaceId={workspaceId}
              access={access.data}
              workspaceName={workspace.data?.name ?? ""}
            />
          ) : null}
          {access.data && section === "business" ? (
            <BusinessSettings
              workspaceId={workspaceId}
              workspaceName={workspace.data?.name ?? ""}
              canEdit={access.data.actions.update_workspace === true}
            />
          ) : null}
          {access.data && section === "fields" ? (
            <FieldSettings workspaceId={workspaceId} canEdit={access.data.actions.update_workspace === true} />
          ) : null}
          {access.data && section === "pipeline" ? (
            <PipelineSettings workspaceId={workspaceId} canEdit={access.data.actions.manage_pipeline === true} />
          ) : null}
          {access.data && section === "suppression" ? (
            <SuppressionSettings
              workspaceId={workspaceId}
              canRead={access.data.actions.read_suppressions === true}
              canManage={access.data.actions.manage_suppressions === true}
            />
          ) : null}
          {access.data && section === "domains" ? (
            <DomainSettings workspaceId={workspaceId} canEdit={access.data.actions.update_workspace === true} />
          ) : null}
          {access.data && section === "sending" ? (
            <SendingDomainSettings
              workspaceId={workspaceId}
              canEdit={access.data.actions.update_workspace === true}
            />
          ) : null}
          {access.data && section === "integrations" ? (
            <IntegrationSettings
              workspaceId={workspaceId}
              canManage={access.data.actions.manage_integrations === true}
            />
          ) : null}
          {access.data && section === "tags" ? (
            <TagSettings workspaceId={workspaceId} canEdit={access.data.actions.update_workspace === true} />
          ) : null}
          {access.data && section === "team" ? (
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
