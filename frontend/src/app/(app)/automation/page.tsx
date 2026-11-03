"use client";

import { Suspense, useCallback, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PauseCircle, PlayCircle, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { Notice } from "@/components/shared/notice";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import { JobActions, JobSheet } from "@/components/automation/job-sheet";
import { ScheduleDialog } from "@/components/automation/schedule-dialog";
import { WorkflowList } from "@/components/automation/workflow-list";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMs, fmtRelative, humanize } from "@/lib/format";
import { JOB_STATUS_META } from "@/lib/status";
import type { Job, Page, WorkflowInfo } from "@/lib/types";

const ACTIVE = ["queued", "running"];

function statsSummary(stats: Record<string, unknown>) {
  const parts = Object.entries(stats)
    .filter(([, v]) => typeof v === "number")
    .slice(0, 3)
    .map(([k, v]) => `${humanize(k).toLowerCase()} ${v}`);
  return parts.join(", ");
}

function AutomationInner() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const jobId = params.get("job");
  const isAdmin = useCan("admin");
  const [editing, setEditing] = useState<WorkflowInfo | null>(null);
  const t = useTableState<{ workflow: string; status: string }>({ filters: { workflow: "", status: "" } });

  const openJob = useCallback(
    (id: string | null) => {
      const sp = new URLSearchParams(params.toString());
      if (id) sp.set("job", id);
      else sp.delete("job");
      const s = sp.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const jobs = useQuery({
    queryKey: ["workflows", "jobs", t.filters, t.page],
    queryFn: () => api.get<Page<Job>>("/workflows/jobs", { workflow: t.filters.workflow, status: t.filters.status, page: t.page, page_size: t.pageSize }),
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.items.some((j) => ACTIVE.includes(j.status)) ? 3000 : false),
  });
  const anyActive = jobs.data?.items.some((j) => ACTIVE.includes(j.status)) ?? false;
  const wfs = useQuery({
    queryKey: ["workflows", "list"],
    queryFn: () => api.get<{ workflows: WorkflowInfo[]; global_paused: boolean }>("/workflows"),
    refetchInterval: anyActive ? 5000 : 30_000,
  });
  const pauseAll = useApiMutation((paused: boolean) => api.post<{ global_paused: boolean }>("/workflows/pause-all", undefined, { paused }), {
    success: (r) => (r.global_paused ? "All automation paused" : "All automation resumed"),
    invalidate: [["workflows"]],
  });

  if (wfs.isLoading) return <PageSkeleton />;
  if (wfs.error || !wfs.data) return <ErrorState error={wfs.error} retry={() => wfs.refetch()} />;
  const { workflows, global_paused } = wfs.data;

  const columns: Column<Job>[] = [
    { key: "workflow", header: "Workflow", cell: (j) => <span className="font-medium">{humanize(j.workflow)}</span> },
    { key: "status", header: "Status", cell: (j) => <StatusBadge kind="job" value={j.status} /> },
    { key: "trigger", header: "Trigger", hideBelow: "md", className: "text-muted-foreground", cell: (j) => humanize(j.trigger) },
    { key: "stats", header: "Result", hideBelow: "lg", className: "text-muted-foreground", cell: (j) => <span className="line-clamp-1 max-w-[32ch] text-xs">{(j.errors?.length ? `${j.errors.length} errors · ` : "") + (statsSummary(j.stats) || "—")}</span> },
    { key: "created", header: "Started", className: "whitespace-nowrap text-muted-foreground", cell: (j) => <span title={fmtDateTime(j.created_at)}>{fmtRelative(j.created_at)}</span> },
    { key: "duration", header: "Took", hideBelow: "sm", className: "tabular-nums text-muted-foreground", cell: (j) => (j.started_at && j.finished_at ? fmtMs(new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) : "—") },
    { key: "actions", header: <span className="sr-only">Actions</span>, className: "text-right", cell: (j) => <div className="flex justify-end"><JobActions job={j} size="xs" onRetried={(n) => openJob(n.id)} /></div> },
  ];

  return (
    <>
      <PageHeader
        title="Automation"
        description="Seven workflows move leads from discovery to replies. Each runs on a schedule, and you can run, pause or retry any of them."
        actions={
          isAdmin &&
          (global_paused ? (
            <Button onClick={() => pauseAll.mutate(false)} disabled={pauseAll.isPending}><PlayCircle /> Resume all</Button>
          ) : (
            <ConfirmDialog
              trigger={<Button variant="outline"><PauseCircle /> Pause all</Button>}
              title="Pause all automation?"
              description="Scheduled runs stop until you resume. Jobs you start manually still run."
              confirmLabel="Pause all"
              onConfirm={() => pauseAll.mutateAsync(true)}
            />
          ))
        }
      />
      {global_paused && (
        <Notice tone="warning" title="All automation is paused" className="mb-6">
          Scheduled workflows won&apos;t run until an admin resumes them.
        </Notice>
      )}

      <WorkflowList workflows={workflows} globalPaused={global_paused} onEdit={setEditing} onOpenJob={openJob} />

      <section className="mt-10 space-y-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-[0.95rem] font-semibold">Jobs</h2>
          {anyActive && <span className="text-xs text-muted-foreground">Refreshing while jobs run</span>}
        </div>
        <DataTable
          columns={columns}
          rows={jobs.data?.items}
          rowKey={(j) => j.id}
          isLoading={jobs.isLoading}
          error={jobs.error}
          onRetry={() => jobs.refetch()}
          page={t.page}
          pageSize={t.pageSize}
          total={jobs.data?.total}
          onPageChange={t.setPage}
          onRowClick={(j) => openJob(j.id)}
          dense
          filters={
            <>
              <FilterSelect value={t.filters.workflow} onChange={(v) => t.setFilter("workflow", v)} allLabel="All workflows" aria-label="Workflow" options={workflows.map((w) => ({ value: w.workflow, label: humanize(w.workflow) }))} />
              <FilterSelect value={t.filters.status} onChange={(v) => t.setFilter("status", v)} allLabel="All statuses" aria-label="Status" options={Object.entries(JOB_STATUS_META).map(([k, m]) => ({ value: k, label: m.label }))} />
            </>
          }
          empty={{ icon: Workflow, title: "No jobs match", description: "Jobs appear here when a workflow runs on schedule or you start one." }}
        />
      </section>

      <JobSheet jobId={jobId} onClose={() => openJob(null)} onOpenJob={openJob} />
      <ScheduleDialog wf={editing} onOpenChange={(v) => !v && setEditing(null)} />
    </>
  );
}

export default function AutomationPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <AutomationInner />
    </Suspense>
  );
}
