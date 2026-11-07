import { useState } from "react";

import { ApiError } from "../api/client";
import { useMe, useMembers } from "../api/queries";
import {
  type BulkAction,
  type BulkResult,
  useBulkContacts,
} from "../api/records";
import { useTags } from "../api/tags";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { useMemberNames } from "../members/names";
import { ownerLabel } from "./parts";

/*
 * The contacts list's bulk bar (decision P3-BK): one action on the
 * selected contacts. Each contact changes on its own, exactly as one change
 * would; the bar says how many changed, how many already were so, and how
 * many were skipped. "Add to automation" and "Export" from the design are
 * not built: automations start from their triggers, and Export follows the
 * list's filters.
 */

const STAGES = ["lead", "prospect", "customer", "inactive"] as const;

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "owner_not_member") return "bulk.error.owner";
    if (error.status === 403) return "bulk.error.forbidden";
  }
  return "bulk.error.generic";
}

export function ContactBulkBar({
  workspaceId,
  selected,
  archivedView,
  onDone,
  onClear,
}: {
  workspaceId: string;
  selected: string[];
  archivedView: boolean;
  onDone: () => void;
  onClear: () => void;
}) {
  const t = useT();
  const me = useMe();
  const members = useMembers(workspaceId, 0, true);
  const names = useMemberNames();
  const tags = useTags(workspaceId);
  const run = useBulkContacts(workspaceId);
  const [action, setAction] = useState<BulkAction>(
    archivedView ? "restore" : "assign_owner",
  );
  const [value, setValue] = useState("");
  const [result, setResult] = useState<BulkResult | null>(null);
  const meId = me.data?.user_id;
  const people = (members.data?.items ?? []).filter(
    (m) => m.status === "active",
  );
  const tagList = tags.data?.items ?? [];

  const needs =
    action === "assign_owner"
      ? "owner"
      : action === "add_tag" || action === "remove_tag"
        ? "tag"
        : action === "set_stage"
          ? "stage"
          : null;
  const chosen =
    needs === "owner" ? value || meId || "" : needs === null ? "-" : value;

  const apply = () => {
    setResult(null);
    run.mutate(
      {
        contact_ids: selected,
        action,
        ...(needs === "owner" ? { owner_user_id: chosen } : {}),
        ...(needs === "tag" ? { tag_id: chosen } : {}),
        ...(needs === "stage" ? { stage: chosen } : {}),
      },
      {
        onSuccess: (done) => {
          setResult(done);
          onDone();
        },
      },
    );
  };

  return (
    <div
      className="bulk-bar"
      role="region"
      aria-label={t("bulk.title", { count: selected.length })}
    >
      <span className="bulk-count">
        {t("bulk.selected", { count: selected.length })}
      </span>
      <select
        className="form-input"
        aria-label={t("bulk.action")}
        value={action}
        onChange={(event) => {
          setAction(event.target.value as BulkAction);
          setValue("");
          setResult(null);
        }}
      >
        {archivedView ? (
          <option value="restore">{t("bulk.do.restore")}</option>
        ) : (
          <>
            <option value="assign_owner">{t("bulk.do.assign_owner")}</option>
            <option value="add_tag">{t("bulk.do.add_tag")}</option>
            <option value="remove_tag">{t("bulk.do.remove_tag")}</option>
            <option value="set_stage">{t("bulk.do.set_stage")}</option>
            <option value="archive">{t("bulk.do.archive")}</option>
          </>
        )}
      </select>
      {needs === "owner" ? (
        <select
          className="form-input"
          aria-label={t("bulk.owner")}
          value={chosen}
          onChange={(event) => {
            setValue(event.target.value);
          }}
        >
          {people.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {ownerLabel(t, m.user_id, meId, names)}
            </option>
          ))}
        </select>
      ) : null}
      {needs === "tag" ? (
        <select
          className="form-input"
          aria-label={t("bulk.tag")}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
          }}
        >
          <option value="">{t("bulk.chooseTag")}</option>
          {tagList.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      ) : null}
      {needs === "stage" ? (
        <select
          className="form-input"
          aria-label={t("bulk.stage")}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
          }}
        >
          <option value="">{t("bulk.chooseStage")}</option>
          {STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {t(`stage.${stage}` as MessageId)}
            </option>
          ))}
        </select>
      ) : null}
      <Button
        size="sm"
        variant="primary"
        isDisabled={run.isPending || !chosen}
        onPress={apply}
      >
        {t("bulk.apply")}
      </Button>
      <Button size="sm" variant="ghost" onPress={onClear}>
        {t("bulk.clear")}
      </Button>
      {result ? (
        <span className="bulk-result" role="status">
          {t("bulk.result", {
            done: result.done,
            unchanged: result.unchanged,
            skipped: result.skipped.length,
          })}
        </span>
      ) : null}
      {run.error ? (
        <span className="notice error" role="alert">
          {t(failure(run.error))}
        </span>
      ) : null}
    </div>
  );
}
