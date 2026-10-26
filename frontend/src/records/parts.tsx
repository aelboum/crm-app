import { Check, ChevronDown, Download, X } from "lucide-react";
import type { ReactNode } from "react";
import { useIntl } from "react-intl";
import {
  Button as AriaButton,
  Dialog as AriaDialog,
  Heading,
  Menu,
  MenuItem,
  MenuTrigger,
  Modal,
  ModalOverlay,
  Popover,
} from "react-aria-components";

import type { Member } from "../api/client";
import type { ExportKind } from "../api/exportContacts";
import type { Stage } from "../api/records";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { exportMessage } from "./useRecordExport";

/*
 * Pieces shared by the Contacts and Companies screens (ScreenContacts.dc.html,
 * ScreenCompanies.dc.html). Colours and sizes follow the design; differences
 * are recorded in DESIGN-FIDELITY.md §4c.
 */

type T = ReturnType<typeof useT>;

const STAGE_LABEL: Record<Stage, MessageId> = {
  lead: "stage.lead",
  prospect: "stage.prospect",
  customer: "stage.customer",
  inactive: "stage.inactive",
};

export function isStage(value: string): value is Stage {
  return value in STAGE_LABEL;
}

export function stageLabel(t: T, stage: string): string {
  return isStage(stage) ? t(STAGE_LABEL[stage]) : stage;
}

/** The design's stage pills; "Customer" takes the colours of its dental "Patient" stage (P2-E). */
export function StagePill({ stage }: { stage: string }) {
  const t = useT();
  return (
    <span className={`stage-pill stage-${isStage(stage) ? stage : "inactive"}`}>{stageLabel(t, stage)}</span>
  );
}

/** The design's six avatar colour pairs, picked from the record ID. */
const AVATAR_TONES = 6;

function toneOf(id: string): number {
  let sum = 0;
  for (const char of id) sum = (sum + char.charCodeAt(0)) % 997;
  return sum % AVATAR_TONES;
}

export function initials(...parts: (string | null | undefined)[]): string {
  const letters = parts
    .flatMap((part) => (part ?? "").trim().split(/\s+/))
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase());
  return letters.slice(0, 2).join("") || "?";
}

export function Avatar({
  id,
  label,
  square = false,
  large = false,
}: {
  id: string;
  label: string;
  square?: boolean;
  large?: boolean;
}) {
  const shape = square ? "avatar-square" : `avatar-tone-${String(toneOf(id))}`;
  return (
    <span className={`avatar ${shape}${large ? " avatar-large" : ""}`} aria-hidden="true">
      {label}
    </span>
  );
}

/** Who owns a record. Members have no stored names yet, so they show by ID (PHASE2-PLAN.md §6.5). */
export function ownerLabel(t: T, ownerId: string | null | undefined, meId: string | undefined): string {
  if (!ownerId) return t("records.owner.none");
  if (ownerId === meId) return t("records.owner.me");
  return t("records.owner.member", { id: ownerId.slice(0, 8) });
}

export function OwnerCell({ ownerId, meId }: { ownerId: string | null | undefined; meId: string | undefined }) {
  const t = useT();
  if (!ownerId) return <span className="muted">{t("records.owner.none")}</span>;
  return (
    <span className="owner-cell">
      <span className="owner-dot" aria-hidden="true">
        {ownerId === meId ? t("records.owner.meShort") : ownerId.slice(0, 2).toUpperCase()}
      </span>
      <span className="owner-name">{ownerLabel(t, ownerId, meId)}</span>
    </span>
  );
}

/** A date in the user's locale; the full date and time on hover. */
export function When({ value }: { value: string }) {
  const intl = useIntl();
  const date = new Date(value);
  return (
    <time dateTime={value} title={intl.formatDate(date, { dateStyle: "full", timeStyle: "short" })}>
      {intl.formatDate(date, { day: "numeric", month: "short", year: "numeric" })}
    </time>
  );
}

export interface Option {
  id: string;
  label: string;
}

/**
 * The design's dashed filter button with a checkbox menu (ScreenContacts.dc.html
 * L32-58). The label shows the selection: "Stage: Lead" or "Stage: 2 selected".
 */
