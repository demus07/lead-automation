"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Field } from "@/components/shared/field";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import type { Contact } from "@/lib/types";
import { CompanyPicker, type PickedCompany } from "./company-picker";

const schema = z.object({
  full_name: z.string().trim().min(1, "Enter a name").max(200),
  job_title: z.string().max(200).optional(),
  email: z.union([z.literal(""), z.string().trim().email("Enter a valid email")]).optional(),
  profile_url: z.union([z.literal(""), z.string().trim().url("Enter a full URL (https://…)")]).optional(),
  source_url: z.union([z.literal(""), z.string().trim().url("Enter a full URL (https://…)")]).optional(),
  is_primary: z.boolean().optional(),
});
type Values = z.infer<typeof schema>;

/**
 * Add (POST /contacts) or edit (PATCH /contacts/{id}) a contact.
 * When `company` is given the picker is hidden (used on the company page).
 */
export function ContactDialog({
  open,
  onOpenChange,
  contact,
  company,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  contact?: Contact | null;
  company?: PickedCompany | null;
}) {
  const editing = !!contact;
  const [picked, setPicked] = useState<PickedCompany | null>(company ?? null);
  const [pickErr, setPickErr] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (!open) return;
    setPicked(company ?? null);
    setPickErr(null);
    form.reset({
      full_name: contact?.full_name ?? "",
      job_title: contact?.job_title ?? "",
      email: contact?.email ?? "",
      profile_url: contact?.profile_url ?? "",
      source_url: contact?.source_url ?? "",
      is_primary: contact?.is_primary ?? false,
    });
  }, [open, contact, company, form]);

  const save = useApiMutation(
    async (v: Values) => {
      if (editing) {
        return api.patch<Contact>(`/contacts/${contact!.id}`, {
          full_name: v.full_name,
          job_title: v.job_title || null,
          email: v.email || null,
          profile_url: v.profile_url || null,
          is_primary: v.is_primary,
        });
      }
      return api.post<Contact>("/contacts", {
        company_id: picked!.id,
        full_name: v.full_name,
        job_title: v.job_title || null,
        email: v.email || null,
        profile_url: v.profile_url || null,
        source_url: v.source_url || null,
      });
    },
    {
      success: editing ? "Contact saved" : "Contact added",
      invalidate: [["contacts"], ["company"]],
      onSuccess: () => onOpenChange(false),
    },
  );

  const errors = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit contact" : "Add contact"}</DialogTitle>
          <DialogDescription>
            {editing
              ? "Changing the email resets its status to unverified until it is checked again."
              : "New emails start as unverified. Run “Verify email” afterwards to check syntax and domain."}
          </DialogDescription>
        </DialogHeader>
        <form
          id="contact-form"
          className="grid gap-4"
          onSubmit={form.handleSubmit((v) => {
            if (!editing && !picked) {
              setPickErr("Choose the company this person works at");
              return;
            }
            save.mutate(v);
          })}
          noValidate
        >
          {!editing && !company && (
            <Field label="Company" htmlFor="contact-company" error={pickErr} required>
              <CompanyPicker id="contact-company" value={picked} onChange={(c) => { setPicked(c); setPickErr(null); }} />
            </Field>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" htmlFor="c-name" error={errors.full_name?.message} required>
              <Input id="c-name" {...form.register("full_name")} aria-invalid={!!errors.full_name} />
            </Field>
            <Field label="Job title" htmlFor="c-title" error={errors.job_title?.message}>
              <Input id="c-title" {...form.register("job_title")} />
            </Field>
          </div>
          <Field label="Email" htmlFor="c-email" error={errors.email?.message}>
            <Input id="c-email" type="email" {...form.register("email")} aria-invalid={!!errors.email} />
          </Field>
          <Field label="Profile URL" htmlFor="c-profile" error={errors.profile_url?.message} hint="LinkedIn or a team page">
            <Input id="c-profile" placeholder="https://" {...form.register("profile_url")} />
          </Field>
          {!editing && (
            <Field label="Source URL" htmlFor="c-source" error={errors.source_url?.message} hint="Where you found this person">
              <Input id="c-source" placeholder="https://" {...form.register("source_url")} />
            </Field>
          )}
          {editing && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="c-primary"
                checked={!!form.watch("is_primary")}
                onCheckedChange={(v) => form.setValue("is_primary", v === true)}
              />
              <Label htmlFor="c-primary" className="font-normal">Primary contact for this company</Label>
            </div>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="contact-form" disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {editing ? "Save contact" : "Add contact"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
