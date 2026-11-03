import { cn } from "@/lib/utils";
import { serviceLabel } from "@/lib/format";

type Svc = "website" | "company_brain" | string | null | undefined;

function svcVar(service: Svc) {
  if (service === "website") return "var(--svc-website)";
  if (service === "company_brain") return "var(--svc-brain)";
  return "var(--brand)";
}

/** Compact numeric score; colour reflects the service, weight reflects strength. */
export function ScoreBadge({ value, service, className }: { value: number | null | undefined; service?: Svc; className?: string }) {
  if (value === null || value === undefined) return <span className={cn("text-muted-foreground tabular-nums", className)}>—</span>;
  const strong = value >= 60;
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-8 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums",
        className,
      )}
      style={{
        color: strong ? "var(--background)" : svcVar(service),
        background: strong ? svcVar(service) : `color-mix(in oklch, ${svcVar(service)} 12%, transparent)`,
      }}
    >
      {value}
    </span>
  );
}

/** Horizontal 0–100 bar with label and optional confidence. */
export function ScoreBar({
  value,
  service,
  label,
  confidence,
  recommended,
  className,
}: {
  value: number | null | undefined;
  service: Svc;
  label?: string;
  confidence?: number | null;
  recommended?: boolean;
  className?: string;
}) {
  const v = value ?? 0;
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="flex items-center gap-1.5 font-medium">
          <span className="size-2 rounded-full" style={{ background: svcVar(service) }} aria-hidden />
          {label ?? serviceLabel(service)}
          {recommended && <span className="text-[0.7rem] font-normal text-muted-foreground">recommended</span>}
        </span>
        <span className="tabular-nums text-muted-foreground">
          <span className="text-sm font-semibold text-foreground">{value ?? "—"}</span>
          {value !== null && value !== undefined && "/100"}
          {confidence !== null && confidence !== undefined && <span className="ml-2">conf {Math.round(confidence * 100)}%</span>}
        </span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-muted" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={v} aria-label={label ?? serviceLabel(service)}>
        <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${v}%`, background: svcVar(service), opacity: value === null || value === undefined ? 0 : 1 }} />
        {/* 60 = default qualification threshold marker */}
        <div className="absolute inset-y-0 left-[60%] w-px bg-foreground/20" aria-hidden />
      </div>
    </div>
  );
}

/** Website vs Company Brain side by side (independent scores). */
export function DualScore({
  website,
  brain,
  recommended,
  compact,
  className,
}: {
  website: number | null | undefined;
  brain: number | null | undefined;
  recommended?: string | null;
  compact?: boolean;
  className?: string;
}) {
  if (compact) {
    return (
      <span className={cn("inline-flex items-center gap-1", className)}>
        <ScoreBadge value={website} service="website" className={cn(recommended === "website" && "ring-1 ring-offset-1 ring-offset-background ring-[var(--svc-website)]")} />
        <ScoreBadge value={brain} service="company_brain" className={cn(recommended === "company_brain" && "ring-1 ring-offset-1 ring-offset-background ring-[var(--svc-brain)]")} />
      </span>
    );
  }
  return (
    <div className={cn("grid gap-3", className)}>
      <ScoreBar value={website} service="website" recommended={recommended === "website"} />
      <ScoreBar value={brain} service="company_brain" recommended={recommended === "company_brain"} />
    </div>
  );
}

export function ServiceBadge({ service, className }: { service: Svc; className?: string }) {
  if (!service || service === "none") return <span className={cn("text-xs text-muted-foreground", className)}>No fit yet</span>;
  const tone = service === "website" ? "tone-website" : service === "company_brain" ? "tone-brain" : "tone-neutral";
  return (
    <span className={cn("tone", tone, "inline-flex h-5 items-center gap-1.5 rounded-md border px-1.5 text-xs font-medium whitespace-nowrap", className)}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {serviceLabel(service)}
    </span>
  );
}
