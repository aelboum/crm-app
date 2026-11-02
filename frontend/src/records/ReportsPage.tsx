import { Download } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { useIntl } from "react-intl";
import { Button as AriaButton } from "react-aria-components";

import { fileDownload } from "../api/exportContacts";
import {
  type AppointmentReport,
  daysBefore,
  daysIn,
  type DealReport,
  exportReport,
  MAX_DAYS,
  type Period,
  type ReportKind,
  type TaskReport,
  todayIn,
  useAppointmentReport,
  useContactReport,
  useDealReport,
  useTaskReport,
} from "../api/reports";
import { useMe, useWorkspaceSettings } from "../api/queries";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { STATUS_LABEL } from "./appointmentParts";
import { formatMoney } from "./dealParts";
import { ownerLabel } from "./parts";

/*
 * Reports (decision P10-A): what happened in a period of whole days in the
 * workspace's time zone, against the same number of days before it. Every
 * figure has a written definition next to it and is counted by the server
 * from stored rows; each card loads and fails on its own. The design's
 * lead-source costs, first-reply times, conversations, reviews and agency
 * comparison are not shown: their data does not exist. No export yet.
 */

type Preset = 7 | 30 | 90;
const PRESETS: Preset[] = [7, 30, 90];

type Status = keyof typeof STATUS_LABEL;

function presetPeriod(today: string, days: number): Period {
  return { start: daysBefore(today, days - 1), end: today };
}

export function ReportsPage({ workspaceId }: { workspaceId: string }) {
  const t = useT();
  const settings = useWorkspaceSettings(workspaceId);
  const [now] = useState(() => new Date());
  const [preset, setPreset] = useState<Preset | "custom">(30);
  const [custom, setCustom] = useState<Period | null>(null);
  if (settings.isPending) return <Loading />;
  const today = todayIn(settings.data?.time_zone, now);
  const period =
    preset === "custom" && custom
      ? custom
      : presetPeriod(today, preset === "custom" ? 30 : preset);
  return (
    <div className="records-page reports-page">
      <div className="records-head">
        <div className="records-head-text">
          <p className="records-kicker">{t("nav.group.insights")}</p>
          <h1 className="records-title">{t("nav.reports")}</h1>
        </div>
      </div>
      <PeriodPicker
        preset={preset}
        period={period}
        onPreset={(next) => {
          setPreset(next);
        }}
        onCustom={(next) => {
          setCustom(next);
          setPreset("custom");
        }}
      />
      <p className="muted reports-note">
        {t("reports.periodNote", {
          days: daysIn(period),
          zone: settings.data?.time_zone ?? "",
        })}
      </p>
      <Headlines workspaceId={workspaceId} period={period} />
      <div className="home-grid reports-grid">
        <ContactsCard workspaceId={workspaceId} period={period} />
        <DealsCard workspaceId={workspaceId} period={period} />
        <TasksCard workspaceId={workspaceId} period={period} />
        <AppointmentsCard workspaceId={workspaceId} period={period} />
        <TeamCard workspaceId={workspaceId} period={period} />
      </div>
    </div>
  );
}

