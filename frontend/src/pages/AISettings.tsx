import { type SyntheticEvent, useState } from "react";

import {
  type AIBudget,
  type AIFeature,
  type AIModel,
  type AISettings as Settings,
  useAIBudget,
  useAISettings,
  useSetAIBudgetCap,
  useSetAIEnabled,
  useSetAIFeature,
  useSetAIModel,
  useSetAIPreferences,
} from "../api/aiSettings";
import { ApiError } from "../api/client";
import { LoadError, Loading } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Settings › AI (decision P9-S). AI only suggests, and it is off until an
 * Owner or Admin turns it on here. Nothing can reach an AI provider unless
 * AI, a feature and a model are all allowed, the platform operator has set
 * up that model, and the platform has not paused AI for the workspace.
 * SaaS-OS checks and audits every change; this page only shows what it
 * answers.
 */

const FEATURE_TEXT: Record<AIFeature, { name: MessageId; desc: MessageId }> = {
  contact_brief: {
    name: "ai.feature.contactBrief",
    desc: "ai.feature.contactBriefDesc",
  },
};

// SaaS-OS's reasons a model cannot be chosen; any other code is shown as is.
const BLOCKED: Record<string, MessageId> = {
  tenant_ai_disabled: "ai.blocked.aiOff",
  use_case_not_granted: "ai.blocked.featureOff",
  residency: "ai.blocked.residency",
  retention: "ai.blocked.retention",
  retention_days: "ai.blocked.retention",
  training_use: "ai.blocked.training",
  capability: "ai.blocked.capability",
  tenant_ai_held: "ai.blocked.held",
};

// Reasons that come from the workspace's switches or a platform pause,
// not from the model (SaaS-OS `list_eligible_models`).
const WORKSPACE_LEVEL = new Set([
  "tenant_ai_disabled",
  "use_case_not_granted",
  "classification_not_granted_for_use_case",
  "tenant_ai_held",
]);

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.code === "unknown_model") return "ai.error.unknownModel";
    if (error.status === 403) return "ai.error.forbidden";
    if (error.status === 422) return "ai.error.refused";
  }
  return "ai.error.generic";
}

function Switch({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="hours-day ai-switch">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
      {label}
    </label>
  );
}

function Reasons({ codes }: { codes: readonly string[] }) {
  const t = useT();
  return (
    <span className="muted">
      {codes.map((code, index) => (
        <span key={code}>
          {index ? " · " : ""}
          {BLOCKED[code] ? (
            t(BLOCKED[code])
          ) : (
            <span className="mono">{code}</span>
          )}
        </span>
      ))}
    </span>
  );
}

function ModelItem({
  model,
  disabled,
  onChange,
}: {
  model: AIModel;
  disabled: boolean;
  onChange: (allowed: boolean) => void;
}) {
  const t = useT();
  const name = `${model.provider_key} · ${model.model_id}`;
  // Only the model's own reasons stop choosing it: the workspace's own
  // switches (AI, the feature) and a platform pause may change later. A
  // model already allowed can always be disallowed.
  const blocked =
    !model.granted &&
    model.blocked_by.some((code) => !WORKSPACE_LEVEL.has(code));
  return (
    <li className="domain-item">
      <div className="domain-head">
        <Switch
          label={name}
          checked={model.granted}
          disabled={disabled || blocked}
          onChange={onChange}
        />
        {model.granted && model.rank !== null ? (
          <Badge tone="neutral">
            {t("ai.models.rank", { rank: model.rank + 1 })}
          </Badge>
        ) : null}
        {model.eligible ? (
          <Badge tone="success">{t("ai.models.usable")}</Badge>
        ) : null}
      </div>
      {model.blocked_by.length ? <Reasons codes={model.blocked_by} /> : null}
    </li>
  );
}

