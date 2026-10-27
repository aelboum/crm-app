import { Calendar, Columns3, Hourglass, Plus, Search, Table2, User } from "lucide-react";
import { type DragEvent, useMemo, useState } from "react";
import { useIntl } from "react-intl";
import { Button as AriaButton } from "react-aria-components";

import { usePipelines, type Stage } from "../api/pipelines";
import {
  type Deal,
  type DealFilters,
  type DealSort,
  type DealSummary,
  minorDigits,
  type Outcome,
  useDealList,
  useDealSummary,
  useUpdateDeal,
} from "../api/opportunities";
import { useAccess, useMe, useMembers, useWorkspaceSettings } from "../api/queries";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { DealDialog, refusalOf } from "./DealDialog";
import { DealDrawer } from "./DealDrawer";
import { daysInStage, formatMoney, isIdle, Money, stageShade } from "./dealParts";
import { FilterMenu, OwnerCell, ownerOptions, SortHeader, When } from "./parts";
import { useDebounced } from "./useDebounced";

/*
 * Opportunities (ScreenPipeline.dc.html, decision P4-B): header with the
 * Board/Table switch and "New opportunity", the summary strip, search, owner
 * and "Idle 7+ days" filters, the board (a column per stage of the
 * workspace's one pipeline) and the table, and the deal drawer.
 *
 * The board and the table read the same list with the same filters; the
 * board's column counts and totals come from the summary for those filters,
 * so they count every matching deal, not only the cards loaded. The board
 * shows open deals; the table can also show won and lost ones.
 *
 * Differences from the design (DESIGN-FIDELITY.md): one pipeline, so no
 * pipeline switcher; no Won column (won and lost are outcomes); summary
 * metrics are those the API computes (open value, weighted forecast, open
 * deals), not "Avg. days in stage" or "Won this month"; cards can be dragged
 * between columns, and the drawer's stage buttons do the same from the
 * keyboard; members show by ID because member names are not stored.
 */

type View = "board" | "table";
type TableOutcome = Outcome | "all";

const OUTCOME_LABEL: Record<TableOutcome, MessageId> = {
  open: "deals.outcome.open",
  won: "deals.outcome.won",
  lost: "deals.outcome.lost",
  all: "deals.outcome.all",
};

