"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, CheckCheck, Loader2, MessagesSquare, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { LogReplyDialog } from "@/components/conversations/log-reply-dialog";
import { CopyButton } from "@/components/shared/copy-button";
import { DataTable, type Column } from "@/components/shared/data-table";
import { FilterSelect } from "@/components/shared/filter-select";
import { JsonView } from "@/components/shared/json-view";
import { Notice } from "@/components/shared/notice";
import { PageHeader } from "@/components/shared/page-header";
import { DetailList } from "@/components/shared/section";
import { StatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative, humanize, truncate } from "@/lib/format";
import { INTERACTION_LABELS } from "@/lib/status";
import type { Interaction, Page } from "@/lib/types";

const PAGE_SIZE = 25;

function ConversationDetail({ item, onChange }: { item: Interaction; onChange: (i: Interaction) => void }) {
  const canAct = useCan("operator");
  const inv = [["conversations"], ["dashboard"]];
  const label = useApiMutation((classification: string) => api.post<Interaction>(`/conversations/${item.id}/label`, { classification }), {
    success: (i) => `Relabelled as ${humanize(i.classification)}`,
    invalidate: inv,
    onSuccess: onChange,
  });
  const reclassify = useApiMutation(() => api.post<Interaction>(`/conversations/${item.id}/reclassify`), {
    success: (i) => `Reclassified as ${humanize(i.classification)}`,
    invalidate: inv,
    onSuccess: onChange,
  });
  const handled = useApiMutation((v: boolean) => api.post<Interaction>(`/conversations/${item.id}/handled`, undefined, { handled: v }), {
    success: (i) => (i.handled ? "Marked handled" : "Marked not handled"),
    invalidate: inv,
    onSuccess: onChange,
  });
  const detail = item.classification_detail ?? {};
  const optOut = detail.opt_out_requested === true || item.classification === "unsubscribe";

  return (
    <div className="space-y-6 px-4 pb-6">
      {optOut && (
        <Notice tone="danger" title="Opt-out requested">
          This sender asked not to be contacted. They&apos;ve been added to the suppression list automatically.
        </Notice>
      )}

      <DetailList
        items={[
          {
            label: "Company",
            value: item.company_id ? <Link className="underline underline-offset-4" href={`/companies/${item.company_id}`}>{item.company_name}</Link> : null,
          },
          { label: "Contact", value: item.contact_name },
          { label: "From", value: item.from_email },
          { label: "To", value: item.to_email },
          { label: "Channel", value: humanize(item.channel) },
          { label: "Received", value: fmtDateTime(item.occurred_at) },
        ]}
      />

      <div className="space-y-2">
        <p className="text-sm font-medium">{item.subject || "No subject"}</p>
        <div className="rounded-lg border bg-muted/40 p-4 text-sm leading-6 whitespace-pre-wrap">{item.snippet || "No text captured."}</div>
      </div>

      <div className="space-y-3 border-t pt-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Classification</span>
          <StatusBadge kind="classification" value={item.classification ?? "unknown"} />
          {item.classification_confidence !== null && (
            <span className="text-xs text-muted-foreground tabular-nums">{Math.round((item.classification_confidence ?? 0) * 100)}% confidence</span>
          )}
          {typeof detail.method === "string" && <span className="text-xs text-muted-foreground">by {detail.method === "human" ? "you" : detail.method}</span>}
        </div>
        {canAct && (
          <div className="flex flex-wrap items-center gap-2">
            <Select value={item.classification ?? "unknown"} onValueChange={(v) => label.mutate(v)} disabled={label.isPending}>
              <SelectTrigger className="w-52" aria-label="Relabel">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {INTERACTION_LABELS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {humanize(l)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => reclassify.mutate()} disabled={reclassify.isPending}>
              {reclassify.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />}
              Reclassify
            </Button>
          </div>
        )}
        {typeof detail.reason === "string" && <p className="text-sm text-muted-foreground">{detail.reason}</p>}
      </div>

      <div className="space-y-3 border-t pt-5">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-sm font-medium">
            <Sparkles className="size-3.5" /> Suggested reply
          </span>
          {item.suggested_reply && <CopyButton text={item.suggested_reply} label="Copy reply" />}
        </div>
        {item.suggested_reply ? (
          <p className="rounded-lg border p-4 text-sm leading-6 whitespace-pre-wrap">{item.suggested_reply}</p>
        ) : (
          <p className="text-sm text-muted-foreground">No suggestion. Suggested replies need an AI model (limited mode classifies by rules only).</p>
        )}
        {item.suggested_action && (
          <p className="text-sm">
            <span className="text-muted-foreground">Suggested action: </span>
            {humanize(item.suggested_action)}
          </p>
        )}
      </div>

      {Object.keys(detail).length > 0 && (
        <details className="border-t pt-5 text-sm">
          <summary className="cursor-pointer text-muted-foreground">Classification details</summary>
          <JsonView value={detail} className="mt-2" />
        </details>
      )}

      {canAct && (
        <div className="border-t pt-5">
          <Button
            variant={item.handled ? "outline" : "default"}
            onClick={() => handled.mutate(!item.handled)}
            disabled={handled.isPending}
            className="w-full sm:w-auto"
          >
            {handled.isPending ? <Loader2 className="animate-spin" /> : <CheckCheck />}
            {item.handled ? "Mark not handled" : "Mark handled"}
          </Button>
        </div>
      )}
    </div>
  );
}

function ConversationsInner() {
  const params = useSearchParams();
  const deepId = params.get("id");
  const canAct = useCan("operator");
  const [page, setPage] = useState(1);
  const [classification, setClassification] = useState("");
  const [handled, setHandled] = useState(deepId ? "" : "false");
  const [direction, setDirection] = useState("");
  const [open, setOpen] = useState<Interaction | null>(null);

  const q = useQuery({
    queryKey: ["conversations", "list", page, classification, handled, direction],
    queryFn: () =>
      api.get<Page<Interaction>>("/conversations", {
        page,
        page_size: PAGE_SIZE,
        classification,
        handled: handled === "" ? undefined : handled,
        direction,
      }),
    placeholderData: (p) => p,
  });

  // Deep link: there is no GET /conversations/{id}, so look it up in a wide unfiltered page.
  const lookup = useQuery({
    queryKey: ["conversations", "lookup", deepId],
    queryFn: () => api.get<Page<Interaction>>("/conversations", { page_size: 200 }),
    enabled: !!deepId,
  });
  useEffect(() => {
    if (!deepId) return;
    const hit = q.data?.items.find((i) => i.id === deepId) ?? lookup.data?.items.find((i) => i.id === deepId);
    if (hit) setOpen(hit);
  }, [deepId, q.data, lookup.data]);

  const set = (fn: (v: string) => void) => (v: string) => {
    fn(v);
    setPage(1);
  };

  const columns: Column<Interaction>[] = [
    {
      key: "dir",
      header: "",
      className: "w-8 pr-0",
      cell: (i) =>
        i.direction === "inbound" ? (
          <ArrowDownLeft className="size-4 text-brand" aria-label="Inbound" />
        ) : (
          <ArrowUpRight className="size-4 text-muted-foreground" aria-label="Outbound" />
        ),
    },
    {
      key: "who",
      header: "From",
      cell: (i) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{i.company_name ?? i.from_email ?? "Unknown"}</p>
          <p className="truncate text-xs text-muted-foreground">{i.contact_name ?? i.from_email ?? humanize(i.channel)}</p>
        </div>
      ),
    },
    {
      key: "subject",
      header: "Message",
      cell: (i) => (
        <div className="max-w-[44ch] min-w-0">
          <p className="truncate">{i.subject || "No subject"}</p>
          <p className="truncate text-xs text-muted-foreground">{truncate(i.snippet, 120)}</p>
        </div>
      ),
    },
    { key: "class", header: "Classification", cell: (i) => <StatusBadge kind="classification" value={i.classification ?? "unknown"} /> },
    {
      key: "handled",
      header: "Status",
      hideBelow: "md",
      cell: (i) => (i.handled ? <ToneBadge tone="neutral">Handled</ToneBadge> : <ToneBadge tone="warning">Needs action</ToneBadge>),
    },
    { key: "when", header: "When", hideBelow: "sm", className: "text-muted-foreground whitespace-nowrap", cell: (i) => fmtRelative(i.occurred_at) },
  ];

  return (
    <div>
      <PageHeader
        title="Conversations"
        description="Replies matched to your leads, classified, with a suggested next step. Nothing is sent from here — copy a suggestion into your mail client."
        actions={canAct ? <LogReplyDialog onLogged={(i) => setOpen(i)} /> : undefined}
      />
      <DataTable
        columns={columns}
        rows={q.data?.items}
        rowKey={(i) => i.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        page={page}
        pageSize={PAGE_SIZE}
        total={q.data?.total}
        onPageChange={setPage}
        onRowClick={setOpen}
        rowClassName={(i) => (!i.handled && i.direction === "inbound" ? "font-medium" : undefined)}
        filters={
          <>
            <FilterSelect
              value={handled}
              onChange={set(setHandled)}
              allLabel="Handled and not"
              aria-label="Handled"
              options={[
                { value: "false", label: "Needs action" },
                { value: "true", label: "Handled" },
              ]}
            />
            <FilterSelect
              value={classification}
              onChange={set(setClassification)}
              allLabel="All classifications"
              aria-label="Classification"
              options={INTERACTION_LABELS.map((l) => ({ value: l, label: humanize(l) }))}
            />
            <FilterSelect
              value={direction}
              onChange={set(setDirection)}
              allLabel="Both directions"
              aria-label="Direction"
              options={[
                { value: "inbound", label: "Inbound" },
                { value: "outbound", label: "Outbound" },
              ]}
            />
          </>
        }
        empty={{
          icon: MessagesSquare,
          title: handled === "false" ? "No replies need action" : "No conversations match",
          description:
            "Replies appear here when Reply monitoring reads a connected mailbox, or when you log one by hand. Connect Gmail or Outlook under Integrations.",
          action: (
            <Button variant="outline" size="sm" asChild>
              <Link href="/settings/integrations">Integrations</Link>
            </Button>
          ),
        }}
      />

      <Sheet open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl data-[side=right]:sm:max-w-xl">
          {open && (
            <>
              <SheetHeader>
                <SheetTitle>{open.company_name ?? open.from_email ?? "Conversation"}</SheetTitle>
                <SheetDescription>
                  {open.direction === "inbound" ? "Inbound" : "Outbound"} {humanize(open.channel).toLowerCase()} · {fmtRelative(open.occurred_at)}
                </SheetDescription>
              </SheetHeader>
              <ConversationDetail key={open.id} item={open} onChange={setOpen} />
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

export default function ConversationsPage() {
  return (
    <Suspense>
      <ConversationsInner />
    </Suspense>
  );
}
