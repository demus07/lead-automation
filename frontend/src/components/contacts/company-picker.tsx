"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import type { Company, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface PickedCompany {
  id: string;
  name: string;
  domain?: string | null;
}

/** Searchable company selector backed by GET /companies?q=. */
export function CompanyPicker({
  value,
  onChange,
  id,
}: {
  value: PickedCompany | null;
  onChange: (c: PickedCompany | null) => void;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text), 250);
    return () => clearTimeout(t);
  }, [text]);
  const res = useQuery({
    queryKey: ["companies", "picker", q],
    queryFn: () => api.get<Page<Company>>("/companies", { q, page_size: 20, sort: "name" }),
    enabled: open,
  });
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-normal">
          <span className={cn("truncate", !value && "text-muted-foreground")}>
            {value ? value.name : "Select a company"}
          </span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search companies" value={text} onValueChange={setText} />
          <CommandList>
            {res.isFetching && (
              <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
                <Loader2 className="size-3 animate-spin" /> Searching
              </div>
            )}
            <CommandEmpty>No companies match.</CommandEmpty>
            <CommandGroup>
              {res.data?.items.map((c) => (
                <CommandItem
                  key={c.id}
                  value={c.id}
                  onSelect={() => {
                    onChange({ id: c.id, name: c.name, domain: c.domain });
                    setOpen(false);
                  }}
                >
                  <Check className={cn("size-4", value?.id === c.id ? "opacity-100" : "opacity-0")} />
                  <span className="truncate">{c.name}</span>
                  {c.domain && <span className="ml-auto truncate text-xs text-muted-foreground">{c.domain}</span>}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