export function FilterMenu({
  label,
  icon,
  options,
  selected,
  onChange,
}: {
  label: string;
  icon: ReactNode;
  options: Option[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const t = useT();
  const active = selected.length > 0;
  const first = options.find((o) => o.id === selected[0]);
  const summary = !active
    ? label
    : selected.length === 1 && first
      ? `${label}: ${first.label}`
      : t("records.filter.many", { label, count: selected.length });
  return (
    <MenuTrigger>
      <AriaButton className={active ? "filter-button active" : "filter-button"}>
        {icon}
        <span>{summary}</span>
        <ChevronDown size={13} aria-hidden="true" className="filter-chevron" />
      </AriaButton>
      <Popover className="menu-popover filter-popover" placement="bottom start" offset={4}>
        <Menu
          aria-label={label}
          className="menu"
          selectionMode="multiple"
          selectedKeys={new Set(selected)}
          onSelectionChange={(keys) => {
            onChange(keys === "all" ? options.map((o) => o.id) : [...keys].map(String));
          }}
        >
          {options.map((option) => (
            <MenuItem key={option.id} id={option.id} className="menu-item filter-item" textValue={option.label}>
              {({ isSelected }) => (
                <>
                  <span className={isSelected ? "check-box checked" : "check-box"} aria-hidden="true">
                    {isSelected ? <Check size={11} /> : null}
                  </span>
                  <span>{option.label}</span>
                </>
              )}
            </MenuItem>
          ))}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}

/** Owner choices for filters and forms: the caller first, then active members by ID. */
export function ownerOptions(t: T, members: Member[], meId: string | undefined): Option[] {
  const active = members.filter((m) => m.status === "active");
  const ordered = [...active.filter((m) => m.user_id === meId), ...active.filter((m) => m.user_id !== meId)];
  return ordered.map((m) => ({ id: m.user_id, label: ownerLabel(t, m.user_id, meId) }));
}

/**
 * The design's right-hand preview drawer (440 px with a scrim). React Aria
 * traps focus, closes on Escape and on the scrim, and returns focus to the
 * control that opened it.
 */
export function Drawer({
  title,
  onClose,
  headerActions,
  children,
}: {
  title: string;
  onClose: () => void;
  headerActions?: ReactNode;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <ModalOverlay
      className="drawer-overlay"
      isOpen
      isDismissable
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal className="drawer">
        <AriaDialog className="drawer-dialog">
          <div className="drawer-head">
            <Heading slot="title" className="drawer-title">
              {title}
            </Heading>
            {headerActions}
            <AriaButton className="icon-button" aria-label={t("records.close")} onPress={onClose}>
              <X size={16} aria-hidden="true" />
            </AriaButton>
          </div>
          <div className="drawer-body">{children}</div>
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}

/** One label/value row of the drawer's field list (`100px 1fr`). */
export function FieldRow({ label, children }: { label: string; children?: ReactNode }) {
  return (
    <div className="field-row">
      <dt>{label}</dt>
      <dd>{children ?? "—"}</dd>
    </div>
  );
}

/** The table header's sort control (ScreenContacts.dc.html L69-75): the active column shows its direction. */
export function SortHeader({
  label,
  active,
  direction,
  onSort,
}: {
  label: string;
  active: boolean;
  direction: "asc" | "desc";
  onSort: () => void;
}) {
  return (
    <AriaButton className={active ? "sort-button active" : "sort-button"} onPress={onSort}>
      {label}
      {active ? <span aria-hidden="true">{direction === "asc" ? " ↑" : " ↓"}</span> : null}
    </AriaButton>
  );
}

/**
 * The header's Export button (slices 3E1, 3E2): enabled for those `/access`
 * allows, otherwise disabled with the reason in its name. The server decides.
 */
export function ExportButton({
  kind,
  allowed,
  running,
  onExport,
}: {
  kind: ExportKind;
  allowed: boolean;
  running: boolean;
  onExport: () => void;
}) {
  const t = useT();
  if (!allowed) {
    return (
      <Button isDisabled aria-label={`${t("records.export")} (${t(exportMessage(kind, "notAllowed"))})`}>
        <Download size={14} aria-hidden="true" />
        {t("records.export")}
      </Button>
    );
  }
  return (
    <Button onPress={onExport} isDisabled={running}>
      {running ? <span className="spinner" aria-hidden="true" /> : <Download size={14} aria-hidden="true" />}
      {running ? t(exportMessage(kind, "running")) : t("records.export")}
    </Button>
  );
}

/** The export's failure (an alert) and its progress (a status message). */
export function ExportNotices({
  kind,
  running,
  error,
}: {
  kind: ExportKind;
  running: boolean;
  error: string | null;
}) {
  const t = useT();
  return (
    <>
      {error ? (
        <p className="notice error records-notice" role="alert">
          {error}
        </p>
      ) : null}
      <p className="sr-only" role="status">
        {running ? t(exportMessage(kind, "running")) : ""}
      </p>
    </>
  );
}
