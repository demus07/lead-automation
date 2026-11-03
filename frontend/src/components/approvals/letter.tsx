"use client";

import { MessageSquareText } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { Draft } from "@/lib/types";

export interface LetterValues {
  subject: string;
  body: string;
  linkedin_connection_note: string;
  linkedin_message: string;
}

export function valuesFrom(d: Draft): LetterValues {
  return {
    subject: d.subject ?? "",
    body: d.body ?? "",
    linkedin_connection_note: d.linkedin_connection_note ?? "",
    linkedin_message: d.linkedin_message ?? "",
  };
}

/** Only fields that differ from the draft, in the shape PATCH /drafts/{id} expects. */
export function diffEdits(d: Draft, v: LetterValues) {
  const out: Partial<LetterValues> = {};
  const base = valuesFrom(d);
  (Object.keys(v) as (keyof LetterValues)[]).forEach((k) => {
    if (v[k] !== base[k]) out[k] = v[k];
  });
  return out;
}

function words(s: string) {
  return s.trim() ? s.trim().split(/\s+/).length : 0;
}

/**
 * The email rendered as a sheet of paper: what the recipient will read. In edit mode the same
 * sheet becomes editable, so the reviewer edits in place rather than in a separate form.
 */
export function Letter({
  draft,
  editing,
  values,
  onChange,
  className,
}: {
  draft: Draft;
  editing: boolean;
  values: LetterValues;
  onChange: (v: LetterValues) => void;
  className?: string;
}) {
  const v = editing ? values : valuesFrom(draft);
  const set = (k: keyof LetterValues) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    onChange({ ...values, [k]: e.target.value });
  const to = draft.contact
    ? `${draft.contact.full_name}${draft.contact.email ? ` <${draft.contact.email}>` : ""}`
    : "No recipient";
  const n = words(v.body);

  return (
    <div className={cn("space-y-5", className)}>
      <article
        className={cn(
          "relative rounded-xl border bg-[var(--paper)] shadow-[0_1px_0_0_var(--border),0_12px_32px_-18px_color-mix(in_oklch,var(--foreground)_30%,transparent)]",
          editing && "ring-2 ring-ring/40",
        )}
        aria-label="Email draft"
      >
        <dl className="grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-2 border-b px-6 py-4 text-sm sm:px-10">
          <dt className="text-muted-foreground">To</dt>
          <dd className="min-w-0 truncate">{to}</dd>
          <dt className="self-center text-muted-foreground">Subject</dt>
          <dd className="min-w-0">
            {editing ? (
              <Input value={v.subject} onChange={set("subject")} maxLength={300} aria-label="Subject" className="h-8 font-medium" />
            ) : (
              <span className="font-medium">{v.subject}</span>
            )}
          </dd>
        </dl>
        <div className="px-6 py-6 sm:px-10 sm:py-8">
          {editing ? (
            <Textarea
              value={v.body}
              onChange={set("body")}
              aria-label="Email body"
              maxLength={10000}
              className="field-sizing-content min-h-72 resize-y border-dashed bg-transparent text-[0.95rem] leading-7 dark:bg-transparent"
            />
          ) : (
            <div className="max-w-[64ch] text-[0.95rem] leading-7 whitespace-pre-wrap text-pretty">{v.body}</div>
          )}
        </div>
        <div className="flex items-center justify-between border-t px-6 py-2.5 text-xs text-muted-foreground sm:px-10">
          <span className="tabular-nums">
            {n} words · v{draft.version}
            {draft.edited_by_user && " · edited by you"}
          </span>
          <span>Unsent draft — you send it yourself</span>
        </div>
      </article>

      {(editing || v.linkedin_connection_note || v.linkedin_message) && (
        <div className="grid gap-4 md:grid-cols-2">
          <LinkedInBlock
            label="LinkedIn connection note"
            limit={300}
            editing={editing}
            value={v.linkedin_connection_note}
            onChange={set("linkedin_connection_note")}
          />
          <LinkedInBlock
            label="LinkedIn message"
            limit={2000}
            editing={editing}
            value={v.linkedin_message}
            onChange={set("linkedin_message")}
          />
        </div>
      )}
    </div>
  );
}

function LinkedInBlock({
  label,
  limit,
  editing,
  value,
  onChange,
}: {
  label: string;
  limit: number;
  editing: boolean;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
}) {
  return (
    <div className="space-y-2 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5 font-medium text-foreground">
          <MessageSquareText className="size-3.5" /> {label}
        </span>
        <span className={cn("tabular-nums", value.length > limit && "text-destructive")}>
          {value.length}/{limit}
        </span>
      </div>
      {editing ? (
        <Textarea value={value} onChange={onChange} maxLength={limit} rows={4} aria-label={label} className="text-sm" />
      ) : value ? (
        <p className="text-sm whitespace-pre-wrap text-pretty">{value}</p>
      ) : (
        <p className="text-sm text-muted-foreground">None written.</p>
      )}
      <p className="text-xs text-muted-foreground">Copy and send manually on LinkedIn — nothing is posted for you.</p>
    </div>
  );
}
