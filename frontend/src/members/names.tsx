import { createContext, type ReactNode, useContext, useMemo } from "react";

import { useMembers } from "../api/queries";

/*
 * Members' display names for the current workspace (decision M-P1). Members
 * choose their own name; until they do, they show by ID as before. The names
 * come from the member list's first page; a member beyond it shows by ID.
 */

export type MemberNames = ReadonlyMap<string, string>;

const NamesContext = createContext<MemberNames>(new Map());

export function MemberNamesProvider({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: ReactNode;
}) {
  const members = useMembers(workspaceId, 0, true);
  const names = useMemo<MemberNames>(() => {
    const map = new Map<string, string>();
    for (const member of members.data?.items ?? []) {
      if (member.display_name) map.set(member.user_id, member.display_name);
    }
    return map;
  }, [members.data]);
  return (
    <NamesContext.Provider value={names}>{children}</NamesContext.Provider>
  );
}

export function useMemberNames(): MemberNames {
  return useContext(NamesContext);
}
