import { CircleDot, Pencil, Plus, Search, Tag, User } from "lucide-react";
import { useMemo, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { ApiError } from "../api/client";
import { activeFields, useFieldDefinitions } from "../api/customFields";
import { useAccess, useMe, useMembers } from "../api/queries";
import { useTags } from "../api/tags";
import {
  type Contact,
  type Direction,
  type ListFilters,
  NO_FILTERS,
  type Sort,
  STAGES,
  type Stage,
  useContact,
  useContactList,
  useLifecycle,
} from "../api/records";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { ContactDialog, sourceLabel } from "./ContactDialog";
import { CustomFieldsSection } from "./CustomFields";
import { ImportButton, ImportDialog } from "./ImportDialog";
import { AppointmentsSection } from "./AppointmentsSection";
import { ConsentSection } from "./ConsentSection";
import { TasksSection } from "./TasksSection";
import { ActivitySection, NotesSection } from "./NotesSection";
import { ListTags, TagSection } from "./TagEditor";
import {
  Avatar,
  Drawer,
  ExportButton,
  ExportNotices,
  FieldRow,
  FilterMenu,
  initials,
  OwnerCell,
  ownerLabel,
  ownerOptions,
  SortHeader,
  StagePill,
  stageLabel,
  When,
} from "./parts";
import { useRecordExport } from "./useRecordExport";
import { useDebounced } from "./useDebounced";

/*
 * Contacts (ScreenContacts.dc.html L12-97 list, L194-222 drawer, L224-247
 * dialog), backed by the slice 3A API. Differences from the design are
 * recorded in DESIGN-FIDELITY.md §4c: no score, tags, saved views, bulk
 * actions, columns picker or quick actions (not built), "Assigned to me"
 * instead of a named person, an Archived view, and "Load more" instead of
 * page numbers (the API pages by cursor).
 */

type View = "all" | "mine" | "leads" | "archived";
const VIEWS: View[] = ["all", "mine", "leads", "archived"];

const VIEW_LABEL: Record<View, MessageId> = {
  all: "contacts.view.all",
  mine: "contacts.view.mine",
  leads: "contacts.view.leads",
  archived: "contacts.view.archived",
};

const DONE: Record<"archive" | "restore" | "delete", MessageId> = {
  archive: "records.done.archive",
  restore: "records.done.restore",
  delete: "records.done.delete",
};

const fullName = (c: Pick<Contact, "first_name" | "last_name">) =>
  [c.first_name, c.last_name].filter(Boolean).join(" ");

export function ContactsPage({
  workspaceId,
  openId,
  onOpen,
  startCreate = false,
  onCreateDone = () => undefined,
  onOpenAppointment = () => undefined,
}: {
  workspaceId: string;
  /** The contact whose preview is open (`?record=` in the URL). */
  openId: string | null;
  onOpen: (id: string | null) => void;
  /** Open the new-contact dialog (`?create=contact`), if the caller may create. */
  startCreate?: boolean;
  /** Called when that dialog closes without saving, to clear the request. */
  onCreateDone?: () => void;
  /** Opens an appointment on the Calendar (decision P5-A). */
  onOpenAppointment?: (id: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const meId = me.data?.user_id;
  const [view, setView] = useState<View>("all");
  const [search, setSearch] = useState("");
  const [stages, setStages] = useState<Stage[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const tags = useTags(workspaceId);
  const [owners, setOwners] = useState<string[]>([]);
  const [sort, setSort] = useState<Sort>("name");
  const [direction, setDirection] = useState<Direction>("asc");
  const [dialog, setDialog] = useState<{ contact: Contact | null } | null>(null);
  const q = useDebounced(search);
  const can = (action: string) => access.data?.actions[action] === true;
  const exporting = useRecordExport("contacts", workspaceId);
  // "New → Contact" in the header opens the dialog through the URL; a
  // caller who may not create contacts just sees the list.
  const activeDialog =
    dialog ?? (startCreate && can("create_contact") ? { contact: null } : null);

  const filters: ListFilters = useMemo(
    () => ({
      ...NO_FILTERS,
      q,
      sort,
      direction,
      archived: view === "archived" ? "true" : "false",
      owners: view === "mine" && meId ? [meId] : owners,
      stages: view === "leads" ? ["lead"] : stages,
      tagIds,
    }),
    [q, sort, direction, view, meId, owners, stages, tagIds],
  );
  const list = useContactList(workspaceId, filters, view !== "mine" || meId !== undefined);
  const items = (list.data?.pages ?? []).flatMap((page) => page.items);
  const first = list.data?.pages[0];
  const filtered = search !== "" || stages.length > 0 || owners.length > 0 || tagIds.length > 0;

  function toggleSort(next: Sort) {
    if (next === sort) {
      setDirection(direction === "asc" ? "desc" : "asc");
    } else {
      setSort(next);
      setDirection(next === "name" ? "asc" : "desc");
    }
  }

  function clear() {
    setSearch("");
    setStages([]);
    setOwners([]);
    setTagIds([]);
  }

  const total = first ? (first.total_capped ? t("records.capped") : String(first.total)) : "";

  return (
    <div className="records-page contacts-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.crm")}</p>
          <h1 className="records-title">
            {t("nav.contacts")}
            {first && view === "all" && !filtered ? <span className="records-count">{total}</span> : null}
          </h1>
        </div>
        <div className="records-actions">
          <ImportButton allowed={can("import_records")} onPress={() => { setImporting(true); }} />
          <ExportButton
            kind="contacts"
            allowed={can("export_records")}
            running={exporting.running}
            onExport={() => void exporting.run(filters)}
          />
          {can("create_contact") ? (
            <Button variant="primary" onPress={() => { setDialog({ contact: null }); }}>
              <Plus size={15} aria-hidden="true" />
              {t("contact.new")}
            </Button>
          ) : null}
        </div>
      </div>

      <ExportNotices kind="contacts" running={exporting.running} error={exporting.error} />

      <div className="view-tabs" role="group" aria-label={t("records.views")}>
        {VIEWS.map((v) => (
          <AriaButton
            key={v}
            aria-pressed={view === v}
            className={view === v ? "view-tab active" : "view-tab"}
            onPress={() => { setView(v); }}
          >
            {t(VIEW_LABEL[v])}
          </AriaButton>
        ))}
      </div>

      <div className="records-toolbar">
        <label className="search-box">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">{t("contacts.search")}</span>
          <input
            type="search"
            value={search}
            placeholder={t("contacts.search")}
            onChange={(event) => { setSearch(event.target.value); }}
            maxLength={100}
          />
        </label>
        {view === "leads" ? null : (
          <FilterMenu
            label={t("contact.field.stage")}
            icon={<CircleDot size={14} aria-hidden="true" />}
            options={STAGES.map((stage) => ({ id: stage, label: stageLabel(t, stage) }))}
            selected={stages}
            onChange={(next) => { setStages(next as Stage[]); }}
          />
        )}
        {view === "mine" ? null : (
          <FilterMenu
            label={t("records.field.owner")}
            icon={<User size={14} aria-hidden="true" />}
            options={ownerOptions(t, members.data?.items ?? [], meId)}
            selected={owners}
            onChange={setOwners}
          />
        )}
        {tags.data?.items.length ? (
          <FilterMenu
            label={t("tags.label")}
            icon={<Tag size={14} aria-hidden="true" />}
            options={tags.data.items.map((tag) => ({ id: tag.id, label: tag.name }))}
            selected={tagIds}
            onChange={setTagIds}
          />
        ) : null}
        {filtered ? (
          <AriaButton className="text-button" onPress={clear}>
            {t("records.clear")}
          </AriaButton>
        ) : null}
        <span className="records-meta">
          {first ? t("records.shown", { shown: items.length, total }) : null}
        </span>
      </div>

      <div className="records-card">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <LoadError error={list.error} onRetry={() => void list.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            title={filtered ? t("contacts.empty.filtered") : view === "archived" ? t("contacts.empty.archived") : t("contacts.empty.none")}
            {...(filtered
              ? { body: t("contacts.empty.filteredBody") }
              : view === "all"
                ? { body: t("contacts.empty.noneBody") }
                : {})}
          />
        ) : (
          <div className="table-scroll">
            <table className="records-table">
              <caption className="sr-only">{t("nav.contacts")}</caption>
              <thead>
                <tr>
                  <th scope="col" aria-sort={sort === "name" ? (direction === "asc" ? "ascending" : "descending") : undefined}>
                    <SortHeader label={t("records.col.name")} active={sort === "name"} direction={direction} onSort={() => { toggleSort("name"); }} />
                  </th>
                  <th scope="col">{t("contact.field.stage")}</th>
                  <th scope="col">{t("records.field.owner")}</th>
                  <th scope="col" className="hide-narrow">{t("tags.label")}</th>
                  <th scope="col" className="hide-narrow">{t("contact.field.company")}</th>
                  <th scope="col" className="hide-narrow">{t("contact.field.source")}</th>
                  <th scope="col" aria-sort={sort === "updated_at" ? (direction === "asc" ? "ascending" : "descending") : undefined}>
                    <SortHeader label={t("records.col.updated")} active={sort === "updated_at"} direction={direction} onSort={() => { toggleSort("updated_at"); }} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((contact) => (
                  // Row clicks mirror the name button, which is the keyboard path.
                   
                  <tr
                    key={contact.id}
                    className={contact.id === openId ? "selected" : undefined}
                    onClick={() => { onOpen(contact.id); }}
                  >
                    <td>
                      <span className="name-cell">
                        <Avatar id={contact.id} label={initials(contact.first_name, contact.last_name)} />
                        <span className="name-text">
                          <AriaButton className="record-link" onPress={() => { onOpen(contact.id); }}>
                            {fullName(contact)}
                          </AriaButton>
                          <span className="name-sub">{contact.email ?? contact.phone}</span>
                        </span>
                      </span>
                    </td>
                    <td>
                      <StagePill stage={contact.lifecycle_stage} />
                    </td>
                    <td>
                      <OwnerCell ownerId={contact.owner_user_id} meId={meId} />
                    </td>
                    <td className="hide-narrow">
                      <ListTags tags={contact.tags} />
                    </td>
                    <td className="hide-narrow">{contact.company?.name ?? <span className="muted">—</span>}</td>
                    <td className="hide-narrow secondary">{sourceLabel(t, contact.source)}</td>
                    <td className="secondary">
                      <When value={contact.updated_at} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.hasNextPage ? (
          <div className="records-footer">
            <Button size="sm" onPress={() => void list.fetchNextPage()} isDisabled={list.isFetchingNextPage}>
              {t("records.loadMore")}
            </Button>
          </div>
        ) : null}
      </div>

      {importing ? (
        <ImportDialog workspaceId={workspaceId} entity="contact" onClose={() => { setImporting(false); }} />
      ) : null}
      {openId ? (
        <ContactDrawer
          workspaceId={workspaceId}
          id={openId}
          meId={meId}
          canUpdate={can("update_contact")}
          canDelete={can("delete_contact")}
          canAddNote={can("create_note")}
          canCreateTags={can("update_workspace")}
          onClose={() => { onOpen(null); }}
          onEdit={(contact) => { setDialog({ contact }); }}
          onOpenAppointment={onOpenAppointment}
        />
      ) : null}
      {activeDialog ? (
        <ContactDialog
          workspaceId={workspaceId}
          contact={activeDialog.contact}
          onClose={() => {
            setDialog(null);
            if (startCreate) onCreateDone();
          }}
          onSaved={(saved) => {
            setDialog(null);
            onOpen(saved.id);
          }}
          onOpenExisting={(id) => {
            setDialog(null);
            onOpen(id);
          }}
        />
      ) : null}
    </div>
  );
}

function ContactDrawer({
  workspaceId,
  id,
  meId,
  canUpdate,
  canDelete,
  canAddNote,
  canCreateTags,
  onClose,
  onEdit,
  onOpenAppointment,
}: {
  workspaceId: string;
  id: string;
  meId: string | undefined;
  canUpdate: boolean;
  canDelete: boolean;
  canAddNote: boolean;
  canCreateTags: boolean;
  onClose: () => void;
  onEdit: (contact: Contact) => void;
  onOpenAppointment: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const contact = useContact(workspaceId, id);
  const definitions = useFieldDefinitions(workspaceId);
  const lifecycle = useLifecycle(workspaceId, "contacts");
  const [confirmDelete, setConfirmDelete] = useState(false);
  // An unsaved note: closing asks first (PHASE3-PLAN.md §21).
  const [draftOpen, setDraftOpen] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const close = () => {
    if (draftOpen) setConfirmDiscard(true);
    else onClose();
  };
  const [refusal, setRefusal] = useState<string | null>(null);
  const record = contact.data;

  function run(action: "archive" | "restore" | "delete") {
    setRefusal(null);
    lifecycle.mutate(
      { id, action },
      {
        onSuccess: () => {
          toast(t(DONE[action]));
          if (action === "delete") onClose();
        },
        onError: (error) => {
          setRefusal(
            error instanceof ApiError && error.code === "duplicate_email"
              ? t("contact.error.restoreDuplicate")
              : t("records.error.generic"),
          );
        },
      },
    );
  }

  return (
    <Drawer
      title={t("contact.preview")}
      onClose={close}
      headerActions={
        record && canUpdate ? (
          <Button size="sm" onPress={() => { onEdit(record); }}>
            <Pencil size={13} aria-hidden="true" />
            {t("records.edit")}
          </Button>
        ) : null
      }
    >
      {contact.isPending ? (
        <Loading />
      ) : contact.isError || !record ? (
        <LoadError error={contact.error} onRetry={() => void contact.refetch()} notFound={t("contact.notFound")} />
      ) : (
        <>
          <div className="drawer-identity">
            <Avatar id={record.id} label={initials(record.first_name, record.last_name)} large />
            <div>
              <p className="drawer-name">{fullName(record)}</p>
              <p className="drawer-headline">
                {[record.job_title, record.company?.name].filter(Boolean).join(t("records.at")) || record.city || ""}
              </p>
            </div>
          </div>
          {record.archived_at ? <p className="notice info">{t("records.archivedNote")}</p> : null}
          <dl className="field-list">
            <FieldRow label={t("contact.field.email")}>{record.email}</FieldRow>
            <FieldRow label={t("contact.field.phone")}>{record.phone}</FieldRow>
            <FieldRow label={t("contact.field.company")}>
              {record.company
                ? record.company.archived
                  ? `${record.company.name} (${t("records.archived")})`
                  : record.company.name
                : null}
            </FieldRow>
            <FieldRow label={t("contact.field.jobTitle")}>{record.job_title}</FieldRow>
            <FieldRow label={t("contact.field.city")}>{record.city}</FieldRow>
            <FieldRow label={t("contact.field.stage")}>
              <StagePill stage={record.lifecycle_stage} />
            </FieldRow>
            <FieldRow label={t("contact.field.source")}>{sourceLabel(t, record.source)}</FieldRow>
            <FieldRow label={t("records.field.owner")}>{ownerLabel(t, record.owner_user_id, meId)}</FieldRow>
            <FieldRow label={t("records.field.created")}>
              <When value={record.created_at} />
            </FieldRow>
            <FieldRow label={t("records.col.updated")}>
              <When value={record.updated_at} />
            </FieldRow>
          </dl>
          {refusal ? (
            <p className="notice error" role="alert">
              {refusal}
            </p>
          ) : null}
          {canUpdate || canDelete ? (
            <div className="drawer-actions">
              {canUpdate ? (
                <Button
                  size="sm"
                  isDisabled={lifecycle.isPending}
                  onPress={() => { run(record.archived_at ? "restore" : "archive"); }}
                >
                  {record.archived_at ? t("records.restore") : t("records.archive")}
                </Button>
              ) : null}
              {canDelete ? (
                <Button size="sm" variant="destructive" isDisabled={lifecycle.isPending} onPress={() => { setConfirmDelete(true); }}>
                  {t("records.delete")}
                </Button>
              ) : null}
            </div>
          ) : null}
          <TasksSection workspaceId={workspaceId} link={{ kind: "contact", id: record.id }} />
          <AppointmentsSection
            workspaceId={workspaceId}
            contact={{ id: record.id, name: fullName(record) }}
            onOpen={onOpenAppointment}
          />
          <ConsentSection workspaceId={workspaceId} contactId={record.id} />
          <CustomFieldsSection
            workspaceId={workspaceId}
            fields={activeFields(definitions.data?.items, "contact")}
            values={record.custom_fields}
            canManage={canCreateTags}
          />
          <TagSection
            workspaceId={workspaceId}
            kind="contacts"
            record={record}
            canEdit={canUpdate}
            canCreate={canCreateTags}
          />
          <NotesSection
            workspaceId={workspaceId}
            kind="contacts"
            id={id}
            meId={meId}
            canAdd={canAddNote}
            onDirtyChange={setDraftOpen}
          />
          <ActivitySection workspaceId={workspaceId} kind="contacts" id={id} meId={meId} />
          <p className="drawer-note">{t("contact.notBuilt")}</p>
          <ConfirmDialog
            isOpen={confirmDiscard}
            title={t("notes.discardTitle")}
            confirmLabel={t("notes.discard")}
            message={t("notes.discardConfirm")}
            onCancel={() => { setConfirmDiscard(false); }}
            onConfirm={() => {
              setConfirmDiscard(false);
              onClose();
            }}
          />
          <ConfirmDialog
            isOpen={confirmDelete}
            title={t("contact.deleteTitle")}
            confirmLabel={t("records.deleteSubmit")}
            message={t("contact.deleteConfirm", { name: fullName(record) })}
            onCancel={() => { setConfirmDelete(false); }}
            onConfirm={() => {
              setConfirmDelete(false);
              run("delete");
            }}
          />
        </>
      )}
    </Drawer>
  );
}
