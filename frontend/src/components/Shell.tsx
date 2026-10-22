import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import { Button } from "react-aria-components";

import { useMe, useSignOut } from "../api/queries";
import { useT } from "../i18n/useT";

export function Shell() {
  const t = useT();
  const me = useMe();
  const signOut = useSignOut();
  const navigate = useNavigate();
  return (
    <>
      <a className="skip-link" href="#main">
        {t("app.skip")}
      </a>
      <header className="shell-header">
        <Link to="/" className="brand">
          {t("app.name")}
        </Link>
        {me.data ? (
          <div className="row">
            {signOut.isError ? (
              <span role="alert" className="field-error">
                {t("app.signOutFailed")}
              </span>
            ) : null}
            <Button
              className="button"
              isDisabled={signOut.isPending}
              onPress={() => {
                // Leave the current page so nothing from the ended session stays on screen.
                signOut.mutate(undefined, {
                  onSuccess: () => void navigate({ to: "/" }),
                });
              }}
            >
              {t("app.signOut")}
            </Button>
          </div>
        ) : null}
      </header>
      <main id="main" className="shell-main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}