export function OpportunitiesPage({
  workspaceId,
  openId,
  onOpen,
  startCreate,
  onCreateDone,
  onOpenContact,
  onOpenCompany,
}: {
  workspaceId: string;
  openId: string | null;
  onOpen: (id: string | null) => void;
  startCreate: boolean;
  onCreateDone: () => void;
  onOpenContact: (id: string) => void;
  onOpenCompany: (id: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const pipelines = usePipelines(workspaceId);
  const settings = useWorkspaceSettings(workspaceId);
  const [view, setView] = useState<View>("board");
  const [search, setSearch] = useState("");
  const [owners, setOwners] = useState<string[]>([]);
  const [idle, setIdle] = useState(false);
  const [outcome, setOutcome] = useState<TableOutcome>("open");
  const [sort, setSort] = useState<DealSort>("updated_at");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [dialog, setDialog] = useState<{ deal: Deal | null } | null>(startCreate ? { deal: null } : null);
  const q = useDebounced(search);
  const can = (action: string) => access.data?.actions[action] === true;
  const pipeline = pipelines.data?.items[0];
  const stages = pipeline?.stages ?? [];
  const currency = settings.data?.currency ?? "EUR";
  const ownerChoices = ownerOptions(t, members.data?.items ?? [], meId);

  const shown: Outcome[] = view === "board" ? ["open"] : outcome === "all" ? [] : [outcome];
  const filters: DealFilters = useMemo(
    () => ({ q, outcomes: shown, stageIds: [], owners, idle, sort, direction }),
    // `shown` is derived from view and outcome.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [q, view, outcome, owners, idle, sort, direction],
  );
  const openFilters: DealFilters = useMemo(() => ({ ...filters, outcomes: ["open"] }), [filters]);
  const list = useDealList(workspaceId, filters);
  const summary = useDealSummary(workspaceId, view === "board" ? filters : openFilters);
  const deals = (list.data?.pages ?? []).flatMap((page) => page.items);
  const first = list.data?.pages[0];
  const filtered = search !== "" || owners.length > 0 || idle;

  function toggleSort(next: DealSort) {
    if (next === sort) {
      setDirection(direction === "asc" ? "desc" : "asc");
    } else {
      setSort(next);
      setDirection(next === "title" || next === "expected_close_date" ? "asc" : "desc");
    }
  }

  const closeDialog = () => {
    setDialog(null);
    if (startCreate) onCreateDone();
  };

  return (
    <div className="records-page deals-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.crm")}</p>
          <h1 className="records-title">
            {t("nav.opportunities")}
            {pipeline ? <span className="deals-pipeline">{pipeline.name}</span> : null}
          </h1>
        </div>
        <div className="records-actions">
          <div className="segmented" role="group" aria-label={t("deals.view")}>
            {(["board", "table"] as const).map((v) => (
              <AriaButton
                key={v}
                className={view === v ? "segment active" : "segment"}
                aria-pressed={view === v}
                onPress={() => {
                  setView(v);
                }}
              >
                {v === "board" ? <Columns3 size={14} aria-hidden="true" /> : <Table2 size={14} aria-hidden="true" />}
                {t(v === "board" ? "deals.board" : "deals.table")}
              </AriaButton>
            ))}
          </div>
          {can("create_opportunity") ? (
            <Button
              variant="primary"
              isDisabled={stages.length === 0}
              onPress={() => {
                setDialog({ deal: null });
              }}
            >
              <Plus size={15} aria-hidden="true" />
              {t("deals.new")}
            </Button>
          ) : null}
        </div>
      </div>

      <SummaryStrip summary={summary.data} currency={currency} />

      <div className="records-toolbar">
        <label className="search-box">
          <Search size={14} aria-hidden="true" />
          <span className="sr-only">{t("deals.search")}</span>
          <input
            type="search"
            value={search}
            placeholder={t("deals.search")}
            maxLength={100}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </label>
        <FilterMenu
          label={t("records.field.owner")}
          icon={<User size={14} aria-hidden="true" />}
          options={ownerChoices.length ? ownerChoices : meId ? [{ id: meId, label: t("records.owner.me") }] : []}
          selected={owners}
          onChange={setOwners}
        />
        <AriaButton
          className={idle ? "chip active idle-chip" : "chip idle-chip"}
          aria-pressed={idle}
          onPress={() => {
            setIdle(!idle);
          }}
        >
          <Hourglass size={13} aria-hidden="true" />
          {t("deals.idle")}
        </AriaButton>
        {view === "table" ? (
          <div className="chip-group" role="group" aria-label={t("deals.outcome.label")}>
            {(["open", "won", "lost", "all"] as const).map((o) => (
              <AriaButton
                key={o}
                className={outcome === o ? "chip active" : "chip"}
                aria-pressed={outcome === o}
                onPress={() => {
                  setOutcome(o);
                }}
              >
                {t(OUTCOME_LABEL[o])}
              </AriaButton>
            ))}
          </div>
        ) : null}
        {filtered ? (
          <AriaButton
            className="text-button"
            onPress={() => {
              setSearch("");
              setOwners([]);
              setIdle(false);
            }}
          >
            {t("records.clear")}
          </AriaButton>
        ) : null}
        <span className="records-meta">
          {first
            ? t("records.shown", {
                shown: deals.length,
                total: first.total_capped ? t("records.capped") : String(first.total),
              })
            : null}
        </span>
      </div>

      {view === "board" ? (
        <p className="deals-hint">{can("update_opportunity") ? t("deals.dragHint") : t("deals.readOnlyHint")}</p>
      ) : null}

      {list.isPending || pipelines.isPending ? (
        <div className="records-card">
          <Loading />
        </div>
      ) : list.isError || pipelines.isError ? (
        <div className="records-card">
          <LoadError
            error={list.error ?? pipelines.error}
            onRetry={() => {
              void list.refetch();
              void pipelines.refetch();
            }}
          />
        </div>
      ) : view === "board" ? (
        <Board
          workspaceId={workspaceId}
          stages={stages}
          deals={deals}
          summary={summary.data}
          currency={currency}
          meId={meId}
          canMove={can("update_opportunity")}
          openId={openId}
          onOpen={onOpen}
        />
      ) : deals.length === 0 ? (
        <div className="records-card">
          <EmptyState
            title={filtered || outcome !== "open" ? t("deals.empty.filtered") : t("deals.empty.none")}
            {...(!filtered && outcome === "open" ? { body: t("deals.empty.noneBody") } : {})}
          />
        </div>
      ) : (
        <DealTable
          deals={deals}
          stages={stages}
          meId={meId}
          sort={sort}
          direction={direction}
          openId={openId}
          onSort={toggleSort}
          onOpen={onOpen}
        />
      )}
      {list.hasNextPage ? (
        <div className="records-footer">
          <Button size="sm" onPress={() => void list.fetchNextPage()} isDisabled={list.isFetchingNextPage}>
            {t("records.loadMore")}
          </Button>
        </div>
      ) : null}

      {openId ? (
        <DealDrawer
          workspaceId={workspaceId}
          id={openId}
          stages={stages}
          meId={meId}
          canUpdate={can("update_opportunity")}
          canDelete={can("delete_opportunity")}
          onClose={() => {
            onOpen(null);
          }}
          onEdit={(deal) => {
            setDialog({ deal });
          }}
          onOpenContact={onOpenContact}
          onOpenCompany={onOpenCompany}
        />
      ) : null}
      {dialog ? (
        <DealDialog
          workspaceId={workspaceId}
          deal={dialog.deal}
          stages={stages}
          currency={currency}
          owners={ownerChoices}
          meId={meId}
          onClose={closeDialog}
          onSaved={(saved) => {
            closeDialog();
            onOpen(saved.id);
          }}
        />
      ) : null}
    </div>
  );
}

