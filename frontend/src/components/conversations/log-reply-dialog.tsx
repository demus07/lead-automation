"use client";

import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { Check, Loader2, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/shared/field";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Company, Contact, Interaction, Page } from "@/lib/types";

const NO_CONTACT = "__none__";

const schema = z.object({
  company_id: z.string().uuid("Choose a company"),
  contact_id: z.string(),
  channel: z.enum(["email", "linkedin", "call", "meeting", "other"]),
  subject: z.string().max(500),
  body: z.string().trim().min(1, "Paste what they said").max(20000),
  occurred_at: z.string(),
});
type Values = z.infer<typeof schema>;

function CompanyPicker({ value, onChange, invalid }: { value: string; onChange: (id: string, name: string) => void; invalid?: boolean }) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setQ(text), 250);
    return () => clearTimeout(t);
  }, [text]);
  const res = useQuery({
    queryKey: ["companies", "picker", q],
    queryFn: () => api.get<Page<Company>>("/companies", { q, page_size: 8, sort: "name" }),
    enabled: !picked,
  });
  if (picked && value) {
    return (
      <div className="flex h-8 items-center justify-between rounded-lg border px-2.5 text-sm">
        <span className="flex items-center gap-1.5 truncate">
          <Check className="size-3.5 text-brand" /> {picked}
        </span>
        <Button type="button" variant="ghost" size="xs" onClick={() => { setPicked(null); onChange("", ""); }}>
          Change
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search companies by name or domain" className="pl-8" aria-invalid={invalid} aria-label="Company" />
      </div>
      <ul className="max-h-40 overflow-y-auto rounded-lg border">
        {res.isLoading && <li className="px-3 py-2 text-sm text-muted-foreground">Searching…</li>}
        {res.data?.items.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No companies match.</li>}
        {res.data?.items.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
              onClick={() => {
                setPicked(c.name);
                onChange(c.id, c.name);
              }}
            >
              <span className="truncate">{c.name}</span>
              <span className="truncate text-xs text-muted-foreground">{c.domain}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LogReplyDialog({ onLogged }: { onLogged?: (i: Interaction) => void }) {
  const [open, setOpen] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { company_id: "", contact_id: NO_CONTACT, channel: "email", subject: "", body: "", occurred_at: "" },
  });
  const companyId = form.watch("company_id");
  const contacts = useQuery({
    queryKey: ["contacts", "for-company", companyId],
    queryFn: () => api.get<Page<Contact>>("/contacts", { company_id: companyId, page_size: 100 }),
    enabled: !!companyId,
  });
  const log = useApiMutation(
    (v: Values) =>
      api.post<Interaction>("/conversations/inbound", {
        company_id: v.company_id,
        contact_id: v.contact_id === NO_CONTACT ? null : v.contact_id,
        channel: v.channel,
        subject: v.subject || null,
        body: v.body,
        occurred_at: v.occurred_at ? new Date(v.occurred_at).toISOString() : null,
      }),
    {
      success: (i) => `Reply logged${i.classification ? ` — classified as ${i.classification.replace(/_/g, " ")}` : ""}`,
      invalidate: [["conversations"], ["dashboard"]],
      onSuccess: (i) => {
        setOpen(false);
        form.reset();
        onLogged?.(i);
      },
    },
  );
  const errs = form.formState.errors;

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) form.reset(); }}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus /> Log a reply
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Log a reply</DialogTitle>
          <DialogDescription>Record a reply that didn&apos;t arrive in a connected mailbox — a LinkedIn message, a call, a meeting. It&apos;s classified like any other reply.</DialogDescription>
        </DialogHeader>
        <form id="log-reply" className="space-y-4" onSubmit={form.handleSubmit((v) => log.mutate(v))} noValidate>
          <Field label="Company" required error={errs.company_id?.message}>
            <Controller
              control={form.control}
              name="company_id"
              render={({ field }) => (
                <CompanyPicker
                  value={field.value}
                  invalid={!!errs.company_id}
                  onChange={(id) => {
                    field.onChange(id);
                    form.setValue("contact_id", NO_CONTACT);
                  }}
                />
              )}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Contact">
              <Controller
                control={form.control}
                name="contact_id"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange} disabled={!companyId}>
                    <SelectTrigger className="w-full" aria-label="Contact">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_CONTACT}>Not linked to a contact</SelectItem>
                      {contacts.data?.items.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.full_name}
                          {c.job_title ? ` · ${c.job_title}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>
            <Field label="Channel">
              <Controller
                control={form.control}
                name="channel"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-full" aria-label="Channel">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="email">Email</SelectItem>
                      <SelectItem value="linkedin">LinkedIn</SelectItem>
                      <SelectItem value="call">Call</SelectItem>
                      <SelectItem value="meeting">Meeting</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
            <Field label="Subject" htmlFor="lr-subject">
              <Input id="lr-subject" {...form.register("subject")} maxLength={500} />
            </Field>
            <Field label="When" htmlFor="lr-when" hint="Defaults to now">
              <Input id="lr-when" type="datetime-local" {...form.register("occurred_at")} />
            </Field>
          </div>
          <Field label="What they said" htmlFor="lr-body" required error={errs.body?.message}>
            <Textarea id="lr-body" rows={6} {...form.register("body")} aria-invalid={!!errs.body} className={cn(errs.body && "border-destructive")} />
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={log.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="log-reply" disabled={log.isPending}>
            {log.isPending && <Loader2 className="animate-spin" />}
            Log reply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
