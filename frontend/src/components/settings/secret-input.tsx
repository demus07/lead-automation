"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ToneBadge } from "@/components/shared/tone-badge";

/**
 * Write-only secret. Shows whether a value is stored (masked); typing replaces it, blank keeps it.
 * "Remove" sends the backend's "__clear__" sentinel.
 */
export function SecretInput({
  id,
  value,
  onChange,
  isSet,
  masked,
  disabled,
  placeholder,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  isSet?: boolean;
  masked?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  const clearing = value === "__clear__";
  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <Input
          id={id}
          type="password"
          autoComplete="off"
          value={clearing ? "" : value}
          disabled={disabled || clearing}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isSet ? "Leave blank to keep the stored key" : (placeholder ?? "Paste key")}
        />
        {isSet && !disabled && (
          <Button type="button" variant="outline" onClick={() => onChange(clearing ? "" : "__clear__")}>
            {clearing ? "Keep key" : "Remove"}
          </Button>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {clearing ? (
          <ToneBadge tone="warning">Will be removed on save</ToneBadge>
        ) : isSet ? (
          <>
            <ToneBadge tone="success">Stored</ToneBadge>
            <code className="font-mono">{masked}</code>
          </>
        ) : (
          <ToneBadge tone="neutral">Not set</ToneBadge>
        )}
      </div>
    </div>
  );
}
