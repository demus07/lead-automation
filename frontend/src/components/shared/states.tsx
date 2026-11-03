"use client";

import { AlertTriangle, RotateCw } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact,
}: {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed text-center",
        compact ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {Icon && (
        <div className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Icon className="size-5" />
        </div>
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="mx-auto max-w-[52ch] text-sm text-pretty text-muted-foreground">{description}</p>}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  retry,
  title,
  className,
}: {
  error: unknown;
  retry?: () => void;
  title?: string;
  className?: string;
}) {
  const status = error instanceof ApiError ? error.status : undefined;
  const heading =
    title ??
    (status === 403
      ? "You don't have access to this"
      : status === 404
        ? "Not found"
        : status === 503
          ? "Unavailable in limited mode"
          : "Couldn't load this");
  return (
    <div className={cn("tone tone-danger flex flex-col items-start gap-3 rounded-xl border p-5 sm:flex-row sm:items-center", className)} role="alert">
      <AlertTriangle className="size-5 shrink-0" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium text-foreground">{heading}</p>
        <p className="text-sm text-muted-foreground">{errorMessage(error)}</p>
      </div>
      {retry && status !== 403 && status !== 404 && (
        <Button variant="outline" size="sm" onClick={retry}>
          <RotateCw /> Try again
        </Button>
      )}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className={cn("h-8", j === 0 ? "w-2/5" : "flex-1")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardsSkeleton({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-24 rounded-xl" />
      ))}
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <CardsSkeleton />
      <Skeleton className="h-72 rounded-xl" />
    </div>
  );
}
