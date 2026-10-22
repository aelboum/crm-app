import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import {
  Bell,
  CalendarPlus,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CircleHelp,
  Kanban,
  LogOut,
  type LucideIcon,
  Menu as MenuIcon,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Settings,
  Shield,
  SquareCheckBig,
  User,
  UserPlus,
  X,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Header,
  Menu,
  MenuItem,
  MenuSection,
  MenuTrigger,
  Modal,
  ModalOverlay,
  Popover,
} from "react-aria-components";

import { useAccess, useMe, useSignOut, useWorkspace } from "../api/queries";
import { useToast } from "../components/ui/Toast";
import { useT } from "../i18n/useT";
import { highestRole } from "../members/actions";
import { findGroup, GROUPS, type Section, SETTINGS_SLUG } from "./navigation";
import { type SidebarState, useSidebar } from "./useSidebar";

/*
 * The application frame, reproduced from the design's grouped shell
 * (LeadStack CRM.dc.html, header L29-144, sidebar L160-186): 52 px header,
 * 232/60 px sidebar, the design's control sizes and colours (styles.css,
 * "Frame"). Controls whose feature does not exist yet are kept where the
 * design puts them but say so: menu items are disabled and marked "soon",
 * and the search trigger answers with the design's own toast.
 */

const SIDEBAR_ID = "workspace-sidebar";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? `${words[0]?.[0] ?? ""}${words[1]?.[0] ?? ""}` : name.slice(0, 2);
  return letters.toUpperCase();
}

function Brand() {
  const t = useT();
  return (
    <Link to="/" className="brand" aria-label={t("app.home")}>
      <span className="brand-tile" data-mark="LS" aria-hidden="true" />
      <span className="brand-name">{t("app.brand")}</span>
    </Link>
  );
}

function SkipLink() {
  const t = useT();
  return (
    <a className="skip-link" href="#main">
      {t("app.skip")}
    </a>
  );
}

function useSignOutAndLeave() {
  const signOut = useSignOut();
  const navigate = useNavigate();
  return {
    signOut,
    // Leave the current page so nothing from the ended session stays on screen.
    run: () => {
      signOut.mutate(undefined, { onSuccess: () => void navigate({ to: "/" }) });
    },
  };
}

