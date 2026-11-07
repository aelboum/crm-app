import { useState } from "react";

import { ApiError } from "../api/client";
import {
  type ContactViewFilters,
  useContactViews,
  useDeleteContactView,
  useSaveContactView,
} from "../api/savedViews";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Saved views on the contacts list (decision P3-SV): apply one of the
 * member's own views, save the current filters under a name, or delete the
 * chosen view. Views are private to the member.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "duplicate_saved_view") return "views.error.duplicate";
    if (error.code === "saved_view_limit") return "views.error.limit";
  }
  return "views.error.generic";
}

export function ContactViews({
  workspaceId,
  current,
  onApply,
}: {
  workspaceId: string;
  current: ContactViewFilters;
  onApply: (filters: ContactViewFilters) => void;
}) {
  const t = useT();
  const views = useContactViews(workspaceId);
  const save = useSaveContactView(workspaceId);
  const remove = useDeleteContactView(workspaceId);
  const [chosen, setChosen] = useState("");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const items = views.data?.items ?? [];
  const problem = save.error ?? remove.error;

  return (
    <div className="saved-views" role="group" aria-label={t("views.title")}>
      <select
        className="form-input"
        aria-label={t("views.choose")}
        value={chosen}
        onChange={(event) => {
          const id = event.target.value;
          setChosen(id);
          const view = items.find((v) => v.id === id);
          if (view) onApply(view.filters);
        }}
      >
        <option value="">{t("views.none")}</option>
        {items.map((view) => (
          <option key={view.id} value={view.id}>
            {view.name}
          </option>
        ))}
      </select>
      {chosen ? (
        <Button
          size="sm"
          variant="ghost"
          isDisabled={remove.isPending}
          onPress={() => {
            remove.mutate(
              { id: chosen },
              {
                onSuccess: () => {
                  setChosen("");
                },
              },
            );
          }}
        >
          {t("views.delete")}
        </Button>
      ) : null}
      {naming ? (
        <>
          <input
            className="form-input"
            aria-label={t("views.name")}
            value={name}
            maxLength={60}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          <Button
            size="sm"
            variant="primary"
            isDisabled={save.isPending || !name.trim()}
            onPress={() => {
              save.mutate(
                { name, filters: current },
                {
                  onSuccess: (view) => {
                    setNaming(false);
                    setName("");
                    setChosen(view.id);
                  },
                },
              );
            }}
          >
            {t("views.save")}
          </Button>
        </>
      ) : (
        <Button
          size="sm"
          onPress={() => {
            setNaming(true);
          }}
        >
          {t("views.saveCurrent")}
        </Button>
      )}
      {problem ? (
        <span className="notice error" role="alert">
          {t(failure(problem))}
        </span>
      ) : null}
    </div>
  );
}
