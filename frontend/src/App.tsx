import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { IntlProvider } from "react-intl";

import { ApiError } from "./api/client";
import { ToastProvider } from "./components/ui/Toast";
import { en } from "./i18n/en";
import type { createAppRouter } from "./router";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A refusal (4xx) will not change on retry; a server or network failure might.
        retry: (count, error) =>
          !(error instanceof ApiError && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function App({
  router,
  queryClient,
}: {
  router: ReturnType<typeof createAppRouter>;
  queryClient: QueryClient;
}) {
  return (
    <IntlProvider locale="en" defaultLocale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>
    </IntlProvider>
  );
}
