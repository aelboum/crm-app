import { Link, useNavigate } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";
import { FieldError, Form, Input, Label, TextField } from "react-aria-components";

import { pendingInvitation } from "../api/invitations";
import { useDirectory, useMe } from "../api/queries";
import { useSignupStatus } from "../api/signups";
import { EmptyState, Loading, LoadError } from "../components/StateNotice";
import { Button, buttonClass } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import { initials } from "../shell/AppFrame";
import { CreateWorkspace } from "./CreateWorkspace";
import { SignInScreen } from "./SignInScreen";

const WORKSPACE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isWorkspaceId(value: string): boolean {
  return WORKSPACE_ID.test(value.trim());
}

/** The caller's workspaces (decision P2-F 2); each link is still authorized
 *  on its own when opened. */
function WorkspaceList({ action, signup = false }: { action?: ReactNode; signup?: boolean }) {
  const t = useT();
  const directory = useDirectory();
  return (
    <section className="card" aria-labelledby="list-heading">
      <div className="row card-head-row">
        <h1 id="list-heading">{t("home.list.title")}</h1>
        {action}
      </div>
      {directory.isPending ? (
        <Loading />
      ) : directory.isError ? (
        <LoadError error={directory.error} onRetry={() => void directory.refetch()} />
      ) : directory.data.items.length === 0 ? (
        <EmptyState title={t(signup ? "home.list.emptySignup" : "home.list.empty")} />
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
  if (!me.data) {
    return <SignInScreen me={me} title={t("home.signedOut.title")} body={t("home.signedOut.body")} redirect offerSignup />;
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
      {waiting ? <WorkspaceList /> : <WorkspacesWithSignup />}
      <OpenWorkspace />
    </>
  );
}

/*
 * Self-service signup's workspace-name step (Stage D), never while an
 * invitation waits in this tab: accepting it comes first. Offered when the
 * server says signup is on, and also while that is unknown (the status check
 * failed), since the backend's kill switch decides in the end. Shown at once
 * to a person with no workspace; otherwise behind "Create workspace".
 */
function WorkspacesWithSignup() {
  const t = useT();
  const availability = useSignupStatus();
  const directory = useDirectory();
  const [chosen, setChosen] = useState(false);
  const offered =
    (availability === "on" || availability === "unknown") && !directory.isPending && !directory.isError;
  const none = directory.data?.items.length === 0;
  // Once shown, the step stays until closed: a refreshed list (for example
  // with the workspace it just created) must not unmount it mid-signup.
  if (offered && none && !chosen) setChosen(true);
  const open = chosen;
  return (
    <>
      <WorkspaceList
        signup={open}
        action={
          offered && !open ? (
            <Button size="sm" onPress={() => {
              setChosen(true);
            }}>
              {t("signup.open")}
            </Button>
          ) : undefined
        }
      />
      {open ? <CreateWorkspace onCancel={none ? undefined : () => {
        setChosen(false);
      }} /> : null}
    </>
  );
}
