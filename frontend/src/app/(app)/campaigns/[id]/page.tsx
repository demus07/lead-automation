"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, ListTree, Pencil, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { DetailList, Section } from "@/components/shared/section";
import { Stat } from "@/components/shared/stat";
import { DualScore, ServiceBadge } from "@/components/shared/score";
import { StatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/shared/states";
import { CampaignFormDialog } from "@/components/campaigns/campaign-form";
import { ArchiveCampaignButton, RunCampaignButton, ToggleActiveButton } from "@/components/campaigns/campaign-actions";
import { useProviders } from "@/components/campaigns/queries";
import { SearchHistoryTable } from "@/components/discovery/history-table";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtNumber, fmtRelative, humanize } from "@/lib/format";
import { LEAD_STATUSES, LEAD_STATUS_META } from "@/lib/status";
import type { Campaign, Company, Job, Page } from "@/lib/types";

function List({ items }: { items: string[] }) {
  return items.length ? <span>{items.join(", ")}</span> : <span className="text-muted-foreground">Any</span>;
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan("operator");
  const [editing, setEditing] = useState(false);
  const [showQueries, setShowQueries] = useState(false);
  const [page, setPage] = useState(1);

  const c = useQuery({ queryKey: ["campaigns", id], queryFn: () => api.get<Campaign>(`/campaigns/${id}`) });
  const providers = useProviders();
  const queries = useQuery({
    queryKey: ["campaigns", id, "queries"],
    queryFn: () => api.get<{ queries: unknown[] }>(`/campaigns/${id}/preview-queries`),
    enabled: showQueries,
  });
  const companies = useQuery({
    queryKey: ["companies", { campaign_id: id, page }],
    queryFn: () => api.get<Page<Company>>("/companies", { campaign_id: id, page, page_size: 10, sort: "-created_at" }),
    placeholderData: (p) => p,
  });
  const jobs = useQuery({
    queryKey: ["workflows", "jobs", "campaign", id],
    queryFn: () => api.get<Page<Job>>("/workflows/jobs", { page_size: 100 }),
    select: (d) => d.items.filter((j) => j.campaign_id === id || j.params?.campaign_id === id).slice(0, 8),
    refetchInterval: (q) => (q.state.data?.items.some((j) => (j.campaign_id === id || j.params?.campaign_id === id) && ["queued", "running"].includes(j.status)) ? 4000 : false),
  });

  if (c.isLoading) return <PageSkeleton />;
  if (c.error || !c.data) return <ErrorState error={c.error} retry={() => c.refetch()} />;
  const camp = c.data;
  const byStatus = camp.stats.by_status ?? {};
  const totalCompanies = camp.stats.companies ?? 0;
  const providerLabel = (k: string) => providers.data?.providers.find((p) => p.key === k)?.label ?? humanize(k);

  const companyCols: Column<Company>[] = [
    { key: "name", header: "Company", cell: (r) => <div><Link href={`/companies/${r.id}`} className="font-medium hover:underline">{r.name}</Link><div className="text-xs text-muted-foreground">{r.domain}</div></div> },
    { key: "status", header: "Status", cell: (r) => <StatusBadge kind="lead" value={r.status} /> },
    { key: "scores", header: "Website · Brain", cell: (r) => <DualScore compact website={r.website_score} brain={r.brain_score} recommended={r.recommended_service} /> },
    { key: "added", header: "Added", hideBelow: "md", className: "text-muted-foreground", cell: (r) => fmtRelative(r.created_at) },
  ];

  return (
    <>
      <PageHeader
        back={{ href: "/campaigns", label: "Campaigns" }}
        title={camp.name}
        description={camp.description || undefined}
        meta={
          <>
            <ToneBadge tone={camp.is_active ? "success" : "neutral"} dot>{camp.is_active ? "Active" : "Paused"}</ToneBadge>
            {camp.target_service !== "any" && <ServiceBadge service={camp.target_service} />}
            {camp.auto_research && <ToneBadge tone="neutral">Auto-research on</ToneBadge>}
          </>
        }
        actions={
          <>
            <ArchiveCampaignButton campaign={camp} onDone={() => router.push("/campaigns")} />
            {can && <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}
            <ToggleActiveButton campaign={camp} />
            <RunCampaignButton campaign={camp} />
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Companies found" value={fmtNumber(totalCompanies)} />
        <Stat label="Qualified or further" value={fmtNumber(camp.stats.qualified ?? 0)} emphasis />
        <Stat label="Unsent drafts in mailbox" value={fmtNumber(camp.stats.email_drafts ?? 0)} />
        <Stat label="Replied" value={fmtNumber(camp.stats.replied ?? 0)} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <Section title="Lead status" description="Where this campaign's companies are in the pipeline.">
            {totalCompanies === 0 ? (
              <p className="text-sm text-muted-foreground">No companies yet. Run the campaign to start discovery.</p>
            ) : (
              <div className="space-y-4">
                <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                  {LEAD_STATUSES.filter((s) => byStatus[s]).map((s, i) => (
                    <div key={s} style={{ width: `${(byStatus[s]! / totalCompanies) * 100}%`, background: `var(--chart-${(i % 5) + 1})` }} />
                  ))}
                </div>
                <ul className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
                  {LEAD_STATUSES.filter((s) => byStatus[s]).map((s, i) => (
                    <li key={s} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2">
                        <span className="size-2 rounded-full" style={{ background: `var(--chart-${(i % 5) + 1})` }} />
                        {LEAD_STATUS_META[s].label}
                      </span>
                      <span className="tabular-nums text-muted-foreground">{byStatus[s]}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Section>

          <Section title="Companies" bodyClassName="p-4" actions={<Button variant="ghost" size="sm" asChild><Link href={`/companies`}>All companies</Link></Button>}>
            <div>
              <DataTable
                columns={companyCols}
                rows={companies.data?.items}
                rowKey={(r) => r.id}
                isLoading={companies.isFetching}
                error={companies.error}
                onRetry={() => companies.refetch()}
                page={page}
                pageSize={10}
                total={companies.data?.total}
                onPageChange={setPage}
                onRowClick={(r) => router.push(`/companies/${r.id}`)}
                dense
                empty={{ icon: Building2, title: "No companies yet", description: "Companies discovered by this campaign will appear here." }}
              />
            </div>
          </Section>

          <Section title="Search history" description="Every query this campaign ran and what it found.">
            <SearchHistoryTable campaignId={id} providers={providers.data?.providers} pageSize={10} />
          </Section>
        </div>

        <div className="min-w-0 space-y-6">
          <Section title="Targeting">
            <DetailList
              className="grid-cols-1 gap-y-1 [&_dt]:mt-2 [&_dt]:text-xs"
              items={[
                { label: "Industries", value: <List items={camp.industries} /> },
                { label: "Geographies", value: <List items={camp.geographies} /> },
                { label: "Company sizes", value: <List items={camp.company_sizes} /> },
                { label: "Target roles", value: <List items={camp.target_roles} /> },
                { label: "Keywords", value: <List items={camp.keywords} /> },
                { label: "Signal focus", value: <List items={camp.signal_focus.map(humanize)} /> },
                { label: "Sources", value: camp.sources.length ? camp.sources.map(providerLabel).join(", ") : <span className="text-muted-foreground">All configured sources</span> },
                { label: "RSS feeds", value: <List items={camp.rss_feeds} /> },
                { label: "Daily limits", value: <span className="tabular-nums">{camp.daily_company_limit} companies · {camp.daily_query_limit} queries</span> },
              ]}
            />
          </Section>

          <Section
            title="Generated queries"
            description="What web-search providers will be asked on the next run."
            actions={!showQueries && <Button variant="outline" size="sm" onClick={() => setShowQueries(true)}><ListTree /> Preview</Button>}
          >
            {!showQueries ? (
              <p className="text-sm text-muted-foreground">Preview the queries built from this campaign&apos;s targeting and templates.</p>
            ) : queries.isLoading ? (
              <p className="text-sm text-muted-foreground">Building queries…</p>
            ) : queries.error ? (
              <ErrorState error={queries.error} retry={() => queries.refetch()} />
            ) : queries.data?.queries.length ? (
              <ol className="space-y-1.5 text-sm">
                {queries.data.queries.map((q, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="w-5 shrink-0 text-right text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                    <span className="min-w-0 break-words">{typeof q === "string" ? q : JSON.stringify(q)}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">No queries — add industries, keywords, signal focus or templates.</p>
            )}
          </Section>

          <Section title="Recent jobs" actions={<Button variant="ghost" size="sm" asChild><Link href="/automation">Automation</Link></Button>}>
            {jobs.data?.length ? (
              <ul className="space-y-2 text-sm">
                {jobs.data.map((j) => (
                  <li key={j.id} className="flex items-center justify-between gap-2">
                    <Link href={`/automation?job=${j.id}`} className="min-w-0 truncate hover:underline">{humanize(j.workflow)}</Link>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-muted-foreground">{fmtRelative(j.created_at)}</span>
                      <StatusBadge kind="job" value={j.status} />
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState compact icon={Workflow} title="No jobs yet" description="Run the campaign to start a discovery job." />
            )}
          </Section>
        </div>
      </div>

      <CampaignFormDialog open={editing} onOpenChange={setEditing} campaign={camp} />
    </>
  );
}
