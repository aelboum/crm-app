import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { type SyntheticEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { type Pipeline, type PipelineChange, type Stage, useChangePipeline, usePipelines } from "../api/pipelines";
import { DuplicateError, FieldErrors } from "../api/records";
import { Dialog } from "../components/ui/Dialog";
import { Loading, LoadError } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { useToast } from "../components/ui/Toast";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";

/*
 * Settings › Pipeline (decision P4, slice 4A). The design has no place to
 * change stages (ScreenPipeline.dc.html only shows them); this section is
 * that place. Everyone sees the stages; Owners and Admins
 * (`manage_pipeline`) rename the pipeline and add, change, reorder and
 * remove stages, and the server enforces that. Reordering uses Move up and
 * Move down buttons, so it works from the keyboard. The probability is
 * checked here, not by the browser's own range check, so its message is
 * the product's. Won and lost are a deal's outcome, not stages.
 */

function failure(error: unknown): MessageId {
  if (error instanceof DuplicateError) return "pipeline.error.duplicate";
  if (error instanceof FieldErrors) return "pipeline.error.invalid";
  if (error instanceof ApiError) {
    if (error.code === "stale_version") return "pipeline.error.stale";
    if (error.code === "stage_limit_reached") return "pipeline.error.full";
    if (error.code === "last_stage") return "pipeline.error.lastStage";
    if (error.code === "stage_in_use" || error.code === "invalid_move_target") return "pipeline.error.stale";
    if (error.code === "stage_not_found" || error.code === "pipeline_not_found") return "pipeline.error.stale";
    if (error.status === 403) return "pipeline.error.forbidden";
  }
  return "pipeline.error.failed";
}

/** A whole percentage from the probability field, or null. */
function percentage(raw: string): number | null {
  if (!/^\d{1,3}$/.test(raw.trim())) return null;
  const value = Number(raw.trim());
  return value <= 100 ? value : null;
}

export function PipelineSettings({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const t = useT();
  const pipelines = usePipelines(workspaceId);
  if (pipelines.isPending) return <Loading />;
  if (pipelines.isError) return <LoadError error={pipelines.error} onRetry={() => void pipelines.refetch()} />;
  const pipeline = pipelines.data.items[0];
  if (!pipeline) return <p className="muted">{t("pipeline.none")}</p>;
  return (
    <PipelineEditor
      key={pipeline.id}
      workspaceId={workspaceId}
      pipeline={pipeline}
      max={pipelines.data.max_stages}
      canEdit={canEdit}
    />
  );
}

function PipelineEditor({
  workspaceId,
  pipeline,
  max,
  canEdit,
}: {
  workspaceId: string;
  pipeline: Pipeline;
  max: number;
  canEdit: boolean;
}) {
  const t = useT();
  const toast = useToast();
  const change = useChangePipeline(workspaceId);
  const [error, setError] = useState<MessageId | null>(null);
  const [name, setName] = useState(pipeline.name);
  const [draft, setDraft] = useState({ name: "", probability: "50" });
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Stage | null>(null);
  const stages = pipeline.stages;

  const apply = (next: PipelineChange, done: MessageId, after?: () => void) => {
    setError(null);
    change.mutate(
      { pipeline, change: next },
      {
        onSuccess: () => {
          toast(t(done));
          after?.();
        },
        onError: (problem) => {
          setError(failure(problem));
        },
      },
    );
  };

  const rename = (event: SyntheticEvent) => {
    event.preventDefault();
    const next = name.trim();
    if (!next || next === pipeline.name) return;
    apply({ kind: "rename", name: next }, "pipeline.renamed");
  };

  const add = (event: SyntheticEvent) => {
    event.preventDefault();
    const stageName = draft.name.trim();
    const probability = percentage(draft.probability);
    if (!stageName) return;
    if (probability === null) {
      setError("pipeline.error.probability");
      return;
    }
    apply({ kind: "add", name: stageName, probability }, "pipeline.stageAdded", () => {
      setDraft({ name: "", probability: "50" });
    });
  };

  const move = (index: number, by: -1 | 1) => {
    const ids = stages.map((stage) => stage.id);
    const [moved] = ids.splice(index, 1);
    if (moved === undefined) return;
    ids.splice(index + by, 0, moved);
    apply({ kind: "reorder", stageIds: ids }, "pipeline.reordered");
  };

  const confirmDelete = (moveTo: string) => {
    if (!deleting) return;
    const stage = deleting;
    setDeleting(null);
    apply({ kind: "delete", stageId: stage.id, moveTo }, "pipeline.stageRemoved");
  };

  const busy = change.isPending;
  return (
    <section className="business-card pipeline-settings" aria-label={t("settings.pipeline")}>
      {canEdit ? null : <p className="profile-note">{t("pipeline.readOnly")}</p>}
      {error ? (
        <p className="notice error" role="alert">
          {t(error)}
        </p>
      ) : null}
      {canEdit ? (
        <form className="tag-new pipeline-name" onSubmit={rename}>
          <div className="form-field">
            <label htmlFor="pipeline-name" className="form-label">
              {t("pipeline.name")}
            </label>
            <input
              id="pipeline-name"
              className="form-input"
              value={name}
              maxLength={60}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </div>
          <Button type="submit" isDisabled={busy || !name.trim() || name.trim() === pipeline.name}>
            {t("pipeline.save")}
          </Button>
        </form>
      ) : (
        <p className="pipeline-title">{pipeline.name}</p>
      )}
      <h2 className="pipeline-stages-title" id="pipeline-stages-title">
        {t("pipeline.stages", { count: stages.length, max })}
      </h2>
      <ol className="tag-rows stage-rows" aria-labelledby="pipeline-stages-title">
        {stages.map((stage, index) =>
          editing === stage.id ? (
            <StageEditRow
              key={stage.id}
              stage={stage}
              busy={busy}
              onSave={(edit) => {
                apply({ kind: "update", stageId: stage.id, ...edit }, "pipeline.stageSaved", () => {
                  setEditing(null);
                });
              }}
              onInvalid={() => {
                setError("pipeline.error.probability");
              }}
              onCancel={() => {
                setEditing(null);
              }}
            />
          ) : (
            <li key={stage.id} className="tag-row stage-row">
              <span className="stage-order" aria-hidden="true">
                {index + 1}
              </span>
              <span className="stage-name">{stage.name}</span>
              <span className="stage-probability">{t("pipeline.probabilityValue", { value: stage.probability })}</span>
              {canEdit ? (
                <span className="tag-row-actions">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("pipeline.moveUp", { name: stage.name })}
                    isDisabled={busy || index === 0}
                    onPress={() => {
                      move(index, -1);
                    }}
                  >
                    <ArrowUp size={13} aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("pipeline.moveDown", { name: stage.name })}
                    isDisabled={busy || index === stages.length - 1}
                    onPress={() => {
                      move(index, 1);
                    }}
                  >
                    <ArrowDown size={13} aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("pipeline.edit", { name: stage.name })}
                    isDisabled={busy}
                    onPress={() => {
                      setError(null);
                      setEditing(stage.id);
                    }}
                  >
                    <Pencil size={13} aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("pipeline.remove", { name: stage.name })}
                    isDisabled={busy || stages.length === 1}
                    onPress={() => {
                      setDeleting(stage);
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </Button>
                </span>
              ) : null}
            </li>
          ),
        )}
      </ol>
      {canEdit ? (
        <form className="tag-new stage-new" onSubmit={add}>
          <div className="form-field">
            <label htmlFor="stage-new-name" className="form-label">
              {t("pipeline.newStage")}
            </label>
            <input
              id="stage-new-name"
              className="form-input"
              value={draft.name}
              maxLength={40}
              onChange={(event) => {
                setDraft((current) => ({ ...current, name: event.target.value }));
              }}
            />
          </div>
          <div className="form-field stage-probability-field">
            <label htmlFor="stage-new-probability" className="form-label">
              {t("pipeline.probability")}
            </label>
            <input
              id="stage-new-probability"
              className="form-input"
              type="number"
              inputMode="numeric"
              value={draft.probability}
              onChange={(event) => {
                setDraft((current) => ({ ...current, probability: event.target.value }));
              }}
            />
          </div>
          <Button type="submit" isDisabled={busy || !draft.name.trim() || stages.length >= max}>
            <Plus size={14} aria-hidden="true" />
            {t("pipeline.addStage")}
          </Button>
        </form>
      ) : null}
      <p className="profile-note">{t("pipeline.outcomesNote")}</p>
      {deleting ? (
        <RemoveStageDialog
          stage={deleting}
          others={stages.filter((s) => s.id !== deleting.id)}
          onConfirm={confirmDelete}
          onCancel={() => {
            setDeleting(null);
          }}
        />
      ) : null}
    </section>
  );
}

