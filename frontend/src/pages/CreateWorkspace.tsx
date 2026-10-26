import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";
import { FieldError, Form, Input, Label, TextField } from "react-aria-components";

import { keys } from "../api/queries";
import {
  attemptFor,
  currentSignup,
  forgetAttempt,
  keptAttempt,
  NAME_MAX,
  NETWORK,
  normalizeWorkspaceName,
  OPEN_STATES,
  type Signup,
  type SignupAttempt,
  SignupError,
  signupEnabled,
  startSignup,
  workspaceNameProblem,
} from "../api/signups";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { SETTINGS_SLUG } from "../shell/navigation";

/*
 * The workspace-name step of self-service signup (decision S-1; SIGNUP-PLAN.md
 * §4, Stage D), for a signed-in person with no invitation waiting in this tab
 * (HomePage decides that). `POST /v1/signups` provisions the workspace; this
 * step reports success only once the backend says the signup is complete,
 * then opens the new workspace's settings.
 */

/** Waits between progress checks while a workspace is set up: about a
 *  minute in all, then the person can resume it. */
export const POLL_DELAYS_MS = [1000, 1000, 2000, 2000, 3000, 5000, 8000, 8000, 10_000, 10_000, 10_000];

type Phase =
  | { kind: "checking" }
  | { kind: "form" }
  | { kind: "verify" }
  | { kind: "unavailable" }
  | { kind: "working" }
  | { kind: "stalled" }
  | { kind: "ended"; state: "failed" | "expired" };

type Refusal = "limit" | "reused" | "denied" | "busy" | "unreachable" | "generic";

const REFUSAL: Record<Refusal, MessageId> = {
  limit: "signup.error.limit",
  reused: "signup.error.reused",
  denied: "signup.error.denied",
  busy: "signup.error.busy",
  unreachable: "signup.error.unreachable",
  generic: "signup.error.generic",
};

