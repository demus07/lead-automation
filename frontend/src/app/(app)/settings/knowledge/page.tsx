"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Loader2, Pencil, Plug, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DataTable, type Column } from "@/components/shared/data-table";
import { ExternalLink } from "@/components/shared/external-link";
import { Field } from "@/components/shared/field";
import { FilterSelect } from "@/components/shared/filter-select";
import { Notice } from "@/components/shared/notice";
import { PageHeader } from "@/components/shared/page-header";
import { Section } from "@/components/shared/section";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import { TagInput } from "@/components/shared/tag-input";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { useTableState } from "@/hooks/use-table-state";
import { api } from "@/lib/api";
import { fmtRelative, humanize, serviceLabel } from "@/lib/format";
import type { Connection, ConnectorDescription, KnowledgeItem, Msg, Page } from "@/lib/types";

const KINDS = ["service", "pricing", "portfolio", "case_study", "testimonial", "positioning", "proposal", "messaging", "other"];
const NONE = "__none__";

type ItemForm = {
  kind: string;
  title: string;
  content: string;
  url: string;
  service: string;
  tags: string[];
  approved_for_outreach: boolean;
  confidential: boolean;
};

const emptyItem: ItemForm = {
  kind: "service",
  title: "",
  content: "",
  url: "",
  service: "",
  tags: [],
  approved_for_outreach: false,
  confidential: false,
};

