import { Pencil, RotateCcw, Trash2, Trophy } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { type Deal, useDeal, useDealHistory, useDeleteDeal, useSetOutcome, useUpdateDeal } from "../api/opportunities";
import type { Stage } from "../api/pipelines";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { refusalOf } from "./DealDialog";
import { daysInStage, eventText, Money, stageShade } from "./dealParts";
import { Drawer, FieldRow, ownerLabel, When } from "./parts";

/*
 * The design's deal drawer (ScreenPipeline.dc.html): title, value with its
 * probability and weighted value, the stage stepper, owner and expected
 * close, the related contact and company, the history, and Mark lost / Mark
 * won. Differences (decision P4-B 5): won and lost are outcomes, so a closed
 * deal shows its outcome and offers Reopen; its stage cannot change. Mark
 * lost asks for the reason the server requires. Changes need
 * `update_opportunity`; Delete needs `delete_opportunity`.
 */

export function DealDrawer({
  workspaceId,
  id,
  stages,
  meId,
  canUpdate,
  canDelete,
  onClose,
  onEdit,
  onOpenContact,
  onOpenCompany,
}: {
  workspaceId: string;
  id: string;
  stages: Stage[];
  meId: string | undefined;
  canUpdate: boolean;
  canDelete: boolean;
  onClose: () => void;
  onEdit: (deal: Deal) => void;
  onOpenContact: (id: string) => void;
  onOpenCompany: (id: string) => void;
}) {
  const t = useT();
  const toast = useToast();
  const query = useDeal(workspaceId, id);
  const update = useUpdateDeal(workspaceId);
  const outcome = useSetOutcome(workspaceId);
  const remove = useDeleteDeal(workspaceId);
  const [refusal, setRefusal] = useState<MessageId | null>(null);
  const [losing, setLosing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const deal = query.data;
  const busy = update.isPending || outcome.isPending || remove.isPending;

  const failed = (error: unknown) => {
    setRefusal(refusalOf(error));
  };

  function move(stage: Stage) {
    if (!deal || stage.id === deal.stage_id) return;
    setRefusal(null);
    update.mutate(
      { id: deal.id, version: deal.version, changes: { stage_id: stage.id } },
      {
        onSuccess: () => {
          toast(t("deals.moved", { title: deal.title, stage: stage.name }));
        },
        onError: failed,
      },
    );
  }

  function setOutcome(next: "open" | "won" | "lost", reason?: string) {
    if (!deal) return;
    setRefusal(null);
    outcome.mutate(
      { id: deal.id, version: deal.version, outcome: next, ...(reason === undefined ? {} : { reason }) },
      {
        onSuccess: () => {
          setLosing(false);
          toast(t(next === "won" ? "deals.markedWon" : next === "lost" ? "deals.markedLost" : "deals.reopened"));
        },
        onError: failed,
      },
    );
  }

  return (
    <Drawer
      title={t("deals.preview")}
      onClose={onClose}
      headerActions={
        deal && canUpdate ? (
          <Button
            size="sm"
            onPress={() => {
              onEdit(deal);
            }}
          >
            <Pencil size={13} aria-hidden="true" />
            {t("records.edit")}
          </Button>
        ) : null
      }
    >
      {query.isPending ? (
        <Loading />
      ) : query.isError || !deal ? (
        <LoadError error={query.error} onRetry={() => void query.refetch()} notFound={t("deals.notFound")} />
      ) : (
        <>
          <div className="deal-identity">
            <p className="drawer-name">{deal.title}</p>
            <p className="deal-value">
              <Money amount={deal.amount} currency={deal.currency} />
            </p>
            {deal.outcome === "open" ? (
              <p className="drawer-headline">
                {deal.weighted_amount !== null ? (
                  <>
                    {t("deals.probability", { value: deal.stage.probability })} ·{" "}
                    {t("deals.weighted")} <Money amount={deal.weighted_amount} currency={deal.currency} />
                  </>
                ) : (
                  t("deals.probability", { value: deal.stage.probability })
                )}
              </p>
            ) : (
              <p className="deal-outcome">
                <Badge tone={deal.outcome === "won" ? "success" : "risk"}>
                  {t(deal.outcome === "won" ? "deals.outcome.won" : "deals.outcome.lost")}
                </Badge>
                {deal.closed_at ? <When value={deal.closed_at} /> : null}
              </p>
            )}
            {deal.outcome === "lost" && deal.lost_reason ? (
              <p className="deal-reason">
                <span className="muted">{t("deals.lostReason")}:</span> {deal.lost_reason}
              </p>
            ) : null}
          </div>

          <section className="drawer-section" aria-labelledby="deal-stage-title">
            <h2 id="deal-stage-title" className="drawer-section-title">
              {t("deals.field.stage")}
            </h2>
            <div className="stage-stepper" role="group" aria-labelledby="deal-stage-title">
              {stages.map((stage) => {
                const current = stage.id === deal.stage_id;
                const reached = stage.position <= deal.stage.position;
                return (
                  <AriaButton
                    key={stage.id}
                    className={current ? "stage-step current" : "stage-step"}
                    aria-pressed={current}
                    aria-label={t("deals.moveTo", { stage: stage.name })}
                    isDisabled={!canUpdate || deal.outcome !== "open" || busy}
                    onPress={() => {
                      move(stage);
                    }}
                  >
                    <span
                      className="stage-step-bar"
                      style={{ background: reached ? stageShade(stage.position, stages.length) : "#E3E6EA" }}
                    />
                    <span className="stage-step-name">{stage.name}</span>
                  </AriaButton>
                );
              })}
            </div>
            {deal.outcome !== "open" ? <p className="form-hint">{t("deals.closedStageHint")}</p> : null}
          </section>

          <dl className="field-list">
            <FieldRow label={t("records.field.owner")}>{ownerLabel(t, deal.owner_user_id, meId)}</FieldRow>
            <FieldRow label={t("deals.field.close")}>
              {deal.expected_close_date ? <When value={`${deal.expected_close_date}T12:00:00`} /> : null}
            </FieldRow>
            <FieldRow label={t("deals.field.contact")}>
              {deal.contact ? (
                <AriaButton
                  className="record-link"
                  onPress={() => {
                    if (deal.contact) onOpenContact(deal.contact.id);
                  }}
                >
                  {deal.contact.name}
                </AriaButton>
              ) : null}
            </FieldRow>
            <FieldRow label={t("deals.field.company")}>
              {deal.company ? (
                <AriaButton
                  className="record-link"
                  onPress={() => {
                    if (deal.company) onOpenCompany(deal.company.id);
                  }}
                >
                  {deal.company.name}
                </AriaButton>
              ) : null}
            </FieldRow>
            <FieldRow label={t("deals.daysInStage")}>
              {daysInStage(deal) === null ? null : t("deals.days", { count: daysInStage(deal) ?? 0 })}
            </FieldRow>
            <FieldRow label={t("records.field.created")}>
              <When value={deal.created_at} />
            </FieldRow>
          </dl>

          {refusal ? (
            <p className="notice error" role="alert">
              {t(refusal)}
            </p>
          ) : null}

          {canUpdate || canDelete ? (
            <div className="deal-actions">
              {canUpdate && deal.outcome === "open" ? (
                <>
                  <Button
                    className="deal-lose"
                    isDisabled={busy}
                    onPress={() => {
                      setLosing(true);
                    }}
                  >
                    {t("deals.markLost")}
                  </Button>
                  <Button
                    variant="primary"
                    className="deal-win"
                    isDisabled={busy}
                    onPress={() => {
                      setOutcome("won");
                    }}
                  >
                    <Trophy size={14} aria-hidden="true" />
                    {t("deals.markWon")}
                  </Button>
                </>
              ) : null}
              {canUpdate && deal.outcome !== "open" ? (
                <Button
                  isDisabled={busy}
                  onPress={() => {
                    setOutcome("open");
                  }}
                >
                  <RotateCcw size={14} aria-hidden="true" />
                  {t("deals.reopen")}
                </Button>
              ) : null}
              {canDelete ? (
                <Button
                  variant="ghost"
                  isDisabled={busy}
                  onPress={() => {
                    setDeleting(true);
                  }}
                >
                  <Trash2 size={14} aria-hidden="true" />
                  {t("deals.delete")}
                </Button>
              ) : null}
            </div>
          ) : null}

          <History workspaceId={workspaceId} id={deal.id} meId={meId} />

          {losing ? (
            <LostDialog
              busy={outcome.isPending}
              onCancel={() => {
                setLosing(false);
              }}
              onConfirm={(reason) => {
                setOutcome("lost", reason);
              }}
            />
          ) : null}
          <ConfirmDialog
            isOpen={deleting}
            title={t("deals.deleteTitle")}
            confirmLabel={t("deals.delete")}
            message={t("deals.deleteMessage", { title: deal.title })}
            onConfirm={() => {
              setDeleting(false);
              remove.mutate(
                { id: deal.id },
                {
                  onSuccess: () => {
                    toast(t("deals.deleted"));
                    onClose();
                  },
                  onError: failed,
                },
              );
            }}
            onCancel={() => {
              setDeleting(false);
            }}
          />
        </>
      )}
    </Drawer>
  );
}

function History({ workspaceId, id, meId }: { workspaceId: string; id: string; meId: string | undefined }) {
  const t = useT();
  const history = useDealHistory(workspaceId, id);
  const entries = (history.data?.pages ?? []).flatMap((page) => page.items);
  return (
    <section className="drawer-section" aria-labelledby="deal-history-title">
      <h2 id="deal-history-title" className="drawer-section-title">
        {t("deals.history.title")}
      </h2>
      {history.isPending ? (
        <Loading />
      ) : history.isError && !history.data ? (
        <LoadError error={history.error} onRetry={() => void history.refetch()} />
      ) : (
        <ol className="deal-history">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span>{eventText(t, entry, meId)}</span>
              <span className="deal-history-meta">
                {ownerLabel(t, entry.actor_user_id, meId)} · <When value={entry.occurred_at} />
              </span>
            </li>
          ))}
        </ol>
      )}
      {history.hasNextPage ? (
        <Button size="sm" onPress={() => void history.fetchNextPage()} isDisabled={history.isFetchingNextPage}>
          {t("records.loadMore")}
        </Button>
      ) : null}
    </section>
  );
}

function LostDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const t = useT();
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setMissing(true);
      return;
    }
    onConfirm(trimmed);
  };
  return (
    <Dialog
      isOpen
      title={t("deals.lostTitle")}
      onClose={onCancel}
      actions={
        <>
          <Button onPress={onCancel}>{t("confirm.cancel")}</Button>
          <Button variant="destructive" type="submit" form="deal-lost-form" isDisabled={busy}>
            {t("deals.markLost")}
          </Button>
        </>
      }
    >
      <form id="deal-lost-form" onSubmit={submit} noValidate>
        <div className="form-field">
          <label htmlFor="deal-lost-reason" className="form-label">
            {t("deals.lostReason")}
          </label>
          <textarea
            id="deal-lost-reason"
            className="form-input form-textarea"
            value={reason}
            maxLength={500}
            rows={3}
            required
            {...(missing ? { "aria-invalid": true, "aria-describedby": "deal-lost-reason-error" } : {})}
            onChange={(event) => {
              setReason(event.target.value);
              setMissing(false);
            }}
          />
          {missing ? (
            <span id="deal-lost-reason-error" className="form-error">
              {t("deals.error.reason")}
            </span>
          ) : null}
        </div>
      </form>
    </Dialog>
  );
}
