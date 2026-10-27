import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ListBox, ListBoxItem } from "react-aria-components";

import { NO_FILTERS, useCompanyList, useContactList } from "../api/records";
import { LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { useDebounced } from "./useDebounced";

/*
 * The contact form's company field (slice 3A hardening). It searches the
 * workspace's own company list (`GET /v1/workspaces/{id}/companies`, prefix
 * search, cursor pages), so any active company can be found, not only the
 * first page. Results come from the query for the current search text alone
 * (each text is its own cached query), so an older, slower answer never
 * replaces a newer one. Only active companies are offered, as the API links
 * only those; a contact's current company stays shown even when archived.
 *
 * The deal form (decision P4-B 4) uses the same control for a contact
 * (`kind="contacts"`): prefix search on name or email, active contacts only.
 */

export type PickerKind = "companies" | "contacts";

const TEXT: Record<PickerKind, Record<string, MessageId>> = {
  companies: {
    none: "contact.noCompany",
    choose: "picker.company.choose",
    change: "picker.company.change",
    remove: "picker.company.remove",
    search: "picker.company.search",
    results: "picker.company.results",
    more: "picker.company.more",
    noMatch: "picker.company.noMatch",
    empty: "picker.company.none",
  },
  contacts: {
    none: "picker.contact.noContact",
    choose: "picker.contact.choose",
    change: "picker.contact.change",
    remove: "picker.contact.remove",
    search: "picker.contact.search",
    results: "picker.contact.results",
    more: "picker.contact.more",
    noMatch: "picker.contact.noMatch",
    empty: "picker.contact.none",
  },
};

function text(kind: PickerKind, key: string): MessageId {
  return TEXT[kind][key] ?? "picker.loadMoreFailed";
}

export interface PickedCompany {
  id: string;
  name: string;
  archived?: boolean;
}

export function CompanyPicker({
  workspaceId,
  id,
  label,
  selected,
  onChange,
  errorId,
  kind = "companies",
}: {
  workspaceId: string;
  /** The id of the control that opens the search; the label points at it. */
  id: string;
  label: string;
  selected: PickedCompany | null;
  onChange: (company: PickedCompany | null) => void;
  /** The id of this field's error message, when there is one. */
  errorId?: string | undefined;
  /** What is picked: a company (the default) or a contact. */
  kind?: PickerKind;
}) {
  const t = useT();
  const [searching, setSearching] = useState(false);
  // Choosing, cancelling and removing unmount the control that had focus:
  // focus returns to the company control instead of leaving the form.
  const trigger = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  useEffect(() => {
    if (!searching && returnFocus.current) {
      returnFocus.current = false;
      trigger.current?.focus();
    }
  });
  const labelId = `${id}-label`;

  const stop = () => {
    returnFocus.current = true;
    setSearching(false);
  };

  return (
    <div className="form-field wide company-picker" role="group" aria-labelledby={labelId}>
      <span id={labelId} className="form-label">
        {label}
      </span>
      {searching ? (
        <SearchPanel
          workspaceId={workspaceId}
          kind={kind}
          id={id}
          selectedId={selected?.id ?? null}
          errorId={errorId}
          onPick={(company) => {
            onChange(company);
            stop();
          }}
          onClose={stop}
        />
      ) : (
        <div className="row picker-current">
          <span className={selected ? "picker-value" : "picker-value muted"}>
            {selected ? selected.name : t(text(kind, "none"))}
            {selected?.archived ? ` · ${t("picker.company.archived")}` : ""}
          </span>
          <Button
            id={id}
            ref={trigger}
            size="sm"
            {...(errorId ? { "aria-describedby": errorId } : {})}
            onPress={() => { setSearching(true); }}
          >
            {selected ? t(text(kind, "change")) : t(text(kind, "choose"))}
          </Button>
          {selected ? (
            <Button
              size="sm"
              variant="ghost"
              onPress={() => {
                returnFocus.current = true;
                onChange(null);
              }}
            >
              {t(text(kind, "remove"))}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** The search box and its results; mounted only while searching, so every
 *  opening starts from an empty search. */
function SearchPanel({
  workspaceId,
  kind,
  id,
  selectedId,
  errorId,
  onPick,
  onClose,
}: {
  workspaceId: string;
  kind: PickerKind;
  id: string;
  selectedId: string | null;
  errorId: string | undefined;
  onPick: (picked: PickedCompany) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const companyList = useCompanyList(workspaceId, { ...NO_FILTERS, q }, kind === "companies");
  const contactList = useContactList(workspaceId, { ...NO_FILTERS, q }, kind === "contacts");
  const list = kind === "companies" ? companyList : contactList;
  // One shape for both kinds: what the option shows and what is picked.
  const options =
    kind === "companies"
      ? (companyList.data?.pages ?? []).flatMap((page) =>
          page.items.map((c) => ({ id: c.id, name: c.name, sub: c.domain ?? c.city })),
        )
      : (contactList.data?.pages ?? []).flatMap((page) =>
          page.items.map((c) => ({
            id: c.id,
            name: [c.first_name, c.last_name].filter(Boolean).join(" "),
            sub: c.email ?? c.phone,
          })),
        );
  const resultsId = `${id}-results`;

  // Escape anywhere in the panel closes the search, not the whole dialog.
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      event.preventDefault();
      onClose();
    }
  };

  let results;
  if (list.isPending) {
    results = (
      <p role="status" className="state-loading">
        <span className="spinner" aria-hidden="true" />
        {t("state.loading")}
      </p>
    );
  } else if (list.isError && !list.data) {
    // A failed later page keeps the results already shown (below).
    results = <LoadError error={list.error} onRetry={() => void list.refetch()} />;
  } else if (options.length === 0) {
    results = (
      <p className="muted" role="status">
        {q ? t(text(kind, "noMatch")) : t(text(kind, "empty"))}
      </p>
    );
  } else {
    results = (
      <>
        <ListBox
          id={resultsId}
          className="picker-results"
          aria-label={t(text(kind, "results"))}
          items={options}
          selectionMode="single"
          selectedKeys={selectedId ? [selectedId] : []}
          onAction={(key) => {
            const option = options.find((c) => c.id === key);
            if (option) onPick({ id: option.id, name: option.name });
          }}
        >
          {(option) => (
            <ListBoxItem id={option.id} className="picker-option" textValue={option.name}>
              <span className="picker-option-name">{option.name}</span>
              {option.sub ? <span className="picker-option-sub">{option.sub}</span> : null}
            </ListBoxItem>
          )}
        </ListBox>
        {list.isFetchNextPageError ? (
          <p className="form-error" role="alert">
            {t("picker.loadMoreFailed")}
          </p>
        ) : null}
        {list.hasNextPage ? (
          <Button size="sm" onPress={() => void list.fetchNextPage()} isDisabled={list.isFetchingNextPage}>
            {list.isFetchingNextPage ? t("state.loading") : t(text(kind, "more"))}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- Escape for the controls inside
    <div className="picker-panel" onKeyDown={onKeyDown}>
      <div className="row">
        <input
          id={id}
          type="search"
          className="form-input picker-search"
          value={search}
          onChange={(event) => { setSearch(event.target.value); }}
          onKeyDown={(event) => {
            // Down arrow moves into the results.
            if (event.key === "ArrowDown") {
              const first = document.getElementById(resultsId)?.querySelector<HTMLElement>('[role="option"]');
              if (first) {
                event.preventDefault();
                first.focus();
              }
            }
          }}
          placeholder={t(text(kind, "search"))}
          aria-label={t(text(kind, "search"))}
          aria-controls={options.length ? resultsId : undefined}
          aria-describedby={errorId}
          aria-invalid={errorId ? true : undefined}
          maxLength={100}
          autoComplete="off"
          // eslint-disable-next-line jsx-a11y/no-autofocus -- opened by the person's own action
          autoFocus
        />
        <Button size="sm" variant="ghost" onPress={onClose}>
          {t("confirm.cancel")}
        </Button>
      </div>
      {results}
    </div>
  );
}
