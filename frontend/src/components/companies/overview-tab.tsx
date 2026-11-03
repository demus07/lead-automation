"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Section, DetailList } from "@/components/shared/section";
import { DualScore, ServiceBadge } from "@/components/shared/score";
import { StatusBadge } from "@/components/shared/status-badge";
import { ExternalLink } from "@/components/shared/external-link";
import { FilterSelect } from "@/components/shared/filter-select";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import { Notice } from "@/components/shared/notice";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { fmtDateTime, fmtRelative, humanize } from "@/lib/format";
import { LEAD_STATUS_META } from "@/lib/status";
import type { Campaign, Company, LeadStatus } from "@/lib/types";
import { COMPANY_SIZES } from "./constants";
import type { CompanyDetail } from "./types";

export function OverviewTab({ d, canEdit, campaigns }: { d: CompanyDetail; canEdit: boolean; campaigns: Campaign[] }) {
  const c = d.company;
  const brief = d.data?.brief;
  const [editing, setEditing] = useState(false);
  const campaign = campaigns.find((x) => x.id === c.campaign_id);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-6">
        <Section
          title="Brief"
          description={brief?.method === "llm" ? "Written by the orchestrator agent; next action checked against the state machine." : "Deterministic next step from the lead's status and data."}
        >
          {brief ? (
            <div className="space-y-4 text-sm">
              {brief.next_action && (
                <div className="flex items-start gap-3 rounded-lg bg-muted/60 px-4 py-3">
                  <ArrowRight className="mt-0.5 size-4 shrink-0 text-brand" />
                  <div>
                    <p className="font-medium">{humanize(brief.next_action)}</p>
                    {brief.reason && <p className="text-muted-foreground">{brief.reason}</p>}
                  </div>
                </div>
              )}
              {brief.lead_summary && <p className="max-w-[72ch] text-pretty leading-relaxed">{brief.lead_summary}</p>}
              {!!brief.open_questions?.length && (
                <div>
                  <p className="mb-1.5 font-medium">Open questions</p>
                  <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                    {brief.open_questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
              {brief.at && <p className="text-xs text-muted-foreground">Updated {fmtRelative(brief.at)}</p>}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No brief yet. One is written after research and scoring run for this company.
            </p>
          )}
        </Section>

        <Section
          title="Company"
          actions={
            canEdit && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )
          }
        >
          {c.description && <p className="mb-4 max-w-[72ch] text-sm text-pretty text-muted-foreground">{c.description}</p>}
          <DetailList
            items={[
              { label: "Website", value: c.website ? <ExternalLink href={c.website} /> : null },
              { label: "Industry", value: c.industry },
              { label: "Location", value: [c.location, c.country].filter(Boolean).join(", ") || null },
              { label: "Size", value: c.size_range ? `${c.size_range} people` : null },
              { label: "Campaign", value: campaign?.name ?? null },
              {
                label: "Tags",
                value: c.tags.length ? (
                  <div className="flex flex-wrap gap-1">
                    {c.tags.map((t) => (
                      <span key={t} className="rounded bg-secondary px-1.5 text-xs">{t}</span>
                    ))}
                  </div>
                ) : null,
              },
              { label: "Public emails", value: d.data?.public_emails?.length ? d.data.public_emails.join(", ") : null },
              { label: "Added", value: fmtDateTime(c.created_at) },
              { label: "Last researched", value: c.last_researched_at ? fmtDateTime(c.last_researched_at) : "Not yet" },
              { label: "Last scored", value: c.last_scored_at ? fmtDateTime(c.last_scored_at) : "Not yet" },
            ]}
          />
        </Section>
      </div>

      <div className="space-y-6">
        <StatusPanel d={d} canEdit={canEdit} />
        <Section title="Opportunity">
          <DualScore website={c.website_score} brain={c.brain_score} recommended={c.recommended_service} />
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Recommended</span>
            <ServiceBadge service={c.recommended_service} />
          </div>
          {d.opportunity?.recommendation_reason && (
            <p className="mt-3 text-sm text-pretty text-muted-foreground">{d.opportunity.recommendation_reason}</p>
          )}
        </Section>
      </div>

      <EditCompanyDialog open={editing} onOpenChange={setEditing} company={c} campaigns={campaigns} />
    </div>
  );
}

function StatusPanel({ d, canEdit }: { d: CompanyDetail; canEdit: boolean }) {
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const change = useApiMutation(
    (v: { status: string; reason: string }) => api.post<Company>(`/companies/${d.company.id}/status`, { status: v.status, reason: v.reason || null }),
    {
      success: (_r, v) => `Status changed to ${LEAD_STATUS_META[v.status as LeadStatus]?.label ?? v.status}`,
      invalidate: [["company", d.company.id], ["companies"]],
      onSuccess: () => {
        setTarget("");
        setReason("");
      },
    },
  );
  // DNC has its own confirmed action in the header.
  const options = d.allowed_transitions.filter((s) => s !== "DO_NOT_CONTACT");
  return (
    <Section title="Status">
      <div className="mb-4 flex items-center gap-2">
        <StatusBadge kind="lead" value={d.company.status} />
        {d.disqualified_reason && <span className="text-xs text-muted-foreground">{d.disqualified_reason}</span>}
      </div>
      {canEdit && options.length > 0 ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (target) change.mutate({ status: target, reason });
          }}
        >
          <Field label="Move to">
            <FilterSelect
              value={target}
              onChange={setTarget}
              allLabel="Choose a status"
              className="w-full"
              options={options.map((s) => ({ value: s, label: LEAD_STATUS_META[s]?.label ?? s }))}
            />
          </Field>
          {target && (
            <Field label="Reason" htmlFor="status-reason" hint={target === "DISQUALIFIED" ? "Saved as the disqualification reason" : "Optional, kept in the audit log"}>
              <Input id="status-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          )}
          <Button type="submit" size="sm" disabled={!target || change.isPending}>
            {change.isPending && <Loader2 className="animate-spin" />}
            Change status
          </Button>
        </form>
      ) : (
        <p className="text-sm text-muted-foreground">
          {d.company.status === "DO_NOT_CONTACT" ? "This company is suppressed. It can't move to another status." : canEdit ? "No manual transitions from this status." : "Viewers can't change status."}
        </p>
      )}
    </Section>
  );
}

