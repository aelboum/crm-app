import { ArrowUpRight, Pencil, Plus, Search, Tag, User } from "lucide-react";
import { type SyntheticEvent, useMemo, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { ApiError } from "../api/client";
import { activeFields, useFieldDefinitions } from "../api/customFields";
import { useAccess, useMe, useMembers } from "../api/queries";
import { useTags } from "../api/tags";
import {
  type Company,
  type CompanyCreate,
  type CompanyUpdate,
  CustomFieldError,
  type Direction,
  DuplicateError,
  FieldErrors,
  type ListFilters,
  NO_FILTERS,
  newIdempotencyKey,
  type Sort,
  useCompany,
  useCompanyList,
  useContactList,
  useCreateCompany,
  useLifecycle,
  useUpdateCompany,
} from "../api/records";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
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
  When,
} from "./parts";
import {
  changedValues,
  createValues,
  type CustomDraft,
  CustomFieldInputs,
  CustomFieldsSection,
  draftOf,
  draftProblems,
} from "./CustomFields";
import { ImportButton, ImportDialog } from "./ImportDialog";
import { ActivitySection, NotesSection } from "./NotesSection";
import { TasksSection } from "./TasksSection";
import { ListTags, TagSection } from "./TagEditor";
import { useDebounced } from "./useDebounced";
import { useRecordExport } from "./useRecordExport";

/*
 * Companies (ScreenCompanies.dc.html): header, search, table, drawer with
 * the company's people, and the create dialog, here also used for editing.
 * Differences (DESIGN-FIDELITY.md §4c): no industry chips (industry is free
 * text in slice 3A and the API has no industry filter), no contact count or
 * pipeline columns (not built), an Active/Archived switch so archived
 * companies can be restored, and "Load more" paging.
 */

type View = "active" | "archived";

const VIEW_LABEL: Record<View, MessageId> = {
  active: "companies.view.active",
  archived: "companies.view.archived",
};

const DONE: Record<"archive" | "restore" | "delete", MessageId> = {
  archive: "records.done.archive",
  restore: "records.done.restore",
  delete: "records.done.delete",
};

