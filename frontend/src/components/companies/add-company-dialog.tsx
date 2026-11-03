"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import { FilterSelect } from "@/components/shared/filter-select";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import type { Campaign, Company } from "@/lib/types";
import { COMPANY_SIZES } from "./constants";

const schema = z.object({
  name: z.string().trim().min(1, "Enter the company name").max(300),
  website: z.string().trim().max(500).optional(),
  industry: z.string().max(200).optional(),
  location: z.string().max(300).optional(),
  country: z.string().max(100).optional(),
  description: z.string().max(4000).optional(),
});
type Values = z.infer<typeof schema>;

export function AddCompanyDialog({
  open,
  onOpenChange,
  campaigns,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  campaigns: Campaign[];
}) {
  const router = useRouter();
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const [tags, setTags] = useState<string[]>([]);
  const [size, setSize] = useState("");
  const [campaign, setCampaign] = useState("");
  useEffect(() => {
    if (open) {
      form.reset({ name: "", website: "", industry: "", location: "", country: "", description: "" });
      setTags([]);
      setSize("");
      setCampaign("");
    }
  }, [open, form]);

  const create = useApiMutation(
    (v: Values) =>
      api.post<Company>("/companies", {
        name: v.name,
        website: v.website || null,
        industry: v.industry || null,
        location: v.location || null,
        country: v.country || null,
        description: v.description || null,
        size_range: size || null,
        campaign_id: campaign || null,
        tags,
      }),
    {
      success: (c) => `Added ${c.name}`,
      invalidate: [["companies"]],
      onSuccess: (c) => {
        onOpenChange(false);
        router.push(`/companies/${c.id}`);
      },
    },
  );
  const e = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add company</DialogTitle>
          <DialogDescription>Duplicates are detected by domain and name. Suppressed domains can&apos;t be added.</DialogDescription>
        </DialogHeader>
        <form id="add-company" className="grid gap-4" onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="co-name" error={e.name?.message} required>
              <Input id="co-name" {...form.register("name")} aria-invalid={!!e.name} />
            </Field>
            <Field label="Website" htmlFor="co-web" hint="Domain or full URL">
              <Input id="co-web" placeholder="example.com" {...form.register("website")} />
            </Field>
            <Field label="Industry" htmlFor="co-ind">
              <Input id="co-ind" {...form.register("industry")} />
            </Field>
            <Field label="Size">
              <FilterSelect value={size} onChange={setSize} allLabel="Unknown" options={COMPANY_SIZES.map((s) => ({ value: s, label: `${s} people` }))} className="w-full" />
            </Field>
            <Field label="Location" htmlFor="co-loc">
              <Input id="co-loc" {...form.register("location")} />
            </Field>
            <Field label="Country" htmlFor="co-country">
              <Input id="co-country" {...form.register("country")} />
            </Field>
          </div>
          <Field label="Campaign">
            <FilterSelect value={campaign} onChange={setCampaign} allLabel="No campaign" options={campaigns.map((c) => ({ value: c.id, label: c.name }))} className="w-full" />
          </Field>
          <Field label="Description" htmlFor="co-desc">
            <Textarea id="co-desc" rows={3} {...form.register("description")} />
          </Field>
          <Field label="Tags">
            <TagInput value={tags} onChange={setTags} />
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="add-company" disabled={create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />}
            Add company
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
