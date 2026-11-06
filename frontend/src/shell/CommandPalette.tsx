import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  CornerDownLeft,
  Kanban,
  Search,
  Settings,
  User,
  UserRound,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Autocomplete,
  Dialog,
  Header,
  Input,
  Menu,
  MenuItem,
  MenuSection,
  Modal,
  ModalOverlay,
  SearchField,
  useFilter,
} from "react-aria-components";

import { api } from "../api/client";
import { where } from "../api/records";
import { type MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ALL_SECTIONS, SETTINGS_SLUG } from "./navigation";

/*
 * The ⌘K palette (LeadStack CRM.dc.html L257-281): 600 px panel, 52 px input,
 * results, footer. From two typed characters it also searches the workspace's
 * contacts and opportunities with their lists' own search (`q`, the server's
 * rules), a few of each; a refused or failed search shows no records rather
 * than invented ones. Workspaces are not searched: the switcher lists them.
 */

/** Records shown per group, and the shortest query that searches them. */
const RECORDS = 5;
const MIN_QUERY = 2;

interface Target {
  id: string;
  label: string;
  sub: string;
  icon: typeof Users;
  section: string;
  search?: { section: "profile" };
}

interface RecordHit {
  key: string;
  label: string;
  sub: string;
  section: "contacts" | "opportunities";
  id: string;
}

export function useCommandPaletteShortcut(setOpen: (update: (open: boolean) => boolean) => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [setOpen]);
}

/** The query once typing pauses, so each keystroke is not a request. */
function useSettled(value: string, ms = 200): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSettled(value);
    }, ms);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, ms]);
  return settled;
}

function useRecordSearch(workspaceId: string, query: string): RecordHit[] {
  const q = query.trim().slice(0, 100);
  const enabled = q.length >= MIN_QUERY;
  const contacts = useQuery({
    queryKey: ["workspace", workspaceId, "palette", "contacts", q],
    enabled,
    retry: false,
    queryFn: async () => {
      const result = await api.GET("/v1/workspaces/{tenant_id}/contacts", {
        params: { path: where(workspaceId), query: { q, limit: RECORDS } },
      });
      return result.data?.items ?? [];
    },
  });
  const deals = useQuery({
    queryKey: ["workspace", workspaceId, "palette", "opportunities", q],
    enabled,
    retry: false,
    queryFn: async () => {
      const result = await api.GET("/v1/workspaces/{tenant_id}/opportunities", {
        params: { path: where(workspaceId), query: { q, limit: RECORDS } },
      });
      return result.data?.items ?? [];
    },
  });
  if (!enabled) return [];
  return [
    ...(contacts.data ?? []).map((c) => ({
      key: `contact:${c.id}`,
      label: [c.first_name, c.last_name].filter(Boolean).join(" "),
      sub: c.email ?? c.company?.name ?? "",
      section: "contacts" as const,
      id: c.id,
    })),
    ...(deals.data ?? []).map((d) => ({
      key: `deal:${d.id}`,
      label: d.title,
      sub: d.contact?.name ?? d.company?.name ?? "",
      section: "opportunities" as const,
      id: d.id,
    })),
  ];
}

function HitItem({ hit }: { hit: RecordHit }) {
  const Icon = hit.section === "contacts" ? UserRound : Kanban;
  return (
    <MenuItem id={hit.key} className="palette-item" textValue={hit.label}>
      <Icon size={15} className="palette-item-icon" aria-hidden="true" />
      <span className="palette-item-label">{hit.label}</span>
      <span className="palette-item-sub">{hit.sub}</span>
      <CornerDownLeft size={13} className="palette-enter" aria-hidden="true" />
    </MenuItem>
  );
}