/** Pages outside a workspace: the start page and sign-in. */
export function PlainLayout() {
  const t = useT();
  const me = useMe();
  const { signOut, run } = useSignOutAndLeave();
  return (
    <>
      <SkipLink />
      <header className="app-header">
        <Brand />
        <span className="header-fill" />
        {me.data ? (
          <>
            {signOut.isError ? (
              <span role="alert" className="field-error">
                {t("app.signOutFailed")}
              </span>
            ) : null}
            <AriaButton className="header-text-button" isDisabled={signOut.isPending} onPress={run}>
              <LogOut size={15} aria-hidden="true" />
              {t("app.signOut")}
            </AriaButton>
          </>
        ) : null}
      </header>
      <main id="main" className="plain-main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}

function WorkspaceSwitcher({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const navigate = useNavigate();
  const workspace = useWorkspace(workspaceId);
  const name = workspace.data?.name ?? "";
  return (
    <MenuTrigger>
      <AriaButton className="ws-switcher">
        <span className="ws-tile" data-mark={name ? initials(name) : ""} aria-hidden="true" />
        <span className="ws-text">
          <span className="ws-name">{name}</span>
          <span className="ws-kind">{t("ws.kind")}</span>
        </span>
        <ChevronsUpDown size={14} className="ws-chevron" aria-hidden="true" />
      </AriaButton>
      <Popover className="menu-popover ws-menu" placement="bottom start" offset={6}>
        <Menu
          className="menu"
          aria-label={t("ws.menu")}
          onAction={(key) => {
            if (key === "other") void navigate({ to: "/" });
          }}
        >
          <MenuSection>
            <Header className="menu-header">{t("ws.current")}</Header>
            <MenuItem id="current" className="menu-item" isDisabled textValue={name}>
              <span className="ws-tile small" data-mark={name ? initials(name) : ""} aria-hidden="true" />
              <span className="menu-item-label">{name}</span>
            </MenuItem>
          </MenuSection>
          <MenuSection>
            <MenuItem id="other" className="menu-item menu-footer-item">
              {t("ws.other")}
            </MenuItem>
          </MenuSection>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

interface CreateItem {
  id: string;
  icon: LucideIcon;
  label: Parameters<ReturnType<typeof useT>>[0];
  key: string;
}

// The design's "+ New" menu for a client workspace, in its order and with its
// shortcut letters. None of these records can be created yet.
const CREATE_ITEMS: CreateItem[] = [
  { id: "contact", icon: UserPlus, label: "create.contact", key: "C" },
  { id: "opportunity", icon: Kanban, label: "create.opportunity", key: "O" },
  { id: "appointment", icon: CalendarPlus, label: "create.appointment", key: "A" },
  { id: "conversation", icon: MessageSquarePlus, label: "create.conversation", key: "M" },
  { id: "task", icon: SquareCheckBig, label: "create.task", key: "T" },
];

function CreateMenu({ workspaceName }: { workspaceName: string }) {
  const t = useT();
  return (
    <MenuTrigger>
      <AriaButton className="new-button">
        <Plus size={16} aria-hidden="true" />
        <span className="new-label">{t("create.new")}</span>
      </AriaButton>
      <Popover className="menu-popover create-menu" placement="bottom end" offset={6}>
        <Menu className="menu" aria-label={t("create.new")} disabledKeys={CREATE_ITEMS.map((c) => c.id)}>
          <MenuSection>
            <Header className="menu-header">{t("create.in", { name: workspaceName })}</Header>
            {CREATE_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <MenuItem
                  key={item.id}
                  id={item.id}
                  className="menu-item"
                  textValue={`${t(item.label)} (${t("nav.soon")})`}
                >
                  <Icon size={15} className="menu-icon" aria-hidden="true" />
                  <span className="menu-item-label">{t(item.label)}</span>
                  <span className="menu-soon">{t("nav.soon")}</span>
                </MenuItem>
              );
            })}
          </MenuSection>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

function Notifications() {
  const t = useT();
  return (
    <DialogTrigger>
      <AriaButton className="icon-button" aria-label={t("notif.button")}>
        <Bell size={17} aria-hidden="true" />
      </AriaButton>
      <Popover className="menu-popover notif-panel" placement="bottom end" offset={6}>
        <Dialog className="notif-dialog" aria-label={t("notif.title")}>
          <div className="notif-head">
            <span className="notif-title">{t("notif.title")}</span>
          </div>
          <p className="notif-empty">{t("notif.empty")}</p>
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}

function HelpMenu() {
  const t = useT();
  return (
    <MenuTrigger>
      <AriaButton className="icon-button help-button" aria-label={t("help.button")}>
        <CircleHelp size={17} aria-hidden="true" />
      </AriaButton>
      <Popover className="menu-popover help-menu" placement="bottom end" offset={6}>
        <Menu className="menu" aria-label={t("help.button")} disabledKeys={["center"]}>
          <MenuItem id="center" className="menu-item" textValue={`${t("help.center")} (${t("nav.soon")})`}>
            <CircleHelp size={15} className="menu-icon" aria-hidden="true" />
            <span className="menu-item-label">{t("help.center")}</span>
            <span className="menu-soon">{t("nav.soon")}</span>
          </MenuItem>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

function ProfileMenu({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const access = useAccess(workspaceId);
  const { signOut, run } = useSignOutAndLeave();
  const role = access.data ? highestRole(access.data.roles) : undefined;
  return (
    <>
      {signOut.isError ? (
        <span role="alert" className="field-error">
          {t("app.signOutFailed")}
        </span>
      ) : null}
      <MenuTrigger>
        <AriaButton className="avatar-button" aria-label={t("profile.button")}>
          <span className="avatar" aria-hidden="true">
            <User size={15} />
          </span>
        </AriaButton>
        <Popover className="menu-popover profile-menu" placement="bottom end" offset={6}>
          <Menu
            className="menu"
            aria-label={t("profile.button")}
            disabledKeys={["profile", "security"]}
            onAction={(key) => {
              if (key === "signout") run();
            }}
          >
            <MenuSection>
              <Header className="profile-head">
                <span className="profile-name">{t("profile.signedIn")}</span>
                {role ? <span className="profile-role">{role}</span> : null}
              </Header>
              <MenuItem id="profile" className="menu-item" textValue={`${t("profile.preferences")} (${t("nav.soon")})`}>
                <User size={15} className="menu-icon" aria-hidden="true" />
                <span className="menu-item-label">{t("profile.preferences")}</span>
                <span className="menu-soon">{t("nav.soon")}</span>
              </MenuItem>
              <MenuItem id="security" className="menu-item" textValue={`${t("profile.security")} (${t("nav.soon")})`}>
                <Shield size={15} className="menu-icon" aria-hidden="true" />
                <span className="menu-item-label">{t("profile.security")}</span>
                <span className="menu-soon">{t("nav.soon")}</span>
              </MenuItem>
              <MenuItem id="signout" className="menu-item" textValue={t("app.signOut")}>
                <LogOut size={15} className="menu-icon" aria-hidden="true" />
                <span className="menu-item-label">{t("app.signOut")}</span>
              </MenuItem>
            </MenuSection>
          </Menu>
        </Popover>
      </MenuTrigger>
    </>
  );
}

function NavItem({
  workspaceId,
  section,
  open,
  onNavigate,
}: {
  workspaceId: string;
  section: Section;
  open: boolean;
  onNavigate: () => void;
}) {
  const t = useT();
  const Icon = section.icon;
  const label = t(section.label);
  return (
    <li>
      <Link
        to="/w/$workspaceId/$section"
        params={{ workspaceId, section: section.slug }}
        className="nav-item"
        activeProps={{ className: "nav-item active", "aria-current": "page" }}
        title={label}
        onClick={onNavigate}
      >
        <Icon size={16} className="nav-icon" aria-hidden="true" />
        {open ? (
          <span className="nav-label">{label}</span>
        ) : (
          <span className="visually-hidden">{label}</span>
        )}
        {section.unavailable && open ? <span className="nav-soon">{t("nav.soonLower")}</span> : null}
        {section.unavailable && !open ? (
          <span className="visually-hidden">{` (${t("nav.soon")})`}</span>
        ) : null}
      </Link>
    </li>
  );
}

function Navigation({
  workspaceId,
  open,
  onNavigate,
}: {
  workspaceId: string;
  open: boolean;
  onNavigate: () => void;
}) {
  const t = useT();
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  return (
    <div className="nav-scroll">
      {GROUPS.map((group, index) => {
        const groupOpen = !closed[group.key] || !open;
        const listId = `nav-group-${group.key}`;
        return (
          <div key={group.key} className="nav-group">
            {group.label && open ? (
              <AriaButton
                className="nav-group-header"
                aria-expanded={groupOpen}
                aria-controls={listId}
                onPress={() => {
                  setClosed((c) => ({ ...c, [group.key]: !c[group.key] }));
                }}
              >
                <span className="nav-group-text">{t(group.label)}</span>
                {groupOpen ? (
                  <ChevronDown size={13} aria-hidden="true" />
                ) : (
                  <ChevronRight size={13} aria-hidden="true" />
                )}
              </AriaButton>
            ) : null}
            {group.label && !open && index > 0 ? <div className="nav-divider" aria-hidden="true" /> : null}
            {groupOpen ? (
              <ul className="nav-list" id={listId} aria-label={group.label ? t(group.label) : undefined}>
                {group.sections.map((section) => (
                  <NavItem
                    key={section.slug}
                    workspaceId={workspaceId}
                    section={section}
                    open={open}
                    onNavigate={onNavigate}
                  />
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function SidebarFooter({
  workspaceId,
  sidebar,
  open,
  onNavigate,
}: {
  workspaceId: string;
  sidebar: SidebarState;
  open: boolean;
  onNavigate: () => void;
}) {
  const t = useT();
  return (
    <div className="sidebar-footer">
      <Link
        to="/w/$workspaceId/$section"
        params={{ workspaceId, section: SETTINGS_SLUG }}
        className="nav-item nav-settings"
        activeProps={{ className: "nav-item nav-settings active-settings", "aria-current": "page" }}
        title={t("nav.settings")}
        onClick={onNavigate}
      >
        <Settings size={16} aria-hidden="true" />
        {open ? <span>{t("nav.settings")}</span> : <span className="visually-hidden">{t("nav.settings")}</span>}
      </Link>
      {sidebar.narrow ? null : (
        <AriaButton
          className="nav-item nav-collapse"
          aria-controls={SIDEBAR_ID}
          aria-expanded={!sidebar.collapsed}
          aria-label={sidebar.collapsed ? t("nav.expand") : t("nav.collapse")}
          onPress={sidebar.toggleCollapsed}
        >
          {sidebar.collapsed ? (
            <PanelLeftOpen size={16} aria-hidden="true" />
          ) : (
            <PanelLeftClose size={16} aria-hidden="true" />
          )}
          {open ? <span aria-hidden="true">{t("nav.collapseShort")}</span> : null}
        </AriaButton>
      )}
    </div>
  );
}

function Sidebar({ workspaceId, sidebar }: { workspaceId: string; sidebar: SidebarState }) {
  const t = useT();
  if (sidebar.narrow) {
    const close = () => {
      sidebar.setOverlayOpen(false);
    };
    return (
      <ModalOverlay
        className="sidebar-scrim"
        isOpen={sidebar.overlayOpen}
        isDismissable
        onOpenChange={sidebar.setOverlayOpen}
      >
        <Modal className="sidebar-overlay">
          <Dialog className="sidebar" aria-label={t("nav.label")}>
            <div className="sidebar-overlay-head">
              <AriaButton className="icon-button" aria-label={t("nav.close")} onPress={close}>
                <X size={16} aria-hidden="true" />
              </AriaButton>
            </div>
            <nav aria-label={t("nav.label")} className="nav">
              <Navigation workspaceId={workspaceId} open onNavigate={close} />
              <SidebarFooter workspaceId={workspaceId} sidebar={sidebar} open onNavigate={close} />
            </nav>
          </Dialog>
        </Modal>
      </ModalOverlay>
    );
  }
  const open = !sidebar.collapsed;
  return (
    <nav
      id={SIDEBAR_ID}
      aria-label={t("nav.label")}
      className={open ? "sidebar nav" : "sidebar nav collapsed"}
    >
      <Navigation workspaceId={workspaceId} open={open} onNavigate={() => undefined} />
      <SidebarFooter workspaceId={workspaceId} sidebar={sidebar} open={open} onNavigate={() => undefined} />
    </nav>
  );
}

/** Everything inside one workspace: header, sidebar and the section page. */
export function AppFrame({ workspaceId, children }: { workspaceId: string; children: ReactNode }) {
  const t = useT();
  const toast = useToast();
  const sidebar = useSidebar();
  const workspace = useWorkspace(workspaceId);
  return (
    <div className="frame">
      <SkipLink />
      <header className="app-header">
        {sidebar.narrow ? (
          <AriaButton
            className="icon-button"
            aria-label={t("nav.open")}
            aria-expanded={sidebar.overlayOpen}
            onPress={() => {
              sidebar.setOverlayOpen(true);
            }}
          >
            <MenuIcon size={18} aria-hidden="true" />
          </AriaButton>
        ) : null}
        <Brand />
        <span className="header-divider" aria-hidden="true" />
        <WorkspaceSwitcher workspaceId={workspaceId} />
        <div className="search-slot">
          <AriaButton
            className="search-trigger"
            onPress={() => {
              toast(t("search.unavailable"));
            }}
          >
            <Search size={15} aria-hidden="true" />
            <span className="search-text">{t("search.placeholder")}</span>
            <kbd className="search-kbd" aria-hidden="true">
              ⌘K
            </kbd>
          </AriaButton>
        </div>
        <div className="header-actions">
          <CreateMenu workspaceName={workspace.data?.name ?? ""} />
          <Notifications />
          <HelpMenu />
          <ProfileMenu workspaceId={workspaceId} />
        </div>
      </header>
      <div className="frame-body">
        <Sidebar workspaceId={workspaceId} sidebar={sidebar} />
        <main id="main" className="frame-main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

/** The design's placeholder page for a module that is not built (LeadStack CRM.dc.html L240-248). */
export function PlaceholderPage({ section }: { section: Section }) {
  const t = useT();
  const group = findGroup(section.slug);
  return (
    <div className="placeholder-page">
      {group?.label ? <p className="placeholder-group">{t(group.label)}</p> : null}
      <h1 className="placeholder-title">{t(section.label)}</h1>
      <div className="placeholder-card">
        <span className="placeholder-badge">{t("unavailable.kicker")}</span>
        <p className="placeholder-desc">{section.unavailable ? t(section.unavailable) : null}</p>
        <p className="placeholder-note">{t("unavailable.note")}</p>
      </div>
    </div>
  );
}
