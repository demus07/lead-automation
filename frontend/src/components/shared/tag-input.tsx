"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Edit a list of strings as chips. Enter or comma adds; Backspace on empty removes the last. */
export function TagInput({
  value,
  onChange,
  placeholder = "Type and press Enter",
  id,
  className,
  disabled,
  suggestions,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  id?: string;
  className?: string;
  disabled?: boolean;
  suggestions?: string[];
}) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const parts = raw
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !value.includes(s));
    if (parts.length) onChange([...value, ...parts]);
    setText("");
  };
  const remaining = suggestions?.filter((s) => !value.includes(s)) ?? [];
  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          "flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 dark:bg-input/30",
          disabled && "pointer-events-none opacity-50",
          className,
        )}
      >
        {value.map((t) => (
          <span key={t} className="inline-flex h-6 items-center gap-1 rounded-md bg-secondary pr-1 pl-2 text-xs">
            {t}
            <button
              type="button"
              onClick={() => onChange(value.filter((x) => x !== t))}
              className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
              aria-label={`Remove ${t}`}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(text);
            } else if (e.key === "Backspace" && !text && value.length) {
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={() => text && add(text)}
          onPaste={(e) => {
            const t = e.clipboardData.getData("text");
            if (/[,\n]/.test(t)) {
              e.preventDefault();
              add(t);
            }
          }}
          placeholder={value.length ? "" : placeholder}
          className="min-w-[8rem] flex-1 bg-transparent py-0.5 outline-none placeholder:text-muted-foreground"
        />
      </div>
      {remaining.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {remaining.map((s) => (
            <button
              type="button"
              key={s}
              onClick={() => onChange([...value, s])}
              className="h-6 rounded-md border border-dashed px-2 text-xs text-muted-foreground hover:border-solid hover:text-foreground"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