export function CommandPalette({
  workspaceId,
  workspaceName,
  isOpen,
  onOpenChange,
}: {
  workspaceId: string;
  workspaceName: string;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const navigate = useNavigate();
  const { contains } = useFilter({ sensitivity: "base" });
  const [query, setQuery] = useState("");
  const hits = useRecordSearch(workspaceId, useSettled(query));
  const contactHits = hits.filter((h) => h.section === "contacts");
  const dealHits = hits.filter((h) => h.section === "opportunities");
  // The server already matched the records (names, email, phone, ...); only
  // pages are filtered here.
  const filter = (textValue: string, input: string, node: { key: unknown }) =>
    String(node.key).includes(":") || contains(textValue, input);

  const sub = (id: MessageId | null) => (id ? t("nav.soon") : t("palette.page"));
  const targets: Target[] = [
    ...ALL_SECTIONS.map((s) => ({
      id: s.slug,
      label: t(s.label),
      sub: sub(s.unavailable),
      icon: s.icon,
      section: s.slug,
    })),
    {
      id: "team",
      label: t("settings.team"),
      sub: t("nav.settings"),
      icon: Users,
      section: SETTINGS_SLUG,
    },
    {
      id: "profile",
      label: t("settings.profile"),
      sub: t("nav.settings"),
      icon: User,
      section: SETTINGS_SLUG,
      search: { section: "profile" },
    },
    { id: "settings", label: t("nav.settings"), sub: t("palette.page"), icon: Settings, section: SETTINGS_SLUG },
  ];

  const close = () => {
    setQuery("");
    onOpenChange(false);
  };

  return (
    <ModalOverlay
      className="palette-overlay"
      isOpen={isOpen}
      isDismissable
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <Modal className="palette">
        <Dialog className="palette-dialog" aria-label={t("palette.title")}>
          <Autocomplete inputValue={query} onInputChange={setQuery} filter={filter}>
            {/* Typing starts at once, as in the design; the dialog restores focus on close. */}
            {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
            <SearchField className="palette-search" aria-label={t("palette.placeholder")} autoFocus>
              <Search size={17} className="palette-search-icon" aria-hidden="true" />
              <Input className="palette-input" placeholder={t("palette.placeholder")} />
              <kbd className="palette-esc" aria-hidden="true">
                esc
              </kbd>
            </SearchField>
            <Menu
              className="palette-results"
              aria-label={t("palette.title")}
              renderEmptyState={() => (
                <p className="palette-empty">{t("palette.noMatches", { query })}</p>
              )}
              onAction={(key) => {
                const hit = hits.find((h) => h.key === key);
                if (hit) {
                  close();
                  void navigate({
                    to: "/w/$workspaceId/$section",
                    params: { workspaceId, section: hit.section },
                    search: { record: hit.id },
                  });
                  return;
                }
                const target = targets.find((x) => x.id === key);
                if (!target) return;
                close();
                void navigate({
                  to: "/w/$workspaceId/$section",
                  params: { workspaceId, section: target.section },
                  search: target.search ?? {},
                });
              }}
            >
              {contactHits.length ? (
                <MenuSection>
                  <Header className="palette-header">{t("nav.contacts")}</Header>
                  {contactHits.map((hit) => (
                    <HitItem key={hit.key} hit={hit} />
                  ))}
                </MenuSection>
              ) : null}
              {dealHits.length ? (
                <MenuSection>
                  <Header className="palette-header">{t("nav.opportunities")}</Header>
                  {dealHits.map((hit) => (
                    <HitItem key={hit.key} hit={hit} />
                  ))}
                </MenuSection>
              ) : null}
              <MenuSection>
                <Header className="palette-header">{t("palette.goTo")}</Header>
                {targets.map((target) => {
                  const Icon = target.icon;
                  return (
                    <MenuItem
                      key={target.id}
                      id={target.id}
                      className="palette-item"
                      textValue={target.label}
                    >
                      <Icon size={15} className="palette-item-icon" aria-hidden="true" />
                      <span className="palette-item-label">{target.label}</span>
                      <span className="palette-item-sub">{target.sub}</span>
                      <CornerDownLeft size={13} className="palette-enter" aria-hidden="true" />
                    </MenuItem>
                  );
                })}
              </MenuSection>
            </Menu>
          </Autocomplete>
          <div className="palette-footer" aria-hidden="true">
            <span>↵ {t("palette.open")}</span>
            <span>⌘K {t("palette.toggle")}</span>
            <span className="palette-footer-fill" />
            <span>{t("palette.scope", { name: workspaceName })}</span>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
