import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";
import { ifMatch, unwrapWrite, where } from "./records";
import type { components } from "./schema";

/*
 * The workspace's sales pipeline and its stages (decision P4, slice 4A).
 * Every role reads it; Owners and Admins change it (`manage_pipeline` in
 * `/access`). Every change sends the pipeline's version and answers with
 * the whole pipeline at its new version, which replaces the cached one.
 */

export type Pipeline = components["schemas"]["PipelineOut"];
export type Stage = components["schemas"]["StageOut"];
type PipelineList = components["schemas"]["PipelineList"];

export const pipelineKeys = {
  all: (workspaceId: string) => ["workspace", workspaceId, "pipelines"] as const,
};

export function usePipelines(workspaceId: string) {
  return useQuery({
    queryKey: pipelineKeys.all(workspaceId),
    queryFn: async () =>
      unwrap(await api.GET("/v1/workspaces/{tenant_id}/pipelines", { params: { path: where(workspaceId) } })),
  });
}

export type PipelineChange =
  | { kind: "rename"; name: string }
  | { kind: "add"; name: string; probability: number }
  | { kind: "update"; stageId: string; name?: string; probability?: number }
  | { kind: "delete"; stageId: string }
  | { kind: "reorder"; stageIds: string[] };

async function send(workspaceId: string, pipeline: Pipeline, change: PipelineChange): Promise<Pipeline> {
  const path = { tenant_id: workspaceId, pipeline_id: pipeline.id };
  const header = ifMatch(pipeline.version);
  switch (change.kind) {
    case "rename":
      return unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}", {
          params: { path, header },
          body: { name: change.name },
        }),
      );
    case "add":
      return unwrapWrite(
        await api.POST("/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages", {
          params: { path, header },
          body: { name: change.name, probability: change.probability },
        }),
      );
    case "update":
      return unwrapWrite(
        await api.PATCH("/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages/{stage_id}", {
          params: { path: { ...path, stage_id: change.stageId }, header },
          body: {
            ...(change.name === undefined ? {} : { name: change.name }),
            ...(change.probability === undefined ? {} : { probability: change.probability }),
          },
        }),
      );
    case "delete":
      return unwrapWrite(
        await api.DELETE("/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages/{stage_id}", {
          params: { path: { ...path, stage_id: change.stageId }, header },
        }),
      );
    case "reorder":
      return unwrapWrite(
        await api.PUT("/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stage-order", {
          params: { path, header },
          body: { stage_ids: change.stageIds },
        }),
      );
  }
}

/** One mutation for every pipeline change; `pipeline` gives the version. */
export function useChangePipeline(workspaceId: string) {
  const client = useQueryClient();
  return useMutation<Pipeline, ApiError, { pipeline: Pipeline; change: PipelineChange }>({
    mutationFn: ({ pipeline, change }) => send(workspaceId, pipeline, change),
    onSuccess: (updated) => {
      client.setQueryData<PipelineList>(pipelineKeys.all(workspaceId), (current) =>
        current
          ? { ...current, items: current.items.map((item) => (item.id === updated.id ? updated : item)) }
          : current,
      );
    },
    // A refusal may mean the cached pipeline is stale: read it again.
    onError: () => client.invalidateQueries({ queryKey: pipelineKeys.all(workspaceId) }),
  });
}
