import Link from "next/link";
import { AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

/** Inline banner for limited mode, warnings and "this is what will happen" copy. */
export function Notice({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: "info" | "warning" | "danger" | "neutral";
  title?: React.ReactNode;
  children?: React.ReactNode;
  action?: { href: string; label: string } | React.ReactNode;
  className?: string;
}) {
  const Icon = tone === "info" || tone === "neutral" ? Info : AlertTriangle;
  const act =
    action && typeof action === "object" && "href" in (action as object) ? (
      <Link
        href={(action as { href: string }).href}
        className="shrink-0 text-sm font-medium text-foreground underline underline-offset-4 hover:no-underline"
      >
        {(action as { label: string }).label}
      </Link>
    ) : (
      (action as React.ReactNode)
    );
  return (
    <div className={cn(`tone tone-${tone}`, "flex flex-col gap-2 rounded-lg border px-4 py-3 sm:flex-row sm:items-center", className)} role="status">
      <Icon className="size-4 shrink-0 self-start sm:self-center" />
      <div className="min-w-0 flex-1 text-sm">
        {title && <p className="font-medium text-foreground">{title}</p>}
        {children && <div className="text-muted-foreground">{children}</div>}
      </div>
      {act}
    </div>
  );
}
