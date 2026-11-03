import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/status";

export function ToneBadge({
  tone = "neutral",
  children,
  className,
  dot,
  title,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        `tone tone-${tone}`,
        "inline-flex h-5 shrink-0 items-center gap-1.5 rounded-md border px-1.5 text-xs font-medium whitespace-nowrap",
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}
