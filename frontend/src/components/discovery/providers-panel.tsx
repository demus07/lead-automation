import { CheckCircle2 } from "lucide-react";
import { StatusBadge } from "@/components/shared/status-badge";
import { humanize } from "@/lib/format";
import type { DiscoveryProvider } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  directory: "Directories",
  hiring: "Hiring threads",
  rss: "Feeds",
  web_search: "Web search",
  crm: "Company Brain",
};
const ORDER = ["directory", "hiring", "rss", "web_search", "crm"];

export function ProvidersPanel({ providers }: { providers: DiscoveryProvider[] }) {
  const kinds = Array.from(new Set(providers.map((p) => p.kind))).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
  return (
    <div className="grid gap-x-8 gap-y-6 md:grid-cols-2">
      {kinds.map((k) => (
        <div key={k} className="min-w-0">
          <h3 className="mb-2 text-sm font-semibold">{KIND_LABEL[k] ?? humanize(k)}</h3>
          <ul className="divide-y rounded-lg border">
            {providers
              .filter((p) => p.kind === k)
              .map((p) => (
                <li key={p.key} className="flex items-start justify-between gap-3 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      {p.label}
                      {p.selected && (
                        <span className="inline-flex items-center gap-1 text-xs font-normal text-brand">
                          <CheckCircle2 className="size-3.5" /> Active provider
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-pretty text-muted-foreground">{p.detail || p.description}</p>
                  </div>
                  <StatusBadge kind="integration" value={p.status} className="mt-0.5" />
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
