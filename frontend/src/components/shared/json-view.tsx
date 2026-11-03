import { cn } from "@/lib/utils";

/** Read-only, scrollable JSON block for logs, stats and raw payloads. */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const empty =
    value === null ||
    value === undefined ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" && value !== null && Object.keys(value).length === 0);
  if (empty) return <p className="text-sm text-muted-foreground">Nothing recorded.</p>;
  return (
    <pre className={cn("max-h-96 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words", className)}>
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