/** Totals per currency, the workspace's first. */
function totalsOf(summary: DealSummary | undefined, currency: string) {
  const sums = new Map<string, { text: string[]; weightedText: string[] }>();
  let count = 0;
  for (const stage of summary?.stages ?? []) {
    count += stage.count;
    for (const total of stage.totals) {
      const entry = sums.get(total.currency) ?? { text: [], weightedText: [] };
      entry.text.push(total.amount);
      entry.weightedText.push(total.weighted_amount);
      sums.set(total.currency, entry);
    }
  }
  const currencies = [...sums.keys()].sort((a, b) => (a === currency ? -1 : b === currency ? 1 : a.localeCompare(b)));
  return { count, currencies, sums };
}

/** Exact decimal addition of amount strings (no floating point). */
function addDecimals(values: string[], digits: number): string {
  const scale = 10n ** BigInt(digits);
  let total = 0n;
  for (const value of values) {
    const [whole = "0", fraction = ""] = value.split(".");
    total += BigInt(whole) * scale + BigInt((fraction + "0".repeat(digits)).slice(0, digits) || "0");
  }
  const text = total.toString().padStart(digits + 1, "0");
  return digits === 0 ? text : `${text.slice(0, -digits)}.${text.slice(-digits)}`;
}

function SummaryStrip({ summary, currency }: { summary: DealSummary | undefined; currency: string }) {
  const t = useT();
  const intl = useIntl();
  const { count, currencies, sums } = totalsOf(summary, currency);
  const money = (pick: "text" | "weightedText") =>
    currencies.length === 0
      ? formatMoney(intl.formatNumber, "0", currency)
      : currencies
          .map((code) => {
            const values = sums.get(code)?.[pick] ?? [];
            return formatMoney(intl.formatNumber, addDecimals(values, minorDigits(code)), code);
          })
          .join(" · ");
  const items: [MessageId, string][] = [
    ["deals.summary.open", money("text")],
    ["deals.summary.weighted", money("weightedText")],
    ["deals.summary.count", String(count)],
  ];
  return (
    <dl className="deals-summary">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{t(label)}</dt>
          <dd>{summary ? value : "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

function Board({
  workspaceId,
  stages,
  deals,
  summary,
  currency,
  meId,
  canMove,
  openId,
  onOpen,
}: {
  workspaceId: string;
  stages: Stage[];
  deals: Deal[];
  summary: DealSummary | undefined;
  currency: string;
  meId: string | undefined;
  canMove: boolean;
  openId: string | null;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const intl = useIntl();
  const toast = useToast();
  const update = useUpdateDeal(workspaceId);
  const [over, setOver] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<MessageId | null>(null);

  function drop(event: DragEvent, stage: Stage) {
    event.preventDefault();
    setOver(null);
    const id = event.dataTransfer.getData("text/plain");
    const deal = deals.find((d) => d.id === id);
    if (!deal || deal.stage_id === stage.id) return;
    setRefusal(null);
    update.mutate(
      { id: deal.id, version: deal.version, changes: { stage_id: stage.id } },
      {
        onSuccess: () => {
          toast(t("deals.moved", { title: deal.title, stage: stage.name }));
        },
        onError: (error) => {
          setRefusal(refusalOf(error));
        },
      },
    );
  }

  const column = (stageId: string) => summary?.stages.find((s) => s.stage_id === stageId);
  return (
    <>
      {refusal ? (
        <p className="notice error records-notice" role="alert">
          {t(refusal)}
        </p>
      ) : null}
      <div className="deal-board" role="list" aria-label={t("deals.board")}>
        {stages.map((stage) => {
          const cards = deals.filter((deal) => deal.stage_id === stage.id);
          const info = column(stage.id);
          const own = info?.totals.find((total) => total.currency === currency) ?? info?.totals[0];
          return (
            // Dropping a dragged card is the mouse path; the drawer's stage
            // buttons are the keyboard path to the same change.
            // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
            <div
              key={stage.id}
              role="listitem"
              aria-labelledby={`stage-${stage.id}`}
              className={over === stage.id ? "deal-column over" : "deal-column"}
              onDragOver={
                canMove
                  ? (event) => {
                      event.preventDefault();
                      if (over !== stage.id) setOver(stage.id);
                    }
                  : undefined
              }
              onDragLeave={() => {
                setOver(null);
              }}
              onDrop={
                canMove
                  ? (event) => {
                      drop(event, stage);
                    }
                  : undefined
              }
            >
              <header className="deal-column-head">
                <h2 id={`stage-${stage.id}`} className="deal-column-title">
                  <span
                    className="stage-dot"
                    style={{ background: stageShade(stage.position, stages.length) }}
                    aria-hidden="true"
                  />
                  <span className="deal-column-name">{stage.name}</span>
                  <span className="deal-column-count">{info?.count ?? cards.length}</span>
                </h2>
                <p className="deal-column-meta">
                  <span className="deal-column-total">
                    {own ? formatMoney(intl.formatNumber, own.amount, own.currency) : formatMoney(intl.formatNumber, "0", currency)}
                    {info && info.totals.length > 1 ? ` ${t("deals.moreCurrencies")}` : ""}
                  </span>
                  <span>{t("deals.probability", { value: stage.probability })}</span>
                </p>
              </header>
              <ul className="deal-cards" aria-label={stage.name}>
                {cards.map((deal) => (
                  // Dragging is the mouse path; the title button opens the
                  // drawer, whose stage buttons do the same from the keyboard.
                  // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
                  <li
                    key={deal.id}
                    className={deal.id === openId ? "deal-card selected" : "deal-card"}
                    draggable={canMove}
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", deal.id);
                      event.dataTransfer.effectAllowed = "move";
                    }}
                  >
                    <AriaButton
                      className="deal-card-title record-link"
                      onPress={() => {
                        onOpen(deal.id);
                      }}
                    >
                      {deal.title}
                    </AriaButton>
                    {deal.contact ?? deal.company ? (
                      <span className="deal-card-sub">{(deal.contact ?? deal.company)?.name}</span>
                    ) : null}
                    <span className="deal-card-meta">
                      <span className="deal-card-value">
                        <Money amount={deal.amount} currency={deal.currency} />
                      </span>
                      {isIdle(deal) ? (
                        <span className="idle-badge">{t("deals.idleDays", { count: daysInStage(deal) ?? 0 })}</span>
                      ) : null}
                      {deal.expected_close_date ? (
                        <span className="deal-card-close">
                          <Calendar size={11} aria-hidden="true" />
                          <When value={`${deal.expected_close_date}T12:00:00`} />
                        </span>
                      ) : null}
                      <OwnerCell ownerId={deal.owner_user_id} meId={meId} />
                    </span>
                  </li>
                ))}
                {cards.length === 0 ? <li className="deal-empty">{t("deals.emptyStage")}</li> : null}
              </ul>
            </div>
          );
        })}
      </div>
    </>
  );
}

function DealTable({
  deals,
  stages,
  meId,
  sort,
  direction,
  openId,
  onSort,
  onOpen,
}: {
  deals: Deal[];
  stages: Stage[];
  meId: string | undefined;
  sort: DealSort;
  direction: "asc" | "desc";
  openId: string | null;
  onSort: (sort: DealSort) => void;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const ariaSort = (column: DealSort) =>
    sort === column ? (direction === "asc" ? "ascending" : "descending") : undefined;
  const header = (column: DealSort, label: MessageId) => (
    <SortHeader
      label={t(label)}
      active={sort === column}
      direction={direction}
      onSort={() => {
        onSort(column);
      }}
    />
  );
  return (
    <div className="records-card">
      <div className="table-scroll">
        <table className="records-table deals-table">
          <caption className="sr-only">{t("nav.opportunities")}</caption>
          <thead>
            <tr>
              <th scope="col" aria-sort={ariaSort("title")}>
                {header("title", "deals.col.deal")}
              </th>
              <th scope="col" className="hide-narrow">
                {t("deals.field.contact")}
              </th>
              <th scope="col">{t("deals.field.stage")}</th>
              <th scope="col" className="numeric" aria-sort={ariaSort("amount")}>
                {header("amount", "deals.field.valueShort")}
              </th>
              <th scope="col" className="numeric hide-narrow">
                {t("deals.col.probability")}
              </th>
              <th scope="col" aria-sort={ariaSort("expected_close_date")}>
                {header("expected_close_date", "deals.field.close")}
              </th>
              <th scope="col" className="hide-narrow">
                {t("records.field.owner")}
              </th>
              <th scope="col" className="numeric hide-narrow">
                {t("deals.col.days")}
              </th>
            </tr>
          </thead>
          <tbody>
            {deals.map((deal) => {
              const days = daysInStage(deal);
              return (
                // Row clicks mirror the title button, which is the keyboard path.
                <tr
                  key={deal.id}
                  className={deal.id === openId ? "selected" : undefined}
                  onClick={() => {
                    onOpen(deal.id);
                  }}
                >
                  <td>
                    <AriaButton
                      className="record-link"
                      onPress={() => {
                        onOpen(deal.id);
                      }}
                    >
                      {deal.title}
                    </AriaButton>
                  </td>
                  <td className="secondary hide-narrow">{deal.contact?.name ?? deal.company?.name ?? "—"}</td>
                  <td>
                    <span className="stage-cell">
                      <span
                        className="stage-dot"
                        style={{ background: stageShade(deal.stage.position, stages.length) }}
                        aria-hidden="true"
                      />
                      {deal.stage.name}
                      {deal.outcome !== "open" ? (
                        <span className={`outcome-tag ${deal.outcome}`}>
                          {t(deal.outcome === "won" ? "deals.outcome.won" : "deals.outcome.lost")}
                        </span>
                      ) : null}
                    </span>
                  </td>
                  <td className="numeric strong">
                    <Money amount={deal.amount} currency={deal.currency} />
                  </td>
                  <td className="numeric hide-narrow secondary">
                    {deal.outcome === "open" ? `${String(deal.stage.probability)}%` : "—"}
                  </td>
                  <td className="secondary">
                    {deal.expected_close_date ? <When value={`${deal.expected_close_date}T12:00:00`} /> : "—"}
                  </td>
                  <td className="hide-narrow">
                    <OwnerCell ownerId={deal.owner_user_id} meId={meId} />
                  </td>
                  <td className={days !== null && days >= 7 ? "numeric hide-narrow idle-text" : "numeric hide-narrow secondary"}>
                    {days === null ? "—" : t("deals.daysShort", { count: days })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
