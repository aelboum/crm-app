import {
  Activity,
  Bot,
  Building2,
  Calendar,
  ChartColumn,
  FileText,
  House,
  Inbox,
  Kanban,
  Library,
  type LucideIcon,
  Megaphone,
  SquareCheckBig,
  Star,
  Users,
  Workflow,
} from "lucide-react";

import type { MessageId } from "../i18n/en";

/**
 * The client-workspace navigation exactly as the design defines it
 * (`CLIENT_NAV` in LeadStack CRM.dc.html): same groups, order, labels and
 * Lucide icons. A module that is not built is marked "soon" in the sidebar,
 * as the design itself does for unbuilt modules (`showPreview`), and opens
 * the design's placeholder page with an honest description.
 */
export interface Section {
  slug: string;
  label: MessageId;
  icon: LucideIcon;
  /** The placeholder page's description, or null when the module works. */
  unavailable: MessageId | null;
}

export interface Group {
  key: string;
  label: MessageId | null;
  sections: Section[];
}

const soon = (slug: string, label: MessageId, icon: LucideIcon, why: MessageId): Section => ({
  slug,
  label,
  icon,
  unavailable: why,
});

const built = (slug: string, label: MessageId, icon: LucideIcon): Section => ({
  slug,
  label,
  icon,
  unavailable: null,
});

export const GROUPS: Group[] = [
  {
    key: "g0",
    label: null,
    sections: [
      soon("home", "nav.home", House, "soon.home"),
      soon("inbox", "nav.inbox", Inbox, "soon.inbox"),
    ],
  },
  {
    key: "crm",
    label: "nav.group.crm",
    sections: [
      built("contacts", "nav.contacts", Users),
      built("companies", "nav.companies", Building2),
      soon("opportunities", "nav.opportunities", Kanban, "soon.sales"),
      soon("tasks", "nav.tasks", SquareCheckBig, "soon.sales"),
    ],
  },
  {
    key: "sched",
    label: "nav.group.scheduling",
    sections: [soon("calendar", "nav.calendar", Calendar, "soon.later")],
  },
  {
    key: "mkt",
    label: "nav.group.marketing",
    sections: [
      soon("campaigns", "nav.campaigns", Megaphone, "soon.later"),
      soon("automations", "nav.automations", Workflow, "soon.later"),
      soon("forms", "nav.forms", FileText, "soon.forms"),
      soon("reviews", "nav.reviews", Star, "soon.deferred"),
    ],
  },
  {
    key: "ai",
    label: "nav.group.ai",
    sections: [
      soon("assistants", "nav.assistants", Bot, "soon.later"),
      soon("knowledge", "nav.knowledge", Library, "soon.later"),
      soon("ai-activity", "nav.aiActivity", Activity, "soon.later"),
    ],
  },
  {
    key: "ins",
    label: "nav.group.insights",
    sections: [soon("reports", "nav.reports", ChartColumn, "soon.later")],
  },
];

/** Settings, pinned to the bottom of the sidebar; today it holds Members. */
export const SETTINGS_SLUG = "settings";

export const ALL_SECTIONS: Section[] = GROUPS.flatMap((g) => g.sections);

export function findSection(slug: string): Section | undefined {
  return ALL_SECTIONS.find((s) => s.slug === slug);
}

export function findGroup(slug: string): Group | undefined {
  return GROUPS.find((g) => g.sections.some((s) => s.slug === slug));
}
