import { Link2Off } from "lucide-react";
import { cn } from "@/lib/utils";
import { hostname } from "@/lib/format";
import type { DraftClaim, EvidenceItem } from "@/lib/types";
import { ExternalLink } from "./external-link";
import { ObservationBadge } from "./observation-badge";

export function EvidenceId({ id, className }: { id: string; className?: string }) {
  return (
    <code
      className={cn(
        "inline-flex h-[1.125rem] items-center rounded border bg-muted px-1 font-mono text-[0.7rem] leading-none text-muted-foreground",
        className,
      )}
    >
      {id}
    </code>
  );
}

/** Evidence items from research (pages, signals, audit checks) with source links and ids. */
export function EvidenceList({
  items,
  className,
  empty = "No evidence recorded.",
  highlight,
}: {
  items: (EvidenceItem & { text?: string; category?: string })[];
  className?: string;
  empty?: string;
  highlight?: string[];
}) {
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className={cn("divide-y rounded-lg border", className)}>
      {items.map((e, i) => (
        <li
          key={`${e.id}-${i}`}
          id={e.id ? `ev-${e.id}` : undefined}
          className={cn("space-y-1.5 p-3 text-sm", highlight?.includes(e.id) && "bg-[color-mix(in_oklch,var(--brand)_7%,transparent)]")}
        >
          <div className="flex flex-wrap items-center gap-2">
            {e.id && <EvidenceId id={e.id} />}
            {e.kind && <span className="text-xs text-muted-foreground">{e.page_kind ?? e.kind}</span>}
            {e.category && <ObservationBadge category={e.category} />}
            {e.url ? (
              <ExternalLink href={e.url} className="max-w-full text-xs">
                {e.title || hostname(e.url)}
              </ExternalLink>
            ) : (
              e.title && <span className="text-xs font-medium">{e.title}</span>
            )}
          </div>
          {(e.text || e.excerpt) && (
            <p className="line-clamp-4 text-xs whitespace-pre-line text-muted-foreground">{e.text || e.excerpt}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Claims an AI draft makes, each tied to evidence ids and their source URLs. Unsupported claims are flagged. */
export function ClaimList({ claims, className }: { claims: DraftClaim[] | null | undefined; className?: string }) {
  if (!claims?.length) return <p className="text-sm text-muted-foreground">The draft declares no factual claims.</p>;
  return (
    <ol className={cn("space-y-3", className)}>
      {claims.map((c, i) => {
        const unsupported = !c.evidence_ids?.length;
        const dropped = (c.declared_ids ?? []).filter((d) => !c.evidence_ids.includes(d));
        return (
          <li key={i} className={cn("rounded-lg border p-3 text-sm", unsupported && "tone tone-danger border-dashed")}>
            <p className={cn("text-pretty", unsupported ? "" : "text-foreground")}>{c.text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {unsupported && (
                <span className="inline-flex items-center gap-1 text-xs font-medium">
                  <Link2Off className="size-3" /> No valid evidence
                </span>
              )}
              {c.evidence_ids?.map((id) => <EvidenceId key={id} id={id} />)}
              {dropped.length > 0 && (
                <span className="text-xs text-muted-foreground" title="Ids the writer cited that don't exist in the research">
                  rejected ids: {dropped.join(", ")}
                </span>
              )}
            </div>
            {!!c.sources?.length && (
              <ul className="mt-2 space-y-1.5 border-l pl-3">
                {c.sources.map((s) => (
                  <li key={s.id} className="text-xs">
                    <div className="flex items-center gap-1.5">
                      <EvidenceId id={s.id} />
                      {s.url && <ExternalLink href={s.url} className="text-xs" />}
                    </div>
                    {s.excerpt && <p className="mt-0.5 line-clamp-2 text-muted-foreground">{s.excerpt}</p>}
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
