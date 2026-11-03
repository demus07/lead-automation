"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/shared/field";
import { TagInput } from "@/components/shared/tag-input";
import { ErrorState, TableSkeleton } from "@/components/shared/states";
import { useSaveSettings, useSettingsSection, type SettingsSection } from "./use-settings";

export type SimpleField =
  | { key: string; label: string; type: "number"; hint?: string; step?: number; min?: number; max?: number; suffix?: string }
  | { key: string; label: string; type: "boolean"; hint?: string }
  | { key: string; label: string; type: "tags"; hint?: string };

type Values = Record<string, unknown>;

function Inner({
  section,
  data,
  fields,
  disabled,
  saveLabel,
  successMsg,
}: {
  section: SettingsSection;
  data: Values;
  fields: SimpleField[];
  disabled?: boolean;
  saveLabel: string;
  successMsg: string;
}) {
  const [v, setV] = useState<Record<string, string | boolean | string[]>>(() => {
    const o: Record<string, string | boolean | string[]> = {};
    for (const f of fields) {
      const raw = data[f.key];
      if (f.type === "number") o[f.key] = raw === undefined || raw === null ? "" : String(raw);
      else if (f.type === "boolean") o[f.key] = !!raw;
      else o[f.key] = Array.isArray(raw) ? (raw as string[]) : [];
    }
    return o;
  });
  const save = useSaveSettings<Values>(section, successMsg);
  const numbers = fields.filter((f) => f.type === "number");

  return (
    <form
      className="space-y-5"
      onSubmit={async (e) => {
        e.preventDefault();
        const patch: Values = {};
        for (const f of fields) {
          if (f.type === "number") patch[f.key] = Number(v[f.key]);
          else patch[f.key] = v[f.key];
        }
        try {
          await save.mutateAsync(patch);
        } catch {
          /* toast */
        }
      }}
    >
      <fieldset disabled={disabled} className="space-y-5">
        {numbers.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {numbers.map((f) =>
              f.type === "number" ? (
                <Field key={f.key} label={f.label} htmlFor={`${section}-${f.key}`} hint={f.hint}>
                  <div className="flex items-center gap-2">
                    <Input
                      id={`${section}-${f.key}`}
                      type="number"
                      step={f.step ?? 1}
                      min={f.min}
                      max={f.max}
                      value={v[f.key] as string}
                      onChange={(e) => setV((s) => ({ ...s, [f.key]: e.target.value }))}
                      className="tabular-nums"
                    />
                    {f.suffix && <span className="shrink-0 text-sm text-muted-foreground">{f.suffix}</span>}
                  </div>
                </Field>
              ) : null,
            )}
          </div>
        )}
        {fields.map((f) =>
          f.type === "boolean" ? (
            <div key={f.key} className="space-y-1">
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={v[f.key] as boolean} onCheckedChange={(x) => setV((s) => ({ ...s, [f.key]: x }))} disabled={disabled} />
                {f.label}
              </label>
              {f.hint && <p className="pl-10 text-xs text-muted-foreground">{f.hint}</p>}
            </div>
          ) : f.type === "tags" ? (
            <Field key={f.key} label={f.label} htmlFor={`${section}-${f.key}`} hint={f.hint}>
              <TagInput id={`${section}-${f.key}`} value={v[f.key] as string[]} onChange={(x) => setV((s) => ({ ...s, [f.key]: x }))} disabled={disabled} />
            </Field>
          ) : null,
        )}
      </fieldset>
      <Button type="submit" disabled={disabled || save.isPending}>
        {save.isPending && <Loader2 className="animate-spin" />}
        {saveLabel}
      </Button>
    </form>
  );
}

/** Loads /settings/{section} and renders the given fields with a Save button. */
export function SimpleSettingsForm({
  section,
  fields,
  disabled,
  saveLabel = "Save",
  successMsg = "Settings saved",
}: {
  section: SettingsSection;
  fields: SimpleField[];
  disabled?: boolean;
  saveLabel?: string;
  successMsg?: string;
}) {
  const q = useSettingsSection<Values>(section);
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <TableSkeleton rows={2} cols={3} />;
  return <Inner section={section} data={q.data} fields={fields} disabled={disabled} saveLabel={saveLabel} successMsg={successMsg} />;
}
