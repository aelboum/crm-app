import { useQueryClient } from "@tanstack/react-query";
import {
  createBrowserHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";
import { useEffect } from "react";

import { ApiError } from "./api/client";
import { keys } from "./api/queries";
import { LoadError } from "./components/StateNotice";
import { HomePage, isWorkspaceId } from "./pages/HomePage";
import { InvitePage } from "./pages/InvitePage";
import { PublicFormPage } from "./pages/PublicFormPage";
import { CompaniesPage } from "./records/CompaniesPage";
import { ContactsPage } from "./records/ContactsPage";
import { CalendarPage } from "./records/CalendarPage";
import { FormsPage } from "./records/FormsPage";
import { OpportunitiesPage } from "./records/OpportunitiesPage";
import { TasksPage } from "./records/TasksPage";
import { type SettingsSection, SettingsPage } from "./pages/WorkspacePage";
import { AppFrame, PlaceholderPage, PlainLayout } from "./shell/AppFrame";
import { findSection, SETTINGS_SLUG } from "./shell/navigation";

const rootRoute = createRootRoute({ component: Outlet });

const plainRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "plain",
  component: PlainLayout,
});

const homeRoute = createRoute({
  getParentRoute: () => plainRoute,
  path: "/",
  component: HomePage,
});

function InviteRoutePage() {
  const { workspaceId } = inviteRoute.useParams();
  return <InvitePage workspaceId={workspaceId} />;
}

// An invitation link (decisions Q4, Q5): /app/invite/<workspace>#<token>.
const inviteRoute = createRoute({
  getParentRoute: () => plainRoute,
  path: "/invite/$workspaceId",
  component: InviteRoutePage,
});

function PublicFormRoutePage() {
  const { workspaceId, formKey } = publicFormRoute.useParams();
  if (!isWorkspaceId(workspaceId)) {
    return (
      <main id="main" className="public-form-page">
        <div className="public-form-card">{notFound}</div>
      </main>
    );
  }
  return <PublicFormPage workspaceId={workspaceId} formKey={formKey} />;
}

// A published form's own page (decision P7-A 10): no app frame, no sign-in.
const publicFormRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/f/$workspaceId/$formKey",
  component: PublicFormRoutePage,
});

const notFound = <LoadError error={new ApiError(404)} onRetry={() => undefined} />;

function WorkspaceLayout() {
  const { workspaceId } = workspaceRoute.useParams();
  const client = useQueryClient();
  // No workspace's data outlives a switch to another one (PHASE2-PLAN.md §6.3).
  useEffect(
    () => () => {
      client.removeQueries({ queryKey: keys.workspace(workspaceId) });
    },
    [client, workspaceId],
  );
  // A malformed ID is answered like an unknown workspace, without a request.
  if (!isWorkspaceId(workspaceId)) {
    return (
      <main id="main" className="plain-main">
        {notFound}
      </main>
    );
  }
  return (
    <AppFrame key={workspaceId} workspaceId={workspaceId}>
      <Outlet />
    </AppFrame>
  );
}

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/w/$workspaceId",
  component: WorkspaceLayout,
});

const workspaceIndexRoute = createRoute({
  getParentRoute: () => workspaceRoute,
  path: "/",
  beforeLoad: ({ params }) => {
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- the router's redirect protocol
    throw redirect({
      to: "/w/$workspaceId/$section",
      params: { workspaceId: params.workspaceId, section: SETTINGS_SLUG },
      replace: true,
    });
  },
});

interface SectionSearch {
  section?: SettingsSection;
  /** The contact or company whose preview is open. */
  record?: string;
  /** Opens a new-record dialog (the header's "New" menu). */
  create?: "contact" | "opportunity";
}

