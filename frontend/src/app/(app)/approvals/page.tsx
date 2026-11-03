"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Inbox, Keyboard, Mail, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FilterSelect } from "@/components/shared/filter-select";
import { PageHeader } from "@/components/shared/page-header";
import { ScoreBadge } from "@/components/shared/score";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/shared/states";
import { ReviewDetail, isTypingTarget } from "@/components/approvals/review-detail";
import { api } from "@/lib/api";
import { fmtRelative, serviceLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApproveResult, Draft, Page } from "@/lib/types";

type QueueState = "pending" | "review" | "later" | "all";
type QueueResponse = Page<Draft> & { counts: Record<string, number> };

const PAGE_SIZE = 50;
const STATES: { key: QueueState; label: string; count: (c: Record<string, number>) => number }[] = [
  { key: "pending", label: "Pending", count: (c) => c.pending_approval ?? 0 },
  { key: "review", label: "Needs review", count: (c) => c.needs_review ?? 0 },
  { key: "later", label: "Later", count: (c) => c.saved_for_later ?? 0 },
  { key: "all", label: "All", count: (c) => (c.pending_approval ?? 0) + (c.needs_review ?? 0) + (c.saved_for_later ?? 0) },
];

const SHORTCUTS: [string, string][] = [
  ["J / ↓", "Next draft"],
  ["K / ↑", "Previous draft"],
  ["A", "Approve (asks to confirm)"],
  ["E", "Edit subject, body and LinkedIn text"],
  ["Esc", "Cancel editing"],
  ["R", "Reject"],
  ["S", "Save for later"],
  ["?", "Show this help"],
];

