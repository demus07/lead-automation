"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleMinus, FileSearch, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { Section, DetailList } from "@/components/shared/section";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { ToneBadge } from "@/components/shared/tone-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { ObservationBadge } from "@/components/shared/observation-badge";
import { EvidenceId, EvidenceList } from "@/components/shared/evidence-list";
import { ExternalLink } from "@/components/shared/external-link";
import { ScoreBar } from "@/components/shared/score";
import { Notice } from "@/components/shared/notice";
import { JsonView } from "@/components/shared/json-view";
import { useCan } from "@/hooks/use-auth";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import { fmtDateTime, humanize } from "@/lib/format";
import { OBSERVATION_META } from "@/lib/status";
import type { AuditCheck, Observation, ResearchReport } from "@/lib/types";
import { cn } from "@/lib/utils";

function groupBy<T>(xs: T[], key: (x: T) => string): [string, T[]][] {
  const m = new Map<string, T[]>();
  xs.forEach((x) => {
    const k = key(x);
    m.set(k, [...(m.get(k) ?? []), x]);
  });
  return Array.from(m.entries());
}

function fmtValue(v: unknown): string {
  if (v === true) return "yes";
  if (v === false) return "no";
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.slice(0, 3).join(" · ") + (v.length > 3 ? ` (+${v.length - 3})` : "") : "none";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function scrollToEvidence(id: string) {
  const el = document.getElementById(`ev-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ring-2", "ring-ring");
  setTimeout(() => el.classList.remove("ring-2", "ring-ring"), 1600);
}

export default function ResearchReportPage() {
  const { id } = useParams<{ id: string }>();
  const canEdit = useCan("operator");
  const q = useQuery({ queryKey: ["research", "report", id], queryFn: () => api.get<ResearchReport>(`/research/${id}`) });
  const rerun = useApiMutation(() => api.post<{ job_id: string; status: string }>(`/research/company/${q.data!.company_id}/run`), {
    success: false,
    invalidate: [["research"], ["company", q.data?.company_id]],
    onSuccess: (r) => jobStartedToast("Research started", r),
  });

  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const r = q.data;
  const method = (r.analysis as { method?: string } | null)?.method ?? "deterministic";
  const valueProp = (r.analysis as { value_proposition?: string } | null)?.value_proposition;
  const summary = r.audit?.summary;
  const checks = r.audit?.checks ?? [];
  const notMeasured = (r.audit?.not_measured ?? []).map(String);
  const robots = (r.robots ?? {}) as { status?: string; homepage_allowed?: boolean; crawl_delay?: number | null; origin?: string };
  const bi = (r.business_info ?? {}) as Record<string, unknown>;
  const flags = (r.injection_flags ?? []).map(String);
  const errors = (r.errors ?? []) as { url?: string | null; error?: string }[];
  const rejected = (r.rejected_observations ?? []) as (Observation & { validation?: string[] })[];
  const evidenceIds = new Set(r.evidence.map((e) => e.id));

  return (
    <>
      <PageHeader
        back={{ href: "/research", label: "Research" }}
        title={r.company ? `${r.company.name} research` : "Research report"}
        description={`Version ${r.version}, researched ${fmtDateTime(r.researched_at ?? r.created_at)}.`}
        meta={
          <>
            <ToneBadge tone={r.status === "complete" ? "success" : r.status === "partial" ? "warning" : "danger"}>{humanize(r.status)}</ToneBadge>
            <ToneBadge tone={method === "llm" ? "violet" : "neutral"}>{method === "llm" ? "AI analysis + checks" : "Deterministic checks only"}</ToneBadge>
            {r.company && <StatusBadge kind="lead" value={r.company.status} />}
            {r.company?.website && <ExternalLink href={r.company.website} className="text-sm" />}
          </>
        }
        actions={
          <>
            {r.company && (
              <Button variant="outline" asChild>
                <Link href={`/companies/${r.company.id}`}>Open company</Link>
              </Button>
            )}
            {canEdit && (
              <Button onClick={() => rerun.mutate()} disabled={rerun.isPending}>
                {rerun.isPending ? <Loader2 className="animate-spin" /> : <FileSearch />} Re-run research
              </Button>
            )}
          </>
        }
      />

      {flags.length > 0 && (
        <Notice tone="warning" title="Possible prompt injection detected" className="mb-6">
          Text on this site looked like instructions aimed at AI systems ({flags.map(humanize).join(", ")}). It was treated as untrusted data and
          never followed. Review observations from these pages with extra care.
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <Section title="Summary">
            <p className="max-w-[72ch] text-sm leading-relaxed text-pretty">{r.summary || "No summary was produced."}</p>
            {valueProp && (
              <p className="mt-3 max-w-[72ch] text-sm text-muted-foreground"><span className="font-medium text-foreground">Value proposition: </span>{valueProp}</p>
            )}
          </Section>

          <Section
            title="Measurable checks"
            description="Pass/fail checks computed from the HTML. Things that can't be measured from HTML are listed, not guessed."
            actions={summary?.score !== undefined && (
              <div className="text-right">
                <span className="text-2xl font-semibold tabular-nums">{summary.score}</span>
                <span className="text-sm text-muted-foreground">/100 · {summary.passed}/{summary.measured} passed</span>
              </div>
            )}
          >
            {summary?.by_area && (
              <div className="mb-6 grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
                {Object.entries(summary.by_area).map(([area, s]) => (
                  <ScoreBar key={area} value={s} service={null} label={humanize(area)} />
                ))}
              </div>
            )}
            {checks.length === 0 ? (
              <p className="text-sm text-muted-foreground">No checks were recorded.</p>
            ) : (
              <div className="space-y-5">
                {groupBy(checks, (c) => c.area).map(([area, items]) => (
                  <div key={area}>
                    <h3 className="mb-2 text-sm font-medium">{humanize(area)}</h3>
                    <ul className="divide-y rounded-lg border">
                      {items.map((c) => <CheckRow key={c.id} c={c} />)}
                    </ul>
                  </div>
                ))}
              </div>
            )}
            {notMeasured.length > 0 && (
              <div className="mt-5 rounded-lg bg-muted/60 px-4 py-3 text-sm">
                <p className="mb-1 font-medium">Not measured</p>
                <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                  {notMeasured.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </div>
            )}
          </Section>

          <Section
            title="Observations"
            description="Every observation is categorised. Hypotheses are inferences, not facts — they mustn't be stated as fact in outreach."
          >
            <div className="mb-4 flex flex-wrap gap-3 text-xs text-muted-foreground">
              {Object.keys(OBSERVATION_META).map((k) => (
                <span key={k} className="inline-flex items-center gap-1.5">
                  <ObservationBadge category={k} />
                  {r.observations.filter((o) => o.category === k).length}
                </span>
              ))}
            </div>
            {r.observations.length === 0 ? (
              <p className="text-sm text-muted-foreground">No observations.</p>
            ) : (
              <div className="space-y-5">
                {groupBy(r.observations, (o) => o.area).map(([area, obs]) => (
                  <div key={area}>
                    <h3 className="mb-2 text-sm font-medium">{humanize(area)}</h3>
                    <ul className="space-y-2">
                      {obs.map((o, i) => (
                        <li key={i} className={cn("rounded-lg border px-3 py-2.5 text-sm", o.category === "hypothesis" && "border-dashed")}>
                          <div className="flex flex-wrap items-start gap-2">
                            <ObservationBadge category={o.category} />
                            <p className="min-w-0 flex-1 text-pretty">{o.text}</p>
                          </div>
                          {o.quote && <blockquote className="mt-2 border-l-2 pl-3 text-xs text-muted-foreground italic">“{o.quote}”</blockquote>}
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            {o.source && <span className="text-xs text-muted-foreground">{o.source === "ai" ? "AI" : humanize(o.source)}</span>}
                            {o.evidence_ids?.map((eid) =>
                              evidenceIds.has(eid) ? (
                                <a key={eid} href={`#ev-${eid}`} onClick={(e) => { e.preventDefault(); scrollToEvidence(eid); }} className="rounded outline-none focus-visible:ring-2 focus-visible:ring-ring">
                                  <EvidenceId id={eid} className="hover:bg-accent hover:text-foreground" />
                                </a>
                              ) : (
                                <EvidenceId key={eid} id={eid} />
                              ),
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Evidence" description="Source excerpts that observations and draft claims cite by id.">
            <EvidenceList items={r.evidence} />
          </Section>

          <Section title="Pages crawled" description={`${r.pages.length} pages fetched.`} bodyClassName="p-0">
            {r.pages.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">No pages could be fetched.</p>
            ) : (
              <ul className="divide-y">
                {r.pages.map((p) => (
                  <li key={p.id} className="px-5 py-3">
                    <details>
                      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 text-sm">
                        <EvidenceId id={p.id} />
                        <span className="font-medium">{p.title || humanize(p.kind)}</span>
                        <span className="text-muted-foreground">{humanize(p.kind)}</span>
                        <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                          {p.word_count ?? 0} words{p.rendered ? " · JS rendered" : ""}
                        </span>
                      </summary>
                      <div className="mt-3 space-y-3 text-sm">
                        <ExternalLink href={p.final_url} className="text-xs">{p.final_url}</ExternalLink>
                        {p.meta_description && <p className="text-muted-foreground">{p.meta_description}</p>}
                        {!!p.headings?.length && (
                          <div>
                            <p className="mb-1 text-xs font-medium">Headings</p>
                            <ul className="space-y-0.5 text-xs text-muted-foreground">
                              {p.headings.map((h, i) => (
                                <li key={i} className={cn(h.level === "h2" && "pl-3", h.level === "h3" && "pl-6")}>
                                  <span className="font-mono text-[0.65rem] opacity-60">{h.level}</span> {h.text}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <ChipRow label="Calls to action" items={p.ctas} />
                        <ChipRow label="Navigation" items={p.nav_items} />
                        <ChipRow label="Technology" items={p.tech} />
                        <ChipRow label="Tools mentioned" items={p.tools_mentioned} />
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {rejected.length > 0 && (
            <Section title="Rejected AI observations" description="AI claims that failed evidence checks and were discarded. Shown for transparency only.">
              <ul className="space-y-2">
                {rejected.map((o, i) => (
                  <li key={i} className="tone tone-danger rounded-lg border border-dashed px-3 py-2.5 text-sm">
                    <p className="text-foreground line-through decoration-1">{o.text}</p>
                    {o.quote && <p className="mt-1 text-xs text-muted-foreground">Quoted: “{o.quote}”</p>}
                    {!!o.validation?.length && <p className="mt-1 text-xs">{o.validation.join("; ")}</p>}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        <aside className="space-y-6">
          <Section title="Crawl">
            <DetailList
              items={[
                {
                  label: "robots.txt",
                  value: (
                    <ToneBadge tone={robots.status === "ok" ? "success" : robots.status ? "warning" : "neutral"}>
                      {robots.status ? humanize(robots.status) : "Unknown"}
                    </ToneBadge>
                  ),
                },
                { label: "Homepage", value: robots.homepage_allowed === false ? "Disallowed" : robots.homepage_allowed ? "Allowed" : "—" },
                { label: "Crawl delay", value: robots.crawl_delay ? `${robots.crawl_delay}s` : "None set" },
                { label: "Pages", value: r.pages.length },
                { label: "Tech", value: r.audit?.tech?.length ? r.audit.tech.join(", ") : null },
              ]}
            />
          </Section>

          <Section title="Business info">
            <BusinessInfo bi={bi} />
          </Section>

          {errors.length > 0 && (
            <Section title="Errors">
              <ul className="space-y-2 text-sm">
                {errors.map((e, i) => (
                  <li key={i} className="flex gap-2">
                    <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                    <div className="min-w-0">
                      <p className="break-words">{e.error}</p>
                      {e.url && <ExternalLink href={e.url} className="text-xs" />}
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {flags.length > 0 && (
            <Section title="Injection flags">
              <ul className="space-y-1.5 text-sm">
                {flags.map((f) => (
                  <li key={f} className="flex items-center gap-2"><ShieldAlert className="size-4 text-warning" />{humanize(f)}</li>
                ))}
              </ul>
            </Section>
          )}
        </aside>
      </div>
    </>
  );
}

function CheckRow({ c }: { c: AuditCheck }) {
  const Icon = c.passed === true ? CheckCircle2 : c.passed === false ? XCircle : CircleMinus;
  return (
    <li className="flex gap-3 px-3 py-2.5 text-sm">
      <Icon className={cn("mt-0.5 size-4 shrink-0", c.passed === true ? "text-success" : c.passed === false ? "text-destructive" : "text-muted-foreground")} aria-label={c.passed ? "Passed" : c.passed === false ? "Failed" : "Not applicable"} />
      <div className="min-w-0 flex-1">
        <p>{c.label}</p>
        <p className="truncate text-xs text-muted-foreground" title={fmtValue(c.value)}>
          {fmtValue(c.value)}
          {c.detail ? ` — ${c.detail}` : ""}
        </p>
      </div>
      {c.evidence_url && <ExternalLink href={c.evidence_url} className="hidden text-xs sm:inline-flex" />}
    </li>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] | null }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-medium">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.map((x, i) => (
          <span key={i} className="rounded bg-secondary px-1.5 py-0.5 text-xs">{x}</span>
        ))}
      </div>
    </div>
  );
}

function BusinessInfo({ bi }: { bi: Record<string, unknown> }) {
  const list = (k: string) => (Array.isArray(bi[k]) ? (bi[k] as unknown[]).map(String) : []);
  const emails = list("public_emails");
  const phones = list("phones");
  const socials = list("social_links");
  const tools = list("tools_mentioned");
  const tech = list("tech");
  const ai = bi.ai;
  const known = new Set(["public_emails", "phones", "social_links", "tools_mentioned", "tech", "ai", "json_ld_orgs"]);
  const rest = Object.fromEntries(Object.entries(bi).filter(([k]) => !known.has(k)));
  if (!emails.length && !phones.length && !socials.length && !tools.length && !tech.length && !ai)
    return <p className="text-sm text-muted-foreground">Nothing extracted.</p>;
  return (
    <div className="space-y-4 text-sm">
      {emails.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium">Public emails</p>
          <ul className="space-y-0.5 break-all text-muted-foreground">{emails.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      {phones.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium">Phones</p>
          <ul className="space-y-0.5 text-muted-foreground">{phones.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      {socials.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium">Social links</p>
          <ul className="space-y-0.5">{socials.map((s) => <li key={s}><ExternalLink href={s} className="text-xs">{s.replace(/^https?:\/\/(www\.)?/, "")}</ExternalLink></li>)}</ul>
        </div>
      )}
      <ChipRow label="Technology" items={tech} />
      <ChipRow label="Tools mentioned" items={tools} />
      {!!ai && (
        <div>
          <p className="mb-1 text-xs font-medium">AI-extracted</p>
          <JsonView value={ai} />
        </div>
      )}
      {Object.keys(rest).length > 0 && <JsonView value={rest} />}
    </div>
  );
}
