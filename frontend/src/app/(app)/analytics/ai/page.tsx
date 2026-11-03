"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { Notice } from "@/components/shared/notice";
import { Section } from "@/components/shared/section";
import { Stat } from "@/components/shared/stat";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { ToneBadge } from "@/components/shared/tone-badge";
import { AnalyticsTabs, BarList, DailyBars, RangeToggle } from "@/components/analytics/parts";
import { useCan } from "@/hooks/use-auth";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMs, fmtNumber, fmtRelative, fmtUsd, humanize } from "@/lib/format";
import type { AIStatus, Page } from "@/lib/types";

interface Usage {
  days: number;
  totals: { calls: number; input_tokens: number; output_tokens: number; cached_tokens: number; cost_usd: number; avg_latency_ms: number };
  by_agent: { agent: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number }[];
  by_model: { provider: string; model: string; calls: number; cost_usd: number }[];
  by_status: Record<string, number>;
  daily: { date: string; calls: number; cost_usd: number }[];
  top_companies: { company_id: string; company_name: string | null; calls: number; cost_usd: number }[];
  status: AIStatus;
}

interface Run {
  id: string;
  agent: string;
  provider: string;
  model: string;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_tokens: number | null;
  cost_usd: number;
  latency_ms: number | null;
  attempts: number | null;
  company_id: string | null;
  job_id: string | null;
  error: string | null;
  created_at: string;
}

function runTone(s: string) {
  if (s === "ok" || s === "cached") return "success" as const;
  if (s === "budget_blocked") return "warning" as const;
  if (s === "error" || s === "invalid_output") return "danger" as const;
  return "neutral" as const;
}

