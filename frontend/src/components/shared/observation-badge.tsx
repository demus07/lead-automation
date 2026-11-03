import { BadgeCheck, Eye, HelpCircle, Lightbulb } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { OBSERVATION_META } from "@/lib/status";

const ICONS = {
  verified_fact: BadgeCheck,
  direct_observation: Eye,
  hypothesis: Lightbulb,
  unknown: HelpCircle,
} as const;

/**
 * Visually distinct per category: verified facts are solid, observations outlined,
 * hypotheses dashed (they must never be presented as fact), unknown muted.
 */
export function ObservationBadge({ category, className }: { category: string; className?: string }) {
  const key = (category in OBSERVATION_META ? category : "unknown") as keyof typeof ICONS;
  const meta = OBSERVATION_META[key];
  const Icon = ICONS[key];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            `tone tone-${meta.tone}`,
            "inline-flex h-5 shrink-0 cursor-help items-center gap-1 rounded-md border px-1.5 text-xs font-medium whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring",
            key === "verified_fact" && "border-transparent bg-[color-mix(in_oklch,var(--t)_18%,transparent)]",
            key === "hypothesis" && "border-dashed bg-transparent",
            key === "unknown" && "opacity-80",
            className,
          )}
        >
          <Icon className="size-3" aria-hidden />
          {meta.label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{meta.help}</TooltipContent>
    </Tooltip>
  );
}
