import { type Access, type Member, ROLES } from "../api/client";
import type { MemberChange } from "../api/queries";
import type { MessageId } from "../i18n/en";

export interface MemberAction {
  key: string;
  label: MessageId;
  role?: string;
  change: MemberChange;
  /** Which confirmation the change needs before it is sent, if any. */
  confirm: "owner" | "revoke" | null;
}

/**
 * The actions to offer for one member row. Mirrors the server's rules
 * (PHASE2-PLAN.md §5.4) only to avoid offering what would be refused; the
 * server decides, and its refusal is shown if the two ever disagree.
 */
export function availableActions(member: Member, access: Access): MemberAction[] {
  const can = (name: string) => access.actions[name] === true;
  const isOwner = member.roles.includes("Owner");
  const isSelf = member.membership_id === access.membership_id;

  if (isSelf) {
    return isOwner && can("remove_role")
      ? [
          {
            key: "step-down",
            label: "action.stepDown",
            change: { kind: "remove_role", role: "Owner" },
            confirm: "owner",
          },
        ]
      : [];
  }
  if (isOwner && !can("manage_owners")) return [];

  const actions: MemberAction[] = [];
  const ownerConfirm = (touchesOwner: boolean) => (touchesOwner ? "owner" : null);

  if (member.status === "active") {
    if (can("assign_role")) {
      for (const role of ROLES) {
        if (member.roles.includes(role) || (role === "Owner" && !can("manage_owners"))) continue;
        actions.push({
          key: `assign-${role}`,
          label: "action.assign",
          role,
          change: { kind: "assign_role", role },
          confirm: ownerConfirm(role === "Owner"),
        });
      }
    }
    if (can("remove_role")) {
      for (const role of ROLES) {
        if (!member.roles.includes(role)) continue;
        actions.push({
          key: `remove-${role}`,
          label: "action.remove",
          role,
          change: { kind: "remove_role", role },
          confirm: ownerConfirm(role === "Owner"),
        });
      }
    }
    if (can("suspend_member")) {
      actions.push({
        key: "suspend",
        label: "action.suspend",
        change: { kind: "suspend" },
        confirm: ownerConfirm(isOwner),
      });
    }
  }
  if (member.status === "suspended" && can("reactivate_member")) {
    actions.push({
      key: "reactivate",
      label: "action.reactivate",
      change: { kind: "reactivate" },
      confirm: ownerConfirm(isOwner),
    });
  }
  if (member.status !== "revoked" && can("revoke_member")) {
    actions.push({
      key: "revoke",
      label: "action.revoke",
      change: { kind: "revoke" },
      confirm: isOwner ? "owner" : "revoke",
    });
  }
  return actions;
}

/**
 * The most senior of a member's roles, for one-line display. The API returns
 * roles alphabetically, so the first one is not necessarily the highest.
 */
export function highestRole(roles: readonly string[]): string | undefined {
  return ROLES.find((role) => roles.includes(role)) ?? roles[0];
}