function waitText(t: ReturnType<typeof useT>, seconds: number): string {
  return seconds < 60
    ? t("signup.wait.seconds", { count: Math.max(1, Math.ceil(seconds)) })
    : t("signup.wait.minutes", { count: Math.ceil(seconds / 60) });
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

const ended = (signup: Signup) => signup.state === "failed" || signup.state === "expired";

export function CreateWorkspace({ onCancel }: { onCancel?: (() => void) | undefined }) {
  const t = useT();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  const [name, setName] = useState(() => keptAttempt()?.name ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ kind: Refusal; wait?: number } | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [sending, setSending] = useState(false);
  const alive = useRef(true);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // Enable the button again once the server's Retry-After has passed.
  const wait = refusal?.wait;
  useEffect(() => {
    if (!blocked || wait === undefined) return;
    const timer = setTimeout(() => {
      setBlocked(false);
      setRefusal(null);
    }, wait * 1000);
    return () => {
      clearTimeout(timer);
    };
  }, [blocked, wait]);

  /** Opens the new workspace first, then refreshes the list: refreshing first
   *  would let the start page close this step before it could navigate. */
  function finish(signup: Signup) {
    forgetAttempt();
    if (!signup.workspace_id) {
      setPhase({ kind: "stalled" });
      return;
    }
    void navigate({
      to: "/w/$workspaceId/$section",
      params: { workspaceId: signup.workspace_id, section: SETTINGS_SLUG },
    });
    client.invalidateQueries({ queryKey: keys.directory }).catch(() => undefined);
  }

  /** Follows a signup until it completes, ends, or the checks run out. */
  async function follow(signup: Signup) {
    let latest: Signup | null = signup;
    for (const delay of [0, ...POLL_DELAYS_MS]) {
      if (delay) {
        await sleep(delay);
        if (!alive.current) return;
        try {
          latest = await currentSignup();
        } catch {
          // A failed check is not a failed signup: keep checking.
          continue;
        }
      }
      if (!alive.current) return;
      if (latest === null) {
        // Signup was switched off meanwhile.
        setPhase({ kind: "unavailable" });
        return;
      }
      if (latest.state === "complete") {
        finish(latest);
        return;
      }
      if (latest.state === "failed" || latest.state === "expired") {
        setPhase({ kind: "ended", state: latest.state });
        return;
      }
      setPhase({ kind: "working" });
    }
    if (alive.current) setPhase({ kind: "stalled" });
  }

  // On arrival: resume an unfinished signup, or ask for a verified email.
  useEffect(() => {
    let active = true;
    currentSignup().then(
      (signup) => {
        if (!active) return;
        if (signup && OPEN_STATES.includes(signup.state)) {
          setPhase({ kind: "working" });
          void follow(signup);
        } else if (signup?.state === "complete") {
          // Finished, perhaps in a tab that closed first: a new attempt is new.
          forgetAttempt();
          setName("");
          setPhase({ kind: "form" });
        } else if (signup && ended(signup) && keptAttempt()) {
          // The attempt this tab was making did not finish.
          setPhase({ kind: "ended", state: signup.state as "failed" | "expired" });
        } else {
          setPhase({ kind: "form" });
        }
      },
      (error: unknown) => {
        if (!active) return;
        setPhase(error instanceof SignupError && error.status === 403 ? { kind: "verify" } : { kind: "form" });
      },
    );
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on arrival
  }, []);

  // Moves focus to the heading when the step changes to a result, so a
  // screen reader hears the new state.
  useEffect(() => {
    if (phase.kind !== "form" && phase.kind !== "checking") heading.current?.focus();
  }, [phase.kind]);

  /** A 403 means a missing verified email only if `current` says so too;
   *  otherwise it is another refusal (for example the origin check). */
  async function explainForbidden() {
    try {
      await currentSignup();
      // `current` answers 404 both to "no signup" and to "switched off".
      const enabled = await signupEnabled().catch(() => true);
      if (enabled) setRefusal({ kind: "denied" });
      else setPhase({ kind: "unavailable" });
    } catch (error) {
      if (error instanceof SignupError && error.status === 403) setPhase({ kind: "verify" });
      else setRefusal({ kind: "denied" });
    }
  }

  async function send(attempt: SignupAttempt = attemptFor(normalizeWorkspaceName(name))) {
    setSending(true);
    setRefusal(null);
    try {
      const signup = await startSignup(attempt.key, attempt.name);
      if (!alive.current) return;
      if (signup.state === "failed" || signup.state === "expired") {
        setPhase({ kind: "ended", state: signup.state });
      } else {
        setPhase({ kind: "working" });
        await follow(signup);
      }
    } catch (error) {
      if (!alive.current) return;
      const failure = error instanceof SignupError ? error : new SignupError(NETWORK, undefined, null);
      setPhase({ kind: "form" });
      if (failure.status === 404) {
        setPhase({ kind: "unavailable" });
      } else if (failure.status === 403) {
        await explainForbidden();
      } else if (failure.status === 409 && failure.reason === "workspace_limit_reached") {
        setRefusal({ kind: "limit" });
      } else if (failure.status === 409 && failure.reason === "idempotency_key_reused") {
        // The kept key belongs to another request: the next submit is new.
        forgetAttempt();
        setRefusal({ kind: "reused" });
      } else if ((failure.status === 400 && failure.reason === "invalid_workspace_name") || failure.status === 422) {
        setNameError(t("signup.name.invalid"));
      } else if (failure.status === 429 || failure.status === 503) {
        setBlocked(true);
        setRefusal({ kind: "busy", wait: failure.retryAfter ?? 5 });
      } else if (failure.status === NETWORK) {
        setRefusal({ kind: "unreachable" });
      } else {
        setRefusal({ kind: "generic" });
      }
    } finally {
      if (alive.current) setSending(false);
    }
  }

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (sending) return;
    const problem = workspaceNameProblem(name);
    if (problem) {
      setNameError(t(`signup.name.${problem}`, { max: NAME_MAX }));
      return;
    }
    void send();
  }

  /** After the checks ran out: repeat this tab's attempt (the backend then
   *  resumes it), or, with none kept here, check its progress again. */
  async function resume() {
    const kept = keptAttempt();
    if (kept) {
      await send(kept);
      return;
    }
    setPhase({ kind: "working" });
    try {
      const signup = await currentSignup();
      if (signup) await follow(signup);
      else if (alive.current) setPhase({ kind: "unavailable" });
    } catch {
      if (alive.current) setPhase({ kind: "stalled" });
    }
  }

  function startAgain() {
    forgetAttempt();
    setRefusal(null);
    setPhase({ kind: "form" });
  }

  let body;
  switch (phase.kind) {
    case "checking":
      body = (
        <p role="status" className="state-loading">
          <span className="spinner" aria-hidden="true" />
          {t("state.loading")}
        </p>
      );
      break;
    case "verify":
      body = (
        <p className="notice error" role="alert">
          {t("signup.verify")}
        </p>
      );
      break;
    case "unavailable":
      body = (
        <p className="notice info" role="status">
          {t("signup.unavailable")}
        </p>
      );
      break;
    case "working":
      body = (
        <p role="status" className="state-loading">
          <span className="spinner" aria-hidden="true" />
          {t("signup.working")}
        </p>
      );
      break;
    case "stalled":
      body = (
        <>
          <p className="notice info" role="status">
            {t("signup.stalled")}
          </p>
          <div className="row">
            <Button variant="primary" isDisabled={sending} onPress={() => void resume()}>
              {t("signup.resume")}
            </Button>
          </div>
        </>
      );
      break;
    case "ended":
      body = (
        <>
          <p className="notice error" role="alert">
            {t(phase.state === "expired" ? "signup.expired" : "signup.failed")}
          </p>
          <div className="row">
            <Button variant="primary" onPress={startAgain}>
              {t("signup.startAgain")}
            </Button>
          </div>
        </>
      );
      break;
    case "form": {
      body = (
        <Form className="stack" onSubmit={submit} validationBehavior="aria">
          <TextField
            className="field"
            value={name}
            onChange={(value) => {
              setName(value);
              setNameError(null);
            }}
            isRequired
            isInvalid={nameError !== null}
            validationBehavior="aria"
          >
            <Label>{t("signup.name.label")}</Label>
            <Input autoComplete="organization" />
            <FieldError className="field-error">{nameError}</FieldError>
          </TextField>
          {refusal ? (
            <p className="notice error" role="alert">
              {t(REFUSAL[refusal.kind])}
              {refusal.wait !== undefined ? ` ${waitText(t, refusal.wait)}` : null}
            </p>
          ) : null}
          <div className="row">
            <Button type="submit" variant="primary" isDisabled={sending || blocked}>
              {sending ? t("signup.sending") : t("signup.submit")}
            </Button>
            {onCancel ? (
              <Button variant="ghost" onPress={onCancel} isDisabled={sending}>
                {t("confirm.cancel")}
              </Button>
            ) : null}
          </div>
        </Form>
      );
      break;
    }
  }

  return (
    <section className="card card-pad stack" aria-labelledby="create-heading">
      <h2 id="create-heading" ref={heading} tabIndex={-1}>
        {t("signup.title")}
      </h2>
      <p className="muted">{t("signup.body")}</p>
      {body}
      <p className="signin-help">{t("signup.invited")}</p>
    </section>
  );
}