export default function AIUsagePage() {
  const [days, setDays] = useState(30);
  const isAdmin = useCan("admin");
  const t = useTableState<{ agent: string; status: string }>({ filters: { agent: "", status: "" } });
  const usage = useQuery({ queryKey: ["ai", "usage", days], queryFn: () => api.get<Usage>("/ai/usage", { days }), placeholderData: (p) => p });
  const agents = useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => api.get<{ agents: { name: string; label: string }[] }>("/ai/status"),
    staleTime: 5 * 60_000,
  });
  const runs = useQuery({
    queryKey: ["ai", "runs", t.filters, t.page],
    queryFn: () => api.get<Page<Run>>("/ai/runs", { agent: t.filters.agent, status: t.filters.status, page: t.page, page_size: t.pageSize }),
    placeholderData: (p) => p,
  });

  const header = (
    <PageHeader
      title="Analytics"
      description="Model calls, tokens, cost and latency for every AI agent."
      actions={<RangeToggle value={days} onChange={setDays} />}
    />
  );
  if (usage.isLoading) return (<>{header}<AnalyticsTabs /><PageSkeleton /></>);
  if (usage.error || !usage.data) return (<>{header}<AnalyticsTabs /><ErrorState error={usage.error} retry={() => usage.refetch()} /></>);
  const u = usage.data;
  const agentLabel = (n: string) => agents.data?.agents.find((a) => a.name === n)?.label ?? humanize(n);
  const budgetUsed = u.status.daily_budget_usd ? u.status.spent_today_usd / u.status.daily_budget_usd : 0;

  const cols: Column<Run>[] = [
    { key: "when", header: "When", className: "whitespace-nowrap text-muted-foreground", cell: (r) => <span title={fmtDateTime(r.created_at)}>{fmtRelative(r.created_at)}</span> },
    { key: "agent", header: "Agent", cell: (r) => agentLabel(r.agent) },
    { key: "model", header: "Model", hideBelow: "md", cell: (r) => <span className="text-xs"><span className="text-muted-foreground">{r.provider}/</span>{r.model}</span> },
    { key: "status", header: "Status", cell: (r) => <span title={r.error ?? undefined}><ToneBadge tone={runTone(r.status)}>{humanize(r.status)}</ToneBadge></span> },
    { key: "tokens", header: "Tokens in / out / cached", hideBelow: "lg", className: "tabular-nums text-xs", cell: (r) => `${fmtNumber(r.input_tokens)} / ${fmtNumber(r.output_tokens)} / ${fmtNumber(r.cached_tokens)}` },
    { key: "cost", header: "Cost", className: "tabular-nums", cell: (r) => fmtUsd(r.cost_usd) },
    { key: "latency", header: "Latency", hideBelow: "sm", className: "tabular-nums text-muted-foreground", cell: (r) => fmtMs(r.latency_ms) },
    { key: "company", header: "Company", hideBelow: "lg", cell: (r) => (r.company_id ? <Link className="text-xs hover:underline" href={`/companies/${r.company_id}`}>Open</Link> : <span className="text-muted-foreground">—</span>) },
    { key: "error", header: "Error", hideBelow: "lg", cell: (r) => (r.error ? <span className="line-clamp-1 max-w-[28ch] text-xs text-destructive" title={r.error}>{r.error}</span> : null) },
  ];

  return (
    <>
      {header}
      <AnalyticsTabs />
      {!u.status.available && (
        <Notice tone="warning" title="AI is not configured" className="mb-6" action={isAdmin ? { href: "/settings/ai", label: "Configure AI" } : undefined}>
          The app runs in limited mode: deterministic research, heuristic scoring, and no AI-written drafts. No model calls are made.
        </Notice>
      )}
      <div className={usage.isFetching ? "opacity-70 transition-opacity" : undefined}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="Model calls" value={fmtNumber(u.totals.calls)} />
          <Stat label="Cost" value={fmtUsd(u.totals.cost_usd)} />
          <Stat label="Input tokens" value={fmtNumber(u.totals.input_tokens)} hint={`${fmtNumber(u.totals.cached_tokens)} cached`} />
          <Stat label="Output tokens" value={fmtNumber(u.totals.output_tokens)} />
          <Stat label="Average latency" value={fmtMs(u.totals.avg_latency_ms || null)} />
          <Stat
            label="Spent today"
            value={fmtUsd(u.status.spent_today_usd)}
            hint={`of ${fmtUsd(u.status.daily_budget_usd)} daily budget`}
            className={budgetUsed >= 0.9 ? "border-destructive/50" : undefined}
          />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Section title="Daily cost">
            <DailyBars data={u.daily} days={days} valueKey="cost_usd" label="Cost" format={(n) => fmtUsd(n)} />
          </Section>
          <Section title="Cost by agent">
            <BarList items={u.by_agent.map((a) => ({ label: agentLabel(a.agent), value: a.cost_usd, hint: `${a.calls} calls · ${fmtMs(a.avg_latency_ms)}` }))} format={(n) => fmtUsd(n)} empty="No AI calls in this period." />
          </Section>
          <Section title="Models">
            <BarList items={u.by_model.map((m) => ({ label: `${m.provider}/${m.model}`, value: m.calls, hint: fmtUsd(m.cost_usd), color: "var(--chart-2)" }))} empty="No AI calls in this period." />
          </Section>
          <Section title="Most expensive companies">
            <BarList
              items={u.top_companies.map((c) => ({
                label: <Link href={`/companies/${c.company_id}`} className="hover:underline">{c.company_name ?? "Company"}</Link>,
                value: c.cost_usd,
                hint: `${c.calls} calls`,
                color: "var(--chart-3)",
              }))}
              format={(n) => fmtUsd(n)}
              empty="No company-level AI spend in this period."
            />
          </Section>
        </div>

        <section className="mt-8 space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[0.95rem] font-semibold">Runs</h2>
            {Object.keys(u.by_status).length > 0 && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {Object.entries(u.by_status).map(([s, n]) => `${n} ${humanize(s).toLowerCase()}`).join(", ")}
              </span>
            )}
          </div>
          <DataTable
            columns={cols}
            rows={runs.data?.items}
            rowKey={(r) => r.id}
            isLoading={runs.isLoading}
            error={runs.error}
            onRetry={() => runs.refetch()}
            page={t.page}
            pageSize={t.pageSize}
            total={runs.data?.total}
            onPageChange={t.setPage}
            dense
            filters={
              <>
                <FilterSelect value={t.filters.agent} onChange={(v) => t.setFilter("agent", v)} allLabel="All agents" aria-label="Agent" options={(agents.data?.agents ?? []).map((a) => ({ value: a.name, label: a.label }))} />
                <FilterSelect value={t.filters.status} onChange={(v) => t.setFilter("status", v)} allLabel="All statuses" aria-label="Status" options={["ok", "cached", "error", "invalid_output", "budget_blocked"].map((s) => ({ value: s, label: humanize(s) }))} />
              </>
            }
            empty={{ icon: Bot, title: "No AI runs", description: u.status.available ? "Runs appear as agents research, score and draft." : "Configure an AI provider to enable agents." }}
          />
        </section>
      </div>
    </>
  );
}
