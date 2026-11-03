"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Ban, Download, MailCheck, MoreHorizontal, Pencil, Plus, Trash2, UserRoundSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable, type Column } from "@/components/shared/data-table";
import { EmailStatusBadge } from "@/components/shared/status-badge";
import { ExternalLink } from "@/components/shared/external-link";
import { FilterSelect } from "@/components/shared/filter-select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Field } from "@/components/shared/field";
import { ContactDialog } from "@/components/contacts/contact-dialog";
import { EmailStatusLegend } from "@/components/contacts/email-legend";
import { useCan } from "@/hooks/use-auth";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useTableState } from "@/hooks/use-table-state";
import { api, download, errorMessage } from "@/lib/api";
import { EMAIL_STATUS_META } from "@/lib/status";
import { fmtRelative } from "@/lib/format";
import type { Contact, EmailStatus, Page } from "@/lib/types";
import { toast } from "sonner";

type Filters = { email_status: string; has_email: string };

export default function ContactsPage() {
  const t = useTableState<Filters>({ sort: "seniority_rank", filters: { email_status: "", has_email: "" } });
  const canEdit = useCan("operator");
  const isAdmin = useCan("admin");
  const [erase, setErase] = useState<Contact | null>(null);
  const [dialog, setDialog] = useState<{ open: boolean; contact: Contact | null }>({ open: false, contact: null });
  const [dnc, setDnc] = useState<Contact | null>(null);
  const [dncNote, setDncNote] = useState("");
  const [del, setDel] = useState<Contact | null>(null);

  const query = {
    q: t.q,
    sort: t.sort,
    page: t.page,
    page_size: t.pageSize,
    email_status: t.filters.email_status || undefined,
    has_email: t.filters.has_email || undefined,
  };
  const list = useQuery({
    queryKey: ["contacts", "list", query],
    queryFn: () => api.get<Page<Contact>>("/contacts", query),
    placeholderData: keepPreviousData,
  });

  const verify = useApiMutation((c: Contact) => api.post<Contact>(`/contacts/${c.id}/verify-email`), {
    success: (c) => `Email checked: ${EMAIL_STATUS_META[c.email_status as EmailStatus]?.label ?? c.email_status}`,
    invalidate: [["contacts"]],
  });
  const markDnc = useApiMutation(
    (v: { c: Contact; note: string }) => api.post(`/contacts/${v.c.id}/do-not-contact`, { reason: "manual", note: v.note || null }),
    { success: "Marked do not contact", invalidate: [["contacts"]] },
  );
  const eraseData = useApiMutation((c: Contact) => api.post(`/admin/erase/contact/${c.id}`), {
    success: "Personal data erased — a suppression record was kept",
    invalidate: [["contacts"]],
  });
  const remove = useApiMutation((c: Contact) => api.delete(`/contacts/${c.id}`), {
    success: "Contact deleted",
    invalidate: [["contacts"]],
  });

  const columns: Column<Contact>[] = [
    {
      key: "name",
      header: "Name",
      sortKey: "full_name",
      cell: (c) => (
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-medium">
            <span className="truncate">{c.full_name}</span>
            {c.is_primary && <span className="text-xs font-normal text-brand">primary</span>}
          </div>
          <div className="truncate text-xs text-muted-foreground">{c.job_title || "No title"}</div>
        </div>
      ),
    },
    {
      key: "company",
      header: "Company",
      cell: (c) =>
        c.company_id ? (
          <Link href={`/companies/${c.company_id}`} className="hover:underline">
            {c.company_name ?? "—"}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "email",
      header: "Email",
      cell: (c) =>
        c.email ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm">{c.email}</span>
            <EmailStatusBadge status={c.email_status} />
          </div>
        ) : (
          <EmailStatusBadge status="none" />
        ),
    },
    {
      key: "seniority",
      header: "Seniority",
      sortKey: "seniority_rank",
      hideBelow: "lg",
      cell: (c) => <span className="tabular-nums text-muted-foreground">{c.seniority_rank}</span>,
    },
    {
      key: "source",
      header: "Source",
      hideBelow: "lg",
      cell: (c) => (
        <div className="text-xs text-muted-foreground">
          {c.source_url ? <ExternalLink href={c.source_url} className="text-xs" /> : c.source_type}
          <div>conf {Math.round(c.confidence * 100)}%</div>
        </div>
      ),
    },
    {
      key: "found",
      header: "Found",
      sortKey: "created_at",
      hideBelow: "md",
      cell: (c) => <span className="text-xs text-muted-foreground">{fmtRelative(c.discovered_at ?? c.created_at)}</span>,
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "w-10 text-right",
      cell: (c) =>
        canEdit ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${c.full_name}`}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setDialog({ open: true, contact: c })}>
                <Pencil /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem disabled={!c.email} onSelect={() => verify.mutate(c)}>
                <MailCheck /> Verify email
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => { setDncNote(""); setDnc(c); }}>
                <Ban /> Do not contact
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => setDel(c)}>
                <Trash2 /> Delete
              </DropdownMenuItem>
              {isAdmin && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={() =>
                      download(`/admin/export/contact/${c.id}`, {}, `contact-${c.id}.json`).catch((e) =>
                        toast.error("Export failed", { description: errorMessage(e) }),
                      )
                    }
                  >
                    <Download /> Export personal data
                  </DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onSelect={() => setErase(c)}>
                    <Trash2 /> Erase personal data
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title="Contacts"
        description="Decision-makers found on official pages, imports and manual entries. Email status is reported as checked — never assumed."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => download("/contacts/export", { q: t.q }, "contacts.csv").catch((e) => toast.error("Export failed", { description: errorMessage(e) }))}
            >
              <Download /> Export CSV
            </Button>
            {canEdit && (
              <Button onClick={() => setDialog({ open: true, contact: null })}>
                <Plus /> Add contact
              </Button>
            )}
          </>
        }
      />
      <EmailStatusLegend />
      <DataTable
        className="mt-4"
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
        searchPlaceholder="Search name, email, title, company"
        filters={
          <>
            <FilterSelect
              aria-label="Email status"
              value={t.filters.email_status}
              onChange={(v) => t.setFilter("email_status", v)}
              allLabel="Any email status"
              options={(Object.keys(EMAIL_STATUS_META) as EmailStatus[]).map((k) => ({ value: k, label: EMAIL_STATUS_META[k].label }))}
            />
            <FilterSelect
              aria-label="Has email"
              value={t.filters.has_email}
              onChange={(v) => t.setFilter("has_email", v)}
              allLabel="With or without email"
              options={[
                { value: "true", label: "Has email" },
                { value: "false", label: "No email" },
              ]}
            />
          </>
        }
        empty={{
          icon: UserRoundSearch,
          title: t.q || t.filters.email_status || t.filters.has_email ? "No contacts match these filters" : "No contacts yet",
          description: "Contacts appear after research finds team pages, or when you add or import them.",
          action: canEdit ? (
            <Button variant="outline" onClick={() => setDialog({ open: true, contact: null })}>
              <Plus /> Add contact
            </Button>
          ) : undefined,
        }}
      />

      <ContactDialog open={dialog.open} contact={dialog.contact} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} />

      <ConfirmDialog
        open={!!dnc}
        onOpenChange={(o) => !o && setDnc(null)}
        title={`Mark ${dnc?.full_name ?? "contact"} as do not contact?`}
        description="Their email goes on the suppression list. No future drafts will be generated or approved for this address."
        confirmLabel="Mark do not contact"
        destructive
        onConfirm={() => markDnc.mutateAsync({ c: dnc!, note: dncNote })}
      >
        <Field label="Note" htmlFor="dnc-note" hint="Optional — why, or who asked">
          <Textarea id="dnc-note" value={dncNote} onChange={(e) => setDncNote(e.target.value)} rows={2} />
        </Field>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!del}
        onOpenChange={(o) => !o && setDel(null)}
        title={`Delete ${del?.full_name ?? "contact"}?`}
        description="The contact is removed from lists and drafting. This doesn't add them to the suppression list."
        confirmLabel="Delete contact"
        destructive
        onConfirm={() => remove.mutateAsync(del!)}
      />

      <ConfirmDialog
        open={!!erase}
        onOpenChange={(o) => !o && setErase(null)}
        title={`Erase all personal data for ${erase?.full_name ?? "this contact"}?`}
        description="Use for data-deletion requests. Name, email, title, profile, draft text and reply content are permanently removed. The email stays on the suppression list so the person is never contacted again. This cannot be undone."
        confirmLabel="Erase permanently"
        destructive
        onConfirm={() => eraseData.mutateAsync(erase!)}
      />
    </>
  );
}
