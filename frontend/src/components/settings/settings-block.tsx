import { cn } from "@/lib/utils";

/** Two-column settings block: title + description on the left (lg), fields on the right. */
export function SettingsBlock({
  title,
  description,
  children,
  footer,
  id,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <section id={id} className={cn("grid gap-4 border-b py-8 first:pt-0 last:border-b-0 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)] lg:gap-10", className)}>
      <div className="space-y-1">
        <h2 className="text-[0.95rem] font-semibold tracking-[-0.01em]">{title}</h2>
        {description && <div className="text-sm text-pretty text-muted-foreground">{description}</div>}
      </div>
      <div className="min-w-0 space-y-5">
        {children}
        {footer && <div className="flex flex-wrap items-center gap-2 pt-1">{footer}</div>}
      </div>
    </section>
  );
}