function SectionPage() {
  const { workspaceId, section: slug } = sectionRoute.useParams();
  const { section: settingsSection, record, create } = sectionRoute.useSearch();
  const navigate = sectionRoute.useNavigate();
  const openRecord = (next: string | null) => {
    void navigate({ search: next ? { record: next } : {} });
  };
  if (slug === "contacts") {
    return (
      <ContactsPage
        workspaceId={workspaceId}
        openId={record ?? null}
        onOpen={openRecord}
        startCreate={create === "contact"}
        onCreateDone={() => {
          void navigate({ search: record ? { record } : {}, replace: true });
        }}
        onOpenAppointment={(id) => {
          void navigate({ params: { workspaceId, section: "calendar" }, search: { record: id } });
        }}
      />
    );
  }
  if (slug === "calendar") {
    return (
      <CalendarPage
        workspaceId={workspaceId}
        openId={record ?? null}
        onOpen={openRecord}
        onOpenContact={(id) => {
          void navigate({ params: { workspaceId, section: "contacts" }, search: { record: id } });
        }}
      />
    );
  }
  if (slug === "companies") {
    return (
      <CompaniesPage
        workspaceId={workspaceId}
        openId={record ?? null}
        onOpen={openRecord}
        onOpenContact={(id) => {
          void navigate({ params: { workspaceId, section: "contacts" }, search: { record: id } });
        }}
      />
    );
  }
  if (slug === "opportunities") {
    return (
      <OpportunitiesPage
        workspaceId={workspaceId}
        openId={record ?? null}
        onOpen={openRecord}
        startCreate={create === "opportunity"}
        onCreateDone={() => {
          void navigate({ search: record ? { record } : {}, replace: true });
        }}
        onOpenContact={(id) => {
          void navigate({ params: { workspaceId, section: "contacts" }, search: { record: id } });
        }}
        onOpenCompany={(id) => {
          void navigate({ params: { workspaceId, section: "companies" }, search: { record: id } });
        }}
      />
    );
  }
  if (slug === "tasks") {
    return (
      <TasksPage
        workspaceId={workspaceId}
        onOpenLink={(kind, id) => {
          const target = kind === "contact" ? "contacts" : kind === "company" ? "companies" : "opportunities";
          void navigate({ params: { workspaceId, section: target }, search: { record: id } });
        }}
      />
    );
  }
  if (slug === "forms") {
    return (
      <FormsPage
        workspaceId={workspaceId}
        formId={record}
        onOpen={(id) => {
          void navigate({ search: id ? { record: id } : {} });
        }}
        onOpenContact={(id) => {
          void navigate({ params: { workspaceId, section: "contacts" }, search: { record: id } });
        }}
      />
    );
  }
  // Settings holds Team & roles and My profile today; every other module is
  // the design's placeholder.
  if (slug === SETTINGS_SLUG) {
    return (
      <SettingsPage
        workspaceId={workspaceId}
        section={settingsSection ?? "team"}
        onSelect={(next) => {
          void navigate({ search: next === "team" ? {} : { section: next } });
        }}
      />
    );
  }
  const section = findSection(slug);
  return section ? <PlaceholderPage section={section} /> : notFound;
}

const sectionRoute = createRoute({
  getParentRoute: () => workspaceRoute,
  path: "$section",
  // Only known settings sections and well-formed record IDs are accepted;
  // anything else is dropped.
  validateSearch: (search: Record<string, unknown>): SectionSearch => ({
    ...(search.section === "profile" ||
    search.section === "business" ||
    search.section === "tags" ||
    search.section === "fields" ||
    search.section === "pipeline"
      ? { section: search.section }
      : {}),
    ...(typeof search.record === "string" && isWorkspaceId(search.record) ? { record: search.record } : {}),
    ...(search.create === "contact" || search.create === "opportunity" ? { create: search.create } : {}),
  }),
  component: SectionPage,
});

const routeTree = rootRoute.addChildren([
  plainRoute.addChildren([homeRoute, inviteRoute]),
  workspaceRoute.addChildren([workspaceIndexRoute, sectionRoute]),
  publicFormRoute,
]);

export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  // Served under /app by the API (crm_app.api.spa).
  return createRouter({ routeTree, history, basepath: "/app" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
