import { describe, expect, it } from "vitest";

import type { Access, Member } from "../api/client";
import { availableActions, highestRole } from "./actions";

const ALL = {
  read_members: true,
  assign_role: true,
  remove_role: true,
  suspend_member: true,
  reactivate_member: true,
  revoke_member: true,
  manage_owners: true,
};
const owner: Access = { membership_id: "me", roles: ["Owner"], actions: ALL };
const admin: Access = {
  membership_id: "me",
  roles: ["Admin"],
  actions: { ...ALL, manage_owners: false },
};
const reader: Access = {
  membership_id: "me",
  roles: ["Read-only"],
  actions: { read_members: true },
};

const member = (roles: string[], status = "active", id = "other"): Member => ({
  membership_id: id,
  user_id: "u",
  status,
  roles,
});

const keys = (m: Member, a: Access) => availableActions(m, a).map((x) => x.key);

describe("availableActions", () => {
  it("offers an Admin nothing on an Owner and never the Owner role", () => {
    expect(keys(member(["Owner"]), admin)).toEqual([]);
    expect(keys(member(["Member"]), admin)).not.toContain("assign-Owner");
  });

  it("lets an Owner grant Owner, with confirmation", () => {
    const grant = availableActions(member(["Admin"]), owner).find((a) => a.key === "assign-Owner");
    expect(grant?.confirm).toBe("owner");
  });

  it("offers only stepping down on your own row, and only to an Owner", () => {
    expect(keys(member(["Owner"], "active", "me"), owner)).toEqual(["step-down"]);
    expect(keys(member(["Admin"], "active", "me"), admin)).toEqual([]);
  });

  it("offers a read-only member nothing", () => {
    expect(keys(member(["Member"]), reader)).toEqual([]);
  });

  it("offers reactivation, not role changes, for a suspended member", () => {
    expect(keys(member(["Member"], "suspended"), admin)).toEqual(["reactivate", "revoke"]);
  });

  it("asks for confirmation before removing anyone", () => {
    const revoke = availableActions(member(["Member"]), admin).find((a) => a.key === "revoke");
    expect(revoke?.confirm).toBe("revoke");
    const ownerRevoke = availableActions(member(["Owner"]), owner).find((a) => a.key === "revoke");
    expect(ownerRevoke?.confirm).toBe("owner");
  });
});

describe("highestRole", () => {
  it("picks the most senior role, not the alphabetically first", () => {
    expect(highestRole(["Admin", "Owner"])).toBe("Owner");
    expect(highestRole(["Member", "Read-only"])).toBe("Member");
    expect(highestRole([])).toBeUndefined();
  });
});
