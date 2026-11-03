"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  FileSearch,
  Inbox,
  ListTodo,
  Loader2,
  MailCheck,
  MessagesSquare,
  NotebookPen,
  PenLine,
  Pencil,
  Plus,
  Radio,
  Trash2,
  UserRoundSearch,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Section, DetailList } from "@/components/shared/section";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/shared/states";
import { EmailStatusBadge, StatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { ExternalLink } from "@/components/shared/external-link";
import { ScoreBar, ScoreBadge, ServiceBadge } from "@/components/shared/score";
import { EvidenceList } from "@/components/shared/evidence-list";
import { JsonView } from "@/components/shared/json-view";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Field } from "@/components/shared/field";
import { ContactDialog } from "@/components/contacts/contact-dialog";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import { fmtDate, fmtDateTime, fmtRelative, humanize, serviceLabel } from "@/lib/format";
import { EMAIL_STATUS_META } from "@/lib/status";
import type { Contact, EmailStatus, Note, Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { CompanyDetail, OpportunityDetail } from "./types";
import { useGenerateDraft } from "./use-generate-draft";

/* ----------------------------------------------------------------------------- contacts */

export function ContactsTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const [dialog, setDialog] = useState<{ open: boolean; contact: Contact | null }>({ open: false, contact: null });
  const gen = useGenerateDraft(d.company.id);
  const verify = useApiMutation((c: Contact) => api.post<Contact>(`/contacts/${c.id}/verify-email`), {
    success: (c) => `Email checked: ${EMAIL_STATUS_META[c.email_status as EmailStatus]?.label ?? c.email_status}`,
    invalidate: [["company", d.company.id], ["contacts"]],
  });
  return (
    <Section
      title="Contacts"
      description="People found on the company's own pages, imported, or added by hand. Seniority decides who drafts go to by default."
      actions={
        canEdit && (
          <Button size="sm" onClick={() => setDialog({ open: true, contact: null })}>
            <Plus /> Add contact
          </Button>
        )
      }
      bodyClassName="p-0"
    >
      {d.contacts.length === 0 ? (
        <div className="p-5">
          <EmptyState compact icon={UserRoundSearch} title="No contacts found yet" description="The contacts workflow searches team and about pages after research. You can also add someone you know." />
        </div>
      ) : (
        <ul className="divide-y">
          {d.contacts.map((c) => (
            <li key={c.id} className="flex flex-col gap-3 px-5 py-3.5 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.full_name}</span>
                  {c.is_primary && <span className="text-xs text-brand">primary</span>}
                  <span className="text-sm text-muted-foreground">{c.job_title || "No title"}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                  {c.email ? <span className="text-muted-foreground">{c.email}</span> : null}
                  <EmailStatusBadge status={c.email ?  c.email_status : "none"} />
                  {c.profile_url && <ExternalLink href={c.profile_url} className="text-xs">Profile</ExternalLink>}
                  {c.source_url && <ExternalLink href={c.source_url} className="text-xs">Source</ExternalLink>}
                  <span className="text-xs text-muted-foreground">conf {Math.round(c.confidence * 100)}%</span>
                </div>
              </div>
              {canEdit && (
                <div className="flex flex-wrap gap-1.5">
                  <Button variant="outline" size="sm" disabled={!c.email || verify.isPending} onClick={() => verify.mutate(c)}>
                    <MailCheck /> Verify email
                  </Button>
                  <Button variant="outline" size="sm" disabled={gen.isPending} onClick={() => gen.mutate({ contact_id: c.id })}>
                    <PenLine /> Draft to {c.first_name || "them"}
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={`Edit ${c.full_name}`} onClick={() => setDialog({ open: true, contact: c })}>
                    <Pencil />
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <ContactDialog
        open={dialog.open}
        contact={dialog.contact}
        company={{ id: d.company.id, name: d.company.name, domain: d.company.domain }}
        onOpenChange={(open) => setDialog((s) => ({ ...s, open }))}
      />
    </Section>
  );
}

/* ----------------------------------------------------------------------------- research */

export function ResearchTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const r = d.research;
  const run = useApiMutation(() => api.post<{ job_id: string; status: string }>(`/research/company/${d.company.id}/run`), {
    success: false,
    invalidate: [["company", d.company.id]],
    onSuccess: (res) => jobStartedToast("Research started", res),
  });
  if (!r) {
    return (
      <EmptyState
        icon={FileSearch}
        title="Not researched yet"
        description="Research crawls the website (respecting robots.txt), runs measurable checks and looks for recent signals."
        action={canEdit && <Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending && <Loader2 className="animate-spin" />}Run research</Button>}
      />
    );
  }
  const summary = r.audit?.summary;
  const method = (r.analysis as { method?: string } | null)?.method;
  return (
    <div className="space-y-6">
      <Section
        title={`Research report v${r.version}`}
        description={`${r.pages.length} pages crawled ${fmtRelative(r.researched_at ?? r.created_at)}. ${method === "llm" ? "AI analysis with evidence checks." : "Deterministic checks only (no AI analysis)."}`}
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link href={`/research/${r.id}`}>Open full report</Link>
          </Button>
        }
      >
        <div className="grid gap-6 md:grid-cols-[1fr_auto]">
          <p className="max-w-[72ch] text-sm leading-relaxed text-pretty">{r.summary || "No summary."}</p>
          {summary?.score !== undefined && (
            <div className="text-right">
              <div className="text-3xl font-semibold tracking-[-0.03em] tabular-nums">{summary.score}</div>
              <div className="text-xs text-muted-foreground">
                site audit · {summary.passed}/{summary.measured} checks passed
              </div>
            </div>
          )}
        </div>
        {summary?.by_area && (
          <div className="mt-5 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(summary.by_area).map(([area, score]) => (
              <ScoreBar key={area} value={score} service={null} label={humanize(area)} />
            ))}
          </div>
        )}
      </Section>
      <div className="grid gap-4 text-sm sm:grid-cols-3">
        <Fact label="Observations" value={r.observations.length} />
        <Fact label="Evidence items" value={r.evidence.length} />
        <Fact label="Injection flags" value={r.injection_flags?.length ?? 0} warn={(r.injection_flags?.length ?? 0) > 0} />
      </div>
    </div>
  );
}

function Fact({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-4 py-3", warn && "tone tone-warning")}>
      <div className="text-xl font-semibold tabular-nums text-foreground">{value}</div>
      <div className="text-muted-foreground">{label}</div>
    </div>
  );
}

/* ----------------------------------------------------------------------------- signals */

export function SignalsTab({ d }: { d: CompanyDetail }) {
  if (!d.signals.length)
    return <EmptyState icon={Radio} title="No signals yet" description="Funding, hiring, launches and leadership changes appear here when research finds them in news and feeds." />;
  return (
    <ul className="divide-y rounded-xl border bg-card">
      {d.signals.map((s) => (
        <li key={s.id} className="space-y-1.5 px-5 py-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge tone="violet">{humanize(s.signal_type)}</ToneBadge>
            <ToneBadge tone={s.freshness === "fresh" ? "success" : s.freshness === "recent" ? "info" : "neutral"}>{humanize(s.freshness)}</ToneBadge>
            <span className="text-xs text-muted-foreground">
              {s.published_at ? fmtDate(s.published_at) : "date unknown"} · conf {Math.round(s.confidence * 100)}% · {s.method}
            </span>
          </div>
          <p className="text-sm text-pretty">{s.description}</p>
          <ExternalLink href={s.source_url} className="text-xs">{s.source_name || undefined}</ExternalLink>
        </li>
      ))}
    </ul>
  );
}

/* ----------------------------------------------------------------------------- opportunity */

export function OpportunityTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const q = useQuery({
    queryKey: ["company", d.company.id, "opportunity"],
    queryFn: () => api.get<OpportunityDetail>(`/opportunities/company/${d.company.id}`),
  });
  const rescore = useApiMutation(() => api.post<{ job_id: string; status: string }>(`/opportunities/company/${d.company.id}/score`), {
    success: false,
    invalidate: [["company", d.company.id]],
    onSuccess: (r) => jobStartedToast("Scoring started", r),
  });
  const o = q.data?.opportunity ?? d.opportunity;
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!o)
    return (
      <EmptyState
        icon={CalendarClock}
        title="Not scored yet"
        description="Scoring rates evidence-backed factors for each service independently, then recommends at most one."
        action={canEdit && <Button onClick={() => rescore.mutate()} disabled={rescore.isPending}>Score now</Button>}
      />
    );
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {(["website", "company_brain"] as const).map((svc) => {
          const score = svc === "website" ? o.website_score : o.brain_score;
          const conf = svc === "website" ? o.website_confidence : o.brain_confidence;
          const exp = svc === "website" ? o.website_explanation : o.brain_explanation;
          return (
            <Section key={svc} title={serviceLabel(svc)}>
              <ScoreBar value={score} service={svc} confidence={conf} recommended={o.recommended_service === svc} label="Opportunity score" />
              <p className="mt-4 text-sm leading-relaxed text-pretty text-muted-foreground">{exp || "No explanation recorded."}</p>
            </Section>
          );
        })}
      </div>
      <Section title="Recommendation" description={o.method ? `Method: ${humanize(o.method)}` : undefined}>
        <DetailList
          items={[
            { label: "Service", value: <ServiceBadge service={o.recommended_service} /> },
            { label: "Why", value: o.recommendation_reason },
            { label: "Sales angle", value: o.sales_angle },
            { label: "Updated", value: fmtDateTime(o.updated_at) },
          ]}
        />
        {!!o.evidence?.length && (
          <div className="mt-5">
            <p className="mb-2 text-sm font-medium">Evidence used</p>
            <EvidenceList
              items={o.evidence.map((e, i) => ({
                id: String(e.id ?? `E${i + 1}`),
                url: typeof e.url === "string" ? e.url : null,
                excerpt: typeof e.text === "string" ? e.text : typeof e.excerpt === "string" ? e.excerpt : JSON.stringify(e),
              }))}
            />
          </div>
        )}
      </Section>
      <Section title="Score history" description="Each scoring run, newest first. Factors are the rated inputs the score was computed from." bodyClassName="p-0">
        {q.isLoading ? (
          <div className="p-5"><TableSkeleton rows={3} cols={4} /></div>
        ) : !q.data?.scores.length ? (
          <p className="p-5 text-sm text-muted-foreground">No scoring runs recorded.</p>
        ) : (
          <ul className="divide-y">
            {q.data.scores.map((s) => (
              <li key={s.id} className="px-5 py-3">
                <details>
                  <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 text-sm">
                    <ScoreBadge value={s.score} service={s.service} />
                    <span className="font-medium">{serviceLabel(s.service)}</span>
                    <span className="text-muted-foreground">conf {Math.round(s.confidence * 100)}% · {humanize(s.method)}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(s.created_at)}</span>
                  </summary>
                  <div className="mt-3 space-y-3 text-sm">
                    {s.explanation && <p className="text-pretty text-muted-foreground">{s.explanation}</p>}
                    {s.sales_angle && <p><span className="text-muted-foreground">Angle: </span>{s.sales_angle}</p>}
                    <JsonView value={s.factors} />
                  </div>
                </details>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

/* ----------------------------------------------------------------------------- drafts */

export function DraftsTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const gen = useGenerateDraft(d.company.id);
  if (!d.drafts.length)
    return (
      <EmptyState
        icon={PenLine}
        title="No drafts yet"
        description="Drafts are generated after the company qualifies. Every claim must cite research evidence."
        action={canEdit && <Button onClick={() => gen.mutate({})} disabled={gen.isPending}>{gen.isPending && <Loader2 className="animate-spin" />}Generate draft</Button>}
      />
    );
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Subject</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Service</TableHead>
            <TableHead>Quality</TableHead>
            <TableHead className="hidden md:table-cell">Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {d.drafts.map((dr) => (
            <TableRow key={dr.id}>
              <TableCell>
                <Link href={`/drafts/${dr.id}`} className="font-medium hover:underline">{dr.subject || "(no subject)"}</Link>
                <div className="text-xs text-muted-foreground">v{dr.version}{dr.edited_by_user ? " · edited" : ""}</div>
              </TableCell>
              <TableCell><StatusBadge kind="draft" value={dr.status} /></TableCell>
              <TableCell><ServiceBadge service={dr.service} /></TableCell>
              <TableCell className="tabular-nums">{dr.quality_score ?? "—"}</TableCell>
              <TableCell className="hidden text-xs text-muted-foreground md:table-cell">{fmtRelative(dr.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/* ----------------------------------------------------------------------------- interactions */

export function InteractionsTab({ d }: { d: CompanyDetail }) {
  if (!d.interactions.length)
    return (
      <EmptyState
        icon={MessagesSquare}
        title="No interactions yet"
        description="Replies from connected mailboxes and replies you log by hand show up here."
        action={<Button variant="outline" asChild><Link href="/conversations">Go to conversations</Link></Button>}
      />
    );
  return (
    <ul className="divide-y rounded-xl border bg-card">
      {d.interactions.map((i) => (
        <li key={i.id} className="space-y-1 px-5 py-3.5">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <ToneBadge tone={i.direction === "inbound" ? "info" : "neutral"}>{i.direction === "inbound" ? "Received" : "Sent"}</ToneBadge>
            <span className="text-muted-foreground">{humanize(i.channel)}</span>
            {i.classification && <StatusBadge kind="classification" value={i.classification} />}
            <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(i.occurred_at)}</span>
          </div>
          {i.subject && <p className="text-sm font-medium">{i.subject}</p>}
          {i.snippet && <p className="line-clamp-3 text-sm text-muted-foreground">{i.snippet}</p>}
        </li>
      ))}
    </ul>
  );
}

/* ----------------------------------------------------------------------------- notes */

export function NotesTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const [body, setBody] = useState("");
  const [del, setDel] = useState<Note | null>(null);
  const add = useApiMutation((text: string) => api.post<Note>(`/companies/${d.company.id}/notes`, { body: text }), {
    success: "Note added",
    invalidate: [["company", d.company.id]],
    onSuccess: () => setBody(""),
  });
  const remove = useApiMutation((n: Note) => api.delete(`/companies/${d.company.id}/notes/${n.id}`), {
    success: "Note deleted",
    invalidate: [["company", d.company.id]],
  });
  return (
    <div className="max-w-3xl space-y-4">
      {canEdit && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) add.mutate(body.trim());
          }}
        >
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="Add a note for your team" aria-label="New note" />
          <Button type="submit" size="sm" disabled={!body.trim() || add.isPending}>
            {add.isPending && <Loader2 className="animate-spin" />}
            Add note
          </Button>
        </form>
      )}
      {d.notes.length === 0 ? (
        <EmptyState compact icon={NotebookPen} title="No notes" description="Notes are internal and never used in outreach." />
      ) : (
        <ul className="space-y-3">
          {d.notes.map((n) => (
            <li key={n.id} className="group rounded-lg border bg-card px-4 py-3">
              <p className="text-sm whitespace-pre-wrap">{n.body}</p>
              <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>{fmtDateTime(n.created_at)}</span>
                {canEdit && (
                  <Button variant="ghost" size="icon-xs" aria-label="Delete note" onClick={() => setDel(n)}>
                    <Trash2 />
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={!!del}
        onOpenChange={(o) => !o && setDel(null)}
        title="Delete this note?"
        confirmLabel="Delete note"
        destructive
        onConfirm={() => remove.mutateAsync(del!)}
      />
    </div>
  );
}

/* ----------------------------------------------------------------------------- tasks */

export function TasksTab({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const inv = [["company", d.company.id]];
  const add = useApiMutation(
    () => api.post<Task>("/tasks", { title: title.trim(), company_id: d.company.id, due_at: due ? new Date(`${due}T09:00:00`).toISOString() : null }),
    { success: "Task added", invalidate: inv, onSuccess: () => { setTitle(""); setDue(""); } },
  );
  const update = useApiMutation((v: { t: Task; status: string }) => api.patch<Task>(`/tasks/${v.t.id}`, { status: v.status }), {
    success: (_r, v) => (v.status === "done" ? "Task completed" : "Task reopened"),
    invalidate: inv,
  });
  const remove = useApiMutation((t: Task) => api.delete(`/tasks/${t.id}`), { success: "Task deleted", invalidate: inv });
  const now = Date.now();
  return (
    <div className="max-w-3xl space-y-4">
      {canEdit && (
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) add.mutate();
          }}
        >
          <Field label="Task" htmlFor="task-title" className="flex-1">
            <Input id="task-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Follow up after their launch" />
          </Field>
          <Field label="Due" htmlFor="task-due">
            <Input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
          <Button type="submit" className="self-end" disabled={!title.trim() || add.isPending}>
            {add.isPending && <Loader2 className="animate-spin" />}
            Add task
          </Button>
        </form>
      )}
      {d.tasks.length === 0 ? (
        <EmptyState compact icon={ListTodo} title="No tasks" description="Track follow-ups and to-dos for this company." />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {d.tasks.map((t) => {
            const done = t.status === "done";
            const overdue = !done && t.due_at && new Date(t.due_at).getTime() < now;
            return (
              <li key={t.id} className="flex items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  disabled={!canEdit || update.isPending}
                  onClick={() => update.mutate({ t, status: done ? "open" : "done" })}
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                    done ? "border-brand bg-brand text-brand-foreground" : "hover:border-foreground",
                  )}
                  aria-label={done ? `Reopen ${t.title}` : `Complete ${t.title}`}
                >
                  {done && <Check className="size-3" />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm", done && "text-muted-foreground line-through")}>{t.title}</p>
                  {t.description && <p className="text-xs text-muted-foreground">{t.description}</p>}
                </div>
                <span className={cn("text-xs tabular-nums", overdue ? "text-destructive" : "text-muted-foreground")}>
                  {t.due_at ? `${overdue ? "Overdue · " : "Due "}${fmtDate(t.due_at)}` : humanize(t.kind)}
                </span>
                {canEdit && (
                  <Button variant="ghost" size="icon-xs" aria-label={`Delete ${t.title}`} onClick={() => remove.mutate(t)}>
                    <Trash2 />
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------------------- sources */

export function SourcesTab({ d }: { d: CompanyDetail }) {
  if (!d.sources.length)
    return <EmptyState icon={Inbox} title="No source records" description="Where this company was found (directory, search result, import or manual entry) is recorded here." />;
  return (
    <ul className="divide-y rounded-xl border bg-card">
      {d.sources.map((s) => (
        <li key={s.id} className="space-y-1 px-5 py-3.5">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{humanize(s.provider)}</span>
            <span className="text-muted-foreground">{humanize(s.source_type)}</span>
            <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(s.created_at)}</span>
          </div>
          {s.title && <p className="text-sm">{s.title}</p>}
          {s.snippet && <p className="line-clamp-2 text-sm text-muted-foreground">{s.snippet}</p>}
          {s.source_url && <ExternalLink href={s.source_url} className="text-xs" />}
        </li>
      ))}
    </ul>
  );
}
