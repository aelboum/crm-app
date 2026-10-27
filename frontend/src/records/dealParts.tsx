import { type IntlShape, useIntl } from "react-intl";

import { type Deal, type DealEvent, IDLE_DAYS, minorDigits } from "../api/opportunities";
import type { MessageId } from "../i18n/en";
import type { useT } from "../i18n/useT";
import { ownerLabel } from "./parts";

type T = ReturnType<typeof useT>;

/*
 * Shared pieces of the Opportunities screens (decision P4-B): money in a
 * deal's own currency, days in the current stage, the design's stage shades
 * and the history's sentences. Amounts arrive as decimal strings; they are
 * formatted from the string itself and never computed with here.
 */

/** The design's column shades, lightest first; later stages are darker. */
const SHADES = ["#A9B4C4", "#7F93B0", "#5A7AA6", "#3E5F92", "#2B4A7A"];

export function stageShade(position: number, count: number): string {
  if (count <= 1) return SHADES[2] ?? "#5A7AA6";
  const index = Math.round((position / (count - 1)) * (SHADES.length - 1));
  return SHADES[Math.min(index, SHADES.length - 1)] ?? "#5A7AA6";
}

/** An amount in its currency, in the user's locale ("€12,500.50"). */
export function Money({ amount, currency }: { amount: string | null | undefined; currency: string }) {
  const intl = useIntl();
  if (amount === null || amount === undefined) return <span className="muted">—</span>;
  return <>{formatMoney(intl.formatNumber, amount, currency)}</>;
}

type Format = IntlShape["formatNumber"];

export function formatMoney(format: Format, amount: string, currency: string): string {
  const digits = minorDigits(currency);
  // The decimal string itself is formatted: no floating point on the way.
  return format(amount as `${number}`, {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Whole days the open deal has been in its stage; null when closed. */
export function daysInStage(deal: Deal, now: number = Date.now()): number | null {
  if (deal.outcome !== "open") return null;
  return Math.max(0, Math.floor((now - Date.parse(deal.stage_entered_at)) / 86_400_000));
}

export function isIdle(deal: Deal): boolean {
  const days = daysInStage(deal);
  return days !== null && days >= IDLE_DAYS;
}

const FIELD_LABEL: Partial<Record<string, MessageId>> = {
  title: "deals.field.titleShort",
  amount: "deals.field.valueShort",
  expected_close_date: "deals.field.close",
  contact_id: "deals.field.contact",
  company_id: "deals.field.company",
};

/** One history entry as a sentence. */
export function eventText(t: T, event: DealEvent, meId: string | undefined): string {
  switch (event.kind) {
    case "created":
      return t("deals.history.created", { stage: event.stage_to_name ?? "" });
    case "updated":
      return t("deals.history.updated", {
        fields: (event.fields ?? [])
          .map((field) => {
            const label = FIELD_LABEL[field];
            return label ? t(label) : field;
          })
          .join(", "),
      });
    case "stage_changed":
      return t(event.stage_cause === "stage_removed" ? "deals.history.stageRemoved" : "deals.history.moved", {
        from: event.stage_from_name ?? "",
        to: event.stage_to_name ?? "",
      });
    case "owner_changed":
      return t("deals.history.owner", { owner: ownerLabel(t, event.owner_to, meId) });
    case "outcome_changed":
      if (event.outcome_to === "won") return t("deals.history.won");
      if (event.outcome_to === "lost") return t("deals.history.lost");
      return t("deals.history.reopened");
    default:
      return event.kind;
  }
}
