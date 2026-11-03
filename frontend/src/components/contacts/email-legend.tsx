import { EmailStatusBadge } from "@/components/shared/status-badge";
import { EMAIL_STATUS_META } from "@/lib/status";
import type { EmailStatus } from "@/lib/types";

const ORDER: EmailStatus[] = ["verified", "published", "domain_valid", "unverified", "invalid"];

/** Explains what each email status does and doesn't mean. Only "verified" is a mailbox check. */
export function EmailStatusLegend() {
  return (
    <details className="group rounded-lg border px-4 py-3 text-sm">
      <summary className="cursor-pointer list-none font-medium marker:hidden">
        <span className="text-muted-foreground group-open:hidden">What do the email statuses mean?</span>
        <span className="hidden group-open:inline">Email statuses</span>
      </summary>
      <dl className="mt-3 grid gap-2.5 sm:grid-cols-[auto_1fr] sm:gap-x-4">
        {ORDER.map((s) => (
          <div key={s} className="contents">
            <dt><EmailStatusBadge status={s} /></dt>
            <dd className="text-muted-foreground">{EMAIL_STATUS_META[s].help}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
