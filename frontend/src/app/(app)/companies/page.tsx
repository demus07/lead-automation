"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Building2, ChevronDown, Download, FileSearch, Gauge, PenLine, Plus, Tag, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { DualScore, ServiceBadge } from "@/components/shared/score";
import { FilterSelect } from "@/components/shared/filter-select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Field } from "@/components/shared/field";
import { AddCompanyDialog } from "@/components/companies/add-company-dialog";
import { useCan } from "@/hooks/use-auth";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useTableState } from "@/hooks/use-table-state";
import { api, download, errorMessage } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import { fmtRelative } from "@/lib/format";
import { LEAD_STATUSES, LEAD_STATUS_META } from "@/lib/status";
import type { Campaign, Company, LeadStatus, Page } from "@/lib/types";

type Filters = {
  status: string;
  service: string;
  min_website: string;
  min_brain: string;
  tag: string;
  campaign_id: string;
};

const EMPTY: Filters = { status: "", service: "", min_website: "", min_brain: "", tag: "", campaign_id: "" };

type BulkResult = { updated?: number; failed?: { id: string; error: string }[]; job_id?: string; count?: number; status?: string };

export default function CompaniesPage() {
  return (
    <Suspense>
      <CompaniesView />
    </Suspense>
  );
}

function CompaniesView() {
  const router = useRouter();
  const params = useSearchParams();
  const [initial] = useState<Filters>(() => ({
    ...EMPTY,
    status: params.get("status") ?? "",
    service: params.get("service") ?? "",
    tag: params.get("tag") ?? "",
    campaign_id: params.get("campaign_id") ?? "",
  }));
  const t = useTableState<Filters>({ sort: "-created_at", filters: initial });
  const canEdit = useCan("operator");
  const [selected, setSelected] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);
  const [tagValue, setTagValue] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [tagText, setTagText] = useState("");

  const f = t.filters;
  const query = {
    q: t.q,
    sort: t.sort,
    page: t.page,
    page_size: t.pageSize,
    status: f.status || undefined,
    service: f.service || undefined,
    min_website: f.min_website || undefined,
    min_brain: f.min_brain || undefined,
    tag: f.tag || undefined,
    campaign_id: f.campaign_id || undefined,
  };
  const list = useQuery({
    queryKey: ["companies", "list", query],
    queryFn: () => api.get<Page<Company>>("/companies", query),
    placeholderData: keepPreviousData,
  });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns") });
  const campaignName = (id: string | null) => campaigns.data?.find((c) => c.id === id)?.name;

  const bulk = useApiMutation(
    (v: { action: string; value?: string; ids: string[] }) => api.post<BulkResult>("/companies/bulk", v),
    {
      success: false,
      invalidate: [["companies"]],
      onSuccess: (r, v) => {
        if (r.job_id) {
          const label = { research: "Research started", qualify: "Scoring started", draft: "Draft generation started" }[v.action] ?? "Job started";
          jobStartedToast(`${label} for ${r.count} companies`, { job_id: r.job_id, status: "queued" });
        } else {
          const verb = v.action === "delete" ? "Deleted" : v.action === "tag" ? "Tagged" : "Updated";
          toast.success(`${verb} ${r.updated ?? 0} companies`, {
            description: r.failed?.length ? `${r.failed.length} failed: ${r.failed[0].error}` : undefined,
          });
        }
        if (v.action === "delete") setSelected([]);
      },
    },
  );

  const columns: Column<Company>[] = [
    {
      key: "name",
      header: "Company",
      sortKey: "name",
      cell: (c) => (
        <div className="min-w-0 max-w-[22rem]">
          <Link href={`/companies/${c.id}`} className="font-medium hover:underline">
            {c.name}
          </Link>
          <div className="truncate text-xs text-muted-foreground">
            {[c.domain, c.industry, c.location].filter(Boolean).join(", ") || "No details yet"}
          </div>
          {c.tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {c.tags.slice(0, 4).map((tg) => (
                <button
                  key={tg}
                  type="button"
                  onClick={() => t.setFilter("tag", tg)}
                  className="rounded bg-secondary px-1.5 text-[0.7rem] text-secondary-foreground hover:bg-accent"
                >
                  {tg}
                </button>
              ))}
            </div>
          )}
        </div>
      ),
    },
    { key: "status", header: "Status", sortKey: "status", cell: (c) => <StatusBadge kind="lead" value={c.status} /> },
    {
      key: "scores",
      header: (
        <span title="Website / Company Brain opportunity scores (0–100)">Scores</span>
      ),
      sortKey: "website_score",
      cell: (c) => <DualScore compact website={c.website_score} brain={c.brain_score} recommended={c.recommended_service} />,
    },
    {
      key: "service",
      header: "Recommended",
      hideBelow: "md",
      cell: (c) => <ServiceBadge service={c.recommended_service} />,
    },
    {
      key: "campaign",
      header: "Campaign",
      hideBelow: "lg",
      cell: (c) => <span className="text-sm text-muted-foreground">{campaignName(c.campaign_id) ?? "—"}</span>,
    },
    {
      key: "researched",
      header: "Researched",
      sortKey: "last_researched_at",
      hideBelow: "lg",
      cell: (c) => <span className="text-xs text-muted-foreground">{c.last_researched_at ? fmtRelative(c.last_researched_at) : "Not yet"}</span>,
    },
    {
      key: "added",
      header: "Added",
      sortKey: "created_at",
      hideBelow: "md",
      cell: (c) => <span className="text-xs text-muted-foreground">{fmtRelative(c.created_at)}</span>,
    },
  ];

  const anyFilter = Object.values(f).some(Boolean) || !!t.q;

  return (
    <>
      <PageHeader
        title="Companies"
        description="Every discovered or imported company, with independent website and Company Brain scores."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() =>
                download("/companies/export", { q: t.q, status: f.status || undefined, service: f.service || undefined, campaign_id: f.campaign_id || undefined }, "companies.csv").catch(
                  (e) => toast.error("Export failed", { description: errorMessage(e) }),
                )
              }
            >
              <Download /> Export CSV
            </Button>
            {canEdit && (
              <Button onClick={() => setAdding(true)}>
                <Plus /> Add company
              </Button>
            )}
          </>
        }
      />

      <DataTable
        columns={columns}
        rows={list.data?.items}
        rowKey={(c) => c.id}
        isLoading={list.isFetching}
        error={list.error}
        onRetry={() => list.refetch()}
        page={t.page}
        pageSize={t.pageSize}
        total={list.data?.total}
        onPageChange={t.setPage}
        sort={t.sort}
        onSortChange={t.setSort}
        search={t.q}
        onSearchChange={t.setQ}
        searchPlaceholder="Search name, domain, industry, location"
        onRowClick={(c) => router.push(`/companies/${c.id}`)}
        selectable={canEdit}
        selected={selected}
        onSelectedChange={setSelected}
        filters={
          <>
            <FilterSelect
              aria-label="Status"
              value={f.status}
              onChange={(v) => t.setFilter("status", v)}
              allLabel="All statuses"
              options={LEAD_STATUSES.map((s) => ({ value: s, label: LEAD_STATUS_META[s].label }))}
            />
            <FilterSelect
              aria-label="Recommended service"
              value={f.service}
              onChange={(v) => t.setFilter("service", v)}
              allLabel="Any service"
              options={[
                { value: "website", label: "Website" },
                { value: "company_brain", label: "Company Brain" },
                { value: "none", label: "No fit" },
              ]}
            />
            {(campaigns.data?.length ?? 0) > 0 && (
              <FilterSelect
                aria-label="Campaign"
                value={f.campaign_id}
                onChange={(v) => t.setFilter("campaign_id", v)}
                allLabel="All campaigns"
                options={(campaigns.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
              />
            )}
            <ScoreFilter label="Website ≥" value={f.min_website} onChange={(v) => t.setFilter("min_website", v)} />
            <ScoreFilter label="Brain ≥" value={f.min_brain} onChange={(v) => t.setFilter("min_brain", v)} />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                t.setFilter("tag", tagText.trim());
              }}
            >
              {f.tag ? (
                <Button type="button" variant="secondary" size="sm" className="h-8" onClick={() => { t.setFilter("tag", ""); setTagText(""); }}>
                  <Tag /> {f.tag} <X />
                </Button>
              ) : (
                <Input value={tagText} onChange={(e) => setTagText(e.target.value)} placeholder="Tag" aria-label="Filter by tag" className="h-8 w-28" />
              )}
            </form>
            {anyFilter && (
              <Button variant="ghost" size="sm" onClick={() => { (Object.keys(EMPTY) as (keyof Filters)[]).forEach((k) => t.setFilter(k, "")); t.setQ(""); setTagText(""); }}>
                Reset
              </Button>
            )}
          </>
        }
        bulkActions={(ids) => (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  Set status <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Only valid transitions are applied</DropdownMenuLabel>
                {LEAD_STATUSES.map((s) => (
                  <DropdownMenuItem key={s} onSelect={() => bulk.mutate({ action: "status", value: s, ids })}>
                    {LEAD_STATUS_META[s as LeadStatus].label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="outline" size="sm" onClick={() => { setTagValue(""); setTagOpen(true); }}>
              <Tag /> Tag
            </Button>
            <Button variant="outline" size="sm" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: "research", ids })}>
              <FileSearch /> Research
            </Button>
            <Button variant="outline" size="sm" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: "qualify", ids })}>
              <Gauge /> Score
            </Button>
            <Button variant="outline" size="sm" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: "draft", ids })}>
              <PenLine /> Generate drafts
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label="More bulk actions">
                  More <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => bulk.mutate({ action: "untag", value: f.tag, ids })} disabled={!f.tag}>
                  Remove tag “{f.tag || "filter by a tag first"}”
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}>
                  <Trash2 /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
        empty={{
          icon: Building2,
          title: anyFilter ? "No companies match these filters" : "No companies yet",
          description: anyFilter
            ? "Clear a filter or search for something else."
            : "Run discovery from a campaign, import a CSV, or add a company by hand.",
          action: anyFilter ? (
            <Button variant="outline" onClick={() => { (Object.keys(EMPTY) as (keyof Filters)[]).forEach((k) => t.setFilter(k, "")); t.setQ(""); setTagText(""); }}>Reset filters</Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" asChild><Link href="/discovery">Go to discovery</Link></Button>
              {canEdit && <Button onClick={() => setAdding(true)}><Plus /> Add company</Button>}
            </div>
          ),
        }}
      />

      <AddCompanyDialog open={adding} onOpenChange={setAdding} campaigns={(campaigns.data ?? []).filter((c) => c.is_active)} />

      <ConfirmDialog
        open={tagOpen}
        onOpenChange={setTagOpen}
        title={`Tag ${selected.length} companies`}
        confirmLabel="Add tag"
        confirmDisabled={!tagValue.trim()}
        onConfirm={() => bulk.mutateAsync({ action: "tag", value: tagValue.trim(), ids: selected })}
      >
        <Field label="Tag" htmlFor="bulk-tag" hint="Up to 60 characters">
          <Input id="bulk-tag" value={tagValue} maxLength={60} onChange={(e) => setTagValue(e.target.value)} autoFocus />
        </Field>
      </ConfirmDialog>

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${selected.length} companies?`}
        description="They disappear from lists, the pipeline and automation. Contacts stay attached but hidden. Suppression is not affected."
        confirmLabel="Delete companies"
        destructive
        requireText={selected.length > 5 ? "delete" : undefined}
        onConfirm={() => bulk.mutateAsync({ action: "delete", ids: selected })}
      />
    </>
  );
}

function ScoreFilter({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex h-8 items-center gap-1.5 rounded-lg border border-input pl-2.5 text-sm text-muted-foreground dark:bg-input/30">
      <span className="whitespace-nowrap">{label}</span>
      <input
        type="number"
        min={0}
        max={100}
        inputMode="numeric"
        value={value}
        placeholder="0"
        onChange={(e) => {
          const n = e.target.value;
          if (n === "" || (Number(n) >= 0 && Number(n) <= 100)) onChange(n);
        }}
        className="h-full w-12 bg-transparent pr-2 text-foreground tabular-nums outline-none"
      />
    </label>
  );
}