function ApprovalsInner() {
  const params = useSearchParams();
  const deepDraft = params.get("draft");
  const initialState = (["pending", "review", "later", "all"].includes(params.get("state") ?? "")
    ? params.get("state")
    : deepDraft
      ? "all"
      : "pending") as QueueState;
  const [state, setState] = useState<QueueState>(initialState);
  const [service, setService] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(deepDraft);
  const [mobileDetail, setMobileDetail] = useState(!!deepDraft);
  const [result, setResult] = useState<{ r: ApproveResult; company: string } | null>(null);
  const [help, setHelp] = useState(false);
  const lastIndex = useRef(0);
  const listRef = useRef<HTMLUListElement>(null);

  const q = useQuery({
    queryKey: ["approvals", "queue", state, service, page],
    queryFn: () => api.get<QueueResponse>("/approvals/queue", { state, service, page, page_size: PAGE_SIZE }),
    placeholderData: (prev) => prev,
  });
  const items = useMemo(() => q.data?.items ?? [], [q.data]);
  const counts = q.data?.counts ?? {};

  // Deep link to a draft that isn't in the queue (e.g. already approved): load it directly.
  const deepInList = !!deepDraft && items.some((d) => d.id === deepDraft);
  const deep = useQuery({
    queryKey: ["draft", deepDraft],
    queryFn: () => api.get<Draft>(`/drafts/${deepDraft}`),
    enabled: !!deepDraft && selectedId === deepDraft && !!q.data && !deepInList,
  });

  // Keep a valid selection: stay on the same index after the current item leaves the queue.
  useEffect(() => {
    if (!q.data) return;
    if (selectedId && (items.some((d) => d.id === selectedId) || (selectedId === deepDraft && deep.data))) return;
    if (selectedId === deepDraft && deep.isLoading) return;
    const next = items[Math.min(lastIndex.current, Math.max(items.length - 1, 0))];
    setSelectedId(next?.id ?? null);
  }, [items, q.data, selectedId, deepDraft, deep.data, deep.isLoading]);

  const index = items.findIndex((d) => d.id === selectedId);
  if (index >= 0) lastIndex.current = index;
  const selected: Draft | undefined = index >= 0 ? items[index] : selectedId === deepDraft ? deep.data : undefined;

  const select = (id: string) => {
    setSelectedId(id);
    setMobileDetail(true);
  };

  // j/k navigation + ? help
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target) || document.querySelector("[role=dialog]")) return;
      if (e.key === "?") {
        e.preventDefault();
        setHelp(true);
        return;
      }
      const k = e.key.toLowerCase();
      if (!items.length) return;
      if (k === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        const n = items[Math.min(index + 1, items.length - 1)];
        if (n) setSelectedId(n.id);
      } else if (k === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const n = items[Math.max(index - 1, 0)];
        if (n) setSelectedId(n.id);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, index]);

  useEffect(() => {
    listRef.current?.querySelector(`[data-id="${selectedId}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const pages = Math.max(1, Math.ceil((q.data?.total ?? 0) / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Approvals"
        description="Check each draft against its evidence, edit if needed, then approve. Approving creates an unsent draft in your mailbox — you send it yourself."
        actions={
          <Button variant="outline" size="sm" onClick={() => setHelp(true)}>
            <Keyboard /> Shortcuts
          </Button>
        }
      />

      {result && (
        <div
          className={cn(
            "tone mb-6 flex items-start gap-3 rounded-xl border px-4 py-3.5",
            result.r.email_draft ? "tone-success" : "tone-warning",
          )}
          role="status"
        >
          {result.r.email_draft ? <Mail className="mt-0.5 size-5 shrink-0" /> : <CheckCircle2 className="mt-0.5 size-5 shrink-0" />}
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-medium text-foreground">
              {result.r.email_draft
                ? `Approved ${result.company} — unsent draft is in ${result.r.email_draft.account}`
                : `Approved ${result.company} — waiting for a mailbox`}
            </p>
            <p className="text-muted-foreground">{result.r.message}</p>
            {!result.r.email_draft && (
              <Link href="/settings/integrations" className="mt-1 inline-block text-foreground underline underline-offset-4">
                Connect Gmail or Outlook
              </Link>
            )}
          </div>
          <Button variant="ghost" size="icon-sm" onClick={() => setResult(null)} aria-label="Dismiss">
            <X />
          </Button>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={state}
          onValueChange={(v) => {
            setState(v as QueueState);
            setPage(1);
            lastIndex.current = 0;
            setSelectedId(null);
          }}
        >
          <TabsList>
            {STATES.map((s) => (
              <TabsTrigger key={s.key} value={s.key} className="px-2.5">
                {s.label}
                <span className="ml-1 text-xs text-muted-foreground tabular-nums">{s.count(counts)}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <FilterSelect
          value={service}
          onChange={(v) => {
            setService(v);
            setPage(1);
          }}
          allLabel="Both services"
          aria-label="Service"
          options={[
            { value: "website", label: "Website" },
            { value: "company_brain", label: "Company Brain" },
          ]}
        />
      </div>

      {q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : q.isLoading ? (
        <div className="rounded-xl border p-4">
          <TableSkeleton rows={6} cols={2} />
        </div>
      ) : !items.length && !selected ? (
        <EmptyState
          icon={Inbox}
          title={state === "pending" ? "Nothing waiting for approval" : "Nothing in this list"}
          description={
            <>
              Drafts appear here after the Draft generation workflow writes them and they pass the quality check. Drafts
              that fail it land in Needs review. Draft generation needs an AI model — if none is configured the app runs in
              limited mode and writes no drafts.
            </>
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="outline" size="sm" asChild>
                <Link href="/settings/ai">Configure AI</Link>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link href="/automation">Open automation</Link>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link href="/pipeline">View pipeline</Link>
              </Button>
            </div>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
          <nav aria-label="Approval queue" className={cn("lg:block", mobileDetail && "hidden")}>
            <div className="lg:sticky lg:top-20">
              <ul ref={listRef} className="max-h-[calc(100svh-14rem)] space-y-1 overflow-y-auto pr-1">
                {items.map((d) => {
                  const active = d.id === selectedId;
                  const failed = d.quality_report?.passed === false;
                  return (
                    <li key={d.id} data-id={d.id}>
                      <button
                        type="button"
                        onClick={() => select(d.id)}
                        aria-current={active ? "true" : undefined}
                        className={cn(
                          "group relative w-full rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          active ? "border-border bg-card shadow-xs" : "hover:bg-accent/60",
                        )}
                      >
                        {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-brand" aria-hidden />}
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-medium">{d.company?.name ?? d.company_name ?? "Unknown company"}</span>
                          <ScoreBadge value={d.quality_score} className={failed ? "tone tone-warning" : undefined} />
                        </div>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">{d.subject}</p>
                        <p className="mt-1 flex items-center gap-1.5 text-[0.7rem] text-muted-foreground">
                          <span
                            className="size-1.5 rounded-full"
                            style={{ background: d.service === "company_brain" ? "var(--svc-brain)" : "var(--svc-website)" }}
                            aria-hidden
                          />
                          {serviceLabel(d.service)}
                          <span>·</span>
                          {d.contact?.full_name ?? "no contact"}
                          <span>·</span>
                          {fmtRelative(d.created_at)}
                        </p>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {pages > 1 && (
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
                    <ChevronLeft />
                  </Button>
                  <span className="tabular-nums">
                    Page {page} of {pages}
                  </span>
                  <Button variant="ghost" size="icon-sm" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page">
                    <ChevronRight />
                  </Button>
                </div>
              )}
              <p className="mt-3 hidden text-xs text-muted-foreground lg:block">
                <kbd className="rounded border px-1">J</kbd> <kbd className="rounded border px-1">K</kbd> to move,{" "}
                <kbd className="rounded border px-1">?</kbd> for all shortcuts
              </p>
            </div>
          </nav>

          <div className={cn("min-w-0", !mobileDetail && "hidden lg:block")}>
            {selected ? (
              <ReviewDetail
                key={selected.id + selected.updated_at}
                draft={selected}
                onBack={() => setMobileDetail(false)}
                onApproved={(r, d) => setResult({ r, company: d.company?.name ?? d.company_name ?? "draft" })}
              />
            ) : deep.isLoading ? (
              <TableSkeleton rows={8} cols={1} />
            ) : (
              <EmptyState compact title="Select a draft to review" />
            )}
          </div>
        </div>
      )}

      <Dialog open={help} onOpenChange={setHelp}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Keyboard shortcuts</DialogTitle>
            <DialogDescription>Shortcuts are ignored while you type in a field.</DialogDescription>
          </DialogHeader>
          <dl className="grid grid-cols-[5rem_1fr] gap-y-2 text-sm">
            {SHORTCUTS.map(([k, v]) => (
              <div key={k} className="contents">
                <dt>
                  <kbd className="rounded border bg-muted px-1.5 py-0.5 text-xs">{k}</kbd>
                </dt>
                <dd className="text-muted-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense>
      <ApprovalsInner />
    </Suspense>
  );
}
