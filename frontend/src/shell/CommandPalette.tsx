import { useNavigate } from "@tanstack/react-router";
import { CornerDownLeft, Search, Settings, User, Users } from "lucide-react";
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

import { type MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ALL_SECTIONS, SETTINGS_SLUG } from "./navigation";

/*
 * The ⌘K palette (LeadStack CRM.dc.html L257-281): 600 px panel, 52 px input,
 * results, footer. The design also searches contacts, opportunities and
 * workspaces; none of those can be searched yet, so only its "Go to" group
 * exists here, and the palette says so instead of returning invented results.
 */

interface Target {
  id: string;
  label: string;
  sub: string;
  icon: typeof Users;
  section: string;
  search?: { section: "profile" };
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
          <Autocomplete inputValue={query} onInputChange={setQuery} filter={contains}>
            {/* Typing starts at once, as in the design; the dialog restores focus on close. */}
            {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
            <SearchField className="palette-search" aria-label={t("palette.placeholder")} autoFocus>
              <Search size={17} className="palette-search-icon" aria-hidden="true" />
              <Input className="palette-input" placeholder={t("palette.placeholder")} />
              <kbd className="palette-esc" aria-hidden="true">
                esc
              </kbd>
            </SearchField>
            <p className="palette-note">{t("palette.recordsUnavailable")}</p>
            <Menu
              className="palette-results"
              aria-label={t("palette.goTo")}
              renderEmptyState={() => (
                <p className="palette-empty">{t("palette.noMatches", { query })}</p>
              )}
              onAction={(key) => {
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
