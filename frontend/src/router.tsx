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
import { MembersPage } from "./pages/WorkspacePage";
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

function SectionPage() {
  const { workspaceId, section: slug } = sectionRoute.useParams();
  // Settings holds Members today; every other module is the design's placeholder.
  if (slug === SETTINGS_SLUG) return <MembersPage workspaceId={workspaceId} />;
  const section = findSection(slug);
  return section ? <PlaceholderPage section={section} /> : notFound;
}

const sectionRoute = createRoute({
  getParentRoute: () => workspaceRoute,
  path: "$section",
  component: SectionPage,
});

const routeTree = rootRoute.addChildren([
  plainRoute.addChildren([homeRoute]),
  workspaceRoute.addChildren([workspaceIndexRoute, sectionRoute]),
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
