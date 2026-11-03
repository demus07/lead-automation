"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shared/field";
import { FilterSelect } from "@/components/shared/filter-select";
import { Section } from "@/components/shared/section";
import { StatusBadge } from "@/components/shared/status-badge";
import { TagInput } from "@/components/shared/tag-input";
import { ChipToggle } from "@/components/campaigns/campaign-form";
import { useCampaignTemplates, usableProviders } from "@/components/campaigns/queries";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { Campaign, DiscoveryProvider } from "@/lib/types";

interface SearchResult {
  job_id: string;
  status: string;
  stats: Record<string, unknown>;
  errors: { error?: string; [k: string]: unknown }[];
}

export function ManualSearch({ providers, campaigns, canRun }: { providers: DiscoveryProvider[]; campaigns: Campaign[]; canRun: boolean }) {
  const templates = useCampaignTemplates();
  const usable = usableProviders(providers);
  const [campaignId, setCampaignId] = useState("");
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [geographies, setGeographies] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [sizes, setSizes] = useState<string[]>([]);
  const [limit, setLimit] = useState(10);
  const [result, setResult] = useState<SearchResult | null>(null);

  const run = useApiMutation(
    () =>
      api.post<SearchResult>("/discovery/search", {
        campaign_id: campaignId || null,
        query: query.trim() || null,
        sources,
        industries,
        geographies,
        keywords,
        company_sizes: sizes,
        limit,
      }),
    {
      success: (r) => (r.status === "succeeded" || r.status === "partial" ? "Search finished" : "Search started"),
      invalidate: [["discovery", "history"], ["workflows"], ["companies"], ["campaigns"]],
      onSuccess: setResult,
    },
  );

  const usingCampaign = !!campaignId;

  return (
    <Section
      title="Run a search"
      description="One-off discovery. With a campaign selected, its filters are used and new companies continue through research."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          run.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Campaign" hint={usingCampaign ? "Uses this campaign's targeting." : "Results go to “Manual searches”."}>
            <FilterSelect
              value={campaignId}
              onChange={setCampaignId}
              allLabel="No campaign (ad-hoc)"
              options={campaigns.map((c) => ({ value: c.id, label: c.name }))}
              className="w-full"
              aria-label="Campaign"
            />
          </Field>
          <Field label="Query" htmlFor="ds-query" hint="Free text for web-search providers.">
            <Input id="ds-query" value={query} maxLength={300} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. dental clinics London" />
          </Field>
        </div>
        <Field label="Sources" hint={usable.length ? "Leave empty to use every available source." : "No source is available."}>
          <ChipToggle
            options={usable.map((p) => p.key)}
            value={sources}
            onChange={setSources}
            labels={Object.fromEntries(usable.map((p) => [p.key, p.label]))}
          />
        </Field>
        {!usingCampaign && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Industries"><TagInput value={industries} onChange={setIndustries} placeholder="e.g. B2B" /></Field>
              <Field label="Geographies"><TagInput value={geographies} onChange={setGeographies} placeholder="e.g. Germany" /></Field>
              <Field label="Keywords"><TagInput value={keywords} onChange={setKeywords} placeholder="e.g. logistics" /></Field>
            </div>
            <Field label="Company sizes">
              <ChipToggle options={templates.data?.sizes ?? []} value={sizes} onChange={setSizes} />
            </Field>
          </>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Max companies" htmlFor="ds-limit" className="w-32">
            <Input id="ds-limit" type="number" min={1} max={100} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(100, Number(e.target.value) || 1)))} />
          </Field>
          <Button type="submit" disabled={!canRun || run.isPending || !usable.length}>
            {run.isPending ? <Loader2 className="animate-spin" /> : <Search />}
            Run search
          </Button>
          {!canRun && <span className="text-xs text-muted-foreground">Operators and admins can run searches.</span>}
        </div>
      </form>

      {result && (
        <div className="mt-5 space-y-3 rounded-lg border bg-muted/40 p-4 text-sm" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge kind="job" value={result.status} />
            <Link href={`/automation?job=${result.job_id}`} className="text-sm underline underline-offset-4 hover:no-underline">
              View job
            </Link>
            {(result.status === "queued" || result.status === "running") && (
              <span className="text-xs text-muted-foreground">Running in the background. New companies appear in the history below.</span>
            )}
          </div>
          {Object.keys(result.stats ?? {}).length > 0 && (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
              {Object.entries(result.stats).filter(([, v]) => typeof v !== "object").map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-muted-foreground">{humanize(k)}</dt>
                  <dd className="font-medium tabular-nums">{String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {result.errors?.length > 0 && (
            <ul className="space-y-1 text-xs">
              {result.errors.map((e, i) => (
                <li key={i} className="tone tone-danger rounded border px-2 py-1">{e.error ?? JSON.stringify(e)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Section>
  );
}
