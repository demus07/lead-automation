"use client";

import { Archive, Loader2, Pause, Play, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import type { Campaign } from "@/lib/types";

export function useRunCampaign() {
  return useApiMutation((id: string) => api.post<{ job_id: string; status: string }>(`/campaigns/${id}/run`, {}), {
    success: false,
    invalidate: [["workflows"], ["discovery", "history"]],
    onSuccess: (res) => jobStartedToast("Discovery started", res),
  });
}

export function RunCampaignButton({ campaign, size = "sm" }: { campaign: Campaign; size?: "sm" | "default" }) {
  const can = useCan("operator");
  const run = useRunCampaign();
  if (!can) return null;
  return (
    <Button
      size={size}
      onClick={() => run.mutate(campaign.id)}
      disabled={!campaign.is_active || run.isPending}
      title={campaign.is_active ? "Run discovery for this campaign now" : "Activate the campaign to run it"}
    >
      {run.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
      Run now
    </Button>
  );
}

export function ToggleActiveButton({ campaign, size = "sm" }: { campaign: Campaign; size?: "sm" | "default" }) {
  const can = useCan("operator");
  const m = useApiMutation((active: boolean) => api.patch<Campaign>(`/campaigns/${campaign.id}`, { is_active: active }), {
    success: (_d, active) => (active ? "Campaign activated" : "Campaign paused"),
    invalidate: [["campaigns"]],
  });
  if (!can) return null;
  return (
    <Button variant="outline" size={size} onClick={() => m.mutate(!campaign.is_active)} disabled={m.isPending}>
      {campaign.is_active ? <Pause /> : <Play />}
      {campaign.is_active ? "Pause" : "Activate"}
    </Button>
  );
}

export function ArchiveCampaignButton({ campaign, onDone, size = "sm" }: { campaign: Campaign; onDone?: () => void; size?: "sm" | "default" }) {
  const can = useCan("operator");
  const m = useApiMutation(() => api.delete(`/campaigns/${campaign.id}`), {
    success: "Campaign archived",
    invalidate: [["campaigns"]],
    onSuccess: () => onDone?.(),
  });
  if (!can) return null;
  return (
    <ConfirmDialog
      trigger={<Button variant="ghost" size={size}><Archive /> Archive</Button>}
      title={`Archive “${campaign.name}”?`}
      description="The campaign stops running and disappears from lists. Companies it already found are kept."
      confirmLabel="Archive campaign"
      destructive
      onConfirm={() => m.mutateAsync()}
    />
  );
}
