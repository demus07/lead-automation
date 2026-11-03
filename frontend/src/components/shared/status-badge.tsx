import { Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { humanize } from "@/lib/format";
import {
  CLASSIFICATION_TONE,
  DRAFT_STATUS_META,
  EMAIL_STATUS_META,
  JOB_STATUS_META,
  LEAD_STATUS_META,
  integrationTone,
  type Tone,
} from "@/lib/status";
import type { DraftStatus, EmailStatus, JobStatus, LeadStatus } from "@/lib/types";
import { ToneBadge } from "./tone-badge";

type Kind = "lead" | "draft" | "job" | "classification" | "integration";

export function StatusBadge({ kind, value, className }: { kind: Kind; value: string | null | undefined; className?: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  let label = humanize(value);
  let tone: Tone = "neutral";
  if (kind === "lead" && value in LEAD_STATUS_META) ({ label, tone } = LEAD_STATUS_META[value as LeadStatus]);
  if (kind === "draft" && value in DRAFT_STATUS_META) ({ label, tone } = DRAFT_STATUS_META[value as DraftStatus]);
  if (kind === "job" && value in JOB_STATUS_META) ({ label, tone } = JOB_STATUS_META[value as JobStatus]);
  if (kind === "classification") tone = CLASSIFICATION_TONE[value] ?? "neutral";
  if (kind === "integration") tone = integrationTone(value);
  return (
    <ToneBadge tone={tone} dot={kind === "job" || kind === "integration"} className={className}>
      {kind === "job" && value === "running" ? (
        <span className="relative -ml-0.5 flex size-1.5" aria-hidden>
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
        </span>
      ) : null}
      {label}
    </ToneBadge>
  );
}

/** Email status shown honestly: only "verified" means a mailbox check passed. Tooltip explains the rest. */
export function EmailStatusBadge({ status, className }: { status: EmailStatus | string; className?: string }) {
  const meta = EMAIL_STATUS_META[status as EmailStatus] ?? { label: humanize(status), tone: "neutral" as Tone, help: "" };
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex cursor-help rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ToneBadge tone={meta.tone} className={className}>
            {meta.label}
            {status !== "verified" && status !== "none" && <Info className="size-3 opacity-70" />}
          </ToneBadge>
        </span>
      </TooltipTrigger>
      {meta.help && <TooltipContent className="max-w-64">{meta.help}</TooltipContent>}
    </Tooltip>
  );
}
