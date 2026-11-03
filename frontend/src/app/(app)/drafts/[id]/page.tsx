"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Mail, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReviewDetail } from "@/components/approvals/review-detail";
import { WordDiff } from "@/components/drafts/word-diff";
import { JsonView } from "@/components/shared/json-view";
import { PageHeader } from "@/components/shared/page-header";
import { Section } from "@/components/shared/section";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/shared/states";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useSession } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtDateTime, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApproveResult, Draft } from "@/lib/types";

const FIELDS = [
  ["subject", "Subject"],
  ["body", "Email body"],
  ["linkedin_connection_note", "LinkedIn connection note"],
  ["linkedin_message", "LinkedIn message"],
] as const;

const ACTION_TONE: Record<string, "success" | "danger" | "warning" | "neutral" | "info"> = {
  approve: "success",
  reject: "danger",
  do_not_contact: "danger",
  save_for_later: "neutral",
  request_regeneration: "warning",
  edit: "info",
};

export default function DraftPage() {
  const { id } = useParams<{ id: string }>();
  const me = useSession().data?.user;
  const [result, setResult] = useState<ApproveResult | null>(null);
  const q = useQuery({ queryKey: ["draft", id], queryFn: () => api.get<Draft>(`/drafts/${id}`) });

  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data;
  const original = d.original ?? {};
  const changedFields = FIELDS.filter(([k]) => (original[k] ?? "") !== (d[k] ?? ""));

  return (
    <div>
      <PageHeader
        back={{ href: "/approvals", label: "Approvals" }}
        title={`Draft for ${d.company?.name ?? "company"}`}
        description="Edit in place, compare with what the AI wrote, and check the evidence before approving."
      />

      {result && (
        <div className={cn("tone mb-6 flex items-start gap-3 rounded-xl border px-4 py-3.5", result.email_draft ? "tone-success" : "tone-warning")} role="status">
          {result.email_draft ? <Mail className="mt-0.5 size-5 shrink-0" /> : <CheckCircle2 className="mt-0.5 size-5 shrink-0" />}
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-medium text-foreground">{result.email_draft ? "Unsent draft created in your mailbox" : "Approved — waiting for a mailbox"}</p>
            <p className="text-muted-foreground">{result.message}</p>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={() => setResult(null)} aria-label="Dismiss">
            <X />
          </Button>
        </div>
      )}

      <ReviewDetail key={d.id + d.updated_at} draft={d} showFullEditorLink={false} onApproved={(r) => setResult(r)} />

      <Tabs defaultValue="changes" className="mt-10">
        <TabsList variant="line">
          <TabsTrigger value="changes">
            Changes <span className="text-xs text-muted-foreground tabular-nums">{changedFields.length}</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            History <span className="text-xs text-muted-foreground tabular-nums">{d.history?.length ?? 0}</span>
          </TabsTrigger>
          <TabsTrigger value="mailbox">
            Mailbox <span className="text-xs text-muted-foreground tabular-nums">{d.email_drafts?.length ?? 0}</span>
          </TabsTrigger>
          <TabsTrigger value="raw">Quality data</TabsTrigger>
        </TabsList>

        <TabsContent value="changes" className="mt-4 space-y-4">
          {!d.original || !Object.keys(d.original).length ? (
            <EmptyState compact title="No original AI text stored for this draft" />
          ) : !changedFields.length ? (
            <EmptyState compact title="No edits yet" description="This is exactly what the AI wrote. Edits you save show here as a word-level comparison." />
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Original AI text compared with the current version. <ins className="tone tone-success rounded-sm px-0.5 no-underline">Added</ins>{" "}
                <del className="tone tone-danger rounded-sm px-0.5">removed</del>
              </p>
              {changedFields.map(([k, label]) => (
                <Section key={k} title={label}>
                  <WordDiff before={original[k] ?? ""} after={d[k] ?? ""} />
                </Section>
              ))}
            </>
          )}
          {d.regeneration_notes && (
            <Section title="Regeneration notes" description="Instructions this version was written with.">
              <p className="text-sm whitespace-pre-wrap">{d.regeneration_notes}</p>
            </Section>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          {!d.history?.length ? (
            <EmptyState compact title="No review actions yet" />
          ) : (
            <ol className="relative space-y-5 border-l pl-6">
              {d.history.map((h, i) => (
                <li key={i} className="relative">
                  <span className="absolute top-1.5 -left-[1.82rem] size-2.5 rounded-full border-2 border-background bg-muted-foreground" aria-hidden />
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <ToneBadge tone={ACTION_TONE[h.action] ?? "neutral"}>{humanize(h.action)}</ToneBadge>
                    <span className="text-muted-foreground">
                      {h.user_id ? (h.user_id === me?.id ? "by you" : "by a teammate") : "by automation"} · {fmtDateTime(h.created_at)}
                    </span>
                  </div>
                  {h.comment && <p className="mt-1.5 text-sm text-pretty">“{h.comment}”</p>}
                  {h.changes && Object.keys(h.changes).length > 0 && (
                    <div className="mt-2 space-y-2">
                      {Object.entries(h.changes).map(([field, ch]) => {
                        const c = ch as { from?: string | null; to?: string | null } | boolean;
                        if (typeof c === "object" && c && "to" in c) {
                          return (
                            <div key={field} className="rounded-lg border p-3">
                              <p className="mb-1 text-xs text-muted-foreground">{humanize(field)}</p>
                              <WordDiff before={c.from ?? ""} after={c.to ?? ""} />
                            </div>
                          );
                        }
                        return (
                          <p key={field} className="text-xs text-muted-foreground">
                            {humanize(field)}: {String(c)}
                          </p>
                        );
                      })}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </TabsContent>

        <TabsContent value="mailbox" className="mt-4">
          {!d.email_drafts?.length ? (
            <EmptyState
              compact
              title="No mailbox draft yet"
              description="After approval, an unsent draft is created in your connected Gmail or Outlook. You send it yourself."
              action={
                <Button variant="outline" size="sm" asChild>
                  <Link href="/settings/integrations">Email accounts</Link>
                </Button>
              }
            />
          ) : (
            <ul className="divide-y rounded-xl border">
              {d.email_drafts.map((e) => (
                <li key={e.id} className="flex flex-col gap-1 p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <ToneBadge tone={e.status === "created" || e.status === "sent" ? "success" : e.last_error ? "danger" : "neutral"}>
                        {humanize(e.status)}
                      </ToneBadge>
                      <span>to {e.to_email ?? "—"}</span>
                    </div>
                    {e.last_error && <p className="text-xs text-destructive">{e.last_error}</p>}
                    {e.external_draft_id && <p className="font-mono text-xs text-muted-foreground">Mailbox id {e.external_draft_id}</p>}
                  </div>
                  <div className="text-xs text-muted-foreground sm:text-right">
                    <p>Created {fmtDateTime(e.created_at)}</p>
                    <p className="tabular-nums">{e.attempts} attempt{e.attempts === 1 ? "" : "s"}</p>
                    {e.sent_detected_at && <p>You sent it {fmtDateTime(e.sent_detected_at)}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="raw" className="mt-4">
          <JsonView value={d.quality_report} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
