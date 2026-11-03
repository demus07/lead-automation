"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Loader2, ScrollText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { JsonView } from "@/components/shared/json-view";
import { Notice } from "@/components/shared/notice";
import { PageHeader } from "@/components/shared/page-header";
import { DetailList } from "@/components/shared/section";
import { useCan } from "@/hooks/use-auth";
import { useTableState } from "@/hooks/use-table-state";
import { api, download, errorMessage } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import type { Page } from "@/lib/types";

interface AuditRow {
  id: string;
  created_at: string;
  actor: string | null;
  actor_type: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  detail: Record<string, unknown> | null;
  ip: string | null;
}

const ENTITY_TYPES = [
  "user",
  "company",
  "contact",
  "campaign",
  "outreach_draft",
  "email_account",
  "settings",
  "suppression",
  "knowledge_item",
  "integration_connection",
  "task",
  "workflow",
];

export default function AuditPage() {
  const isAdmin = useCan("admin");
  const t = useTableState<{ entity_type: string }>({ filters: { entity_type: "" } });
  const [action, setAction] = useState("");
  const [selected, setSelected] = useState<AuditRow | null>(null);
  const [exporting, setExporting] = useState(false);
  const q = useQuery({
    queryKey: ["audit", t.page, t.q, t.filters],
    queryFn: () =>
      api.get<Page<AuditRow>>("/admin/audit", {
        page: t.page,
        page_size: t.pageSize,
        action: t.q,
        entity_type: t.filters.entity_type,
      }),
    enabled: isAdmin,
    placeholderData: (p) => p,
  });

  async function exportAll() {
    setExporting(true);
    try {
      await download("/admin/export/all", undefined, "agency-growth-engine-export.zip");
      toast.success("Export downloaded");
    } catch (e) {
      toast.error("Export failed", { description: errorMessage(e) });
    } finally {
      setExporting(false);
    }
  }

  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <PageHeader title="Audit log" />
        <Notice tone="warning" title="Admins only">The audit log and full data export are available to admins.</Notice>
      </div>
    );
  }

  const columns: Column<AuditRow>[] = [
    { key: "when", header: "When", cell: (a) => <span className="text-sm whitespace-nowrap tabular-nums text-muted-foreground">{fmtDateTime(a.created_at)}</span> },
    { key: "actor", header: "Actor", cell: (a) => <span className="text-sm">{a.actor ?? humanize(a.actor_type)}</span>, hideBelow: "sm" },
    { key: "action", header: "Action", cell: (a) => <code className="font-mono text-xs">{a.action}</code> },
    {
      key: "entity",
      header: "Entity",
      cell: (a) =>
        a.entity_type ? (
          <span className="text-sm text-muted-foreground">
            {humanize(a.entity_type)}
            {a.entity_id && <code className="ml-1.5 font-mono text-xs">{a.entity_id.slice(0, 8)}</code>}
          </span>
        ) : (
          "—"
        ),
      hideBelow: "md",
    },
    { key: "ip", header: "IP", cell: (a) => <span className="font-mono text-xs text-muted-foreground">{a.ip ?? "—"}</span>, hideBelow: "lg" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit log"
        description="Every sign-in, approval, settings change and export, with who did it and when. Select a row to see its detail."
        actions={
          <Button variant="outline" onClick={exportAll} disabled={exporting}>
            {exporting ? <Loader2 className="animate-spin" /> : <Download />}
            Export all data
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={q.data?.items}
        rowKey={(a) => a.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        page={t.page}
        pageSize={t.pageSize}
        total={q.data?.total}
        onPageChange={t.setPage}
        filters={
          <>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                t.setQ(action.trim());
              }}
            >
              <Input
                value={action}
                onChange={(e) => setAction(e.target.value)}
                onBlur={() => t.setQ(action.trim())}
                placeholder="Action starts with, e.g. draft."
                aria-label="Action prefix"
                className="w-64"
              />
            </form>
            <FilterSelect
              value={t.filters.entity_type}
              onChange={(v) => t.setFilter("entity_type", v)}
              allLabel="All entities"
              aria-label="Entity type"
              options={ENTITY_TYPES.map((e) => ({ value: e, label: humanize(e) }))}
            />
          </>
        }
        onRowClick={setSelected}
        dense
        empty={{ icon: ScrollText, title: "No matching entries", description: "Try a shorter action prefix or a different entity type." }}
      />
      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="font-mono text-base">{selected.action}</SheetTitle>
                <SheetDescription>{fmtDateTime(selected.created_at)}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-6">
                <DetailList
                  items={[
                    { label: "Actor", value: selected.actor ?? humanize(selected.actor_type) },
                    { label: "Actor type", value: humanize(selected.actor_type) },
                    { label: "Entity", value: selected.entity_type ? humanize(selected.entity_type) : null },
                    { label: "Entity id", value: selected.entity_id ? <code className="font-mono text-xs break-all">{selected.entity_id}</code> : null },
                    { label: "IP", value: selected.ip },
                  ]}
                />
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Detail</h3>
                  <JsonView value={selected.detail} />
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
