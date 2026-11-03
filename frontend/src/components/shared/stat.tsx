import Link from "next/link";
import { cn } from "@/lib/utils";

/** A single metric. Number first, label second; optional hint and link. */
export function Stat({
  label,
  value,
  hint,
  href,
  emphasis,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  href?: string;
  emphasis?: boolean;
  className?: string;
}) {
  const body = (
    <>
      <div className={cn("text-[1.65rem] leading-none font-semibold tracking-[-0.03em] tabular-nums", emphasis && "text-brand")}>{value}</div>
      <div className="mt-2 text-sm text-muted-foreground">{label}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground/80">{hint}</div>}
    </>
  );
  const cls = cn("block rounded-xl border bg-card p-4", href && "transition-colors hover:bg-accent/60", className);
  return href ? (
    <Link href={href} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}
