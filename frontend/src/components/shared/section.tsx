import { cn } from "@/lib/utils";

/** A titled panel. Use for grouping on detail and settings pages. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("rounded-xl border bg-card text-card-foreground", className)}>
      {(title || actions) && (
        <div className="flex flex-col gap-2 border-b px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-0.5">
            {title && <h2 className="text-[0.95rem] font-semibold tracking-[-0.01em]">{title}</h2>}
            {description && <p className="text-sm text-pretty text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Definition list for label/value pairs. */
export function DetailList({ items, className }: { items: { label: React.ReactNode; value: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-6 gap-y-2.5 text-sm", className)}>
      {items.map((it, i) => (
        <div key={i} className="contents">
          <dt className="text-muted-foreground">{it.label}</dt>
          <dd className="min-w-0 break-words">{it.value ?? <span className="text-muted-foreground">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}
