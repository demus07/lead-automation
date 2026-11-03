"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ClipboardList, Radio, ShieldAlert } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { ToneBadge } from "@/components/shared/tone-badge";
import { ExternalLink } from "@/components/shared/external-link";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtDate, fmtRelative, humanize, truncate } from "@/lib/format";
import type { Page, ResearchListItem, Signal } from "@/lib/types";

const SIGNAL_TYPES = [
  "funding",
  "product_launch",
  "expansion",
  "hiring",
  "executive_appointment",
  "acquisition",
  "rebrand",
  "digital_transformation",
  "growth",
  "partnership",
  "other",
];

export default function ResearchPage() {
  const [tab, setTab] = useState("reports");
  return (
    <>
      <PageHeader
        title="Research"
        description="Website research reports with measurable checks, and buying signals found in news and feeds."
      />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line" className="mb-5 border-b pb-1">
          <TabsTrigger value="reports" className="px-2.5"><ClipboardList /> Reports</TabsTrigger>
          <TabsTrigger value="signals" className="px-2.5"><Radio /> Signals</TabsTrigger>
        </TabsList>
        <TabsContent value="reports"><Reports /></TabsContent>
        <TabsContent value="signals"><Signals /></TabsContent>
      </Tabs>
    </>
  );
}

function Reports() {
  const router = useRouter();
  const t = useTableState<{ status: string }>({ filters: { status: "" } });
  const query = { q: t.q, status: t.filters.status || undefined, page: t.page, page_size: t.pageSize };
  const list = useQuery({
    queryKey: ["research", "list", query],
    queryFn: () => api.get<Page<ResearchListItem>>("/research", query),
    placeholderData: keepPreviousData,
  });
  const columns: Column<ResearchListItem>[] = [
    {
      key: "company",
      header: "Company",
      cell: (r) => (
        <div className="min-w-0 max-w-[26rem]">
          <Link href={`/research/${r.id}`} className="font-medium hover:underline">{r.company_name ?? "Unknown company"}</Link>
          <div className="truncate text-xs text-muted-foreground">{r.domain}</div>
        </div>
      ),
    },
    {
      key: "summary",
      header: "Summary",
      hideBelow: "lg",
      cell: (r) => <span className="line-clamp-2 max-w-[40ch] text-sm text-muted-foreground">{truncate(r.summary, 180) || "—"}</span>,
    },
    {
      key: "audit",
      header: "Audit",
      cell: (r) => <span className="font-medium tabular-nums">{r.audit_score ?? "—"}</span>,
    },
    {
      key: "coverage",
      header: "Pages · obs.",
      hideBelow: "md",
      cell: (r) => <span className="tabular-nums text-muted-foreground">{r.pages} · {r.observations}</span>,
    },
    {
      key: "method",
      header: "Method",
      hideBelow: "md",
      cell: (r) => (
        <div className="flex items-center gap-1.5">
          <ToneBadge tone={r.method === "llm" ? "violet" : "neutral"}>{r.method === "llm" ? "AI + checks" : "Checks only"}</ToneBadge>
          {r.injection_flags > 0 && (
            <ToneBadge tone="warning" title="Prompt-injection attempts were detected and neutralised">
              <ShieldAlert className="size-3" /> {r.injection_flags}
            </ToneBadge>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => <ToneBadge tone={r.status === "complete" ? "success" : r.status === "failed" ? "danger" : "info"}>{humanize(r.status)}</ToneBadge>,
    },
    { key: "when", header: "Researched", hideBelow: "sm", cell: (r) => <span className="text-xs text-muted-foreground">{fmtRelative(r.created_at)}</span> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={list.data?.items}
      rowKey={(r) => r.id}
      isLoading={list.isFetching}
      error={list.error}
      onRetry={() => list.refetch()}
      page={t.page}
      pageSize={t.pageSize}
      total={list.data?.total}
      onPageChange={t.setPage}
      search={t.q}
      onSearchChange={t.setQ}
      searchPlaceholder="Search company name"
      onRowClick={(r) => router.push(`/research/${r.id}`)}
      filters={
        <FilterSelect
          aria-label="Report status"
          value={t.filters.status}
          onChange={(v) => t.setFilter("status", v)}
          allLabel="All statuses"
          options={["complete", "partial", "failed"].map((s) => ({ value: s, label: humanize(s) }))}
        />
      }
      empty={{
        icon: ClipboardList,
        title: t.q || t.filters.status ? "No reports match" : "No research yet",
        description: "Run research from a company page or in bulk from the Companies list.",
      }}
    />
  );
}

function Signals() {
  const t = useTableState<{ signal_type: string; freshness: string; min_confidence: string }>({
    filters: { signal_type: "", freshness: "", min_confidence: "" },
  });
  const f = t.filters;
  const query = {
    signal_type: f.signal_type || undefined,
    freshness: f.freshness || undefined,
    min_confidence: f.min_confidence || undefined,
    page: t.page,
    page_size: t.pageSize,
  };
  const list = useQuery({
    queryKey: ["research", "signals", query],
    queryFn: () => api.get<Page<Signal>>("/research/signals", query),
    placeholderData: keepPreviousData,
  });
  const columns: Column<Signal>[] = [
    {
      key: "company",
      header: "Company",
      cell: (s) => <Link href={`/companies/${s.company_id}`} className="font-medium hover:underline">{s.company_name ?? "—"}</Link>,
    },
    { key: "type", header: "Signal", cell: (s) => <ToneBadge tone="violet">{humanize(s.signal_type)}</ToneBadge> },
    {
      key: "desc",
      header: "What happened",
      cell: (s) => (
        <div className="max-w-[48ch] space-y-0.5">
          <p className="line-clamp-2 text-sm">{s.description}</p>
          <ExternalLink href={s.source_url} className="text-xs">{s.source_name || undefined}</ExternalLink>
        </div>
      ),
    },
    {
      key: "fresh",
      header: "Freshness",
      hideBelow: "md",
      cell: (s) => <ToneBadge tone={s.freshness === "fresh" ? "success" : s.freshness === "recent" ? "info" : "neutral"}>{humanize(s.freshness)}</ToneBadge>,
    },
    {
      key: "conf",
      header: "Confidence",
      hideBelow: "md",
      cell: (s) => <span className="tabular-nums text-muted-foreground">{Math.round(s.confidence * 100)}% · {s.method}</span>,
    },
    { key: "date", header: "Published", hideBelow: "sm", cell: (s) => <span className="text-xs text-muted-foreground">{s.published_at ? fmtDate(s.published_at) : "Unknown"}</span> },
  ];
  return (
    <DataTable
      columns={columns}
      rows={list.data?.items}
      rowKey={(s) => s.id}
      isLoading={list.isFetching}
      error={list.error}
      onRetry={() => list.refetch()}
      page={t.page}
      pageSize={t.pageSize}
      total={list.data?.total}
      onPageChange={t.setPage}
      filters={
        <>
          <FilterSelect aria-label="Signal type" value={f.signal_type} onChange={(v) => t.setFilter("signal_type", v)} allLabel="All signal types" options={SIGNAL_TYPES.map((s) => ({ value: s, label: humanize(s) }))} />
          <FilterSelect aria-label="Freshness" value={f.freshness} onChange={(v) => t.setFilter("freshness", v)} allLabel="Any age" options={["fresh", "recent", "stale", "unknown"].map((s) => ({ value: s, label: humanize(s) }))} />
          <FilterSelect
            aria-label="Minimum confidence"
            value={f.min_confidence}
            onChange={(v) => t.setFilter("min_confidence", v)}
            allLabel="Any confidence"
            options={[
              { value: "0.5", label: "Confidence ≥ 50%" },
              { value: "0.7", label: "Confidence ≥ 70%" },
              { value: "0.9", label: "Confidence ≥ 90%" },
            ]}
          />
        </>
      }
      empty={{ icon: Radio, title: "No signals match", description: "Signals are collected during research from news and RSS feeds." }}
    />
  );
}
