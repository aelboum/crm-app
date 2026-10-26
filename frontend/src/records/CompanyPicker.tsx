import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ListBox, ListBoxItem } from "react-aria-components";

import { NO_FILTERS, useCompanyList } from "../api/records";
import { LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
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
 */

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
}: {
  workspaceId: string;
  /** The id of the control that opens the search; the label points at it. */
  id: string;
  label: string;
  selected: PickedCompany | null;
  onChange: (company: PickedCompany | null) => void;
  /** The id of this field's error message, when there is one. */
  errorId?: string | undefined;
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
            {selected ? selected.name : t("contact.noCompany")}
            {selected?.archived ? ` · ${t("picker.company.archived")}` : ""}
          </span>
          <Button
            id={id}
            ref={trigger}
            size="sm"
            {...(errorId ? { "aria-describedby": errorId } : {})}
            onPress={() => { setSearching(true); }}
          >
            {selected ? t("picker.company.change") : t("picker.company.choose")}
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
              {t("picker.company.remove")}
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
  id,
  selectedId,
  errorId,
  onPick,
  onClose,
}: {
  workspaceId: string;
  id: string;
  selectedId: string | null;
  errorId: string | undefined;
  onPick: (company: PickedCompany) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const list = useCompanyList(workspaceId, { ...NO_FILTERS, q });
  const companies = (list.data?.pages ?? []).flatMap((page) => page.items);
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
  } else if (companies.length === 0) {
    results = (
      <p className="muted" role="status">
        {q ? t("picker.company.noMatch") : t("picker.company.none")}
      </p>
    );
  } else {
    results = (
      <>
        <ListBox
          id={resultsId}
          className="picker-results"
          aria-label={t("picker.company.results")}
          items={companies}
          selectionMode="single"
          selectedKeys={selectedId ? [selectedId] : []}
          onAction={(key) => {
            const company = companies.find((c) => c.id === key);
            if (company) onPick({ id: company.id, name: company.name });
          }}
        >
          {(company) => (
            <ListBoxItem id={company.id} className="picker-option" textValue={company.name}>
              <span className="picker-option-name">{company.name}</span>
              {company.domain ?? company.city ? (
                <span className="picker-option-sub">{company.domain ?? company.city}</span>
              ) : null}
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
            {list.isFetchingNextPage ? t("state.loading") : t("picker.company.more")}
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
          placeholder={t("picker.company.search")}
          aria-label={t("picker.company.search")}
          aria-controls={companies.length ? resultsId : undefined}
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
