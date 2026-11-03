"use client";

import { CalendarClock, Loader2, Pause, Pencil, Play, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import { fmtDateTime, fmtRelative } from "@/lib/format";
import type { Job, WorkflowInfo } from "@/lib/types";

function WorkflowRow({ wf, globalPaused, onEdit, onOpenJob }: { wf: WorkflowInfo; globalPaused: boolean; onEdit: () => void; onOpenJob: (id: string) => void }) {
  const isOperator = useCan("operator");
  const isAdmin = useCan("admin");
  const s = wf.schedule;
  const run = useApiMutation(() => api.post<Job>(`/workflows/${wf.workflow}/run`, { params: {} }), {
    success: false,
    invalidate: [["workflows"]],
    onSuccess: (j) => {
      jobStartedToast(`${wf.label.replace(/^\d+ · /, "")} started`, { job_id: j.id, status: j.status });
      onOpenJob(j.id);
    },
  });
  const patch = useApiMutation((body: { paused?: boolean; enabled?: boolean }) => api.patch(`/workflows/${wf.workflow}/schedule`, body), {
    success: (_d, b) => (b.paused !== undefined ? (b.paused ? "Workflow paused" : "Workflow resumed") : b.enabled ? "Schedule enabled" : "Schedule disabled"),
    invalidate: [["workflows"]],
  });
  const canRun = wf.workflow === "maintenance" ? isAdmin : isOperator;
  const counts = wf.counts;
  const step = wf.label.match(/^(\d+) · (.*)$/);

  return (
    <li className="grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] md:items-center md:gap-6">
      <div className="flex min-w-0 gap-3">
        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium text-muted-foreground tabular-nums">
          {step ? step[1] : <CalendarClock className="size-3.5" />}
        </span>
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{step ? step[2] : wf.label}</span>
            {s && !s.enabled && <ToneBadge tone="neutral">Schedule off</ToneBadge>}
            {s?.paused && <ToneBadge tone="warning">Paused</ToneBadge>}
            {globalPaused && !s?.paused && <ToneBadge tone="warning">Paused globally</ToneBadge>}
          </div>
          <p className="text-sm text-pretty text-muted-foreground">{wf.description}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {s && <code className="font-mono">{s.cron}</code>}
            {s && <span>batch {s.batch_size}</span>}
            {s?.next_run_at && s.enabled && !s.paused && <span title={fmtDateTime(s.next_run_at)}>next {fmtRelative(s.next_run_at)}</span>}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pl-9 text-xs text-muted-foreground md:pl-0">
        {wf.last_job ? (
          <button type="button" onClick={() => onOpenJob(wf.last_job!.id)} className="inline-flex items-center gap-2 rounded hover:text-foreground">
            <StatusBadge kind="job" value={wf.last_job.status} />
            <span>{fmtRelative(wf.last_job.created_at)}</span>
          </button>
        ) : (
          <span>Never run</span>
        )}
        <span className="tabular-nums">
          {counts.succeeded ?? 0} ok
          {counts.failed ? <span className="text-destructive"> · {counts.failed} failed</span> : null}
          {counts.partial ? <span> · {counts.partial} partial</span> : null}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 pl-9 md:justify-end md:pl-0">
        {isAdmin && s && (
          <label className="mr-1 flex items-center gap-1.5 text-xs text-muted-foreground" title="Run on schedule">
            <Switch checked={s.enabled} onCheckedChange={(v) => patch.mutate({ enabled: v })} disabled={patch.isPending} aria-label="Run on schedule" size="sm" />
            Scheduled
          </label>
        )}
        {isAdmin && s && (
          <Button variant="ghost" size="icon-sm" onClick={onEdit} aria-label="Edit schedule" title="Edit schedule">
            <Pencil />
          </Button>
        )}
        {isAdmin && s && (
          <Button variant="outline" size="sm" onClick={() => patch.mutate({ paused: !s.paused })} disabled={patch.isPending}>
            {s.paused ? <Play /> : <Pause />}
            {s.paused ? "Resume" : "Pause"}
          </Button>
        )}
        {canRun && (
          <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
            Run now
          </Button>
        )}
      </div>
    </li>
  );
}

export function WorkflowList({ workflows, globalPaused, onEdit, onOpenJob }: { workflows: WorkflowInfo[]; globalPaused: boolean; onEdit: (w: WorkflowInfo) => void; onOpenJob: (id: string) => void }) {
  return (
    <ul className="divide-y rounded-xl border bg-card">
      {workflows.map((wf) => (
        <WorkflowRow key={wf.workflow} wf={wf} globalPaused={globalPaused} onEdit={() => onEdit(wf)} onOpenJob={onOpenJob} />
      ))}
    </ul>
  );
}
