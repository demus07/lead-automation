"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { KanbanSquare, Rows3 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { StatusBadge } from "@/components/shared/status-badge";
import { DualScore, ScoreBar, ServiceBadge } from "@/components/shared/score";
import { ErrorState } from "@/components/shared/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api } from "@/lib/api";
import { fmtRelative, truncate } from "@/lib/format";
import type { Campaign, LeadStatus, Opportunity, Page } from "@/lib/types";

interface PipelineItem {
  id: string;
  name: string;
  domain: string | null;
  status: LeadStatus;
  website_score: number | null;
  brain_score: number | null;
  recommended_service: string | null;
  updated_at: string;
}
interface Pipeline {
  columns: { label: string; statuses: LeadStatus[]; items: PipelineItem[] }[];
}

export default function PipelinePage() {
  const [view, setView] = useState<"board" | "table">("board");
  const [campaign, setCampaign] = useState("");
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns") });

  return (
    <div>
      <PageHeader
        title="Pipeline"
        description="Companies by stage, with website and Company Brain opportunity scored independently."
        actions={
          <ToggleGroup type="single" variant="outline" value={view} onValueChange={(v) => v && setView(v as "board" | "table")} aria-label="View">
            <ToggleGroupItem value="board" aria-label="Board">
              <KanbanSquare /> Board
            </ToggleGroupItem>
            <ToggleGroupItem value="table" aria-label="Opportunities table">
              <Rows3 /> Opportunities
            </ToggleGroupItem>
          </ToggleGroup>
        }
      />
      {view === "board" ? (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <FilterSelect
              value={campaign}
              onChange={setCampaign}
              allLabel="All campaigns"
              aria-label="Campaign"
              options={(campaigns.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
            />
          </div>
          <Board campaignId={campaign} />
        </>
      ) : (
        <OpportunitiesTable />
      )}
    </div>
  );
}

function Board({ campaignId }: { campaignId: string }) {
  const q = useQuery({
    queryKey: ["pipeline", campaignId],
    queryFn: () => api.get<Pipeline>("/opportunities/pipeline", { campaign_id: campaignId || undefined }),
    refetchInterval: 60_000,
  });
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const cols = q.data?.columns;
  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-4 md:-mx-8 md:px-8">
      <div className="flex min-w-max gap-3">
        {(cols ?? Array.from({ length: 7 }, () => null)).map((c, i) => (
          <div key={c?.label ?? i} className="flex w-64 shrink-0 flex-col rounded-xl bg-muted/50 p-2">
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-sm font-medium">{c?.label ?? <Skeleton className="h-4 w-24" />}</span>
              {c && <span className="text-xs text-muted-foreground tabular-nums">{c.items.length >= 50 ? "50+" : c.items.length}</span>}
            </div>
            <div className="flex max-h-[calc(100svh-17rem)] min-h-24 flex-col gap-2 overflow-y-auto p-0.5">
              {!c && <Skeleton className="h-20 rounded-lg" />}
              {c?.items.length === 0 && <p className="px-2 py-6 text-center text-xs text-muted-foreground">Empty</p>}
              {c?.items.map((it) => (
                <Link
                  key={it.id}
                  href={`/companies/${it.id}`}
                  className="block space-y-2 rounded-lg border bg-card p-3 shadow-xs transition-colors hover:border-foreground/20"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{it.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{it.domain}</p>
                    </div>
                    <DualScore compact website={it.website_score} brain={it.brain_score} recommended={it.recommended_service} />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    {c.statuses.length > 1 ? <StatusBadge kind="lead" value={it.status} /> : <ServiceBadge service={it.recommended_service} />}
                    <span className="text-[0.7rem] text-muted-foreground">{fmtRelative(it.updated_at)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function OpportunitiesTable() {
  const [page, setPage] = useState(1);
  const [service, setService] = useState("");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState<"best" | "recent">("best");
  const q = useQuery({
    queryKey: ["opportunities", page, service, minScore, sort],
    queryFn: () =>
      api.get<Page<Opportunity>>("/opportunities", {
        page,
        page_size: 25,
        service: service || undefined,
        min_score: minScore || undefined,
        sort,
      }),
    placeholderData: (prev) => prev,
  });

  const columns: Column<Opportunity>[] = [
    {
      key: "company",
      header: "Company",
      cell: (o) => (
        <Link href={`/companies/${o.company_id}`} className="block min-w-0">
          <span className="block truncate font-medium">{o.company?.name}</span>
          <span className="block truncate text-xs text-muted-foreground">{o.company?.domain ?? o.company?.industry}</span>
        </Link>
      ),
    },
    {
      key: "scores",
      header: "Website vs Company Brain",
      headClassName: "w-72",
      cell: (o) => (
        <div className="grid w-64 gap-2">
          <ScoreBar value={o.website_score} service="website" confidence={o.website_confidence} recommended={o.recommended_service === "website"} />
          <ScoreBar value={o.brain_score} service="company_brain" confidence={o.brain_confidence} recommended={o.recommended_service === "company_brain"} />
        </div>
      ),
    },
    {
      key: "rec",
      header: "Recommended",
      cell: (o) => (
        <div className="max-w-xs space-y-1">
          <ServiceBadge service={o.recommended_service} />
          {o.recommendation_reason && <p className="line-clamp-2 text-xs text-muted-foreground">{o.recommendation_reason}</p>}
        </div>
      ),
    },
    {
      key: "angle",
      header: "Sales angle",
      hideBelow: "lg",
      cell: (o) => <span className="line-clamp-3 max-w-sm text-xs text-muted-foreground">{truncate(o.sales_angle, 220) || "—"}</span>,
    },
    { key: "status", header: "Status", hideBelow: "md", cell: (o) => <StatusBadge kind="lead" value={o.company?.status} /> },
    { key: "method", header: "Method", hideBelow: "lg", cell: (o) => <span className="text-xs text-muted-foreground">{o.method ?? "—"}</span> },
  ];

  return (
    <DataTable
      columns={columns}
      rows={q.data?.items}
      rowKey={(o) => o.id}
      isLoading={q.isFetching}
      error={q.error}
      onRetry={() => q.refetch()}
      page={page}
      pageSize={25}
      total={q.data?.total}
      onPageChange={setPage}
      filters={
        <>
          <FilterSelect
            value={service}
            onChange={(v) => {
              setService(v);
              setPage(1);
            }}
            allLabel="Any recommendation"
            aria-label="Recommended service"
            options={[
              { value: "website", label: "Website" },
              { value: "company_brain", label: "Company Brain" },
              { value: "none", label: "No fit" },
            ]}
          />
          <Input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => {
              setMinScore(e.target.value);
              setPage(1);
            }}
            placeholder="Min score"
            className="w-28"
            aria-label="Minimum score (either service)"
          />
          <FilterSelect
            value={sort === "best" ? "" : "recent"}
            onChange={(v) => setSort(v === "recent" ? "recent" : "best")}
            allLabel="Best score first"
            aria-label="Sort"
            options={[{ value: "recent", label: "Recently updated" }]}
          />
        </>
      }
      empty={{
        icon: KanbanSquare,
        title: "No opportunities scored yet",
        description: "Qualification scores researched companies for both services. Run it from Automation or a company page.",
      }}
    />
  );
}