export function CompaniesPage({
  workspaceId,
  openId,
  onOpen,
  onOpenContact,
}: {
  workspaceId: string;
  openId: string | null;
  onOpen: (id: string | null) => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const meId = me.data?.user_id;
  const [view, setView] = useState<View>("active");
  const [search, setSearch] = useState("");
  const [owners, setOwners] = useState<string[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const tags = useTags(workspaceId);
  const [sort, setSort] = useState<Sort>("name");
  const [direction, setDirection] = useState<Direction>("asc");
  const [dialog, setDialog] = useState<{ company: Company | null } | null>(null);
  const q = useDebounced(search);
  const can = (action: string) => access.data?.actions[action] === true;
  const exporting = useRecordExport("companies", workspaceId);

  const filters: ListFilters = useMemo(
    () => ({ ...NO_FILTERS, q, sort, direction, owners, tagIds, archived: view === "archived" ? "true" : "false" }),
    [q, sort, direction, owners, tagIds, view],
  );
  const list = useCompanyList(workspaceId, filters);
  const items = (list.data?.pages ?? []).flatMap((page) => page.items);
  const first = list.data?.pages[0];
  const filtered = search !== "" || owners.length > 0 || tagIds.length > 0;
  const total = first ? (first.total_capped ? t("records.capped") : String(first.total)) : "";

  function toggleSort(next: Sort) {
    if (next === sort) {
      setDirection(direction === "asc" ? "desc" : "asc");
    } else {
      setSort(next);
      setDirection(next === "name" ? "asc" : "desc");
    }
  }

  const ariaSort = (column: Sort) =>
    sort === column ? (direction === "asc" ? "ascending" : "descending") : undefined;

  return (
    <div className="records-page companies-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.crm")}</p>
          <h1 className="records-title">
            {t("nav.companies")}
            {first && view === "active" && !filtered ? <span className="records-count">{total}</span> : null}
          </h1>
        </div>
        <div className="records-actions">
          <ImportButton allowed={can("import_records")} onPress={() => { setImporting(true); }} />
          <ExportButton
            kind="companies"
            allowed={can("export_records")}
            running={exporting.running}
            onExport={() => void exporting.run(filters)}
          />
          {can("create_company") ? (
            <Button variant="primary" onPress={() => { setDialog({ company: null }); }}>
              <Plus size={15} aria-hidden="true" />
              {t("company.new")}
            </Button>
          ) : null}
        </div>
      </div>

      <ExportNotices kind="companies" running={exporting.running} error={exporting.error} />

      <div className="records-toolbar">
        <label className="search-box">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">{t("companies.search")}</span>
          <input
            type="search"
            value={search}
            placeholder={t("companies.search")}
            onChange={(event) => { setSearch(event.target.value); }}
            maxLength={100}
          />
        </label>
        <FilterMenu
          label={t("records.field.owner")}
          icon={<User size={14} aria-hidden="true" />}
          options={ownerOptions(t, members.data?.items ?? [], meId)}
          selected={owners}
          onChange={setOwners}
        />
        {tags.data?.items.length ? (
          <FilterMenu
            label={t("tags.label")}
            icon={<Tag size={14} aria-hidden="true" />}
            options={tags.data.items.map((tag) => ({ id: tag.id, label: tag.name }))}
            selected={tagIds}
            onChange={setTagIds}
          />
        ) : null}
        <div className="chip-group" role="group" aria-label={t("records.views")}>
          {(["active", "archived"] as const).map((v) => (
            <AriaButton
              key={v}
              className={view === v ? "chip active" : "chip"}
              aria-pressed={view === v}
              onPress={() => { setView(v); }}
            >
              {t(VIEW_LABEL[v])}
            </AriaButton>
          ))}
        </div>
        {filtered ? (
          <AriaButton
            className="text-button"
            onPress={() => {
              setSearch("");
              setOwners([]);
              setTagIds([]);
            }}
          >
            {t("records.clear")}
          </AriaButton>
        ) : null}
        <span className="records-meta">{first ? t("records.shown", { shown: items.length, total }) : null}</span>
      </div>

      <div className="records-card">
        {list.isPending ? (
          <Loading />
        ) : list.isError ? (
          <LoadError error={list.error} onRetry={() => void list.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            title={
              filtered
                ? t("companies.empty.filtered")
                : view === "archived"
                  ? t("companies.empty.archived")
                  : t("companies.empty.none")
            }
            {...(!filtered && view !== "archived" ? { body: t("companies.empty.noneBody") } : {})}
          />
        ) : (
          <div className="table-scroll">
            <table className="records-table">
              <caption className="sr-only">{t("nav.companies")}</caption>
              <thead>
                <tr>
                  <th scope="col" aria-sort={ariaSort("name")}>
                    <SortHeader
                      label={t("company.col.company")}
                      active={sort === "name"}
                      direction={direction}
                      onSort={() => { toggleSort("name"); }}
                    />
                  </th>
                  <th scope="col">{t("company.field.industry")}</th>
                  <th scope="col">{t("records.field.owner")}</th>
                  <th scope="col" className="hide-narrow">
                    {t("tags.label")}
                  </th>
                  <th scope="col" className="hide-narrow">
                    {t("company.field.city")}
                  </th>
                  <th scope="col" aria-sort={ariaSort("updated_at")}>
                    <SortHeader
                      label={t("records.col.updated")}
                      active={sort === "updated_at"}
                      direction={direction}
                      onSort={() => { toggleSort("updated_at"); }}
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((company) => (
                  // Row clicks mirror the name button, which is the keyboard path.
                   
                  <tr
                    key={company.id}
                    className={company.id === openId ? "selected" : undefined}
                    onClick={() => { onOpen(company.id); }}
                  >
                    <td>
                      <span className="name-cell">
                        <Avatar id={company.id} label={initials(company.name)} square />
                        <span className="name-text">
                          <AriaButton className="record-link" onPress={() => { onOpen(company.id); }}>
                            {company.name}
                          </AriaButton>
                          <span className="name-sub">{company.domain ?? company.website ?? ""}</span>
                        </span>
                      </span>
                    </td>
                    <td className="secondary">{company.industry ?? <span className="muted">—</span>}</td>
                    <td>
                      <OwnerCell ownerId={company.owner_user_id} meId={meId} />
                    </td>
                    <td className="hide-narrow">
                      <ListTags tags={company.tags} />
                    </td>
                    <td className="hide-narrow muted">{company.city ?? "—"}</td>
                    <td className="secondary">
                      <When value={company.updated_at} />
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
        <ImportDialog workspaceId={workspaceId} entity="company" onClose={() => { setImporting(false); }} />
      ) : null}
      {openId ? (
        <CompanyDrawer
          workspaceId={workspaceId}
          id={openId}
          meId={meId}
          canUpdate={can("update_company")}
          canDelete={can("delete_company")}
          canAddNote={can("create_note")}
          canCreateTags={can("update_workspace")}
          onClose={() => { onOpen(null); }}
          onEdit={(company) => { setDialog({ company }); }}
          onOpenContact={onOpenContact}
        />
      ) : null}
      {dialog ? (
        <CompanyDialog
          workspaceId={workspaceId}
          company={dialog.company}
          onClose={() => { setDialog(null); }}
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

function CompanyDrawer({
  workspaceId,
  id,
  meId,
  canUpdate,
  canDelete,
  canAddNote,
  canCreateTags,
  onClose,
  onEdit,
  onOpenContact,
}: {
  workspaceId: string;
  id: string;
  meId: string | undefined;
  canUpdate: boolean;
  canDelete: boolean;
  canAddNote: boolean;
  canCreateTags: boolean;
  onClose: () => void;
  onEdit: (company: Company) => void;
  onOpenContact: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const company = useCompany(workspaceId, id);
  const definitions = useFieldDefinitions(workspaceId);
  const people = useContactList(workspaceId, { ...NO_FILTERS, companyIds: [id] });
  const lifecycle = useLifecycle(workspaceId, "companies");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  // An unsaved note: closing asks first (PHASE3-PLAN.md §21).
  const [draftOpen, setDraftOpen] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const close = () => {
    if (draftOpen) setConfirmDiscard(true);
    else onClose();
  };
  const record = company.data;
  const contacts = (people.data?.pages ?? []).flatMap((page) => page.items);

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
            error instanceof ApiError && error.code === "duplicate_domain"
              ? t("company.error.restoreDuplicate")
              : t("records.error.generic"),
          );
        },
      },
    );
  }

  return (
    <Drawer
      title={t("company.preview")}
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
      {company.isPending ? (
        <Loading />
      ) : company.isError || !record ? (
        <LoadError error={company.error} onRetry={() => void company.refetch()} notFound={t("company.notFound")} />
      ) : (
        <>
          <div className="drawer-identity">
            <Avatar id={record.id} label={initials(record.name)} square large />
            <div>
              <p className="drawer-name">{record.name}</p>
              <p className="drawer-headline">
                {[record.industry, record.city, record.domain ?? record.website].filter(Boolean).join(" · ")}
              </p>
            </div>
          </div>
          {record.archived_at ? <p className="notice info">{t("records.archivedNote")}</p> : null}
          <dl className="field-list">
            <FieldRow label={t("company.field.domain")}>{record.domain}</FieldRow>
            <FieldRow label={t("company.field.website")}>{record.website}</FieldRow>
            <FieldRow label={t("company.field.phone")}>{record.phone}</FieldRow>
            <FieldRow label={t("company.field.industry")}>{record.industry}</FieldRow>
            <FieldRow label={t("company.field.city")}>{record.city}</FieldRow>
            <FieldRow label={t("company.field.country")}>{record.country_code}</FieldRow>
            <FieldRow label={t("records.field.owner")}>{ownerLabel(t, record.owner_user_id, meId)}</FieldRow>
            <FieldRow label={t("records.field.created")}>
              <When value={record.created_at} />
            </FieldRow>
          </dl>
          <TasksSection workspaceId={workspaceId} link={{ kind: "company", id: record.id }} />
          <CustomFieldsSection
            workspaceId={workspaceId}
            fields={activeFields(definitions.data?.items, "company")}
            values={record.custom_fields}
            canManage={canCreateTags}
          />
          <TagSection
            workspaceId={workspaceId}
            kind="companies"
            record={record}
            canEdit={canUpdate}
            canCreate={canCreateTags}
          />
          <section className="drawer-section" aria-labelledby="company-people">
            <h2 id="company-people" className="drawer-section-title">
              {t("company.people")}
            </h2>
            {people.isPending ? (
              <Loading />
            ) : people.isError && !people.data ? (
              <LoadError error={people.error} onRetry={() => void people.refetch()} />
            ) : contacts.length === 0 ? (
              <p className="muted">{t("company.noPeople")}</p>
            ) : (
              <ul className="people-list">
                {contacts.map((person) => (
                  <li key={person.id}>
                    <AriaButton className="person-card" onPress={() => { onOpenContact(person.id); }}>
                      <Avatar id={person.id} label={initials(person.first_name, person.last_name)} />
                      <span className="person-text">
                        <span className="person-name">
                          {[person.first_name, person.last_name].filter(Boolean).join(" ")}
                        </span>
                        <span className="person-sub">{person.job_title ?? ""}</span>
                      </span>
                      <StagePill stage={person.lifecycle_stage} />
                      <ArrowUpRight size={14} aria-hidden="true" />
                    </AriaButton>
                  </li>
                ))}
              </ul>
            )}
            {people.isFetchNextPageError ? (
              <div className="notice error row" role="alert">
                <p>{t("company.morePeopleFailed")}</p>
                <Button size="sm" onPress={() => void people.fetchNextPage()}>
                  {t("state.retry")}
                </Button>
              </div>
            ) : people.hasNextPage ? (
              <div className="people-more">
                <Button size="sm" onPress={() => void people.fetchNextPage()} isDisabled={people.isFetchingNextPage}>
                  {people.isFetchingNextPage ? t("state.loading") : t("company.loadMorePeople")}
                </Button>
              </div>
            ) : (people.data?.pages.length ?? 0) > 1 ? (
              <p className="muted" role="status">
                {t("company.allPeople", { count: contacts.length })}
              </p>
            ) : null}
          </section>
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
                <Button
                  size="sm"
                  variant="destructive"
                  isDisabled={lifecycle.isPending}
                  onPress={() => { setConfirmDelete(true); }}
                >
                  {t("records.delete")}
                </Button>
              ) : null}
            </div>
          ) : null}
          <NotesSection
            workspaceId={workspaceId}
            kind="companies"
            id={id}
            meId={meId}
            canAdd={canAddNote}
            onDirtyChange={setDraftOpen}
          />
          <ActivitySection workspaceId={workspaceId} kind="companies" id={id} meId={meId} />
          <p className="drawer-note">{t("company.notBuilt")}</p>
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
            title={t("company.deleteTitle")}
            confirmLabel={t("records.deleteSubmit")}
            message={t("company.deleteConfirm", { name: record.name })}
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

type Field = "name" | "domain" | "website" | "phone" | "industry" | "city" | "country_code" | "owner_user_id";
const FIELDS: Field[] = ["name", "domain", "website", "phone", "industry", "city", "country_code", "owner_user_id"];
type Values = Record<Field, string>;

const valuesOf = (company: Company | null): Values => ({
  name: company?.name ?? "",
  domain: company?.domain ?? "",
  website: company?.website ?? "",
  phone: company?.phone ?? "",
  industry: company?.industry ?? "",
  city: company?.city ?? "",
  country_code: company?.country_code ?? "",
  owner_user_id: company?.owner_user_id ?? "",
});

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

function refusalMessage(error: ApiError): MessageId {
  switch (error.code) {
    case "duplicate_domain":
      return "company.error.duplicate";
    case "stale_version":
      return "records.error.stale";
    case "owner_not_member":
      return "records.error.owner";
    case "conflict":
      return "records.error.conflict";
    case "invalid_custom_field":
      return "fields.error.value";
    case "unknown_custom_field":
    case "custom_fields_too_large":
      return "fields.error.record";
    default:
      return error.status === 403 ? "records.error.denied" : "records.error.generic";
  }
}

const LABEL: Record<Field, MessageId> = {
  name: "company.field.name",
  domain: "company.field.domain",
  website: "company.field.website",
  phone: "company.field.phone",
  industry: "company.field.industry",
  city: "company.field.city",
  country_code: "company.field.country",
  owner_user_id: "records.field.owner",
};

/** New and edit company (ScreenCompanies.dc.html dialog, 500 px). */
function CompanyDialog({
  workspaceId,
  company,
  onClose,
  onSaved,
  onOpenExisting,
}: {
  workspaceId: string;
  company: Company | null;
  onClose: () => void;
  onSaved: (saved: Company) => void;
  onOpenExisting: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const create = useCreateCompany(workspaceId);
  const update = useUpdateCompany(workspaceId);
  const [values, setValues] = useState<Values>(() => valuesOf(company));
  const [invalid, setInvalid] = useState<Set<Field>>(new Set());
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  const [key] = useState(newIdempotencyKey);
  const owners = ownerOptions(t, members.data?.items ?? [], me.data?.user_id);
  // Custom fields (decision P3-D): the active ones, typed inputs.
  const definitions = useFieldDefinitions(workspaceId);
  const fields = activeFields(definitions.data?.items, "company");
  const [custom, setCustom] = useState<CustomDraft | null>(null);
  const draft = custom ?? draftOf(fields, company?.custom_fields);
  const [invalidCustom, setInvalidCustom] = useState<Set<string>>(new Set());

  function body(): CompanyCreate {
    return {
      name: values.name.trim(),
      domain: orNull(values.domain),
      website: orNull(values.website),
      phone: orNull(values.phone),
      industry: orNull(values.industry),
      city: orNull(values.city),
      country_code: orNull(values.country_code),
      owner_user_id: orNull(values.owner_user_id),
      ...(Object.keys(createValues(fields, draft)).length
        ? { custom_fields: createValues(fields, draft) }
        : {}),
    };
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    setRefusal(null);
    const customProblems = new Set(draftProblems(fields, draft));
    setInvalidCustom(customProblems);
    if (!values.name.trim()) {
      setInvalid(new Set(["name"]));
      return;
    }
    setInvalid(new Set());
    if (customProblems.size > 0) return;
    const fail = (error: ApiError) => {
      if (error instanceof CustomFieldError && error.key) setInvalidCustom(new Set([error.key]));
      if (error instanceof FieldErrors) {
        setInvalid(new Set(error.fields.filter((f): f is Field => FIELDS.includes(f as Field))));
      }
      setRefusal(error);
    };
    const done = (saved: Company) => {
      toast(company ? t("records.saved") : t("company.created"));
      onSaved(saved);
    };
    if (company) {
      const next = body();
      const before = valuesOf(company);
      const changes: CompanyUpdate = {};
      for (const field of FIELDS) {
        if (values[field].trim() !== before[field].trim()) Object.assign(changes, { [field]: next[field] });
      }
      const customChanges = changedValues(fields, draft, company.custom_fields);
      if (Object.keys(customChanges).length) changes.custom_fields = customChanges;
      if (Object.keys(changes).length === 0) {
        onClose();
        return;
      }
      update.mutate({ id: company.id, version: company.version, changes }, { onSuccess: done, onError: fail });
    } else {
      create.mutate({ body: body(), key }, { onSuccess: done, onError: fail });
    }
  }

  const field = (name: Field, options: { wide?: boolean; required?: boolean; placeholder?: string } = {}) => {
    const id = `company-${name}`;
    const message = invalid.has(name)
      ? name === "name" && !(refusal instanceof FieldErrors)
        ? t("company.error.name")
        : t("records.error.field")
      : null;
    return (
      <div className={options.wide ? "form-field wide" : "form-field"}>
        <label className="form-label" htmlFor={id}>
          {t(LABEL[name])}
          {options.required ? <span className="required"> *</span> : null}
        </label>
        {name === "owner_user_id" ? (
          <select
            id={id}
            className="form-input form-select"
            value={values.owner_user_id}
            onChange={(event) => { setValues((prev) => ({ ...prev, owner_user_id: event.target.value })); }}
          >
            <option value="">{t("records.owner.none")}</option>
            {owners.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            className={message ? "form-input invalid" : "form-input"}
            value={values[name]}
            placeholder={options.placeholder}
            aria-invalid={message ? true : undefined}
            aria-describedby={message ? `${id}-error` : undefined}
            autoComplete="off"
            onChange={(event) => {
              setValues((prev) => ({ ...prev, [name]: event.target.value }));
              setInvalid((prev) => {
                const next = new Set(prev);
                next.delete(name);
                return next;
              });
            }}
          />
        )}
        {message ? (
          <span id={`${id}-error`} className="form-error">
            {message}
          </span>
        ) : null}
      </div>
    );
  };

  const duplicateOf = refusal instanceof DuplicateError ? refusal.existingId : undefined;

  return (
    <Dialog
      isOpen
      title={company ? t("company.edit") : t("company.new")}
      onClose={onClose}
      actions={
        <>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button
            variant="primary"
            type="submit"
            form="company-form"
            isDisabled={create.isPending || update.isPending}
          >
            {company ? t("records.saveChanges") : t("company.create")}
          </Button>
        </>
      }
    >
      <form id="company-form" className="record-form" onSubmit={submit} noValidate>
        {field("name", { wide: true, required: true })}
        {field("website", { placeholder: "https://example.com" })}
        {field("domain", { placeholder: "example.com" })}
        {field("industry")}
        {field("phone")}
        {field("city")}
        {field("country_code", { placeholder: "NL" })}
        {field("owner_user_id")}
        <CustomFieldInputs
          fields={fields}
          draft={draft}
          invalid={invalidCustom}
          idPrefix="company"
          onChange={(key, value) => {
            setCustom({ ...draft, [key]: value });
            setInvalidCustom((prev) => {
              const next = new Set(prev);
              next.delete(key);
              return next;
            });
          }}
        />
        <p className="form-hint wide">{t("company.hint")}</p>
        {refusal && !(refusal instanceof FieldErrors && refusal.fields.length > 0) ? (
          <div className="notice error wide" role="alert">
            <p>{t(refusalMessage(refusal))}</p>
            {duplicateOf ? (
              <Button size="sm" onPress={() => { onOpenExisting(duplicateOf); }}>
                {t("records.openExisting")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
