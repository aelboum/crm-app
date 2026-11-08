import { createContext, type ReactNode, useContext, useMemo } from "react";
import { useIntl } from "react-intl";

import { useIntegrationNames } from "../api/integrations";
import { useMembers } from "../api/queries";
import type { MessageId } from "../i18n/en";

/*
 * Members' display names for the current workspace (decision M-P1). Members
 * choose their own name; until they do, they show by ID as before. The names
 * come from the member list's first page; a member beyond it shows by ID.
 * Integrations (decision P12-N) show by their name, marked as an
 * integration, wherever they made an entry.
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
  const intl = useIntl();
  const members = useMembers(workspaceId, 0, true);
  const integrations = useIntegrationNames(workspaceId);
  const names = useMemo<MemberNames>(() => {
    const map = new Map<string, string>();
    for (const item of integrations.data?.items ?? []) {
      const id: MessageId = "members.integrationName";
      map.set(item.id, intl.formatMessage({ id }, { name: item.name }));
    }
    for (const member of members.data?.items ?? []) {
      if (member.display_name) map.set(member.user_id, member.display_name);
    }
    return map;
  }, [members.data, integrations.data, intl]);
  return (
    <NamesContext.Provider value={names}>{children}</NamesContext.Provider>
  );
}

export function useMemberNames(): MemberNames {
  return useContext(NamesContext);
}