function Policy({
  workspaceId,
  settings,
  canManage,
}: {
  workspaceId: string;
  settings: Settings;
  canManage: boolean;
}) {
  const t = useT();
  const setEnabled = useSetAIEnabled(workspaceId);
  const setFeature = useSetAIFeature(workspaceId);
  const setModel = useSetAIModel(workspaceId);
  const busy =
    setEnabled.isPending || setFeature.isPending || setModel.isPending;
  const problem = setEnabled.error ?? setFeature.error ?? setModel.error;
  return (
    <section className="records-card domains" aria-label={t("ai.title")}>
      <h2 className="settings-card-title">{t("ai.title")}</h2>
      <p className="muted">{t("ai.intro")}</p>
      <Switch
        label={t("ai.enabled")}
        checked={settings.enabled}
        disabled={!canManage || busy}
        onChange={(enabled) => {
          setEnabled.mutate(enabled);
        }}
      />
      <h3 className="field-label">{t("ai.features")}</h3>
      <ul className="domain-items">
        {settings.features.map((feature) => (
          <li key={feature.feature} className="domain-item">
            <Switch
              label={t(FEATURE_TEXT[feature.feature].name)}
              checked={feature.enabled}
              disabled={!canManage || busy}
              onChange={(enabled) => {
                setFeature.mutate({ feature: feature.feature, enabled });
              }}
            />
            <span className="muted">
              {t(FEATURE_TEXT[feature.feature].desc)}
            </span>
          </li>
        ))}
      </ul>
      {settings.models.map((group) => {
        const granted = group.models.filter((m) => m.granted).length;
        return (
          <div key={group.feature}>
            <h3 className="field-label">
              {t("ai.models.for", {
                feature: t(FEATURE_TEXT[group.feature].name),
              })}
            </h3>
            {group.models.length === 0 ? (
              <p className="muted">{t("ai.models.none")}</p>
            ) : (
              <ul className="domain-items">
                {group.models.map((model) => (
                  <ModelItem
                    key={`${model.provider_key}/${model.model_id}`}
                    model={model}
                    disabled={!canManage || busy}
                    onChange={(allowed) => {
                      setModel.mutate({
                        feature: group.feature,
                        provider_key: model.provider_key,
                        model_id: model.model_id,
                        enabled: allowed,
                        // A newly allowed model is tried after the others.
                        rank: allowed ? granted : null,
                      });
                    }}
                  />
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {problem ? (
        <p className="notice error" role="alert">
          {t(failure(problem))}
        </p>
      ) : null}
    </section>
  );
}

const RETENTION = ["", "0", "30"] as const;

function Preferences({
  workspaceId,
  settings,
  canManage,
}: {
  workspaceId: string;
  settings: Settings;
  canManage: boolean;
}) {
  const t = useT();
  const save = useSetAIPreferences(workspaceId);
  const saved = settings.preferences;
  const [training, setTraining] = useState(saved.exclude_training_use);
  const [retention, setRetention] = useState(
    saved.max_retention_days === null ? "" : String(saved.max_retention_days),
  );
  const [residency, setResidency] = useState(
    saved.allowed_residency.join(", "),
  );

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    save.mutate({
      exclude_training_use: training,
      max_retention_days: retention === "" ? null : Number(retention),
      allowed_residency: residency
        .split(",")
        .map((tag) => tag.trim().toLowerCase())
        .filter(Boolean),
    });
  };
  const retentionChoices: readonly string[] = (
    RETENTION as readonly string[]
  ).includes(retention)
    ? RETENTION
    : [...RETENTION, retention];

  return (
    <section className="records-card domains" aria-label={t("ai.prefs.title")}>
      <h2 className="settings-card-title">{t("ai.prefs.title")}</h2>
      <p className="muted">{t("ai.prefs.intro")}</p>
      <form className="domains" onSubmit={submit}>
        <label className="hours-day ai-switch">
          <input
            type="checkbox"
            checked={training}
            disabled={!canManage}
            onChange={(event) => {
              setTraining(event.target.checked);
            }}
          />
          {t("ai.prefs.training")}
        </label>
        <label className="field">
          <span className="field-label">{t("ai.prefs.retention")}</span>
          <select
            className="form-input"
            value={retention}
            disabled={!canManage}
            onChange={(event) => {
              setRetention(event.target.value);
            }}
          >
            {retentionChoices.map((value) => (
              <option key={value} value={value}>
                {value === ""
                  ? t("ai.prefs.retentionAny")
                  : t("ai.prefs.retentionDays", { days: Number(value) })}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t("ai.prefs.residency")}</span>
          <input
            className="form-input"
            value={residency}
            maxLength={400}
            placeholder="eu"
            aria-describedby="ai-residency-hint"
            disabled={!canManage}
            onChange={(event) => {
              setResidency(event.target.value);
            }}
          />
        </label>
        <span id="ai-residency-hint" className="muted">
          {t("ai.prefs.residencyHint")}
        </span>
        {canManage ? (
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={save.isPending}
          >
            {t("ai.prefs.save")}
          </Button>
        ) : null}
      </form>
      {save.isSuccess ? (
        <p className="notice info" role="status">
          {t("ai.saved")}
        </p>
      ) : null}
      {save.error ? (
        <p className="notice error" role="alert">
          {t(failure(save.error))}
        </p>
      ) : null}
    </section>
  );
}

const STATE: Record<string, MessageId> = {
  unconfigured: "ai.budget.state.unconfigured",
  ok: "ai.budget.state.ok",
  warning: "ai.budget.state.warning",
  exhausted: "ai.budget.state.exhausted",
  currency_conflict: "ai.budget.state.currencyConflict",
  unavailable: "ai.budget.state.unavailable",
};

function money(amount: string | null, currency: string | null): string {
  return amount === null ? "—" : `${amount} ${currency ?? ""}`.trim();
}

const AMOUNT = /^\d{1,10}(\.\d{1,2})?$/;

function BudgetCard({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}) {
  const t = useT();
  const budget = useAIBudget(workspaceId);
  const save = useSetAIBudgetCap(workspaceId);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("");
  const shown: AIBudget | undefined = budget.data;
  const chosenCurrency = currency || shown?.currency || "EUR";

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    save.mutate(
      { currency: chosenCurrency, amount: amount.trim() },
      {
        onSuccess: () => {
          setAmount("");
        },
      },
    );
  };

  return (
    <section className="records-card domains" aria-label={t("ai.budget.title")}>
      <h2 className="settings-card-title">{t("ai.budget.title")}</h2>
      <p className="muted">{t("ai.budget.intro")}</p>
      {budget.isPending ? (
        <Loading />
      ) : budget.isError ? (
        <LoadError error={budget.error} onRetry={() => void budget.refetch()} />
      ) : (
        <dl className="ai-budget">
          <dt>{t("ai.budget.status")}</dt>
          <dd>
            {t(STATE[budget.data.state] ?? "ai.budget.state.unavailable")}
          </dd>
          <dt>{t("ai.budget.limit")}</dt>
          <dd>{money(budget.data.limit, budget.data.currency)}</dd>
          <dt>{t("ai.budget.spent")}</dt>
          <dd>{money(budget.data.settled, budget.data.currency)}</dd>
          <dt>{t("ai.budget.remaining")}</dt>
          <dd>{money(budget.data.remaining, budget.data.currency)}</dd>
        </dl>
      )}
      {canManage ? (
        <form className="domain-form" onSubmit={submit}>
          <label className="field">
            <span className="field-label">{t("ai.budget.cap")}</span>
            <input
              className="form-input"
              inputMode="decimal"
              value={amount}
              maxLength={13}
              placeholder="25.00"
              onChange={(event) => {
                setAmount(event.target.value);
              }}
            />
          </label>
          <label className="field">
            <span className="field-label">{t("ai.budget.currency")}</span>
            <input
              className="form-input"
              value={chosenCurrency}
              maxLength={3}
              onChange={(event) => {
                setCurrency(event.target.value.toUpperCase());
              }}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isDisabled={save.isPending || !AMOUNT.test(amount.trim())}
          >
            {t("ai.budget.setCap")}
          </Button>
          <Button
            size="sm"
            isDisabled={save.isPending}
            onPress={() => {
              save.mutate({ currency: chosenCurrency, amount: null });
            }}
          >
            {t("ai.budget.removeCap")}
          </Button>
        </form>
      ) : null}
      {save.error ? (
        <p className="notice error" role="alert">
          {t(failure(save.error))}
        </p>
      ) : null}
    </section>
  );
}

export function AISettings({
  workspaceId,
  canRead,
  canManage,
  canReadUsage,
  canManageBudget,
}: {
  workspaceId: string;
  canRead: boolean;
  canManage: boolean;
  canReadUsage: boolean;
  canManageBudget: boolean;
}) {
  const t = useT();
  const settings = useAISettings(workspaceId, canRead);
  if (!canRead) {
    return (
      <p className="notice info" role="status">
        {t("ai.notAllowed")}
      </p>
    );
  }
  return (
    <>
      {settings.isPending ? (
        <Loading />
      ) : settings.isError ? (
        <LoadError
          error={settings.error}
          onRetry={() => void settings.refetch()}
        />
      ) : (
        <>
          <Policy
            workspaceId={workspaceId}
            settings={settings.data}
            canManage={canManage}
          />
          <Preferences
            // Saved preferences start a fresh form.
            key={JSON.stringify(settings.data.preferences)}
            workspaceId={workspaceId}
            settings={settings.data}
            canManage={canManage}
          />
        </>
      )}
      {canReadUsage ? (
        <BudgetCard workspaceId={workspaceId} canManage={canManageBudget} />
      ) : null}
    </>
  );
}
