"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shared/field";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import type { WorkflowInfo } from "@/lib/types";

const PRESETS = [
  { label: "Every 15 min", cron: "*/15 * * * *" },
  { label: "Every 30 min", cron: "*/30 * * * *" },
  { label: "Hourly", cron: "0 * * * *" },
  { label: "Daily 06:00", cron: "0 6 * * *" },
  { label: "Weekdays 08:00", cron: "0 8 * * 1-5" },
];

export function ScheduleDialog({ wf, onOpenChange }: { wf: WorkflowInfo | null; onOpenChange: (v: boolean) => void }) {
  const [cron, setCron] = useState("");
  const [batch, setBatch] = useState(0);
  useEffect(() => {
    if (wf?.schedule) {
      setCron(wf.schedule.cron);
      setBatch(wf.schedule.batch_size);
    }
  }, [wf]);
  const save = useApiMutation(() => api.patch(`/workflows/${wf!.workflow}/schedule`, { cron: cron.trim(), batch_size: batch }), {
    success: "Schedule saved",
    invalidate: [["workflows"]],
    onSuccess: () => onOpenChange(false),
  });
  return (
    <Dialog open={!!wf} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit schedule · {wf?.label}</DialogTitle>
          <DialogDescription>Times are in the server&apos;s timezone (UTC unless configured otherwise).</DialogDescription>
        </DialogHeader>
        <form
          id="sched-form"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field label="Cron expression" htmlFor="cron" hint="minute hour day-of-month month day-of-week">
            <Input id="cron" value={cron} onChange={(e) => setCron(e.target.value)} className="font-mono" maxLength={100} />
          </Field>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button key={p.cron} type="button" onClick={() => setCron(p.cron)} className="h-6 rounded-md border px-2 text-xs text-muted-foreground hover:text-foreground">
                {p.label}
              </button>
            ))}
          </div>
          <Field label="Batch size" htmlFor="batch" hint="Items processed per scheduled run (0–500).">
            <Input id="batch" type="number" min={0} max={500} value={batch} onChange={(e) => setBatch(Math.max(0, Math.min(500, Number(e.target.value) || 0)))} />
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="sched-form" disabled={save.isPending || !cron.trim()}>
            {save.isPending && <Loader2 className="animate-spin" />}
            Save schedule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
