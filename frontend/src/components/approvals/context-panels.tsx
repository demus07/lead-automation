import Link from "next/link";
import { CheckCircle2, CircleAlert, XCircle } from "lucide-react";
import { ExternalLink } from "@/components/shared/external-link";
import { DualScore } from "@/components/shared/score";
import { EmailStatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Draft, QualityReport } from "@/lib/types";

/** Unboxed rail block: heading + content, separated by hairlines rather than cards. */
export function RailBlock({ title, children, action, className }: { title: string; children: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <section className={cn("space-y-2.5 border-t pt-4 first:border-t-0 first:pt-0", className)}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

export function RecipientBlock({ draft }: { draft: Draft }) {
  const c = draft.contact;
  return (
    <RailBlock title="Recipient">
      {c ? (
        <div className="space-y-1.5 text-sm">
          <p className="font-medium">{c.full_name}</p>
          {c.job_title && <p className="text-muted-foreground">{c.job_title}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <span className="break-all">{c.email ?? <span className="text-muted-foreground">No email</span>}</span>
            <EmailStatusBadge status={c.email_status} />
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {c.profile_url && <ExternalLink href={c.profile_url}>Profile</ExternalLink>}
            {c.source_url && <ExternalLink href={c.source_url}>Where we found them</ExternalLink>}
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No contact attached to this draft.</p>
      )}
    </RailBlock>
  );
}

export function CompanyBlock({ draft, researchSummary, researchId }: { draft: Draft; researchSummary?: string | null; researchId?: string | null }) {
  const co = draft.company;
  if (!co) return null;
  const brief = co.brief;
  return (
    <RailBlock
      title="Company"
      action={
        <Link href={`/companies/${co.id}`} className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground">
          Open company
        </Link>
      }
    >
      <div className="space-y-3 text-sm">
        <div>
          <p className="font-medium">{co.name}</p>
          {co.website && <ExternalLink href={co.website} className="text-xs" />}
        </div>
        <DualScore website={co.website_score} brain={co.brain_score} recommended={co.recommended_service} />
        {brief?.next_action && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Suggested next step</p>
            <p>
              <span className="font-medium">{humanize(brief.next_action)}</span>
              {brief.reason && <span className="text-muted-foreground"> — {brief.reason}</span>}
            </p>
          </div>
        )}
        {(brief?.lead_summary || researchSummary) && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Research summary</p>
            <p className="text-pretty">{brief?.lead_summary || researchSummary}</p>
          </div>
        )}
        {!!brief?.open_questions?.length && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Open questions</p>
            <ul className="list-disc space-y-0.5 pl-4">
              {brief.open_questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        )}
        {researchId && (
          <Link href={`/research/${researchId}`} className="inline-block text-xs underline underline-offset-4">
            View full research
          </Link>
        )}
      </div>
    </RailBlock>
  );
}

const SEVERITY_TONE = { high: "danger", medium: "warning", low: "neutral" } as const;

export function QualitySummary({ score, report, className }: { score: number | null; report: QualityReport | null; className?: string }) {
  const passed = report?.passed;
  const Icon = passed ? CheckCircle2 : passed === false ? XCircle : CircleAlert;
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center gap-3">
        <span className={cn("text-3xl font-semibold tracking-[-0.03em] tabular-nums", passed === false && "text-[var(--tone-warning)]")}>
          {score ?? "—"}
        </span>
        <div className="text-xs text-muted-foreground">
          <p className="flex items-center gap-1 font-medium text-foreground">
            <Icon className={cn("size-3.5", passed ? "text-[var(--tone-success)]" : "text-[var(--tone-warning)]")} />
            {passed ? "Passes the quality gate" : passed === false ? "Below the quality gate" : "Not checked"}
          </p>
          <p>
            Threshold {report?.threshold ?? "—"}
            {report?.deterministic_score !== undefined && ` · rule checks ${report.deterministic_score}`}
          </p>
        </div>
      </div>
      {report?.after_human_edit && <p className="text-xs text-muted-foreground">Re-checked by rules after your edit (no AI review).</p>}
      {report?.ai_note && <p className="text-xs text-muted-foreground">{report.ai_note}</p>}
      {report?.issues?.length ? (
        <ul className="space-y-1.5">
          {report.issues.map((i, n) => (
            <li key={n} className="flex items-start gap-2 text-sm">
              <ToneBadge tone={SEVERITY_TONE[i.severity as keyof typeof SEVERITY_TONE] ?? "neutral"} className="mt-0.5">
                {humanize(i.severity)}
              </ToneBadge>
              <span className="min-w-0 text-pretty">
                {i.text}
                <span className="ml-1 text-xs text-muted-foreground">({i.source === "ai" ? "AI review" : "rule"})</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        report && <p className="text-sm text-muted-foreground">No issues found.</p>
      )}
      {report?.ai_scores && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {Object.entries(report.ai_scores)
            .filter(([, v]) => typeof v === "number")
            .map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{humanize(k)}</dt>
                <dd className="tabular-nums">{String(v)}</dd>
              </div>
            ))}
        </dl>
      )}
    </div>
  );
}