function PeriodPicker({
  preset,
  period,
  onPreset,
  onCustom,
}: {
  preset: Preset | "custom";
  period: Period;
  onPreset: (preset: Preset) => void;
  onCustom: (period: Period) => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Period>(period);
  const [problem, setProblem] = useState<MessageId | null>(null);
  function apply() {
    if (!draft.start || !draft.end) {
      setProblem("reports.custom.required");
    } else if (draft.end < draft.start) {
      setProblem("reports.custom.order");
    } else if (daysIn(draft) > MAX_DAYS) {
      setProblem("reports.custom.long");
    } else {
      setProblem(null);
      onCustom(draft);
    }
  }
  return (
    <div className="reports-period">
      <div className="segmented" role="group" aria-label={t("reports.period")}>
        {PRESETS.map((days) => (
          <AriaButton
            key={days}
            className={preset === days ? "segment active" : "segment"}
            aria-pressed={preset === days}
            onPress={() => {
              onPreset(days);
            }}
          >
            {t("reports.lastDays", { count: days })}
          </AriaButton>
        ))}
      </div>
      <form
        className="reports-custom"
        aria-label={t("reports.custom")}
        onSubmit={(event) => {
          event.preventDefault();
          apply();
        }}
      >
        <label>
          <span>{t("reports.custom.start")}</span>
          <input
            type="date"
            value={draft.start}
            aria-invalid={problem !== null}
            aria-describedby={problem ? "reports-custom-problem" : undefined}
            onChange={(event) => {
              setDraft({ ...draft, start: event.target.value });
            }}
          />
        </label>
        <label>
          <span>{t("reports.custom.end")}</span>
          <input
            type="date"
            value={draft.end}
            aria-invalid={problem !== null}
            aria-describedby={problem ? "reports-custom-problem" : undefined}
            onChange={(event) => {
              setDraft({ ...draft, end: event.target.value });
            }}
          />
        </label>
        <Button
          size="sm"
          type="submit"
          variant={preset === "custom" ? "secondary" : "ghost"}
        >
          {t("reports.custom.apply")}
        </Button>
        {problem ? (
          <p id="reports-custom-problem" className="field-error" role="alert">
            {t(problem)}
          </p>
        ) : null}
      </form>
    </div>
  );
}

function Card({
  id,
  title,
  children,
  csv,
}: {
  id: string;
  title: string;
  children: ReactNode;
  // The card's figures as a CSV download (decision P10-B).
  csv?: { workspaceId: string; kind: ReportKind; period: Period };
}) {
  return (
    <section className="home-card" aria-labelledby={id}>
      <div className="home-card-head">
        <h2 id={id} className="home-card-title">
          {title}
        </h2>
        {csv ? <CsvButton {...csv} title={title} /> : null}
      </div>
      {children}
    </section>
  );
}

function CsvButton({
  workspaceId,
  kind,
  period,
  title,
}: {
  workspaceId: string;
  kind: ReportKind;
  period: Period;
  title: string;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <span className="report-csv">
      <Button
        size="sm"
        aria-label={t("reports.csvNamed", { report: title })}
        isDisabled={busy}
        onPress={() => {
          setBusy(true);
          setFailed(false);
          exportReport(workspaceId, kind, period)
            .then(({ blob, fileName }) => {
              fileDownload.save(blob, fileName);
            })
            .catch(() => {
              setFailed(true);
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        <Download size={13} aria-hidden="true" />
        {t("reports.csv")}
      </Button>
      {failed ? (
        <span className="notice error" role="alert">
          {t("reports.csvFailed")}
        </span>
      ) : null}
    </span>
  );
}

function Capped({ capped }: { capped: boolean }) {
  const t = useT();
  return capped ? <p className="notice info">{t("reports.capped")}</p> : null;
}

/** "Previous 30 days: 12", or nothing when there is no comparison. */
function Before({ value, days }: { value: string | null; days: number }) {
  const t = useT();
  return value === null ? null : <>{t("reports.before", { days, value })}</>;
}

function Headlines({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const intl = useIntl();
  const contacts = useContactReport(workspaceId, period);
  const deals = useDealReport(workspaceId, period);
  const tasks = useTaskReport(workspaceId, period);
  const appointments = useAppointmentReport(workspaceId, period);
  const days = daysIn(period);
  const n = (value: number) => intl.formatNumber(value);
  const percent = (value: number | null | undefined) =>
    value === null || value === undefined ? "—" : `${n(value)}%`;
  const tiles: {
    key: string;
    label: MessageId;
    value: string | null;
    note: ReactNode;
    failed: boolean;
  }[] = [
    {
      key: "contacts",
      label: "reports.kpi.contacts",
      value: contacts.data ? n(contacts.data.created) : null,
      note: contacts.data ? (
        <Before days={days} value={n(contacts.data.created_before)} />
      ) : null,
      failed: contacts.isError,
    },
    {
      key: "won",
      label: "reports.kpi.won",
      value: deals.data ? n(deals.data.won) : null,
      note: deals.data ? (
        <Before days={days} value={n(deals.data.won_before)} />
      ) : null,
      failed: deals.isError,
    },
    {
      key: "rate",
      label: "reports.kpi.winRate",
      value: deals.data ? percent(deals.data.win_rate) : null,
      note: deals.data ? (
        <Before days={days} value={percent(deals.data.win_rate_before)} />
      ) : null,
      failed: deals.isError,
    },
    {
      key: "tasks",
      label: "reports.kpi.completed",
      value: tasks.data ? n(tasks.data.completed) : null,
      note: tasks.data ? (
        <Before days={days} value={n(tasks.data.completed_before)} />
      ) : null,
      failed: tasks.isError,
    },
    {
      key: "appointments",
      label: "reports.kpi.held",
      value: appointments.data ? n(appointments.data.held) : null,
      note: appointments.data ? (
        <Before days={days} value={n(appointments.data.held_before)} />
      ) : null,
      failed: appointments.isError,
    },
  ];
  return (
    <section aria-label={t("reports.kpis")}>
      <ul className="home-kpis reports-kpis">
        {tiles.map((tile) => (
          <li key={tile.key}>
            <div className="home-kpi">
              <span className="home-kpi-label">{t(tile.label)}</span>
              <span className="home-kpi-value">
                {tile.failed ? "—" : (tile.value ?? "…")}
              </span>
              <span
                className={
                  tile.failed ? "home-kpi-note error" : "home-kpi-note"
                }
              >
                {tile.failed ? t("dash.failed") : tile.note}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Bars({
  rows,
}: {
  rows: { key: string; label: string; value: number }[];
}) {
  const intl = useIntl();
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <ul className="home-stages">
      {rows.map((row) => (
        <li key={row.key} className="home-stage">
          <span className="home-stage-name">{row.label}</span>
          <span className="home-stage-value">
            {intl.formatNumber(row.value)}
          </span>
          <span className="home-stage-bar" aria-hidden="true">
            <span
              style={{
                width: `${String((row.value / max) * 100)}%`,
                background: "var(--accent)",
              }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

function ContactsCard({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const report = useContactReport(workspaceId, period);
  return (
    <Card
      id="reports-contacts"
      title={t("reports.contacts")}
      csv={{ workspaceId, kind: "contacts", period }}
    >
      {report.isError ? (
        <LoadError error={report.error} onRetry={() => void report.refetch()} />
      ) : report.data ? (
        <>
          <Capped capped={report.data.capped} />
          {report.data.sources.length ? (
            <Bars
              rows={report.data.sources.map((row) => ({
                key: row.source,
                label: t(`source.${row.source}` as MessageId),
                value: row.count,
              }))}
            />
          ) : (
            <p className="muted">{t("reports.contacts.none")}</p>
          )}
          <p className="muted reports-definition">
            {t("reports.contacts.definition")}
          </p>
        </>
      ) : (
        <Loading />
      )}
    </Card>
  );
}

function Amounts({ values }: { values: DealReport["won_value"] }) {
  const intl = useIntl();
  if (!values.length) return <>—</>;
  return (
    <>
      {values
        .map((v) => formatMoney(intl.formatNumber, v.amount, v.currency))
        .join(" · ")}
    </>
  );
}

function DealsCard({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const intl = useIntl();
  const report = useDealReport(workspaceId, period);
  const data = report.data;
  return (
    <Card
      id="reports-deals"
      title={t("reports.deals")}
      csv={{ workspaceId, kind: "deals", period }}
    >
      {report.isError ? (
        <LoadError error={report.error} onRetry={() => void report.refetch()} />
      ) : data ? (
        <>
          <Capped capped={data.capped} />
          <dl className="reports-figures">
            <dt>{t("reports.deals.created")}</dt>
            <dd>{intl.formatNumber(data.created)}</dd>
            <dt>{t("reports.deals.won")}</dt>
            <dd>
              {intl.formatNumber(data.won)} ·{" "}
              <Amounts values={data.won_value} />
            </dd>
            <dt>{t("reports.deals.lost")}</dt>
            <dd>
              {intl.formatNumber(data.lost)} ·{" "}
              <Amounts values={data.lost_value} />
            </dd>
          </dl>
          <p className="muted reports-definition">
            {t("reports.deals.definition")}
          </p>
        </>
      ) : (
        <Loading />
      )}
    </Card>
  );
}

function TasksCard({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const intl = useIntl();
  const report = useTaskReport(workspaceId, period);
  const data: TaskReport | undefined = report.data;
  return (
    <Card
      id="reports-tasks"
      title={t("reports.tasks")}
      csv={{ workspaceId, kind: "tasks", period }}
    >
      {report.isError ? (
        <LoadError error={report.error} onRetry={() => void report.refetch()} />
      ) : data ? (
        <>
          <Capped capped={data.capped} />
          <dl className="reports-figures">
            <dt>{t("reports.tasks.created")}</dt>
            <dd>{intl.formatNumber(data.created)}</dd>
            <dt>{t("reports.tasks.onTime")}</dt>
            <dd>{intl.formatNumber(data.on_time)}</dd>
            <dt>{t("reports.tasks.late")}</dt>
            <dd>{intl.formatNumber(data.late)}</dd>
            <dt>{t("reports.tasks.noDue")}</dt>
            <dd>{intl.formatNumber(data.no_due)}</dd>
            <dt>{t("reports.tasks.overdue")}</dt>
            <dd>{intl.formatNumber(data.overdue_now)}</dd>
          </dl>
          <p className="muted reports-definition">
            {t("reports.tasks.definition")}
          </p>
        </>
      ) : (
        <Loading />
      )}
    </Card>
  );
}

function AppointmentsCard({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const intl = useIntl();
  const report = useAppointmentReport(workspaceId, period);
  const data: AppointmentReport | undefined = report.data;
  return (
    <Card
      id="reports-appointments"
      title={t("reports.appointments")}
      csv={{ workspaceId, kind: "appointments", period }}
    >
      {report.isError ? (
        <LoadError error={report.error} onRetry={() => void report.refetch()} />
      ) : data ? (
        <>
          <Capped capped={data.capped} />
          {data.statuses.length ? (
            <Bars
              rows={data.statuses.map((row) => ({
                key: row.status,
                label: t(STATUS_LABEL[row.status as Status]),
                value: row.count,
              }))}
            />
          ) : (
            <p className="muted">{t("reports.appointments.none")}</p>
          )}
          <p className="reports-line">
            {t("reports.appointments.noShow", {
              value:
                data.no_show_rate === null
                  ? "—"
                  : `${intl.formatNumber(data.no_show_rate)}%`,
            })}
          </p>
          <p className="muted reports-definition">
            {t("reports.appointments.definition")}
          </p>
        </>
      ) : (
        <Loading />
      )}
    </Card>
  );
}

function TeamCard({
  workspaceId,
  period,
}: {
  workspaceId: string;
  period: Period;
}) {
  const t = useT();
  const intl = useIntl();
  const me = useMe();
  const meId = me.data?.user_id;
  const deals = useDealReport(workspaceId, period);
  const tasks = useTaskReport(workspaceId, period);
  const appointments = useAppointmentReport(workspaceId, period);
  const people = new Set<string>();
  const won = new Map<string, DealReport["owners"][number]>();
  const done = new Map<string, number>();
  const held = new Map<string, number>();
  for (const row of deals.data?.owners ?? []) {
    if (row.user_id) {
      people.add(row.user_id);
      won.set(row.user_id, row);
    }
  }
  for (const row of tasks.data?.completed_by ?? []) {
    if (row.user_id) {
      people.add(row.user_id);
      done.set(row.user_id, row.count);
    }
  }
  for (const row of appointments.data?.hosts ?? []) {
    if (row.user_id) {
      people.add(row.user_id);
      held.set(row.user_id, row.count);
    }
  }
  const cell = (failed: boolean, value: number | undefined) =>
    failed ? "—" : intl.formatNumber(value ?? 0);
  const loading = deals.isPending || tasks.isPending || appointments.isPending;
  return (
    <Card id="reports-team" title={t("reports.team")}>
      {loading ? (
        <Loading />
      ) : people.size ? (
        <div className="table-scroll">
          <table className="records-table reports-team">
            <thead>
              <tr>
                <th scope="col">{t("reports.team.member")}</th>
                <th scope="col" className="numeric">
                  {t("reports.team.won")}
                </th>
                <th scope="col" className="numeric">
                  {t("reports.team.value")}
                </th>
                <th scope="col" className="numeric">
                  {t("reports.team.tasks")}
                </th>
                <th scope="col" className="numeric">
                  {t("reports.team.appointments")}
                </th>
              </tr>
            </thead>
            <tbody>
              {[...people].map((id) => (
                <tr key={id}>
                  <th scope="row">{ownerLabel(t, id, meId)}</th>
                  <td className="numeric">
                    {cell(deals.isError, won.get(id)?.won)}
                  </td>
                  <td className="numeric">
                    {deals.isError ? (
                      "—"
                    ) : (
                      <Amounts values={won.get(id)?.won_value ?? []} />
                    )}
                  </td>
                  <td className="numeric">
                    {cell(tasks.isError, done.get(id))}
                  </td>
                  <td className="numeric">
                    {cell(appointments.isError, held.get(id))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">{t("reports.team.none")}</p>
      )}
      <p className="muted reports-definition">{t("reports.team.definition")}</p>
    </Card>
  );
}
