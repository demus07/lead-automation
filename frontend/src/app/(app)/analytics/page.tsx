"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { Section } from "@/components/shared/section";
import { Stat } from "@/components/shared/stat";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/shared/states";
import { AnalyticsTabs, BarList, DailyBars, RangeToggle } from "@/components/analytics/parts";
import { api } from "@/lib/api";
import { fmtNumber, fmtPercent, fmtUsd, humanize, serviceLabel } from "@/lib/format";
import { DRAFT_STATUS_META } from "@/lib/status";
import type { DraftStatus } from "@/lib/types";

interface CampaignRow {
  id: string;
  name: string;
  companies: number;
  qualified: number;
  contacted: number;
  replied: number;
  positive: number;
  reply_rate: number | null;
}

interface Analytics {
  days: number;
  funnel: { stage: string; count: number }[];
  by_service: Record<string, number>;
  by_source: { provider: string; companies: number }[];
  discovered_daily: { date: string; count: number }[];
  approvals: Record<string, number>;
  drafts: Record<string, number>;
  avg_quality: number | null;
  edit_rate: number;
  approval_rate: number | null;
  emails_sent_by_user: number;
  replies: Record<string, number>;
  reply_rate: number | null;
  campaigns: CampaignRow[];
  signals: Record<string, number>;
  ai_cost_usd: number;
  cost_per_approved_draft: number | null;
}

const SERVICE_COLOR: Record<string, string> = {
  website: "var(--svc-website)",
  company_brain: "var(--svc-brain)",
};

function sorted(rec: Record<string, number>) {
  return Object.entries(rec).sort((a, b) => b[1] - a[1]);
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const q = useQuery({
    queryKey: ["analytics", days],
    queryFn: () => api.get<Analytics>("/analytics", { days }),
    placeholderData: (p) => p,
  });

  const header = (
    <PageHeader
      title="Analytics"
      description="How leads move through the pipeline, and what it costs. Counts cover companies discovered in the selected period."
      actions={<RangeToggle value={days} onChange={setDays} />}
    />
  );

  if (q.isLoading) return (<>{header}<AnalyticsTabs /><PageSkeleton /></>);
  if (q.error || !q.data) return (<>{header}<AnalyticsTabs /><ErrorState error={q.error} retry={() => q.refetch()} /></>);
  const a = q.data;
  const top = a.funnel[0]?.count ?? 0;

  const campaignCols: Column<CampaignRow>[] = [
    { key: "name", header: "Campaign", cell: (c) => <Link href={`/campaigns/${c.id}`} className="font-medium hover:underline">{c.name}</Link> },
    { key: "companies", header: "Companies", className: "tabular-nums", cell: (c) => fmtNumber(c.companies) },
    { key: "qualified", header: "Qualified", className: "tabular-nums", cell: (c) => fmtNumber(c.qualified) },
    { key: "contacted", header: "Contacted", hideBelow: "sm", className: "tabular-nums", cell: (c) => fmtNumber(c.contacted) },
    { key: "replied", header: "Replied", hideBelow: "sm", className: "tabular-nums", cell: (c) => fmtNumber(c.replied) },
    { key: "positive", header: "Positive", hideBelow: "md", className: "tabular-nums", cell: (c) => fmtNumber(c.positive) },
    { key: "rate", header: "Reply rate", className: "tabular-nums", cell: (c) => fmtPercent(c.reply_rate, 1) },
  ];

  const replyTotal = Object.values(a.replies).reduce((s, n) => s + n, 0);

  return (
    <>
      {header}
      <AnalyticsTabs />
      <div className={q.isFetching ? "opacity-70 transition-opacity" : undefined}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="Companies discovered" value={fmtNumber(top)} />
          <Stat label="Approval rate" value={fmtPercent(a.approval_rate)} hint="approved ÷ (approved + rejected)" />
          <Stat label="Drafts edited by you" value={fmtPercent(a.edit_rate)} />
          <Stat label="Average draft quality" value={a.avg_quality ?? "—"} />
          <Stat label="Reply rate" value={fmtPercent(a.reply_rate, 1)} hint={`${a.emails_sent_by_user} sent by you`} />
          <Stat label="AI spend" value={fmtUsd(a.ai_cost_usd)} hint={a.cost_per_approved_draft !== null ? `${fmtUsd(a.cost_per_approved_draft)} per approved draft` : undefined} />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Section title="Funnel" description="Companies that reached each stage (or beyond).">
            {top === 0 ? (
              <p className="text-sm text-muted-foreground">No companies discovered in this period.</p>
            ) : (
              <ol className="space-y-3">
                {a.funnel.map((f, i) => {
                  const prev = i === 0 ? null : a.funnel[i - 1].count;
                  return (
                    <li key={f.stage} className="space-y-1">
                      <div className="flex items-baseline justify-between gap-2 text-sm">
                        <span>{f.stage}</span>
                        <span className="tabular-nums">
                          <span className="font-semibold">{fmtNumber(f.count)}</span>
                          {prev !== null && (
                            <span className="ml-2 text-xs text-muted-foreground">{prev ? fmtPercent(f.count / prev) : "—"} of previous</span>
                          )}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                        <div className="h-full rounded-full bg-brand" style={{ width: `${(f.count / top) * 100}%`, opacity: 1 - i * 0.09 }} />
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Section>
          <Section title="Discovered per day">
            <DailyBars data={a.discovered_daily} days={days} valueKey="count" label="Companies" />
          </Section>
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          <Section title="Recommended service">
            <BarList
              items={sorted(a.by_service).map(([k, v]) => ({ label: k === "unscored" ? "Not scored yet" : serviceLabel(k), value: v, color: SERVICE_COLOR[k] ?? "var(--chart-5)" }))}
            />
          </Section>
          <Section title="Source">
            <BarList items={[...a.by_source].sort((x, y) => y.companies - x.companies).map((s) => ({ label: humanize(s.provider), value: s.companies }))} />
          </Section>
          <Section title="Buying signals">
            <BarList items={sorted(a.signals).map(([k, v]) => ({ label: humanize(k), value: v, color: "var(--chart-4)" }))} empty="No signals found in this period." />
          </Section>
          <Section title="Review decisions" description="What reviewers did in the approval queue.">
            <BarList items={sorted(a.approvals).map(([k, v]) => ({ label: humanize(k), value: v, color: k === "approve" ? "var(--brand)" : "var(--chart-5)" }))} empty="No review decisions yet." />
          </Section>
          <Section title="Drafts by status">
            <BarList
              items={sorted(a.drafts).map(([k, v]) => ({ label: DRAFT_STATUS_META[k as DraftStatus]?.label ?? humanize(k), value: v, color: "var(--chart-3)" }))}
              empty="No drafts generated in this period."
            />
          </Section>
          <Section title="Replies" description={replyTotal ? `${replyTotal} inbound` : undefined}>
            <BarList items={sorted(a.replies).map(([k, v]) => ({ label: humanize(k), value: v, color: "var(--chart-2)" }))} empty="No replies in this period." />
          </Section>
        </div>

        <section className="mt-8 space-y-3">
          <h2 className="text-[0.95rem] font-semibold">Campaign performance</h2>
          {a.campaigns.length ? (
            <DataTable columns={campaignCols} rows={a.campaigns} rowKey={(c) => c.id} dense />
          ) : (
            <EmptyState icon={BarChart3} title="No campaigns yet" action={<Link href="/campaigns" className="text-sm underline underline-offset-4">Create a campaign</Link>} />
          )}
        </section>
      </div>
    </>
  );
}
