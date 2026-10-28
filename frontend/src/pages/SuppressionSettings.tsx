import { Plus, Search, Trash2 } from "lucide-react";
import { type SyntheticEvent, useState } from "react";

import { ApiError } from "../api/client";
import {
  ADD_MAX,
  AddressesRefused,
  REASONS,
  type Reason,
  splitAddresses,
  type Suppression,
  useAddSuppressions,
  useRemoveSuppression,
  useSuppressions,
} from "../api/suppression";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { When } from "../records/parts";

/*
 * Settings › Suppression list (decision P7-B 10): addresses this workspace
 * must never email. Owners, Admins and Members see the list; Owners and
 * Admins add addresses (pasted, with a reason and note) and remove them.
 * The server enforces every rule; a refused paste names the lines, never
 * the addresses.
 */

export const REASON_LABEL: Record<Reason, MessageId> = {
  manual: "suppression.reason.manual",
  unsubscribed: "suppression.reason.unsubscribed",
  bounced: "suppression.reason.bounced",
  complained: "suppression.reason.complained",
};

type T = ReturnType<typeof useT>;

function failure(t: T, error: unknown): string {
  if (error instanceof AddressesRefused) {
    const lines = error.positions.map((p) => String(p + 1)).join(", ");
    return t("suppression.error.lines", { count: error.positions.length, lines });
  }
  if (error instanceof ApiError) {
    if (error.code === "invalid_note") return t("suppression.error.note");
    if (error.code === "suppression_limit") return t("suppression.error.limit");
  }
  return t("suppression.error.failed");
}

export function SuppressionSettings({
  workspaceId,
  canRead,
  canManage,
}: {
  workspaceId: string;
  canRead: boolean;
  canManage: boolean;
}) {
  const t = useT();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const list = useSuppressions(workspaceId, term, canRead);
  const remove = useRemoveSuppression(workspaceId);
  const [removing, setRemoving] = useState<Suppression | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!canRead) {
    return (
      <section className="business-card" aria-label={t("settings.suppression")}>
        <p className="muted">{t("suppression.denied")}</p>
      </section>
    );
  }

  const pages = list.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);
  const first = pages[0];

  const confirmRemove = () => {
    if (!removing) return;
    const row = removing;
    setRemoving(null);
    setError(null);
    remove.mutate(
      { id: row.id },
      {
        onSuccess: () => {
          toast(t("suppression.removed"));
        },
        onError: (problem) => {
          setError(failure(t, problem));
        },
      },
    );
  };

  return (
    <section className="business-card suppression-settings" aria-label={t("settings.suppression")}>
      <p className="profile-note">{t("suppression.intro")}</p>
      {canManage ? (
        <AddForm workspaceId={workspaceId} />
      ) : (
        <p className="profile-note">{t("suppression.readOnly")}</p>
      )}
      {error ? (
        <p className="notice error" role="alert">
          {error}
        </p>
      ) : null}
      <form
        className="suppression-search"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          setTerm(search.trim());
        }}
      >
        <label htmlFor="suppression-search" className="sr-only">
          {t("suppression.search")}
        </label>
        <input
          id="suppression-search"
          className="form-input"
          type="search"
          placeholder={t("suppression.search")}
          value={search}
          maxLength={320}
          onChange={(event) => {
            setSearch(event.target.value);
            if (event.target.value.trim() === "") setTerm("");
          }}
        />
        <Button type="submit" size="sm">
          <Search size={13} aria-hidden="true" />
          {t("suppression.search")}
        </Button>
      </form>
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : items.length === 0 ? (
        <p className="muted">{term ? t("suppression.noMatch") : t("suppression.empty")}</p>
      ) : (
        <>
          {first ? (
            <p className="profile-note" role="status">
              {t("suppression.total", { count: first.total, capped: String(first.total_capped) })}
            </p>
          ) : null}
          <div className="suppression-table-wrap">
            <table className="suppression-table">
              <thead>
                <tr>
                  <th scope="col">{t("suppression.column.email")}</th>
                  <th scope="col">{t("suppression.column.reason")}</th>
                  <th scope="col">{t("suppression.column.added")}</th>
                  {canManage ? (
                    <th scope="col">
                      <span className="sr-only">{t("suppression.column.actions")}</span>
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td className="suppression-email">{row.email}</td>
                    <td>
                      {t(REASON_LABEL[row.reason])}
                      {row.origin === "consent_withdrawn" ? (
                        <span className="muted"> · {t("suppression.fromWithdrawal")}</span>
                      ) : null}
                      {row.note ? <span className="suppression-note">{row.note}</span> : null}
                    </td>
                    <td>
                      <When value={row.created_at} />
                    </td>
                    {canManage ? (
                      <td>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`${t("suppression.remove")} ${row.email}`}
                          isDisabled={remove.isPending}
                          onPress={() => {
                            setRemoving(row);
                          }}
                        >
                          <Trash2 size={13} aria-hidden="true" />
                          {t("suppression.remove")}
                        </Button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.hasNextPage ? (
            <Button
              size="sm"
              isDisabled={list.isFetchingNextPage}
              onPress={() => {
                void list.fetchNextPage();
              }}
            >
              {t("suppression.more")}
            </Button>
          ) : null}
        </>
      )}
      <ConfirmDialog
        isOpen={removing !== null}
        title={t("suppression.removeTitle")}
        confirmLabel={t("suppression.remove")}
        message={t("suppression.removeBody", { email: removing?.email ?? "" })}
        onConfirm={confirmRemove}
        onCancel={() => {
          setRemoving(null);
        }}
      />
    </section>
  );
}

