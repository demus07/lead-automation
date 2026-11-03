"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { History } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/shared/data-table";
import { DetailList } from "@/components/shared/section";
import { ExternalLink } from "@/components/shared/external-link";
import { FilterSelect } from "@/components/shared/filter-select";
import { JsonView } from "@/components/shared/json-view";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative, humanize } from "@/lib/format";
import type { Campaign, DiscoveryProvider, Page } from "@/lib/types";

export interface SearchQueryRow {
  id: string;
  campaign_id: string | null;
  job_id: string | null;
  provider: string;
  query: string;
  params: Record<string, unknown>;
  trigger: string;
  status: string;
  result_count: number;
  new_companies: number;
  error: string | null;
  results: { url?: string; name?: string; domain?: string; title?: string; [k: string]: unknown }[];
  created_at: string;
}

function statusTone(s: string) {
  if (s === "ok") return "success" as const;
  if (s === "error" || s === "failed") return "danger" as const;
  return "neutral" as const;
}

export function SearchHistoryTable({
  campaignId,
  providers,
  campaigns,
  pageSize = 15,
}: {
  campaignId?: string;
  providers?: DiscoveryProvider[];
  campaigns?: Campaign[];
  pageSize?: number;
}) {
  const t = useTableState<{ provider: string; campaign: string }>({ pageSize, filters: { provider: "", campaign: "" } });
  const [open, setOpen] = useState<SearchQueryRow | null>(null);
  const cid = campaignId ?? t.filters.campaign;
  const q = useQuery({
    queryKey: ["discovery", "history", cid, t.filters.provider, t.page, t.pageSize],
    queryFn: () =>
      api.get<Page<SearchQueryRow>>("/discovery/history", {
        campaign_id: cid || undefined,
        provider: t.filters.provider || undefined,
        page: t.page,
        page_size: t.pageSize,
      }),
    placeholderData: (prev) => prev,
  });
  const campaignName = (id: string | null) => campaigns?.find((c) => c.id === id)?.name;
  const providerLabel = (k: string) => providers?.find((p) => p.key === k)?.label ?? humanize(k);

  const columns: Column<SearchQueryRow>[] = [
    { key: "when", header: "When", className: "text-muted-foreground whitespace-nowrap", cell: (r) => <span title={fmtDateTime(r.created_at)}>{fmtRelative(r.created_at)}</span> },
    { key: "provider", header: "Source", cell: (r) => <span className="whitespace-nowrap">{providerLabel(r.provider)}</span> },
    { key: "query", header: "Query", cell: (r) => <span className="line-clamp-2 max-w-[42ch] text-sm">{r.query}</span> },
    ...(campaignId ? [] : [{ key: "campaign", header: "Campaign", hideBelow: "lg" as const, cell: (r: SearchQueryRow) => (r.campaign_id ? <Link className="hover:underline" href={`/campaigns/${r.campaign_id}`}>{campaignName(r.campaign_id) ?? "Campaign"}</Link> : "—") }]),
    { key: "status", header: "Result", cell: (r) => <ToneBadge tone={statusTone(r.status)}>{humanize(r.status)}</ToneBadge> },
    { key: "found", header: "Found", className: "tabular-nums", cell: (r) => r.result_count },
    { key: "new", header: "New", className: "tabular-nums", cell: (r) => <span className={r.new_companies ? "font-medium text-brand" : "text-muted-foreground"}>{r.new_companies}</span> },
  ];

  return (
    <>
      <DataTable
        columns={columns}
        rows={q.data?.items}
        rowKey={(r) => r.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        page={t.page}
        pageSize={t.pageSize}
        total={q.data?.total}
        onPageChange={t.setPage}
        onRowClick={setOpen}
        dense
        filters={
          <>
            {providers && (
              <FilterSelect value={t.filters.provider} onChange={(v) => t.setFilter("provider", v)} allLabel="All sources" aria-label="Source" options={providers.map((p) => ({ value: p.key, label: p.label }))} />
            )}
            {!campaignId && campaigns && (
              <FilterSelect value={t.filters.campaign} onChange={(v) => t.setFilter("campaign", v)} allLabel="All campaigns" aria-label="Campaign" options={campaigns.map((c) => ({ value: c.id, label: c.name }))} />
            )}
          </>
        }
        empty={{ icon: History, title: "No searches yet", description: "Searches appear here after you run discovery." }}
      />
      <Sheet open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          {open && (
            <>
              <SheetHeader>
                <SheetTitle>{providerLabel(open.provider)}</SheetTitle>
                <SheetDescription>{open.query}</SheetDescription>
              </SheetHeader>
              <div className="space-y-6 px-4 pb-6">
                <DetailList
                  items={[
                    { label: "Run", value: fmtDateTime(open.created_at) },
                    { label: "Trigger", value: humanize(open.trigger) },
                    { label: "Result", value: <ToneBadge tone={statusTone(open.status)}>{humanize(open.status)}</ToneBadge> },
                    { label: "Found / new", value: <span className="tabular-nums">{open.result_count} / {open.new_companies}</span> },
                    { label: "Job", value: open.job_id ? <Link className="hover:underline" href={`/automation?job=${open.job_id}`}>View job</Link> : "—" },
                  ]}
                />
                {open.error && <p className="tone tone-danger rounded-lg border p-3 text-sm">{open.error}</p>}
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Results</h3>
                  {open.results.length ? (
                    <ul className="divide-y rounded-lg border text-sm">
                      {open.results.map((r, i) => (
                        <li key={i} className="flex items-center justify-between gap-3 px-3 py-2">
                          <span className="min-w-0 truncate font-medium">{r.name ?? r.title ?? r.domain ?? "Result"}</span>
                          <span className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                            {r.domain && <span>{r.domain}</span>}
                            {r.url && <ExternalLink href={r.url} className="text-xs">Source</ExternalLink>}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No results recorded.</p>
                  )}
                </div>
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Parameters</h3>
                  <JsonView value={open.params} />
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
