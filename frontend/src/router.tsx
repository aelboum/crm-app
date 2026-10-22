import {
  createBrowserHistory,
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import { Shell } from "./components/Shell";
import { LoadError } from "./components/StateNotice";
import { ApiError } from "./api/client";
import { HomePage, isWorkspaceId } from "./pages/HomePage";
import { WorkspacePage } from "./pages/WorkspacePage";

const rootRoute = createRootRoute({ component: Shell });

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});

function WorkspaceRoute() {
  const { workspaceId } = workspaceRoute.useParams();
  // A malformed ID is answered like an unknown workspace, without a request.
  if (!isWorkspaceId(workspaceId)) {
    return <LoadError error={new ApiError(404)} onRetry={() => undefined} />;
  }
  return <WorkspacePage key={workspaceId} workspaceId={workspaceId} />;
}

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/w/$workspaceId",
  component: WorkspaceRoute,
});

const routeTree = rootRoute.addChildren([homeRoute, workspaceRoute]);

export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  // Served under /app by the API (crm_app.api.spa).
  return createRouter({ routeTree, history, basepath: "/app" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