function EditCompanyDialog({
  open,
  onOpenChange,
  company,
  campaigns,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  company: Company;
  campaigns: Campaign[];
}) {
  const [v, setV] = useState({ name: "", industry: "", location: "", country: "", size_range: "", description: "", campaign_id: "" });
  const [tags, setTags] = useState<string[]>([]);
  useEffect(() => {
    if (!open) return;
    setV({
      name: company.name,
      industry: company.industry ?? "",
      location: company.location ?? "",
      country: company.country ?? "",
      size_range: company.size_range ?? "",
      description: company.description ?? "",
      campaign_id: company.campaign_id ?? "",
    });
    setTags(company.tags);
  }, [open, company]);
  const save = useApiMutation(
    () =>
      api.patch<Company>(`/companies/${company.id}`, {
        name: v.name.trim(),
        industry: v.industry || null,
        location: v.location || null,
        country: v.country || null,
        size_range: v.size_range || null,
        description: v.description || null,
        campaign_id: v.campaign_id || null,
        tags,
      }),
    { success: "Company saved", invalidate: [["company", company.id], ["companies"]], onSuccess: () => onOpenChange(false) },
  );
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setV((s) => ({ ...s, [k]: e.target.value }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit company</DialogTitle>
          <DialogDescription>The domain can&apos;t be changed — it&apos;s how duplicates are detected.</DialogDescription>
        </DialogHeader>
        <form
          id="edit-company"
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (v.name.trim()) save.mutate();
          }}
        >
          <Field label="Name" htmlFor="e-name" required error={!v.name.trim() ? "Enter a name" : null}>
            <Input id="e-name" value={v.name} onChange={set("name")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Industry" htmlFor="e-ind"><Input id="e-ind" value={v.industry} onChange={set("industry")} /></Field>
            <Field label="Size">
              <FilterSelect value={v.size_range} onChange={(x) => setV((s) => ({ ...s, size_range: x }))} allLabel="Unknown" className="w-full" options={COMPANY_SIZES.map((s) => ({ value: s, label: `${s} people` }))} />
            </Field>
            <Field label="Location" htmlFor="e-loc"><Input id="e-loc" value={v.location} onChange={set("location")} /></Field>
            <Field label="Country" htmlFor="e-country"><Input id="e-country" value={v.country} onChange={set("country")} /></Field>
          </div>
          <Field label="Campaign">
            <FilterSelect value={v.campaign_id} onChange={(x) => setV((s) => ({ ...s, campaign_id: x }))} allLabel="No campaign" className="w-full" options={campaigns.map((c) => ({ value: c.id, label: c.name }))} />
          </Field>
          <Field label="Description" htmlFor="e-desc"><Textarea id="e-desc" rows={3} value={v.description} onChange={set("description")} /></Field>
          <Field label="Tags"><TagInput value={tags} onChange={setTags} /></Field>
          {save.error ? <Notice tone="danger">Fix the problem above and save again.</Notice> : null}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="edit-company" disabled={save.isPending || !v.name.trim()}>
            {save.isPending && <Loader2 className="animate-spin" />}
            Save company
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
