"use client";

import { useForm, useFieldArray, Controller, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import type { AgencyProfile } from "@/lib/types";
import { SettingsBlock } from "./settings-block";

const optionalUrl = z
  .string()
  .trim()
  .max(1000)
  .refine((v) => !v || /^https?:\/\/\S+$/i.test(v), "Use a full URL starting with http:// or https://");

export const agencySchema = z.object({
  agency_name: z.string().trim().max(200),
  website: optionalUrl,
  description: z.string().max(4000),
  services: z
    .array(
      z.object({
        key: z.string(),
        name: z.string().trim().min(1, "Give the service a name").max(200),
        description: z.string().max(4000),
        enabled: z.boolean(),
      }),
    )
    .refine((s) => s.some((x) => x.enabled), "Enable at least one service"),
  target_industries: z.array(z.string()),
  target_geographies: z.array(z.string()),
  ideal_client_profile: z.string().max(4000),
  typical_budgets: z.string().max(1000),
  case_studies: z.array(
    z.object({
      title: z.string().trim().min(1, "Add a title").max(300),
      summary: z.string().max(4000),
      url: optionalUrl,
      service: z.string(),
    }),
  ),
  portfolio_links: z.array(z.string()),
  testimonials: z.array(
    z.object({
      quote: z.string().trim().min(1, "Add the quote").max(2000),
      author: z.string().max(200),
      company: z.string().max(200),
      approved: z.boolean(),
    }),
  ),
  tone: z.string().max(2000),
  sender_name: z.string().max(200),
  sender_title: z.string().max(200),
  signature: z.string().max(2000),
  call_to_action: z.string().max(500),
  include_opt_out_line: z.boolean(),
  opt_out_line: z.string().max(500),
  postal_address: z.string().max(1000),
});

export type AgencyValues = z.infer<typeof agencySchema>;

export type AgencySectionKey = "basics" | "services" | "targeting" | "proof" | "voice" | "sender";

export const ALL_SECTIONS: AgencySectionKey[] = ["basics", "services", "targeting", "proof", "voice", "sender"];

export function toValues(p: Partial<AgencyProfile> | undefined): AgencyValues {
  return {
    agency_name: p?.agency_name ?? "",
    website: p?.website ?? "",
    description: p?.description ?? "",
    services: (p?.services ?? []).map((s) => ({
      key: s.key,
      name: s.name ?? "",
      description: s.description ?? "",
      enabled: s.enabled ?? true,
    })),
    target_industries: p?.target_industries ?? [],
    target_geographies: p?.target_geographies ?? [],
    ideal_client_profile: p?.ideal_client_profile ?? "",
    typical_budgets: p?.typical_budgets ?? "",
    case_studies: (p?.case_studies ?? []).map((c) => ({
      title: c.title ?? "",
      summary: c.summary ?? "",
      url: c.url ?? "",
      service: c.service ?? "",
    })),
    portfolio_links: p?.portfolio_links ?? [],
    testimonials: (p?.testimonials ?? []).map((t) => ({
      quote: t.quote ?? "",
      author: t.author ?? "",
      company: t.company ?? "",
      approved: !!t.approved,
    })),
    tone: p?.tone ?? "",
    sender_name: p?.sender_name ?? "",
    sender_title: p?.sender_title ?? "",
    signature: p?.signature ?? "",
    call_to_action: p?.call_to_action ?? "",
    include_opt_out_line: p?.include_opt_out_line ?? true,
    opt_out_line: p?.opt_out_line ?? "",
    postal_address: p?.postal_address ?? "",
  };
}

const NONE = "__none__";

function ServiceSelect({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>Any service</SelectItem>
        <SelectItem value="website">Website</SelectItem>
        <SelectItem value="company_brain">Company Brain</SelectItem>
      </SelectContent>
    </Select>
  );
}

function Sections({ form, sections, disabled }: { form: UseFormReturn<AgencyValues>; sections: AgencySectionKey[]; disabled?: boolean }) {
  const { register, control, watch, formState } = form;
  const errors = formState.errors;
  const services = useFieldArray({ control, name: "services" });
  const cases = useFieldArray({ control, name: "case_studies" });
  const testimonials = useFieldArray({ control, name: "testimonials" });
  const has = (s: AgencySectionKey) => sections.includes(s);

  return (
    <fieldset disabled={disabled} className="min-w-0">
      {has("basics") && (
        <SettingsBlock title="Agency" description="How the agency is introduced in research briefs and outreach.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Agency name" htmlFor="agency_name" error={errors.agency_name?.message}>
              <Input id="agency_name" {...register("agency_name")} />
            </Field>
            <Field label="Website" htmlFor="website" error={errors.website?.message}>
              <Input id="website" placeholder="https://" {...register("website")} />
            </Field>
          </div>
          <Field label="What the agency does" htmlFor="description" hint="Two or three sentences. Used as context for every AI agent.">
            <Textarea id="description" rows={4} {...register("description")} />
          </Field>
        </SettingsBlock>
      )}

      {has("services") && (
        <SettingsBlock
          title="Services"
          description="The two services are scored independently. Disable one to stop recommending it."
        >
          {errors.services?.root?.message && <p className="text-sm text-destructive">{errors.services.root.message}</p>}
          {services.fields.map((f, i) => (
            <div key={f.id} className="space-y-3 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-3">
                <code className="font-mono text-xs text-muted-foreground">{f.key}</code>
                <Controller
                  control={control}
                  name={`services.${i}.enabled`}
                  render={({ field }) => (
                    <label className="flex items-center gap-2 text-sm">
                      <Switch checked={field.value} onCheckedChange={field.onChange} disabled={disabled} />
                      {field.value ? "Offered" : "Not offered"}
                    </label>
                  )}
                />
              </div>
              <Field label="Name" htmlFor={`svc-name-${i}`} error={errors.services?.[i]?.name?.message}>
                <Input id={`svc-name-${i}`} {...register(`services.${i}.name`)} />
              </Field>
              <Field label="Description" htmlFor={`svc-desc-${i}`} hint="What you deliver, for whom, and the outcome.">
                <Textarea id={`svc-desc-${i}`} rows={3} {...register(`services.${i}.description`)} />
              </Field>
            </div>
          ))}
        </SettingsBlock>
      )}

      {has("targeting") && (
        <SettingsBlock title="Targeting" description="Who you want to work with. Campaigns can narrow this further.">
          <Field label="Target industries" htmlFor="industries">
            <Controller
              control={control}
              name="target_industries"
              render={({ field }) => <TagInput id="industries" value={field.value} onChange={field.onChange} placeholder="e.g. SaaS, Professional services" disabled={disabled} />}
            />
          </Field>
          <Field label="Target geographies" htmlFor="geos">
            <Controller
              control={control}
              name="target_geographies"
              render={({ field }) => <TagInput id="geos" value={field.value} onChange={field.onChange} placeholder="e.g. United Kingdom, DACH" disabled={disabled} />}
            />
          </Field>
          <Field label="Ideal client profile" htmlFor="icp" hint="Size, stage, signals that make a company a good fit.">
            <Textarea id="icp" rows={4} {...register("ideal_client_profile")} />
          </Field>
          <Field label="Typical budgets" htmlFor="budgets">
            <Input id="budgets" placeholder="e.g. £25k–£80k per website project" {...register("typical_budgets")} />
          </Field>
        </SettingsBlock>
      )}

      {has("proof") && (
        <SettingsBlock
          title="Proof"
          description="Case studies, portfolio and testimonials the writer may reference. Only approved testimonials are quoted."
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">Case studies</h3>
              <Button type="button" variant="outline" size="sm" onClick={() => cases.append({ title: "", summary: "", url: "", service: "" })}>
                <Plus /> Add case study
              </Button>
            </div>
            {cases.fields.length === 0 && <p className="text-sm text-muted-foreground">No case studies yet.</p>}
            {cases.fields.map((f, i) => (
              <div key={f.id} className="space-y-3 rounded-lg border p-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
                  <Field label="Title" htmlFor={`cs-title-${i}`} error={errors.case_studies?.[i]?.title?.message}>
                    <Input id={`cs-title-${i}`} {...register(`case_studies.${i}.title`)} />
                  </Field>
                  <Field label="Service" htmlFor={`cs-svc-${i}`}>
                    <Controller
                      control={control}
                      name={`case_studies.${i}.service`}
                      render={({ field }) => <ServiceSelect id={`cs-svc-${i}`} value={field.value} onChange={field.onChange} />}
                    />
                  </Field>
                </div>
                <Field label="Summary" htmlFor={`cs-sum-${i}`}>
                  <Textarea id={`cs-sum-${i}`} rows={3} {...register(`case_studies.${i}.summary`)} />
                </Field>
                <div className="flex items-end gap-2">
                  <Field label="Link" htmlFor={`cs-url-${i}`} className="flex-1" error={errors.case_studies?.[i]?.url?.message}>
                    <Input id={`cs-url-${i}`} placeholder="https://" {...register(`case_studies.${i}.url`)} />
                  </Field>
                  <Button type="button" variant="ghost" size="icon" onClick={() => cases.remove(i)} aria-label="Remove case study">
                    <Trash2 />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <Field label="Portfolio links" htmlFor="portfolio">
            <Controller
              control={control}
              name="portfolio_links"
              render={({ field }) => <TagInput id="portfolio" value={field.value} onChange={field.onChange} placeholder="Paste a URL and press Enter" disabled={disabled} />}
            />
          </Field>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">Testimonials</h3>
              <Button type="button" variant="outline" size="sm" onClick={() => testimonials.append({ quote: "", author: "", company: "", approved: false })}>
                <Plus /> Add testimonial
              </Button>
            </div>
            {testimonials.fields.length === 0 && <p className="text-sm text-muted-foreground">No testimonials yet.</p>}
            {testimonials.fields.map((f, i) => (
              <div key={f.id} className="space-y-3 rounded-lg border p-4">
                <Field label="Quote" htmlFor={`t-q-${i}`} error={errors.testimonials?.[i]?.quote?.message}>
                  <Textarea id={`t-q-${i}`} rows={2} {...register(`testimonials.${i}.quote`)} />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Author" htmlFor={`t-a-${i}`}>
                    <Input id={`t-a-${i}`} {...register(`testimonials.${i}.author`)} />
                  </Field>
                  <Field label="Company" htmlFor={`t-c-${i}`}>
                    <Input id={`t-c-${i}`} {...register(`testimonials.${i}.company`)} />
                  </Field>
                </div>
                <div className="flex items-center justify-between">
                  <Controller
                    control={control}
                    name={`testimonials.${i}.approved`}
                    render={({ field }) => (
                      <label className="flex items-center gap-2 text-sm">
                        <Checkbox checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} disabled={disabled} />
                        Client approved this for use in outreach
                      </label>
                    )}
                  />
                  <Button type="button" variant="ghost" size="icon" onClick={() => testimonials.remove(i)} aria-label="Remove testimonial">
                    <Trash2 />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </SettingsBlock>
      )}

      {has("voice") && (
        <SettingsBlock title="Voice" description="How drafts should sound and what they ask for.">
          <Field label="Tone" htmlFor="tone">
            <Textarea id="tone" rows={3} {...register("tone")} />
          </Field>
          <Field label="Call to action" htmlFor="cta" hint="The single ask every email ends with.">
            <Input id="cta" {...register("call_to_action")} />
          </Field>
          <Controller
            control={control}
            name="include_opt_out_line"
            render={({ field }) => (
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={field.value} onCheckedChange={field.onChange} disabled={disabled} />
                Include an opt-out line in every email
              </label>
            )}
          />
          {watch("include_opt_out_line") && (
            <Field label="Opt-out line" htmlFor="optout">
              <Input id="optout" {...register("opt_out_line")} />
            </Field>
          )}
        </SettingsBlock>
      )}

      {has("sender") && (
        <SettingsBlock title="Sender" description="Who the drafts are from. You still send every email yourself.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sender name" htmlFor="sender_name">
              <Input id="sender_name" {...register("sender_name")} />
            </Field>
            <Field label="Sender title" htmlFor="sender_title">
              <Input id="sender_title" {...register("sender_title")} />
            </Field>
          </div>
          <Field label="Signature" htmlFor="signature">
            <Textarea id="signature" rows={4} {...register("signature")} />
          </Field>
          <Field
            label="Postal address"
            htmlFor="postal_address"
            hint="Required in commercial email in some jurisdictions (for example CAN-SPAM)."
          >
            <Textarea id="postal_address" rows={2} {...register("postal_address")} />
          </Field>
        </SettingsBlock>
      )}
    </fieldset>
  );
}

/**
 * Agency profile form. Renders all sections (settings page) or a subset (wizard steps).
 * onSubmit receives the full value set; the caller PUTs it to /settings/agency_profile.
 */
export function AgencyProfileForm({
  profile,
  sections = ALL_SECTIONS,
  onSubmit,
  submitLabel = "Save changes",
  disabled,
  secondaryAction,
}: {
  profile: Partial<AgencyProfile> | undefined;
  sections?: AgencySectionKey[];
  onSubmit: (values: AgencyValues) => Promise<unknown>;
  submitLabel?: string;
  disabled?: boolean;
  secondaryAction?: React.ReactNode;
}) {
  const form = useForm<AgencyValues>({ resolver: zodResolver(agencySchema), defaultValues: toValues(profile) });
  const submitting = form.formState.isSubmitting;
  return (
    <form
      onSubmit={form.handleSubmit(async (v) => {
        try {
          await onSubmit(v);
          form.reset(v);
        } catch {
          /* toast already shown */
        }
      })}
      noValidate
    >
      <Sections form={form} sections={sections} disabled={disabled} />
      <div className="sticky bottom-0 z-10 -mx-1 mt-2 flex flex-wrap items-center justify-end gap-2 border-t bg-background/90 px-1 py-3 backdrop-blur">
        {form.formState.isDirty && !disabled && <span className="mr-auto text-xs text-muted-foreground">Unsaved changes</span>}
        {secondaryAction}
        <Button type="submit" disabled={disabled || submitting}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
