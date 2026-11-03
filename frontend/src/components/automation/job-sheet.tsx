"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Ban, Loader2, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { JsonView } from "@/components/shared/json-view";
import { DetailList } from "@/components/shared/section";
import { ErrorState, TableSkeleton } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMs, humanize } from "@/lib/format";
import type { Job } from "@/lib/types";

const ACTIVE = ["queued", "running"];
const RETRYABLE = ["failed", "partial", "cancelled", "skipped"];

interface LogEntry {
  at?: string;
  msg?: string;
  data?: unknown;
}
interface ErrEntry {
  at?: string;
  error?: string;
  [k: string]: unknown;
}

function duration(j: Job) {
  if (!j.started_at) return "—";
  const end = j.finished_at ? new Date(j.finished_at).getTime() : Date.now();
  return fmtMs(end - new Date(j.started_at).getTime());
}

export function JobActions({ job, onRetried, size = "sm" }: { job: Job; onRetried?: (j: Job) => void; size?: "sm" | "xs" }) {
  const can = useCan("operator");
  const retry = useApiMutation(() => api.post<Job>(`/workflows/jobs/${job.id}/retry`), {
    success: "Job retried",
    invalidate: [["workflows"]],
    onSuccess: (j) => onRetried?.(j),
  });
  const cancel = useApiMutation(() => api.post<Job>(`/workflows/jobs/${job.id}/cancel`), {
    // The API returns 200 even if the job finished before the cancel landed.
    success: (j) => (j.status === "cancelled" ? "Job cancelled" : `Job already ${j.status}; nothing to cancel`),
    invalidate: [["workflows"]],
  });
  if (!can) return null;
  return (
    <div className="flex gap-1.5">
      {RETRYABLE.includes(job.status) && (
        <Button variant="outline" size={size} onClick={() => retry.mutate()} disabled={retry.isPending}>
          {retry.isPending ? <Loader2 className="animate-spin" /> : <RotateCw />} Retry
        </Button>
      )}
      {ACTIVE.includes(job.status) && (
        <ConfirmDialog
          trigger={<Button variant="outline" size={size}><Ban /> Cancel</Button>}
          title="Cancel this job?"
          description="It stops before the next item. Work already done is kept."
          confirmLabel="Cancel job"
          cancelLabel="Keep running"
          destructive
          onConfirm={() => cancel.mutateAsync()}
        />
      )}
    </div>
  );
}

export function JobSheet({ jobId, onClose, onOpenJob }: { jobId: string | null; onClose: () => void; onOpenJob: (id: string) => void }) {
  const q = useQuery({
    queryKey: ["workflows", "job", jobId],
    queryFn: () => api.get<Job>(`/workflows/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data && ACTIVE.includes(query.state.data.status) ? 3000 : false),
  });
  const j = q.data;
  const log = (j?.log ?? []) as LogEntry[];
  const errors = (j?.errors ?? []) as ErrEntry[];

  return (
    <Sheet open={!!jobId} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {j ? humanize(j.workflow) : "Job"}
            {j && <StatusBadge kind="job" value={j.status} />}
          </SheetTitle>
          <SheetDescription className="font-mono text-xs">{jobId}</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-4 pb-8">
          {q.isLoading ? (
            <TableSkeleton rows={5} cols={2} />
          ) : q.error || !j ? (
            <ErrorState error={q.error} retry={() => q.refetch()} />
          ) : (
            <>
              <JobActions job={j} onRetried={(n) => onOpenJob(n.id)} />
              <DetailList
                items={[
                  { label: "Trigger", value: humanize(j.trigger) },
                  { label: "Created", value: fmtDateTime(j.created_at) },
                  { label: "Started", value: fmtDateTime(j.started_at) },
                  { label: "Finished", value: fmtDateTime(j.finished_at) },
                  { label: "Duration", value: duration(j) },
                  { label: "Attempts", value: <span className="tabular-nums">{j.attempts} of {j.max_attempts}</span> },
                  ...(j.next_retry_at ? [{ label: "Next retry", value: fmtDateTime(j.next_retry_at) }] : []),
                  ...(j.parent_id ? [{ label: "Started by", value: <button className="underline underline-offset-4" onClick={() => onOpenJob(j.parent_id!)}>Parent job</button> }] : []),
                  ...(j.campaign_id ? [{ label: "Campaign", value: <Link className="underline underline-offset-4" href={`/campaigns/${j.campaign_id}`}>Open campaign</Link> }] : []),
                  ...(j.company_id ? [{ label: "Company", value: <Link className="underline underline-offset-4" href={`/companies/${j.company_id}`}>Open company</Link> }] : []),
                ]}
              />
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Stats</h3>
                {Object.keys(j.stats).length ? (
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
                    {Object.entries(j.stats).map(([k, v]) => (
                      <div key={k} className="min-w-0">
                        <dt className="text-xs text-muted-foreground">{humanize(k)}</dt>
                        <dd className="truncate text-sm font-medium tabular-nums">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-sm text-muted-foreground">No stats yet.</p>
                )}
              </div>
              {errors.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Errors ({errors.length})</h3>
                  <ul className="space-y-1.5">
                    {errors.map((e, i) => (
                      <li key={i} className="tone tone-danger rounded-lg border px-3 py-2 text-xs">
                        <p className="text-foreground">{e.error ?? JSON.stringify(e)}</p>
                        {e.at && <p className="mt-0.5 text-muted-foreground">{fmtDateTime(e.at)}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Log</h3>
                {log.length ? (
                  <ol className="space-y-1 border-l pl-3 text-xs">
                    {log.map((l, i) => (
                      <li key={i}>
                        <span className="mr-2 text-muted-foreground tabular-nums">{l.at ? fmtDateTime(l.at).split(", ")[1] : ""}</span>
                        {l.msg}
                        {l.data !== undefined && <span className="ml-1 text-muted-foreground">{JSON.stringify(l.data)}</span>}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm text-muted-foreground">No log entries.</p>
                )}
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Parameters</h3>
                <JsonView value={j.params} />
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
