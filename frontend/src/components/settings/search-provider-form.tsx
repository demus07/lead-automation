"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import type { DiscoverySettings } from "@/lib/types";
import { SecretInput } from "./secret-input";
import { useSaveSettings } from "./use-settings";

const PROVIDERS = [
  { value: "none", label: "None (limited mode)", help: "Discovery uses public directories, hiring threads and RSS only." },
  { value: "brave", label: "Brave Search API", help: "Independent web index with a free tier. Needs an API key." },
  { value: "tavily", label: "Tavily", help: "Search API designed for AI agents. Needs an API key." },
  { value: "serpapi", label: "SerpAPI (Google results)", help: "Google results via SerpAPI. Needs an API key." },
  { value: "searxng", label: "SearXNG (self-hosted)", help: "Your own instance with JSON output enabled. No key." },
];

type Keys = "brave_api_key" | "tavily_api_key" | "serpapi_api_key";

/** Search provider + quotas (/settings/discovery). `compact` hides advanced fields (used in onboarding). */
export function SearchProviderForm({
  settings,
  disabled,
  compact,
  onSaved,
  submitLabel = "Save search settings",
}: {
  settings: DiscoverySettings;
  disabled?: boolean;
  compact?: boolean;
  onSaved?: () => void;
  submitLabel?: string;
}) {
  const [v, setV] = useState({
    web_search_provider: settings.web_search_provider,
    brave_api_key: "",
    tavily_api_key: "",
    serpapi_api_key: "",
    searxng_url: settings.searxng_url ?? "",
    daily_search_quota: String(settings.daily_search_quota ?? 100),
    default_country: settings.default_country ?? "",
    results_per_query: String(settings.results_per_query ?? 10),
    excluded_domains: settings.excluded_domains ?? [],
    sec_user_agent_contact: settings.sec_user_agent_contact ?? "",
  });
  const save = useSaveSettings<DiscoverySettings>("discovery", "Search settings saved");
  const set = <K extends keyof typeof v>(k: K, val: (typeof v)[K]) => setV((s) => ({ ...s, [k]: val }));
  const p = v.web_search_provider;
  const keyFor: Record<string, Keys | undefined> = { brave: "brave_api_key", tavily: "tavily_api_key", serpapi: "serpapi_api_key" };
  const key = keyFor[p];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const patch: Record<string, unknown> = {
      web_search_provider: v.web_search_provider,
      searxng_url: v.searxng_url.trim(),
      brave_api_key: v.brave_api_key,
      tavily_api_key: v.tavily_api_key,
      serpapi_api_key: v.serpapi_api_key,
    };
    if (!compact) {
      Object.assign(patch, {
        daily_search_quota: Number(v.daily_search_quota),
        default_country: v.default_country.trim(),
        results_per_query: Number(v.results_per_query),
        excluded_domains: v.excluded_domains,
        sec_user_agent_contact: v.sec_user_agent_contact.trim(),
      });
    }
    try {
      await save.mutateAsync(patch);
      setV((s) => ({ ...s, brave_api_key: "", tavily_api_key: "", serpapi_api_key: "" }));
      onSaved?.();
    } catch {
      /* toast shown */
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <fieldset disabled={disabled} className="space-y-5">
        <Field label="Web search provider" htmlFor="wsp" hint={PROVIDERS.find((x) => x.value === p)?.help}>
          <Select value={p} onValueChange={(x) => set("web_search_provider", x as DiscoverySettings["web_search_provider"])} disabled={disabled}>
            <SelectTrigger id="wsp" className="w-full sm:w-80">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {key && (
          <Field label={`${PROVIDERS.find((x) => x.value === p)?.label} API key`} htmlFor="wsp-key">
            <SecretInput
              id="wsp-key"
              value={v[key]}
              onChange={(x) => set(key, x)}
              isSet={settings[`${key}_is_set` as const]}
              masked={settings[`${key}_masked` as const]}
              disabled={disabled}
            />
          </Field>
        )}
        {p === "searxng" && (
          <Field label="SearXNG URL" htmlFor="searx" hint="Base URL of your instance, for example https://search.example.com">
            <Input id="searx" value={v.searxng_url} onChange={(e) => set("searxng_url", e.target.value)} placeholder="https://" />
          </Field>
        )}
        {!compact && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Daily search quota" htmlFor="quota" hint="Web searches per day, all campaigns.">
                <Input id="quota" type="number" min={0} max={100000} value={v.daily_search_quota} onChange={(e) => set("daily_search_quota", e.target.value)} className="tabular-nums" />
              </Field>
              <Field label="Results per query" htmlFor="rpq">
                <Input id="rpq" type="number" min={1} max={100} value={v.results_per_query} onChange={(e) => set("results_per_query", e.target.value)} className="tabular-nums" />
              </Field>
              <Field label="Default country" htmlFor="country" hint="ISO code, e.g. gb">
                <Input id="country" value={v.default_country} onChange={(e) => set("default_country", e.target.value)} />
              </Field>
            </div>
            <Field label="Excluded domains" htmlFor="excl" hint="Results from these domains are never saved as companies.">
              <TagInput id="excl" value={v.excluded_domains} onChange={(x) => set("excluded_domains", x)} disabled={disabled} />
            </Field>
            <Field label="SEC EDGAR contact" htmlFor="sec" hint="Email or URL sent in the User-Agent; the SEC requires one for EDGAR access.">
              <Input id="sec" value={v.sec_user_agent_contact} onChange={(e) => set("sec_user_agent_contact", e.target.value)} />
            </Field>
          </>
        )}
      </fieldset>
      <Button type="submit" disabled={disabled || save.isPending}>
        {save.isPending && <Loader2 className="animate-spin" />}
        {submitLabel}
      </Button>
    </form>
  );
}
