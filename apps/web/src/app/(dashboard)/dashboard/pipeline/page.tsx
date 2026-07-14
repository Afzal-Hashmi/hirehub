"use client";
/**
 * Kanban pipeline board — drag candidates between stages.
 * Uses @dnd-kit for accessible drag-and-drop.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useState } from "react";
import { useAuthStore } from "@/lib/store";
import { applicationsApi, jobsApi } from "@/lib/api";
import { scoreColor } from "@/lib/utils";
import { toast } from "sonner";

interface Stage {
  id: string;
  name: string;
  color: string;
  order: number;
}

interface Application {
  id: string;
  candidate: { full_name: string; email: string };
  job: { title: string };
  current_stage: Stage | null;
  ai_score: number | null;
  status: string;
}

function KanbanCard({ app }: { app: Application }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm cursor-grab hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
            <span className="text-xs font-semibold text-indigo-700">{app.candidate.full_name[0]}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{app.candidate.full_name}</p>
            <p className="text-xs text-gray-500 truncate">{app.job.title}</p>
          </div>
        </div>
        {app.ai_score !== null && (
          <span className={`text-xs font-bold shrink-0 ${scoreColor(app.ai_score)}`}>
            {app.ai_score}%
          </span>
        )}
      </div>
    </div>
  );
}

function KanbanColumn({ stage, apps }: { stage: Stage; apps: Application[] }) {
  return (
    <div className="flex-1 min-w-[220px] max-w-[280px]">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: stage.color }} />
        <h3 className="text-sm font-semibold text-gray-700">{stage.name}</h3>
        <span className="ml-auto text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
          {apps.length}
        </span>
      </div>
      <SortableContext items={apps.map((a) => a.id)} strategy={verticalListSortingStrategy}>
        <div className="space-y-2 min-h-[100px]">
          {apps.map((app) => (
            <KanbanCard key={app.id} app={app} />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}

export default function PipelinePage() {
  const { currentOrgId } = useAuthStore();
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const { data: jobs } = useQuery({
    queryKey: ["jobs", currentOrgId],
    queryFn: () => jobsApi.list(currentOrgId!).then((r) => r.data),
    enabled: !!currentOrgId,
  });

  const activeJobId = selectedJobId ?? jobs?.[0]?.id;

  const { data: job } = useQuery({
    queryKey: ["job", currentOrgId, activeJobId],
    queryFn: () => jobsApi.get(currentOrgId!, activeJobId!).then((r) => r.data),
    enabled: !!currentOrgId && !!activeJobId,
  });

  const { data: applications } = useQuery({
    queryKey: ["applications", currentOrgId, activeJobId],
    queryFn: () =>
      applicationsApi.list(currentOrgId!, { job_id: activeJobId, limit: 200 }).then((r) => r.data),
    enabled: !!currentOrgId && !!activeJobId,
  });

  const moveStageMutation = useMutation({
    mutationFn: ({ appId, stageId }: { appId: string; stageId: string }) =>
      applicationsApi.moveStage(currentOrgId!, appId, stageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications", currentOrgId, activeJobId] });
    },
    onError: () => toast.error("Failed to move candidate"),
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const stages: Stage[] = job?.stages ?? [];
  const appsByStage = new Map<string, Application[]>();
  stages.forEach((s: Stage) => appsByStage.set(s.id, []));
  applications?.forEach((app: Application) => {
    if (app.current_stage?.id) {
      appsByStage.get(app.current_stage.id)?.push(app);
    }
  });

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    // Find which stage the drop target belongs to
    const targetStageId = stages.find((s: Stage) =>
      appsByStage.get(s.id)?.some((a) => a.id === over.id) || s.id === over.id
    )?.id;

    if (targetStageId) {
      moveStageMutation.mutate({ appId: active.id as string, stageId: targetStageId });
    }
  };

  return (
    <div className="space-y-4 h-full">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Pipeline</h1>
        <select
          value={activeJobId ?? ""}
          onChange={(e) => setSelectedJobId(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {jobs?.map((j: { id: string; title: string }) => (
            <option key={j.id} value={j.id}>
              {j.title}
            </option>
          ))}
        </select>
      </div>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {stages.map((stage: Stage) => (
            <KanbanColumn
              key={stage.id}
              stage={stage}
              apps={appsByStage.get(stage.id) ?? []}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}
