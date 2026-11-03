"use client";

import { useState } from "react";
import { CheckCircle2, Loader2, Plus, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field } from "@/components/shared/field";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import type { LLMSettings } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SecretInput } from "./secret-input";
import { useSaveSettings } from "./use-settings";

type PriceRow = { model: string; input: string; output: string; cache_read: string };

const PROVIDER_HELP: Record<string, string> = {
  none: "No AI. The app runs in limited mode: deterministic research checks, heuristic scoring, rule-based reply labels. Drafts can't be generated.",
  openai_compatible: "OpenAI or any OpenAI-compatible endpoint (Azure, OpenRouter, vLLM, Ollama…).",
  anthropic: "Claude models via the Anthropic API.",
};

/** Test connection: POST /ai/test. Uses the *saved* settings. */
export function TestConnection({ disabled }: { disabled?: boolean }) {
  const [result, setResult] = useState<{ ok: boolean; model?: string; message: string } | null>(null);
  const test = useApiMutation(() => api.post<{ ok: boolean; model?: string; message: string }>("/ai/test"), {
    onSuccess: (r) => setResult(r),
    invalidate: [["ai"]],
  });
  return (
    <div className="space-y-2">
      <Button type="button" variant="outline" onClick={() => test.mutate()} disabled={disabled || test.isPending}>
        {test.isPending && <Loader2 className="animate-spin" />}
        Test connection
      </Button>
      {result && (
        <p className={cn("tone flex items-start gap-2 rounded-lg border px-3 py-2 text-sm", result.ok ? "tone-success" : "tone-danger")} role="status">
          {result.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
          <span className="text-foreground">
            {result.ok ? `Connected${result.model ? ` to ${result.model}` : ""}. Reply: “${result.message}”` : result.message}
          </span>
        </p>
      )}
      <p className="text-xs text-muted-foreground">Tests the saved settings. Save first if you changed anything.</p>
    </div>
  );
}

export function LLMForm({
  settings,
  disabled,
  compact,
  onSaved,
  submitLabel = "Save AI provider",
}: {
  settings: LLMSettings;
  disabled?: boolean;
  compact?: boolean;
  onSaved?: () => void;
  submitLabel?: string;
}) {
  const [v, setV] = useState({
    provider: settings.provider,
    base_url: settings.base_url ?? "",
    api_key: "",
    model_fast: settings.model_fast ?? "",
    model_smart: settings.model_smart ?? "",
    temperature: String(settings.temperature ?? 0.3),
    effort_fast: settings.effort_fast ?? "low",
    effort_smart: settings.effort_smart ?? "medium",
    max_output_tokens: String(settings.max_output_tokens ?? 1800),
    daily_budget_usd: String(settings.daily_budget_usd ?? 5),
    max_calls_per_company: String(settings.max_calls_per_company ?? 12),
    max_retries: String(settings.max_retries ?? 2),
    timeout_seconds: String(settings.timeout_seconds ?? 90),
    json_mode: settings.json_mode ?? true,
  });
  const [pricing, setPricing] = useState<PriceRow[]>(
    Object.entries(settings.pricing ?? {}).map(([model, p]) => ({
      model,
      input: String(p.input ?? ""),
      output: String(p.output ?? ""),
      cache_read: p.cache_read !== undefined ? String(p.cache_read) : "",
    })),
  );
  const save = useSaveSettings<LLMSettings>("llm", "AI provider saved");
  const set = <K extends keyof typeof v>(k: K, val: (typeof v)[K]) => setV((s) => ({ ...s, [k]: val }));
  const isAnthropic = v.provider === "anthropic";
  const off = v.provider === "none";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const patch: Record<string, unknown> = {
      provider: v.provider,
      api_key: v.api_key,
      model_fast: v.model_fast.trim(),
      model_smart: v.model_smart.trim(),
    };
    if (v.provider === "openai_compatible") patch.base_url = v.base_url.trim();
    if (!compact) {
      const priceObj: LLMSettings["pricing"] = {};
      for (const r of pricing) {
        if (!r.model.trim()) continue;
        priceObj[r.model.trim()] = {
          input: Number(r.input) || 0,
          output: Number(r.output) || 0,
          ...(r.cache_read !== "" ? { cache_read: Number(r.cache_read) || 0 } : {}),
        };
      }
      Object.assign(patch, {
        temperature: Number(v.temperature),
        effort_fast: v.effort_fast,
        effort_smart: v.effort_smart,
        max_output_tokens: Number(v.max_output_tokens),
        daily_budget_usd: Number(v.daily_budget_usd),
        max_calls_per_company: Number(v.max_calls_per_company),
        max_retries: Number(v.max_retries),
        timeout_seconds: Number(v.timeout_seconds),
        json_mode: v.json_mode,
        pricing: priceObj,
      });
    } else {
      patch.daily_budget_usd = Number(v.daily_budget_usd);
    }
    try {
      await save.mutateAsync(patch);
      set("api_key", "");
      onSaved?.();
    } catch {
      /* toast shown */
    }
  }

  const effortSelect = (k: "effort_fast" | "effort_smart", id: string) => (
    <Select value={v[k]} onValueChange={(x) => set(k, x)} disabled={disabled}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {["low", "medium", "high"].map((x) => (
          <SelectItem key={x} value={x}>
            {x[0].toUpperCase() + x.slice(1)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <form onSubmit={submit} className="space-y-5">
      <fieldset disabled={disabled} className="space-y-5">
        <Field label="Provider" htmlFor="llm-provider" hint={PROVIDER_HELP[v.provider]}>
          <Select value={v.provider} onValueChange={(x) => set("provider", x as LLMSettings["provider"])} disabled={disabled}>
            <SelectTrigger id="llm-provider" className="w-full sm:w-80">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None (limited mode)</SelectItem>
              <SelectItem value="openai_compatible">OpenAI-compatible</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {v.provider === "openai_compatible" && (
          <Field label="Base URL" htmlFor="llm-base">
            <Input id="llm-base" value={v.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder="https://api.openai.com/v1" />
          </Field>
        )}
        {!off && (
          <>
            <Field label="API key" htmlFor="llm-key">
              <SecretInput
                id="llm-key"
                value={v.api_key}
                onChange={(x) => set("api_key", x)}
                isSet={settings.api_key_is_set}
                masked={settings.api_key_masked}
                disabled={disabled}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Fast model" htmlFor="m-fast" hint="Extraction and classification.">
                <Input id="m-fast" value={v.model_fast} onChange={(e) => set("model_fast", e.target.value)} />
              </Field>
              <Field label="Smart model" htmlFor="m-smart" hint="Research analysis, scoring and writing.">
                <Input id="m-smart" value={v.model_smart} onChange={(e) => set("model_smart", e.target.value)} />
              </Field>
            </div>
          </>
        )}
        <Field label="Daily budget (USD)" htmlFor="budget" hint="AI calls stop for the day once spend reaches this.">
          <Input id="budget" type="number" step="0.5" min={0} max={10000} value={v.daily_budget_usd} onChange={(e) => set("daily_budget_usd", e.target.value)} className="w-40 tabular-nums" />
        </Field>

        {!compact && !off && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Temperature" htmlFor="temp" hint={isAnthropic ? "Ignored for Anthropic models." : "0–2"}>
                <Input id="temp" type="number" step="0.1" min={0} max={2} value={v.temperature} onChange={(e) => set("temperature", e.target.value)} disabled={disabled || isAnthropic} className="tabular-nums" />
              </Field>
              <Field label="Max output tokens" htmlFor="mot">
                <Input id="mot" type="number" min={100} max={32000} value={v.max_output_tokens} onChange={(e) => set("max_output_tokens", e.target.value)} className="tabular-nums" />
              </Field>
              <Field label="Max calls per company" htmlFor="mcpc">
                <Input id="mcpc" type="number" min={1} max={200} value={v.max_calls_per_company} onChange={(e) => set("max_calls_per_company", e.target.value)} className="tabular-nums" />
              </Field>
              <Field label="Max retries" htmlFor="mr">
                <Input id="mr" type="number" min={0} max={10} value={v.max_retries} onChange={(e) => set("max_retries", e.target.value)} className="tabular-nums" />
              </Field>
              <Field label="Timeout (seconds)" htmlFor="to">
                <Input id="to" type="number" min={5} max={600} value={v.timeout_seconds} onChange={(e) => set("timeout_seconds", e.target.value)} className="tabular-nums" />
              </Field>
            </div>
            {isAnthropic && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Effort, fast tier" htmlFor="ef">{effortSelect("effort_fast", "ef")}</Field>
                <Field label="Effort, smart tier" htmlFor="es">{effortSelect("effort_smart", "es")}</Field>
              </div>
            )}
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={v.json_mode} onCheckedChange={(x) => set("json_mode", x)} disabled={disabled} />
              Request JSON mode (structured output)
            </label>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium">Pricing</h3>
                  <p className="text-xs text-muted-foreground">USD per 1M tokens, used for cost tracking.</p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => setPricing((p) => [...p, { model: "", input: "", output: "", cache_read: "" }])}>
                  <Plus /> Add model
                </Button>
              </div>
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Model</TableHead>
                      <TableHead className="w-28">Input</TableHead>
                      <TableHead className="w-28">Output</TableHead>
                      <TableHead className="w-28">Cache read</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pricing.map((r, i) => {
                      const upd = (k: keyof PriceRow, val: string) => setPricing((p) => p.map((x, j) => (j === i ? { ...x, [k]: val } : x)));
                      return (
                        <TableRow key={i}>
                          <TableCell className="py-1.5">
                            <Input value={r.model} onChange={(e) => upd("model", e.target.value)} aria-label="Model" className="h-7 min-w-40 font-mono text-xs" />
                          </TableCell>
                          {(["input", "output", "cache_read"] as const).map((k) => (
                            <TableCell key={k} className="py-1.5">
                              <Input type="number" step="0.01" min={0} value={r[k]} onChange={(e) => upd(k, e.target.value)} aria-label={k} className="h-7 tabular-nums" />
                            </TableCell>
                          ))}
                          <TableCell className="py-1.5">
                            <Button type="button" variant="ghost" size="icon-sm" onClick={() => setPricing((p) => p.filter((_, j) => j !== i))} aria-label="Remove model">
                              <Trash2 />
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
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
