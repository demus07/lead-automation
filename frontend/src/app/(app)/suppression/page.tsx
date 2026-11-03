"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Plus, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DataTable, type Column } from "@/components/shared/data-table";
import { Field } from "@/components/shared/field";
import { PageHeader } from "@/components/shared/page-header";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtDate, humanize } from "@/lib/format";
import type { Page, Suppression } from "@/lib/types";

const PROTECTED = new Set(["opt_out", "unsubscribe"]);
const REASONS = ["manual", "dnc", "bounced", "complaint", "competitor", "existing_client", "other"];

function AddDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [kind, setKind] = useState<"email" | "domain">("email");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("manual");
  const [note, setNote] = useState("");
  const add = useApiMutation(
    () => api.post<Suppression>("/suppression", { kind, value: value.trim(), reason, note: note.trim() || null }),
    {
      success: (s) => `${s.value} suppressed`,
      invalidate: [["suppression"], ["companies"], ["contacts"]],
      onSuccess: () => {
        setValue("");
        setNote("");
        onOpenChange(false);
      },
    },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add to suppression list</DialogTitle>
          <DialogDescription>
            Suppressed addresses and domains are never drafted to. A suppressed domain also marks its company as do not contact.
          </DialogDescription>
        </DialogHeader>
        <form
          id="sup-form"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[9rem_1fr]">
            <Field label="Type" htmlFor="sup-kind">
              <Select value={kind} onValueChange={(v) => setKind(v as "email" | "domain")}>
                <SelectTrigger id="sup-kind" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="domain">Domain</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label={kind === "email" ? "Email address" : "Domain"} htmlFor="sup-value" required>
              <Input
                id="sup-value"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={kind === "email" ? "name@company.com" : "company.com"}
                autoComplete="off"
              />
            </Field>
          </div>
          <Field label="Reason" htmlFor="sup-reason">
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger id="sup-reason" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REASONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {humanize(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Note" htmlFor="sup-note">
            <Textarea id="sup-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="sup-form" disabled={add.isPending || value.trim().length < 3}>
            {add.isPending && <Loader2 className="animate-spin" />}
            Suppress
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeactivateDialog({ row, onClose }: { row: Suppression; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const m = useApiMutation(() => api.post<Suppression>(`/suppression/${row.id}/deactivate`, undefined, { reason: reason.trim() }), {
    success: `${row.value} is no longer suppressed`,
    invalidate: [["suppression"]],
  });
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Deactivate suppression for ${row.value}?`}
      description="Use this only to correct a mistaken entry. The record is kept for audit, and outreach to this address becomes possible again."
      confirmLabel="Deactivate"
      destructive
      confirmDisabled={reason.trim().length < 3}
      onConfirm={() => m.mutateAsync()}
    >
      <Field label="Why is this being corrected?" htmlFor="deact-reason" hint="Recorded in the audit log. At least 3 characters.">
        <Textarea id="deact-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </ConfirmDialog>
  );
}

export default function SuppressionPage() {
  const canAdd = useCan("operator");
  const isAdmin = useCan("admin");
  const t = useTableState<{ active: string }>({ filters: { active: "true" } });
  const [adding, setAdding] = useState(false);
  const [deactivating, setDeactivating] = useState<Suppression | null>(null);
  const q = useQuery({
    queryKey: ["suppression", t.page, t.q, t.filters],
    queryFn: () =>
      api.get<Page<Suppression>>("/suppression", {
        page: t.page,
        page_size: t.pageSize,
        q: t.q,
        // The API has no "all" option (active defaults to true), so the UI offers active or inactive.
        active: t.filters.active,
      }),
    placeholderData: (p) => p,
  });

  const columns: Column<Suppression>[] = [
    {
      key: "value",
      header: "Email or domain",
      cell: (s) => (
        <div className="flex items-center gap-2">
          <span className="font-medium break-all">{s.value}</span>
          <span className="text-xs text-muted-foreground">{s.kind}</span>
        </div>
      ),
    },
    {
      key: "reason",
      header: "Reason",
      cell: (s) => <ToneBadge tone={PROTECTED.has(s.reason) ? "danger" : "neutral"}>{humanize(s.reason)}</ToneBadge>,
    },
    { key: "source", header: "Source", cell: (s) => <span className="line-clamp-1 text-sm text-muted-foreground">{s.source || "—"}</span>, hideBelow: "lg" },
    { key: "active", header: "Status", cell: (s) => (s.active ? <ToneBadge tone="danger" dot>Active</ToneBadge> : <ToneBadge tone="neutral" dot>Inactive</ToneBadge>) },
    { key: "created", header: "Added", cell: (s) => <span className="text-sm text-muted-foreground">{fmtDate(s.created_at)}</span>, hideBelow: "md" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (s) => {
        if (!isAdmin || !s.active) return null;
        if (PROTECTED.has(s.reason))
          return <span className="text-xs text-muted-foreground" title="People who opted out are never re-enabled">Opt-out, permanent</span>;
        return (
          <Button variant="ghost" size="sm" onClick={() => setDeactivating(s)}>
            Deactivate
          </Button>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Suppression list"
        description="Addresses and domains that must never be contacted. Opt-outs are added automatically from replies and can't be removed."
        actions={
          canAdd && (
            <Button onClick={() => setAdding(true)}>
              <Plus /> Add entry
            </Button>
          )
        }
      />
      <DataTable
        columns={columns}
        rows={q.data?.items}
        rowKey={(s) => s.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        page={t.page}
        pageSize={t.pageSize}
        total={q.data?.total}
        onPageChange={t.setPage}
        search={t.q}
        onSearchChange={t.setQ}
        searchPlaceholder="Search email or domain"
        filters={
          <Select value={t.filters.active} onValueChange={(v) => t.setFilter("active", v)}>
            <SelectTrigger className="h-8 min-w-36" aria-label="Status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="true">Active</SelectItem>
              <SelectItem value="false">Inactive (corrected)</SelectItem>
            </SelectContent>
          </Select>
        }
        empty={{
          icon: ShieldOff,
          title: "Nothing suppressed",
          description: "Add an email or domain to make sure it's never drafted to.",
        }}
      />
      <AddDialog open={adding} onOpenChange={setAdding} />
      {deactivating && <DeactivateDialog row={deactivating} onClose={() => setDeactivating(null)} />}
    </div>
  );
}
