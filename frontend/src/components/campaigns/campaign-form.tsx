"use client";

import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { Campaign } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useCampaignTemplates, useProviders } from "./queries";

const schema = z.object({
  name: z.string().trim().min(1, "Give the campaign a name").max(200),
  description: z.string().max(4000),
  is_active: z.boolean(),
  target_service: z.enum(["any", "website", "company_brain"]),
  industries: z.array(z.string()).max(50),
  geographies: z.array(z.string()).max(50),
  company_sizes: z.array(z.string()),
  target_roles: z.array(z.string()).max(50),
  keywords: z.array(z.string()).max(50),
  query_templates: z.array(z.string()).max(50),
  signal_focus: z.array(z.string()),
  sources: z.array(z.string()),
  rss_feeds: z.array(z.string().url("Each feed must be a full URL (https://…)")).max(50),
  daily_company_limit: z.coerce.number().int().min(1).max(1000),
  daily_query_limit: z.coerce.number().int().min(1).max(500),
  auto_research: z.boolean(),
});
export type CampaignValues = z.infer<typeof schema>;

const EMPTY: CampaignValues = {
  name: "",
  description: "",
  is_active: true,
  target_service: "any",
  industries: [],
  geographies: [],
  company_sizes: [],
  target_roles: [],
  keywords: [],
  query_templates: [],
  signal_focus: [],
  sources: [],
  rss_feeds: [],
  daily_company_limit: 25,
  daily_query_limit: 20,
  auto_research: true,
};

function toValues(c?: Campaign | null): CampaignValues {
  if (!c) return EMPTY;
  const { name, description, is_active, target_service, industries, geographies, company_sizes, target_roles, keywords,
    query_templates, signal_focus, sources, rss_feeds, daily_company_limit, daily_query_limit, auto_research } = c;
  return { name, description, is_active, target_service, industries, geographies, company_sizes, target_roles, keywords,
    query_templates, signal_focus, sources, rss_feeds, daily_company_limit, daily_query_limit, auto_research };
}

export function ChipToggle({ options, value, onChange, labels }: { options: string[]; value: string[]; onChange: (v: string[]) => void; labels?: Record<string, string> }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button
            key={o}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}
            className={cn(
              "h-7 rounded-md border px-2.5 text-xs transition-colors",
              on ? "border-foreground bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {labels?.[o] ?? o}
          </button>
        );
      })}
    </div>
  );
}