/** Removing a stage names where its deals go (decision P4-B 8); the next
 *  stage is proposed. A stage without deals is simply removed. */
function RemoveStageDialog({
  stage,
  others,
  onConfirm,
  onCancel,
}: {
  stage: Stage;
  others: Stage[];
  onConfirm: (moveTo: string) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const next = others.find((s) => s.position > stage.position) ?? others[others.length - 1];
  const [target, setTarget] = useState(next?.id ?? "");
  return (
    <Dialog
      isOpen
      role="alertdialog"
      title={t("pipeline.removeTitle")}
      onClose={onCancel}
      actions={
        <>
          <Button onPress={onCancel}>{t("confirm.cancel")}</Button>
          <Button
            variant="destructive"
            isDisabled={!target}
            onPress={() => {
              onConfirm(target);
            }}
          >
            {t("pipeline.removeConfirm")}
          </Button>
        </>
      }
    >
      <p>{t("pipeline.removeMessage", { name: stage.name })}</p>
      <div className="form-field">
        <label htmlFor="stage-move-to" className="form-label">
          {t("pipeline.moveDealsTo")}
        </label>
        <select
          id="stage-move-to"
          className="form-input form-select"
          value={target}
          onChange={(event) => {
            setTarget(event.target.value);
          }}
        >
          {others.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
    </Dialog>
  );
}

function StageEditRow({
  stage,
  busy,
  onSave,
  onInvalid,
  onCancel,
}: {
  stage: Stage;
  busy: boolean;
  onSave: (edit: { name?: string; probability?: number }) => void;
  onInvalid: () => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(stage.name);
  const [probability, setProbability] = useState(String(stage.probability));
  const input = useRef<HTMLInputElement>(null);
  // The edit was just asked for: its first field takes focus.
  useEffect(() => {
    input.current?.focus();
  }, []);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    const nextName = name.trim();
    const nextProbability = percentage(probability);
    if (!nextName) return;
    if (nextProbability === null) {
      onInvalid();
      return;
    }
    const edit = {
      ...(nextName === stage.name ? {} : { name: nextName }),
      ...(nextProbability === stage.probability ? {} : { probability: nextProbability }),
    };
    if (Object.keys(edit).length === 0) onCancel();
    else onSave(edit);
  };

  return (
    <li className="tag-row editing">
      <form className="tag-new stage-new" onSubmit={submit}>
        <div className="form-field">
          <label htmlFor={`stage-name-${stage.id}`} className="form-label">
            {t("pipeline.stageName", { name: stage.name })}
          </label>
          <input
            ref={input}
            id={`stage-name-${stage.id}`}
            className="form-input"
            value={name}
            maxLength={40}
            onChange={(event) => {
              setName(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") onCancel();
            }}
          />
        </div>
        <div className="form-field stage-probability-field">
          <label htmlFor={`stage-probability-${stage.id}`} className="form-label">
            {t("pipeline.probability")}
          </label>
          <input
            id={`stage-probability-${stage.id}`}
            className="form-input"
            type="number"
            inputMode="numeric"
            value={probability}
            onChange={(event) => {
              setProbability(event.target.value);
            }}
          />
        </div>
        <Button type="submit" variant="primary" isDisabled={busy}>
          {t("pipeline.save")}
        </Button>
        <Button onPress={onCancel}>{t("confirm.cancel")}</Button>
      </form>
    </li>
  );
}
