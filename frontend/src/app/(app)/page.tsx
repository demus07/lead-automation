"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bot, Inbox, MailCheck, Radar, Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { Notice } from "@/components/shared/notice";
import { Section } from "@/components/shared/section";
import { Stat } from "@/components/shared/stat";
import { StatusBadge } from "@/components/shared/status-badge";
import { DualScore, ServiceBadge } from "@/components/shared/score";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/shared/states";
import { ExternalLink } from "@/components/shared/external-link";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtNumber, fmtRelative, fmtUsd, humanize } from "@/lib/format";
import { LEAD_STATUSES, LEAD_STATUS_META } from "@/lib/status";
import type { Dashboard } from "@/lib/types";

export default function OverviewPage() {
  const isAdmin = useCan("admin");
  const q = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("/dashboard"),
    refetchInterval: 60_000,
  });

  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data;
  const k = d.kpis;
  const waiting = k.pending_approval;

  return (
    <div className="space-y-8">
      <PageHeader title="Overview" description="What needs your attention, and how the pipeline is moving." />

      {!d.onboarding_completed && (
        <div className="flex flex-col gap-4 rounded-xl border border-l-4 border-l-brand bg-card p-5 sm:flex-row sm:items-center">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
            <Sparkles className="size-5" />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="font-medium">Tell the engine about your agency</p>
            <p className="max-w-[70ch] text-sm text-muted-foreground">
              Your services, ideal clients, case studies and sender details shape every score and draft. Setup takes about ten
              minutes and you can change everything later.
            </p>
          </div>
          <Button asChild className="bg-brand text-brand-foreground hover:bg-brand/90">
            <Link href="/onboarding">
              {isAdmin ? "Start setup" : "View setup"} <ArrowRight />
            </Link>
          </Button>
        </div>
      )}

      <SystemNotices d={d} />

      {/* The one thing that matters most: drafts waiting for a human. */}
      <section className="grid gap-6 rounded-xl border bg-card p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col justify-between gap-6">
          <div>
            <div className="flex items-baseline gap-3">
              <span className="text-6xl leading-none font-semibold tracking-[-0.05em] tabular-nums">{waiting}</span>
              <span className="text-sm text-muted-foreground">
                {waiting === 1 ? "draft is" : "drafts are"} waiting for your approval
              </span>
            </div>
            <p className="mt-3 max-w-[46ch] text-sm text-muted-foreground">
              {k.needs_review > 0
                ? `${k.needs_review} more failed the quality gate and need a closer look. `
                : ""}
              Approving creates an unsent draft in your mailbox — you send it yourself.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild className="bg-brand text-brand-foreground hover:bg-brand/90">
              <Link href="/approvals">
                <MailCheck /> Review approvals
              </Link>
            </Button>
            {k.needs_review > 0 && (
              <Button asChild variant="outline">
                <Link href="/approvals?state=review">Needs review ({k.needs_review})</Link>
              </Button>
            )}
          </div>
        </div>
        <div className="min-w-0">
          {d.pending_drafts.length ? (
            <ul className="divide-y rounded-lg border">
              {d.pending_drafts.map((p) => (
                <li key={p.id}>
                  <Link href={`/approvals?draft=${p.id}`} className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-accent/60">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{p.company_name ?? "Unknown company"}</p>
                      <p className="truncate text-xs text-muted-foreground">{p.subject}</p>
                    </div>
                    <ServiceBadge service={p.service} className="hidden sm:inline-flex" />
                    <span className="w-14 text-right text-xs text-muted-foreground tabular-nums" title="Quality score">
                      Q {p.quality_score ?? "—"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              compact
              icon={Inbox}
              title="Queue is clear"
              description={
                d.system.ai.available
                  ? "New drafts appear here after research, qualification and draft generation."
                  : "Drafts can't be generated until an AI provider is configured."
              }
              className="h-full"
            />
          )}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Stat label="Companies" value={fmtNumber(k.companies)} href="/companies" />
        <Stat label="Found today" value={fmtNumber(k.discovered_today)} hint={`${fmtNumber(k.discovered_week)} this week`} href="/discovery" />
        <Stat label="Qualified" value={fmtNumber(k.qualified)} href="/pipeline" />
        <Stat label="Contacts with email" value={fmtNumber(k.contacts_with_email)} href="/contacts" />
        <Stat label="Unhandled replies" value={fmtNumber(k.unhandled_replies)} href="/conversations" emphasis={k.unhandled_replies > 0} />
        <Stat label="Open tasks" value={fmtNumber(k.open_tasks)} />
        <Stat label="Failed jobs (7d)" value={fmtNumber(k.failed_jobs_week)} href="/automation" />
        <Stat label="AI spend today" value={fmtUsd(d.system.ai.spent_today_usd)} hint={`of ${fmtUsd(d.system.ai.daily_budget_usd)} budget`} href="/analytics/ai" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Top opportunities"
          description="Highest website or Company Brain score."
          actions={<Button asChild variant="ghost" size="sm"><Link href="/pipeline">Pipeline <ArrowRight /></Link></Button>}
          bodyClassName="p-0"
        >
          {d.top_opportunities.length ? (
            <ul className="divide-y">
              {d.top_opportunities.map((o) => (
                <li key={o.id}>
                  <Link href={`/companies/${o.id}`} className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/60">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{o.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{o.domain}</p>
                    </div>
                    <StatusBadge kind="lead" value={o.status} />
                    <DualScore compact website={o.website_score} brain={o.brain_score} recommended={o.recommended_service} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={Radar} title="No scored companies yet" description="Scores appear once companies are researched and qualified." className="m-5" />
          )}
        </Section>

        <Section title="Pipeline by status" bodyClassName="space-y-2">
          <StatusBars byStatus={d.by_status} />
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Section title="Recent signals" bodyClassName="p-0" className="lg:col-span-2">
          {d.recent_signals.length ? (
            <ul className="divide-y">
              {d.recent_signals.map((s) => (
                <li key={s.id} className="space-y-1 px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Link href={`/companies/${s.company_id}`} className="font-medium text-foreground hover:underline">
                      {s.company_name ?? "Company"}
                    </Link>
                    <span>{humanize(s.signal_type)}</span>
                    <span>{humanize(s.freshness)}</span>
                    {s.published_at && <span>{fmtRelative(s.published_at)}</span>}
                  </div>
                  <p className="text-sm">
                    <ExternalLink href={s.source_url}>{s.description}</ExternalLink>
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={Search} title="No strong signals yet" description="Funding, hiring and launch signals with confidence ≥ 50% show here." className="m-5" />
          )}
        </Section>

        <div className="space-y-6">
          <Section
            title="Replies to handle"
            bodyClassName="p-0"
            actions={<Button asChild variant="ghost" size="sm"><Link href="/conversations">All <ArrowRight /></Link></Button>}
          >
            {d.recent_replies.length ? (
              <ul className="divide-y">
                {d.recent_replies.map((r) => (
                  <li key={r.id}>
                    <Link href={`/conversations?id=${r.id}`} className="block space-y-1 px-5 py-3 hover:bg-accent/60">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">{r.company_name ?? "Unknown"}</span>
                        <StatusBadge kind="classification" value={r.classification} />
                      </div>
                      <p className="truncate text-xs text-muted-foreground">{r.subject || "No subject"}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-muted-foreground">No unhandled replies.</p>
            )}
          </Section>

          <Section
            title="Recent jobs"
            bodyClassName="p-0"
            actions={<Button asChild variant="ghost" size="sm"><Link href="/automation">Automation <ArrowRight /></Link></Button>}
          >
            {d.recent_jobs.length ? (
              <ul className="divide-y">
                {d.recent_jobs.map((j) => (
                  <li key={j.id}>
                    <Link href={`/automation?job=${j.id}`} className="flex items-center justify-between gap-2 px-5 py-2.5 hover:bg-accent/60">
                      <span className="min-w-0">
                        <span className="block truncate text-sm">{humanize(j.workflow)}</span>
                        <span className="text-xs text-muted-foreground">
                          {humanize(j.trigger)} · {fmtRelative(j.created_at)}
                        </span>
                      </span>
                      <StatusBadge kind="job" value={j.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-muted-foreground">No jobs have run yet.</p>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

function SystemNotices({ d }: { d: Dashboard }) {
  const s = d.system;
  return (
    <div className="space-y-2 empty:hidden">
      {!s.ai.available && (
        <Notice tone="warning" title="Limited mode: no AI provider configured" action={{ href: "/settings/ai", label: "Configure AI" }}>
          Research uses deterministic checks, scoring uses the transparent heuristic, and outreach drafts can&apos;t be generated.
        </Notice>
      )}
      {s.ai.available && s.ai.budget_remaining_usd <= 0 && (
        <Notice tone="warning" title="Today's AI budget is used up" action={{ href: "/settings/ai", label: "Adjust budget" }}>
          AI steps pause until tomorrow or until the budget is raised.
        </Notice>
      )}
      {!s.web_search.configured && (
        <Notice tone="info" title="No web search provider" action={{ href: "/settings/integrations", label: "Add a provider" }}>
          Discovery uses public directories, hiring threads and RSS only.
        </Notice>
      )}
      {s.email_accounts === 0 && (
        <Notice tone="info" title="No mailbox connected" action={{ href: "/settings/integrations", label: "Connect Gmail or Outlook" }}>
          Approved drafts wait here until a mailbox is connected; then they appear as unsent drafts in it.
        </Notice>
      )}
      {s.ai.available && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Bot className="size-3.5" /> AI provider: {humanize(s.ai.provider)}
        </p>
      )}
    </div>
  );
}

function StatusBars({ byStatus }: { byStatus: Dashboard["by_status"] }) {
  const rows = LEAD_STATUSES.map((s) => ({ s, n: byStatus[s] ?? 0 })).filter((r) => r.n > 0);
  const max = Math.max(1, ...rows.map((r) => r.n));
  if (!rows.length) return <p className="text-sm text-muted-foreground">No companies yet. Run discovery to fill the pipeline.</p>;
  return (
    <ul className="space-y-2">
      {rows.map(({ s, n }) => (
        <li key={s}>
          <Link href={`/companies?status=${s}`} className="group grid grid-cols-[9.5rem_1fr_2.5rem] items-center gap-3 text-sm">
            <span className="truncate text-muted-foreground group-hover:text-foreground">{LEAD_STATUS_META[s].label}</span>
            <span className="h-2 overflow-hidden rounded-full bg-muted">
              <span className={`tone tone-${LEAD_STATUS_META[s].tone} block h-full rounded-full`} style={{ width: `${(n / max) * 100}%`, background: "var(--t)" }} />
            </span>
            <span className="text-right tabular-nums">{n}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

