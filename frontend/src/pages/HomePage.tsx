import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { FieldError, Form, Input, Label, TextField } from "react-aria-components";

import { pendingInvitation } from "../api/invitations";
import { useDirectory, useMe } from "../api/queries";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button, buttonClass } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import { initials } from "../shell/AppFrame";

const WORKSPACE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isWorkspaceId(value: string): boolean {
  return WORKSPACE_ID.test(value.trim());
}

/** The caller's workspaces (decision P2-F 2); each link is still authorized
 *  on its own when opened. */
function WorkspaceList() {
  const t = useT();
  const directory = useDirectory();
  return (
    <section className="card" aria-labelledby="list-heading">
      <h1 id="list-heading">{t("home.list.title")}</h1>
      {directory.isPending ? (
        <Loading />
      ) : directory.isError ? (
        <LoadError error={directory.error} onRetry={() => void directory.refetch()} />
      ) : directory.data.items.length === 0 ? (
        <EmptyState title={t("home.list.empty")} />
      ) : (
        <ul className="workspace-list">
          {directory.data.items.map((workspace) => (
            <li key={workspace.id}>
              <Link className="workspace-link" to="/w/$workspaceId" params={{ workspaceId: workspace.id }}>
                <span className="ws-tile small" data-mark={initials(workspace.name)} aria-hidden="true" />
                {workspace.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OpenWorkspace() {
  const t = useT();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  return (
    <section className="card" aria-labelledby="open-heading">
      <h2 id="open-heading">{t("home.open.title")}</h2>
      <p className="muted">{t("home.open.body")}</p>
      <Form
        className="row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!isWorkspaceId(value)) return;
          void navigate({
            to: "/w/$workspaceId",
            params: { workspaceId: value.trim().toLowerCase() },
          });
        }}
      >
        <TextField
          className="field"
          value={value}
          onChange={setValue}
          isRequired
          validate={(v) => (v === "" || isWorkspaceId(v) ? null : t("home.open.invalid"))}
          validationBehavior="aria"
        >
          <Label>{t("home.open.label")}</Label>
          <Input className="mono" spellCheck={false} autoComplete="off" />
          <FieldError className="field-error" />
        </TextField>
        <Button type="submit" variant="primary" isDisabled={!isWorkspaceId(value)}>
          {t("home.open.submit")}
        </Button>
      </Form>
    </section>
  );
}

export function HomePage() {
  const t = useT();
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (me.isError) return <LoadError error={me.error} onRetry={() => void me.refetch()} />;
  if (me.data === null) {
    return (
      <section className="card" aria-labelledby="signin-heading">
        <h1 id="signin-heading">{t("home.signedOut.title")}</h1>
        <p className="muted">{t("home.signedOut.body")}</p>
        <div className="row">
          <a className={buttonClass("primary")} href="/auth/login">
            {t("home.signIn")}
          </a>
        </div>
      </section>
    );
  }
  const waiting = pendingInvitation();
  return (
    <>
      {waiting ? (
        // Sign-in always lands here; an invitation opened before it waits in this tab.
        <div className="notice info row" role="status">
          <p>{t("accept.pending")}</p>
          <Link className={buttonClass("primary", "sm")} to="/invite/$workspaceId" params={{ workspaceId: waiting.workspaceId }}>
            {t("accept.continue")}
          </Link>
        </div>
      ) : null}
      <WorkspaceList />
      <OpenWorkspace />
    </>
  );
}