function AddForm({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const toast = useToast();
  const add = useAddSuppressions(workspaceId);
  const [text, setText] = useState("");
  const [reason, setReason] = useState<Reason>("manual");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const emails = splitAddresses(text);
    if (emails.length === 0) {
      setError(t("suppression.error.none"));
      return;
    }
    if (emails.length > ADD_MAX) {
      setError(t("suppression.error.tooMany", { max: ADD_MAX }));
      return;
    }
    setError(null);
    add.mutate(
      { emails, reason, note: note.trim() || null },
      {
        onSuccess: (result) => {
          setText("");
          setNote("");
          toast(t("suppression.added", { added: result.added, already: result.already_suppressed }));
        },
        onError: (problem) => {
          setError(failure(t, problem));
        },
      },
    );
  };

  return (
    <form className="suppression-add" onSubmit={submit} noValidate aria-labelledby="suppression-add-title">
      <h2 id="suppression-add-title" className="field-label">
        {t("suppression.add")}
      </h2>
      <div className="form-field">
        <label htmlFor="suppression-addresses" className="form-label">
          {t("suppression.addresses")}
        </label>
        <textarea
          id="suppression-addresses"
          className="form-input form-textarea"
          rows={4}
          value={text}
          aria-describedby="suppression-addresses-hint"
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <p id="suppression-addresses-hint" className="form-hint">
          {t("suppression.addressesHint", { max: ADD_MAX })}
        </p>
      </div>
      <div className="suppression-add-row">
        <div className="form-field">
          <label htmlFor="suppression-reason" className="form-label">
            {t("suppression.reason")}
          </label>
          <select
            id="suppression-reason"
            className="form-input form-select"
            value={reason}
            onChange={(event) => {
              const next = REASONS.find((value) => value === event.target.value);
              if (next) setReason(next);
            }}
          >
            {REASONS.map((value) => (
              <option key={value} value={value}>
                {t(REASON_LABEL[value])}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field suppression-note-field">
          <label htmlFor="suppression-note" className="form-label">
            {t("suppression.note")}
          </label>
          <input
            id="suppression-note"
            className="form-input"
            value={note}
            maxLength={500}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
        </div>
      </div>
      {error ? (
        <p className="notice error" role="alert">
          {error}
        </p>
      ) : null}
      <div>
        <Button type="submit" variant="primary" isDisabled={add.isPending}>
          <Plus size={14} aria-hidden="true" />
          {t("suppression.submit")}
        </Button>
      </div>
    </form>
  );
}
