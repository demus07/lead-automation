import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { hostname } from "@/lib/format";

export function ExternalLink({
  href,
  children,
  className,
  icon = true,
}: {
  href: string | null | undefined;
  children?: React.ReactNode;
  className?: string;
  icon?: boolean;
}) {
  if (!href) return <span className="text-muted-foreground">—</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn(
        "inline-flex min-w-0 items-center gap-0.5 text-foreground underline decoration-border underline-offset-[3px] transition-colors hover:decoration-foreground",
        className,
      )}
    >
      <span className="truncate">{children ?? hostname(href)}</span>
      {icon && <ArrowUpRight className="size-3 shrink-0 opacity-60" aria-hidden />}
    </a>
  );
}
