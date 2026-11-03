"use client";

import { useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shared/field";
import { FilterSelect } from "@/components/shared/filter-select";
import { Section } from "@/components/shared/section";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { request } from "@/lib/api";
import { humanize } from "@/lib/format";
import type { Campaign } from "@/lib/types";

interface ImportReport {
  rows: number;
  companies_created: number;
  companies_matched: number;
  contacts_created: number;
  contacts_matched: number;
  skipped: number;
  suppressed: number;
  errors: { row?: number; error?: string; [k: string]: unknown }[];
  mapping: Record<string, string>;
  company_ids: string[];
}

export function CsvImport({ campaigns, canRun }: { campaigns: Campaign[]; canRun: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [campaignId, setCampaignId] = useState("");
  const [tags, setTags] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);

  const upload = useApiMutation(
    () => {
      const fd = new FormData();
      fd.append("file", file as File);
      if (campaignId) fd.append("campaign_id", campaignId);
      fd.append("tags", tags);
      return request<ImportReport>("/discovery/import", { method: "POST", body: fd });
    },
    {
      success: (r) => `Imported ${r.rows} rows`,
      invalidate: [["companies"], ["contacts"], ["campaigns"]],
      onSuccess: (r) => {
        setReport(r);
        setFile(null);
        if (fileRef.current) fileRef.current.value = "";
      },
    },
  );

  const counts: [string, number][] = report
    ? [
        ["Rows read", report.rows],
        ["Companies created", report.companies_created],
        ["Companies matched", report.companies_matched],
        ["Contacts created", report.contacts_created],
        ["Contacts matched", report.contacts_matched],
        ["Skipped", report.skipped],
        ["Suppressed", report.suppressed],
      ]
    : [];

  return (
    <Section title="Import a CSV" description="Companies (and optional contacts). Columns like name, website, domain, email, title are detected automatically. Max 10 MB.">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) upload.mutate();
        }}
      >
        <Field label="File" htmlFor="csv-file" required>
          <Input id="csv-file" ref={fileRef} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="file:mr-3 file:text-sm" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Campaign">
            <FilterSelect value={campaignId} onChange={setCampaignId} allLabel="None" options={campaigns.map((c) => ({ value: c.id, label: c.name }))} className="w-full" aria-label="Campaign" />
          </Field>
          <Field label="Tags" htmlFor="csv-tags" hint="Comma-separated, added to every company.">
            <Input id="csv-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="event-2026, referral" />
          </Field>
        </div>
        <Button type="submit" disabled={!canRun || !file || upload.isPending}>
          {upload.isPending ? <Loader2 className="animate-spin" /> : <FileUp />}
          Import CSV
        </Button>
      </form>

      {report && (
        <div className="mt-5 space-y-4 border-t pt-5 text-sm" aria-live="polite">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            {counts.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted-foreground">{k}</dt>
                <dd className="text-base font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          {Object.keys(report.mapping).length > 0 && (
            <div>
              <p className="mb-1.5 text-xs text-muted-foreground">Detected columns</p>
              <ul className="flex flex-wrap gap-1.5">
                {Object.entries(report.mapping).map(([field, col]) => (
                  <li key={field} className="rounded-md border px-2 py-0.5 text-xs">
                    <span className="text-muted-foreground">{col}</span> → {humanize(field)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.errors.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs text-muted-foreground">{report.errors.length} row errors</p>
              <ul className="max-h-48 space-y-1 overflow-auto text-xs">
                {report.errors.map((e, i) => (
                  <li key={i} className="tone tone-danger rounded border px-2 py-1">
                    {e.row !== undefined && <span className="font-medium">Row {e.row}: </span>}
                    {e.error ?? JSON.stringify(e)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}
