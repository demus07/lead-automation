"use client";

import { useState } from "react";
import Link from "next/link";
import { Megaphone, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { ToneBadge } from "@/components/shared/tone-badge";
import { ServiceBadge } from "@/components/shared/score";
import { CampaignFormDialog } from "@/components/campaigns/campaign-form";
import { RunCampaignButton, ToggleActiveButton } from "@/components/campaigns/campaign-actions";
import { useCampaigns } from "@/components/campaigns/queries";
import { useCan } from "@/hooks/use-auth";
import { fmtNumber, fmtRelative } from "@/lib/format";
import type { Campaign } from "@/lib/types";
import { useRouter } from "next/navigation";

export default function CampaignsPage() {
  const q = useCampaigns();
  const can = useCan("operator");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rows = (q.data ?? []).filter((c) => !search || c.name.toLowerCase().includes(search.toLowerCase()));

  const columns: Column<Campaign>[] = [
    {
      key: "name",
      header: "Campaign",
      cell: (c) => (
        <div className="min-w-0">
          <Link href={`/campaigns/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
          <div className="truncate text-xs text-muted-foreground">
            {[c.industries.slice(0, 3).join(", "), c.geographies.slice(0, 2).join(", ")].filter(Boolean).join(" in ") || "No filters"}
          </div>
        </div>
      ),
    },
    {
      key: "state",
      header: "State",
      cell: (c) => <ToneBadge tone={c.is_active ? "success" : "neutral"} dot>{c.is_active ? "Active" : "Paused"}</ToneBadge>,
    },
    { key: "service", header: "Service", hideBelow: "md", cell: (c) => (c.target_service === "any" ? <span className="text-xs text-muted-foreground">Any</span> : <ServiceBadge service={c.target_service} />) },
    { key: "companies", header: "Companies", className: "tabular-nums", cell: (c) => fmtNumber(c.stats.companies ?? 0) },
    { key: "qualified", header: "Qualified", hideBelow: "sm", className: "tabular-nums", cell: (c) => fmtNumber(c.stats.qualified ?? 0) },
    { key: "drafts", header: "Mailbox drafts", hideBelow: "lg", className: "tabular-nums", cell: (c) => fmtNumber(c.stats.email_drafts ?? 0) },
    { key: "replied", header: "Replied", hideBelow: "lg", className: "tabular-nums", cell: (c) => fmtNumber(c.stats.replied ?? 0) },
    { key: "updated", header: "Updated", hideBelow: "md", className: "text-muted-foreground", cell: (c) => fmtRelative(c.updated_at) },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (c) => (
        <div className="flex justify-end gap-1.5">
          <ToggleActiveButton campaign={c} />
          <RunCampaignButton campaign={c} />
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Each campaign describes the companies you want and where discovery should look for them."
        actions={can && <Button onClick={() => setOpen(true)}><Plus /> New campaign</Button>}
      />
      <DataTable
        columns={columns}
        rows={q.data ? rows : undefined}
        rowKey={(c) => c.id}
        isLoading={q.isLoading}
        error={q.error}
        onRetry={() => q.refetch()}
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search campaigns"
        onRowClick={(c) => router.push(`/campaigns/${c.id}`)}
        empty={{
          icon: Megaphone,
          title: search ? "No campaigns match" : "No campaigns yet",
          description: search ? "Try a different name." : "Create a campaign to start discovering companies on a schedule.",
          action: can && !search ? <Button onClick={() => setOpen(true)}><Plus /> New campaign</Button> : undefined,
        }}
      />
      <CampaignFormDialog open={open} onOpenChange={setOpen} onSaved={(c) => router.push(`/campaigns/${c.id}`)} />
    </>
  );
}
