"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/shared/page-header";
import { Notice } from "@/components/shared/notice";
import { ErrorState, TableSkeleton } from "@/components/shared/states";
import { ToneBadge } from "@/components/shared/tone-badge";
import { LLMForm, TestConnection } from "@/components/settings/llm-form";
import { SettingsBlock } from "@/components/settings/settings-block";
import { SimpleSettingsForm } from "@/components/settings/simple-settings-form";
import { useSettingsSection } from "@/components/settings/use-settings";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtUsd } from "@/lib/format";
import type { AIStatus, LLMSettings } from "@/lib/types";

interface AIStatusFull extends AIStatus {
  model_fast: string;
  model_smart: string;
  max_calls_per_company: number;
  mode: "full" | "limited";
  limited_mode_effects: string[];
  agents: { name: string; label: string; tier: string; responsibility: string; output: string }[];
}

function StatusPanel() {
  const q = useQuery({ queryKey: ["ai", "status"], queryFn: () => api.get<AIStatusFull>("/ai/status") });
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <TableSkeleton rows={3} cols={3} />;
  const s = q.data;
  const pct = s.daily_budget_usd > 0 ? Math.min(100, (s.spent_today_usd / s.daily_budget_usd) * 100) : 0;
  return (
    <div className="space-y-5">
      {s.mode === "limited" ? (
        <Notice tone="warning" title="Limited mode">
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {s.limited_mode_effects.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Notice>
      ) : (
        <Notice tone="info" title="Full mode">
          Using {s.provider}: fast tier {s.model_fast}, smart tier {s.model_smart}.
        </Notice>
      )}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-muted-foreground">Spent today</span>
          <span className="tabular-nums">
            <span className="font-semibold">{fmtUsd(s.spent_today_usd)}</span>
            <span className="text-muted-foreground"> of {fmtUsd(s.daily_budget_usd)}</span>
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Daily AI budget used">
          <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-xs text-muted-foreground">
          {fmtUsd(s.budget_remaining_usd)} remaining. Each company may use up to {s.max_calls_per_company} AI calls.
        </p>
      </div>
      <ul className="divide-y rounded-lg border">
        {s.agents.map((a) => (
          <li key={a.name} className="space-y-1 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{a.label}</span>
              <ToneBadge tone={a.tier === "smart" ? "violet" : "info"}>{a.tier === "smart" ? "Smart tier" : "Fast tier"}</ToneBadge>
            </div>
            <p className="text-sm text-muted-foreground">{a.responsibility}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AISettingsPage() {
  const isAdmin = useCan("admin");
  const llm = useSettingsSection<LLMSettings>("llm");

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="AI configuration"
        description="Model provider, budgets, quality gate and scoring thresholds. AI output is always validated against evidence before you see it."
      />
      {!isAdmin && (
        <Notice tone="warning" className="mb-6" title="Read only">
          Only admins can change AI settings.
        </Notice>
      )}

      <SettingsBlock title="Status and agents" description="What runs on AI today, spend against the daily budget, and what each agent is responsible for.">
        <StatusPanel />
      </SettingsBlock>

      <SettingsBlock
        title="Provider"
        description="API keys are write-only: they're stored encrypted and never shown again. Leave the key blank to keep the stored one."
      >
        {llm.error ? (
          <ErrorState error={llm.error} retry={() => llm.refetch()} />
        ) : !llm.data ? (
          <TableSkeleton rows={4} cols={2} />
        ) : (
          <div className="space-y-6">
            <LLMForm settings={llm.data} disabled={!isAdmin} />
            <div className="border-t pt-5">
              <TestConnection disabled={!isAdmin || llm.data.provider === "none"} />
            </div>
          </div>
        )}
      </SettingsBlock>

      <SettingsBlock
        title="Quality gate"
        description="Drafts scoring below the threshold go to Needs review instead of the approval queue. High-severity issues always fail."
      >
        <SimpleSettingsForm
          section="quality"
          disabled={!isAdmin}
          saveLabel="Save quality settings"
          successMsg="Quality settings saved"
          fields={[
            { key: "threshold", label: "Pass threshold", type: "number", min: 0, max: 100, suffix: "/100" },
            { key: "max_regenerations", label: "Automatic regenerations", type: "number", min: 0, max: 10, hint: "Retries before a draft needs review." },
            { key: "min_words", label: "Minimum words", type: "number", min: 0 },
            { key: "max_words", label: "Maximum words", type: "number", min: 0 },
            { key: "target_min_words", label: "Target minimum words", type: "number", min: 0 },
            { key: "target_max_words", label: "Target maximum words", type: "number", min: 0 },
            { key: "banned_phrases", label: "Banned phrases", type: "tags", hint: "Drafts containing these fail the deterministic check." },
          ]}
        />
      </SettingsBlock>

      <SettingsBlock title="Scoring" description="When a lead counts as qualified, and how far ahead one service must be to be recommended over the other.">
        <SimpleSettingsForm
          section="scoring"
          disabled={!isAdmin}
          saveLabel="Save scoring settings"
          successMsg="Scoring settings saved"
          fields={[
            { key: "qualification_threshold", label: "Qualification threshold", type: "number", min: 0, max: 100, suffix: "/100" },
            { key: "service_margin", label: "Service margin", type: "number", min: 0, max: 100, suffix: "points", hint: "Minimum lead of the winning score." },
            { key: "min_confidence", label: "Minimum confidence", type: "number", min: 0, max: 1, step: 0.05, hint: "0–1" },
          ]}
        />
      </SettingsBlock>

      <SettingsBlock title="Research" description="How much of each website is crawled and how recent a signal must be to count.">
        <SimpleSettingsForm
          section="research"
          disabled={!isAdmin}
          saveLabel="Save research settings"
          successMsg="Research settings saved"
          fields={[
            { key: "max_pages", label: "Pages per site", type: "number", min: 1, max: 50 },
            { key: "request_delay_seconds", label: "Delay between requests", type: "number", min: 0, step: 0.5, suffix: "s" },
            { key: "recrawl_after_days", label: "Re-crawl after", type: "number", min: 1, suffix: "days" },
            { key: "signal_lookback_days", label: "Signal lookback", type: "number", min: 1, suffix: "days" },
            { key: "fresh_signal_days", label: "Fresh signal within", type: "number", min: 1, suffix: "days" },
            { key: "recent_signal_days", label: "Recent signal within", type: "number", min: 1, suffix: "days" },
            { key: "use_news_rss", label: "Look for news via RSS", type: "boolean" },
          ]}
        />
      </SettingsBlock>

      <SettingsBlock title="Data retention" description="How long records are kept before the maintenance workflow removes them.">
        <SimpleSettingsForm
          section="retention"
          disabled={!isAdmin}
          saveLabel="Save retention settings"
          successMsg="Retention settings saved"
          fields={[
            { key: "page_cache_days", label: "Crawled page cache", type: "number", min: 1, suffix: "days" },
            { key: "ai_runs_days", label: "AI run logs", type: "number", min: 1, suffix: "days" },
            { key: "audit_log_days", label: "Audit log", type: "number", min: 1, suffix: "days" },
            { key: "rejected_drafts_days", label: "Rejected drafts", type: "number", min: 1, suffix: "days" },
            { key: "disqualified_companies_days", label: "Disqualified companies", type: "number", min: 1, suffix: "days" },
            { key: "interactions_days", label: "Conversations", type: "number", min: 1, suffix: "days" },
          ]}
        />
      </SettingsBlock>
    </div>
  );
}
