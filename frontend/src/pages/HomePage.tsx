import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button, FieldError, Form, Input, Label, TextField } from "react-aria-components";

import { useMe } from "../api/queries";
import { Loading, LoadError } from "../components/StateNotice";
import { useT } from "../i18n/useT";

const WORKSPACE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isWorkspaceId(value: string): boolean {
  return WORKSPACE_ID.test(value.trim());
}

function OpenWorkspace() {
  const t = useT();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  return (
    <section className="card" aria-labelledby="open-heading">
      <h1 id="open-heading">{t("home.open.title")}</h1>
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
        <Button type="submit" className="button primary" isDisabled={!isWorkspaceId(value)}>
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
          <a className="button primary" href="/auth/login">
            {t("home.signIn")}
          </a>
        </div>
      </section>
    );
  }
  return <OpenWorkspace />;
}
