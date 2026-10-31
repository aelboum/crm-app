import { Plus } from "lucide-react";
import { useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { RECORD_DEALS, useRecordDeals } from "../api/opportunities";
import { usePipelines } from "../api/pipelines";
import {
  useAccess,
  useMe,
  useMembers,
  useWorkspaceSettings,
} from "../api/queries";
import { LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import type { PickedCompany } from "./CompanyPicker";
import { DealDialog } from "./DealDialog";
import { Money, stageShade } from "./dealParts";
import { ownerOptions } from "./parts";

/*
 * A contact's or company's deals in its drawer (decision P4-E): every
 * outcome, most recently changed first, each opening on the Opportunities
 * page, and "New opportunity" with the record filled in. Who may create
 * follows `/access`.
 */

export function DealsSection({
  workspaceId,
  link,
  onOpen,
}: {
  workspaceId: string;
  /** The record, plus the contact's company so a new deal links to both. */
  link:
    | { kind: "contact"; contact: PickedCompany; company: PickedCompany | null }
    | { kind: "company"; company: PickedCompany };
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const canCreate = access.data?.actions.create_opportunity === true;
  const members = useMembers(
    workspaceId,
    0,
    canCreate && access.data?.actions.read_members === true,
  );
  const pipelines = usePipelines(workspaceId);
  const settings = useWorkspaceSettings(workspaceId);
  const record = link.kind === "contact" ? link.contact : link.company;
  const list = useRecordDeals(workspaceId, { kind: link.kind, id: record.id });
  const [creating, setCreating] = useState(false);
  const deals = list.data?.items ?? [];
  const total = list.data?.total ?? deals.length;
  const stages = pipelines.data?.items[0]?.stages ?? [];
  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const choices = owners.length
    ? owners
    : meId
      ? [{ id: meId, label: t("records.owner.me") }]
      : [];
  const headingId = `${link.kind}-deals-title`;
  return (
    <section className="drawer-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="drawer-section-title">
        {t("deals.section", { count: total })}
      </h2>
      {list.isError ? (
        <LoadError error={list.error} onRetry={() => void list.refetch()} />
      ) : null}
      {deals.length ? (
        <ul className="deal-list">
          {deals.map((deal) => (
            <li key={deal.id}>
              <AriaButton
                className="deal-row"
                onPress={() => {
                  onOpen(deal.id);
                }}
              >
                <span className="deal-row-text">
                  <span className="deal-row-title">{deal.title}</span>
                  <span className="deal-row-meta stage-cell">
                    <span
                      className="stage-dot"
                      style={{
                        background: stageShade(
                          deal.stage.position,
                          Math.max(stages.length, 1),
                        ),
                      }}
                      aria-hidden="true"
                    />
                    {deal.stage.name}
                    {deal.outcome !== "open" ? (
                      <span className={`outcome-tag ${deal.outcome}`}>
                        {t(
                          deal.outcome === "won"
                            ? "deals.outcome.won"
                            : "deals.outcome.lost",
                        )}
                      </span>
                    ) : null}
                  </span>
                </span>
                <span className="deal-row-amount">
                  <Money amount={deal.amount} currency={deal.currency} />
                </span>
              </AriaButton>
            </li>
          ))}
        </ul>
      ) : list.isPending ? null : (
        <p className="muted">{t("deals.sectionEmpty")}</p>
      )}
      {total > deals.length ? (
        <p className="muted">
          {t("deals.sectionMore", { shown: RECORD_DEALS, total })}
        </p>
      ) : null}
      {canCreate && stages.length ? (
        <Button
          size="sm"
          onPress={() => {
            setCreating(true);
          }}
        >
          <Plus size={13} aria-hidden="true" />
          {t("deals.new")}
        </Button>
      ) : null}
      {creating ? (
        <DealDialog
          workspaceId={workspaceId}
          deal={null}
          stages={stages}
          currency={settings.data?.currency ?? "EUR"}
          owners={choices}
          meId={meId}
          links={
            link.kind === "contact"
              ? { contact: link.contact, company: link.company }
              : { company: link.company }
          }
          onClose={() => {
            setCreating(false);
          }}
          onSaved={() => {
            setCreating(false);
          }}
        />
      ) : null}
    </section>
  );
}