function ItemDialog({ item, open, onOpenChange }: { item: KnowledgeItem | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [v, setV] = useState<ItemForm>(
    item
      ? {
          kind: item.kind,
          title: item.title,
          content: item.content,
          url: item.url ?? "",
          service: item.service ?? "",
          tags: item.tags ?? [],
          approved_for_outreach: item.approved_for_outreach,
          confidential: item.confidential,
        }
      : emptyItem,
  );
  const save = useApiMutation(
    (body: Record<string, unknown>) => (item ? api.patch<KnowledgeItem>(`/knowledge/${item.id}`, body) : api.post<KnowledgeItem>("/knowledge", body)),
    { success: item ? "Knowledge item saved" : "Knowledge item added", invalidate: [["knowledge"]], onSuccess: () => onOpenChange(false) },
  );
  const set = <K extends keyof ItemForm>(k: K, val: ItemForm[K]) => setV((s) => ({ ...s, [k]: val }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{item ? "Edit knowledge item" : "Add knowledge item"}</DialogTitle>
          <DialogDescription>Only items approved for outreach can be referenced in drafts. Confidential items are used for context only.</DialogDescription>
        </DialogHeader>
        <form
          id="kn-form"
          className="max-h-[60vh] space-y-4 overflow-y-auto pr-1"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({
              kind: v.kind,
              title: v.title.trim(),
              content: v.content,
              url: v.url.trim() || null,
              service: v.service || null,
              tags: v.tags,
              approved_for_outreach: v.approved_for_outreach,
              confidential: v.confidential,
            });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Kind" htmlFor="kn-kind">
              <Select value={v.kind} onValueChange={(x) => set("kind", x)}>
                <SelectTrigger id="kn-kind" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => (
                    <SelectItem key={k} value={k}>
                      {humanize(k)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Service" htmlFor="kn-svc">
              <Select value={v.service || NONE} onValueChange={(x) => set("service", x === NONE ? "" : x)}>
                <SelectTrigger id="kn-svc" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Not specific</SelectItem>
                  <SelectItem value="website">Website</SelectItem>
                  <SelectItem value="company_brain">Company Brain</SelectItem>
                  <SelectItem value="both">Both</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>
          <Field label="Title" htmlFor="kn-title" required>
            <Input id="kn-title" value={v.title} onChange={(e) => set("title", e.target.value)} required maxLength={300} />
          </Field>
          <Field label="Content" htmlFor="kn-content">
            <Textarea id="kn-content" rows={6} value={v.content} onChange={(e) => set("content", e.target.value)} />
          </Field>
          <Field label="Link" htmlFor="kn-url">
            <Input id="kn-url" value={v.url} onChange={(e) => set("url", e.target.value)} placeholder="https://" />
          </Field>
          <Field label="Tags" htmlFor="kn-tags">
            <TagInput id="kn-tags" value={v.tags} onChange={(x) => set("tags", x)} />
          </Field>
          <div className="space-y-3 rounded-lg border p-3">
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={v.approved_for_outreach}
                onCheckedChange={(x) => setV((s) => ({ ...s, approved_for_outreach: x, confidential: x ? false : s.confidential }))}
              />
              Approved for outreach
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={v.confidential}
                onCheckedChange={(x) => setV((s) => ({ ...s, confidential: x, approved_for_outreach: x ? false : s.approved_for_outreach }))}
              />
              Confidential
            </label>
            <p className="text-xs text-muted-foreground">An item can&apos;t be both: confidential material is never quoted to prospects.</p>
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="kn-form" disabled={save.isPending || !v.title.trim()}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {item ? "Save item" : "Add item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KnowledgeTable() {
  const canEdit = useCan("operator");
  const t = useTableState<{ kind: string; approved: string }>({ filters: { kind: "", approved: "" } });
  const [editing, setEditing] = useState<KnowledgeItem | null>(null);
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["knowledge", "items", t.page, t.q, t.filters],
    queryFn: () =>
      api.get<Page<KnowledgeItem>>("/knowledge", {
        page: t.page,
        page_size: t.pageSize,
        q: t.q,
        kind: t.filters.kind,
        approved: t.filters.approved,
      }),
    placeholderData: (p) => p,
  });
  const patch = useApiMutation(({ id, body }: { id: string; body: Partial<KnowledgeItem> }) => api.patch<KnowledgeItem>(`/knowledge/${id}`, body), {
    success: "Knowledge item saved",
    invalidate: [["knowledge"]],
  });
  const del = useApiMutation((id: string) => api.delete<Msg>(`/knowledge/${id}`), { success: "Knowledge item deleted", invalidate: [["knowledge"]] });

  const columns: Column<KnowledgeItem>[] = [
    {
      key: "title",
      header: "Item",
      cell: (k) => (
        <div className="min-w-0 max-w-md space-y-0.5">
          <div className="truncate font-medium">{k.title}</div>
          <div className="line-clamp-1 text-xs whitespace-normal text-muted-foreground">{k.content || "No content"}</div>
          {k.url && <ExternalLink href={k.url} className="text-xs" />}
        </div>
      ),
    },
    { key: "kind", header: "Kind", cell: (k) => <span className="text-sm">{humanize(k.kind)}</span>, hideBelow: "md" },
    { key: "service", header: "Service", cell: (k) => <span className="text-sm">{k.service ? (k.service === "both" ? "Both" : serviceLabel(k.service)) : "—"}</span>, hideBelow: "lg" },
    { key: "source", header: "Source", cell: (k) => <span className="text-sm text-muted-foreground">{humanize(k.source)}</span>, hideBelow: "lg" },
    {
      key: "approved",
      header: "Use in outreach",
      cell: (k) => (
        <Switch
          checked={k.approved_for_outreach}
          disabled={!canEdit || k.confidential || patch.isPending}
          onCheckedChange={(x) => patch.mutate({ id: k.id, body: { approved_for_outreach: x } })}
          aria-label="Approved for outreach"
          title={k.confidential ? "Confidential items can't be approved for outreach" : undefined}
        />
      ),
    },
    {
      key: "confidential",
      header: "Confidential",
      cell: (k) => (
        <Switch
          checked={k.confidential}
          disabled={!canEdit || k.approved_for_outreach || patch.isPending}
          onCheckedChange={(x) => patch.mutate({ id: k.id, body: { confidential: x } })}
          aria-label="Confidential"
          title={k.approved_for_outreach ? "Remove outreach approval first" : undefined}
        />
      ),
      hideBelow: "sm",
    },
    { key: "updated", header: "Updated", cell: (k) => <span className="text-sm text-muted-foreground">{fmtRelative(k.updated_at)}</span>, hideBelow: "lg" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (k) =>
        canEdit ? (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="icon-sm" onClick={() => { setEditing(k); setOpen(true); }} aria-label="Edit">
              <Pencil />
            </Button>
            <ConfirmDialog
              trigger={
                <Button variant="ghost" size="icon-sm" aria-label="Delete">
                  <Trash2 />
                </Button>
              }
              title={`Delete “${k.title}”?`}
              description="Drafts generated from now on won't use this item."
              confirmLabel="Delete"
              destructive
              onConfirm={() => del.mutateAsync(k.id)}
            />
          </div>
        ) : null,
    },
  ];

  return (
    <>
      <DataTable
        columns={columns}
        rows={q.data?.items}
        rowKey={(k) => k.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        page={t.page}
        pageSize={t.pageSize}
        total={q.data?.total}
        onPageChange={t.setPage}
        search={t.q}
        onSearchChange={t.setQ}
        searchPlaceholder="Search title or content"
        filters={
          <>
            <FilterSelect value={t.filters.kind} onChange={(v) => t.setFilter("kind", v)} allLabel="All kinds" aria-label="Kind" options={KINDS.map((k) => ({ value: k, label: humanize(k) }))} />
            <FilterSelect
              value={t.filters.approved}
              onChange={(v) => t.setFilter("approved", v)}
              allLabel="Any approval"
              aria-label="Approval"
              options={[
                { value: "true", label: "Approved for outreach" },
                { value: "false", label: "Not approved" },
              ]}
            />
          </>
        }
        toolbarEnd={
          canEdit && (
            <Button onClick={() => { setEditing(null); setOpen(true); }}>
              <Plus /> Add item
            </Button>
          )
        }
        empty={{
          icon: BookOpen,
          title: "No knowledge items",
          description: "Add services, pricing, case studies and positioning so drafts can reference real material, or sync a connector below.",
        }}
      />
      {open && <ItemDialog key={editing?.id ?? "new"} item={editing} open={open} onOpenChange={setOpen} />}
    </>
  );
}

function AddConnectionDialog({ available, open, onOpenChange }: { available: ConnectorDescription[]; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [provider, setProvider] = useState(available[0]?.key ?? "");
  const [name, setName] = useState("");
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, string>>({});
  const c = available.find((a) => a.key === provider);
  const create = useApiMutation((body: Record<string, unknown>) => api.post<Connection>("/knowledge/connectors", body), {
    success: "Connector added",
    invalidate: [["knowledge", "connectors"], ["integrations"]],
    onSuccess: () => onOpenChange(false),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add connector</DialogTitle>
          <DialogDescription>Credentials are encrypted at rest and never shown again.</DialogDescription>
        </DialogHeader>
        <form
          id="conn-form"
          className="max-h-[60vh] space-y-4 overflow-y-auto pr-1"
          onSubmit={(e) => {
            e.preventDefault();
            const clean = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v.trim() !== ""));
            create.mutate({ provider, name: name.trim(), credentials: clean(creds), config: clean(config) });
          }}
        >
          <Field label="Source" htmlFor="conn-provider" hint={c?.description}>
            <Select
              value={provider}
              onValueChange={(x) => {
                setProvider(x);
                setCreds({});
                setConfig({});
              }}
            >
              <SelectTrigger id="conn-provider" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {available.map((a) => (
                  <SelectItem key={a.key} value={a.key}>
                    {a.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Name" htmlFor="conn-name" required hint="So you can tell connections apart.">
            <Input id="conn-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={c ? `${c.label} knowledge` : ""} required />
          </Field>
          {c?.credential_fields.map((f) => (
            <Field key={f.name} label={f.label} htmlFor={`cred-${f.name}`}>
              <Input
                id={`cred-${f.name}`}
                type={f.secret === "true" ? "password" : "text"}
                autoComplete="off"
                value={creds[f.name] ?? ""}
                onChange={(e) => setCreds((s) => ({ ...s, [f.name]: e.target.value }))}
              />
            </Field>
          ))}
          {c?.config_fields.map((f) => (
            <Field key={f.name} label={f.label} htmlFor={`cfg-${f.name}`}>
              <Input id={`cfg-${f.name}`} value={config[f.name] ?? ""} onChange={(e) => setConfig((s) => ({ ...s, [f.name]: e.target.value }))} />
            </Field>
          ))}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="conn-form" disabled={create.isPending || !name.trim() || !provider}>
            {create.isPending && <Loader2 className="animate-spin" />}
            Add connector
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Connectors() {
  const isAdmin = useCan("admin");
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["knowledge", "connectors"],
    queryFn: () => api.get<{ available: ConnectorDescription[]; connections: Connection[]; note: string }>("/knowledge/connectors"),
  });
  const test = useApiMutation((id: string) => api.post<{ status: string; message: string }>(`/knowledge/connectors/${id}/test`), {
    onSuccess: (r) => (r.status === "connected" ? toast.success("Connection works", { description: r.message }) : toast.error("Connection failed", { description: r.message })),
    invalidate: [["knowledge", "connectors"], ["integrations"]],
  });
  const sync = useApiMutation((id: string) => api.post<{ created: number; updated: number; note: string }>(`/knowledge/connectors/${id}/sync`), {
    onSuccess: (r) => toast.success(`Synced: ${r.created} new, ${r.updated} updated`, { description: r.note }),
    invalidate: [["knowledge"], ["integrations"]],
  });
  const del = useApiMutation((id: string) => api.delete<Msg>(`/knowledge/connectors/${id}`), {
    success: (r) => r.message || "Connector removed",
    invalidate: [["knowledge", "connectors"], ["integrations"]],
  });

  return (
    <Section
      title="Company Brain connectors"
      description="Pull knowledge from Notion, Slack, Teams or your own Company Brain API. Imported items need your approval before they're used in outreach."
      actions={
        isAdmin && q.data && q.data.available.length > 0 ? (
          <Button variant="outline" onClick={() => setOpen(true)}>
            <Plus /> Add connector
          </Button>
        ) : null
      }
    >
      {q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : !q.data ? (
        <TableSkeleton rows={2} cols={3} />
      ) : (
        <div className="space-y-4">
          {q.data.connections.length === 0 ? (
            <EmptyState compact icon={Plug} title="No connectors yet" description={`Available: ${q.data.available.map((a) => a.label).join(", ")}.`} />
          ) : (
            <ul className="divide-y rounded-lg border">
              {q.data.connections.map((c) => (
                <li key={c.id} className="flex flex-col gap-3 p-4 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{c.name}</span>
                      <span className="text-xs text-muted-foreground">{c.connector?.label ?? c.provider}</span>
                      <StatusBadge kind="integration" value={c.status} />
                      {!c.credentials_set && c.connector?.credential_fields.length ? <ToneBadge tone="warning">No credentials</ToneBadge> : null}
                    </div>
                    <p className="text-xs text-muted-foreground">Last synced {fmtRelative(c.last_synced_at)}</p>
                    {c.last_error && <p className="text-xs break-words text-destructive">{c.last_error}</p>}
                  </div>
                  {isAdmin && (
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => test.mutate(c.id)} disabled={test.isPending}>
                        {test.isPending && test.variables === c.id && <Loader2 className="animate-spin" />}
                        Test
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => sync.mutate(c.id)} disabled={sync.isPending}>
                        {sync.isPending && sync.variables === c.id ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                        Sync
                      </Button>
                      <ConfirmDialog
                        trigger={
                          <Button variant="ghost" size="sm">
                            <Trash2 /> Remove
                          </Button>
                        }
                        title={`Remove ${c.name}?`}
                        description="Stored credentials are deleted. Items already imported stay in the knowledge base."
                        confirmLabel="Remove"
                        destructive
                        onConfirm={() => del.mutateAsync(c.id)}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">{q.data.note}</p>
        </div>
      )}
      {open && q.data && <AddConnectionDialog available={q.data.available} open={open} onOpenChange={setOpen} />}
    </Section>
  );
}

export default function KnowledgePage() {
  const canEdit = useCan("operator");
  return (
    <div className="space-y-8">
      <PageHeader
        title="Knowledge"
        description="What the writer may draw on: services, pricing, proof and positioning. Nothing reaches a prospect unless it's approved for outreach."
      />
      {!canEdit && <Notice tone="warning" title="Read only">Viewers can browse knowledge but not change it.</Notice>}
      <KnowledgeTable />
      <Connectors />
    </div>
  );
}