export function CampaignFormDialog({
  open,
  onOpenChange,
  campaign,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  campaign?: Campaign | null;
  onSaved?: (c: Campaign) => void;
}) {
  const templates = useCampaignTemplates();
  const providers = useProviders();
  const form = useForm<CampaignValues>({ resolver: zodResolver(schema), defaultValues: toValues(campaign) });
  useEffect(() => {
    if (open) form.reset(toValues(campaign));
  }, [open, campaign, form]);

  const save = useApiMutation(
    (v: CampaignValues) => (campaign ? api.patch<Campaign>(`/campaigns/${campaign.id}`, v) : api.post<Campaign>("/campaigns", v)),
    {
      success: campaign ? "Campaign saved" : "Campaign created",
      invalidate: [["campaigns"]],
      onSuccess: (c) => {
        onOpenChange(false);
        onSaved?.(c);
      },
    },
  );

  const errors = form.formState.errors;
  const providerOpts = (providers.data?.providers ?? []).map((p) => p.key);
  const providerLabels = Object.fromEntries((providers.data?.providers ?? []).map((p) => [p.key, `${p.label}${["available", "connected"].includes(p.status) ? "" : " (not configured)"}`]));
  const signalKeys = Object.keys(templates.data?.signal_templates ?? {});

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{campaign ? "Edit campaign" : "New campaign"}</DialogTitle>
          <DialogDescription>
            A campaign defines who to look for and where. Discovery runs on its schedule or when you run it now.
          </DialogDescription>
        </DialogHeader>
        <form id="campaign-form" onSubmit={form.handleSubmit((v) => save.mutateAsync(v).catch(() => undefined))} className="space-y-6" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="c-name" error={errors.name?.message} required className="sm:col-span-2">
              <Input id="c-name" {...form.register("name")} aria-invalid={!!errors.name} />
            </Field>
            <Field label="Description" htmlFor="c-desc" className="sm:col-span-2">
              <Textarea id="c-desc" rows={2} {...form.register("description")} />
            </Field>
            <Field label="Target service" hint="Limit qualification to one service, or score both.">
              <Controller
                control={form.control}
                name="target_service"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="any">Any service</SelectItem>
                      <SelectItem value="website">Website</SelectItem>
                      <SelectItem value="company_brain">Company Brain</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>
            <div className="flex flex-col justify-end gap-3 pb-1">
              <Controller control={form.control} name="is_active" render={({ field }) => (
                <label className="flex items-center gap-2 text-sm"><Switch checked={field.value} onCheckedChange={field.onChange} /> Active (runs on schedule)</label>
              )} />
              <Controller control={form.control} name="auto_research" render={({ field }) => (
                <label className="flex items-center gap-2 text-sm"><Switch checked={field.value} onCheckedChange={field.onChange} /> Research new companies automatically</label>
              )} />
            </div>
          </div>

          <fieldset className="space-y-4">
            <legend className="mb-2 text-sm font-semibold">Who to find</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Industries"><Controller control={form.control} name="industries" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="e.g. B2B SaaS" />} /></Field>
              <Field label="Geographies"><Controller control={form.control} name="geographies" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="e.g. United Kingdom" />} /></Field>
              <Field label="Target roles" hint="Decision-makers to look for."><Controller control={form.control} name="target_roles" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="e.g. Head of Marketing" />} /></Field>
              <Field label="Keywords"><Controller control={form.control} name="keywords" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="e.g. fintech" />} /></Field>
            </div>
            <Field label="Company sizes" hint="Employees. Leave empty for any size.">
              <Controller control={form.control} name="company_sizes" render={({ field }) => (
                <ChipToggle options={templates.data?.sizes ?? []} value={field.value} onChange={field.onChange} />
              )} />
            </Field>
          </fieldset>

          <fieldset className="space-y-4">
            <legend className="mb-2 text-sm font-semibold">Where to look</legend>
            <Field label="Sources" hint="Leave empty to use every configured source." error={errors.sources?.message}>
              <Controller control={form.control} name="sources" render={({ field }) => (
                <ChipToggle options={providerOpts} value={field.value} onChange={field.onChange} labels={providerLabels} />
              )} />
            </Field>
            <Field label="Signal focus" hint="Buying signals that shape web-search queries.">
              <Controller control={form.control} name="signal_focus" render={({ field }) => (
                <ChipToggle options={signalKeys} value={field.value} onChange={field.onChange} labels={Object.fromEntries(signalKeys.map((k) => [k, humanize(k)]))} />
              )} />
            </Field>
            <Field label="Custom query templates" hint="Placeholders: {industry}, {geo}, {year}. Used by web-search providers.">
              <Controller control={form.control} name="query_templates" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="{industry} company rebrand {year} {geo}" />} />
            </Field>
            <Field label="RSS feeds" error={errors.rss_feeds?.message ?? (Array.isArray(errors.rss_feeds) ? errors.rss_feeds.find(Boolean)?.message : undefined)}>
              <Controller control={form.control} name="rss_feeds" render={({ field }) => <TagInput value={field.value} onChange={field.onChange} placeholder="https://example.com/feed.xml" />} />
            </Field>
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New companies per day" htmlFor="c-dcl" error={errors.daily_company_limit?.message}>
              <Input id="c-dcl" type="number" min={1} max={1000} {...form.register("daily_company_limit")} />
            </Field>
            <Field label="Search queries per day" htmlFor="c-dql" error={errors.daily_query_limit?.message}>
              <Input id="c-dql" type="number" min={1} max={500} {...form.register("daily_query_limit")} />
            </Field>
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="campaign-form" disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {campaign ? "Save campaign" : "Create campaign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
