"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, TableSkeleton } from "./states";
import type { LucideIcon } from "lucide-react";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  /** Server sort field; when set the header becomes a sort toggle. */
  sortKey?: string;
  className?: string;
  headClassName?: string;
  /** Hide below this breakpoint to keep tables readable on phones. */
  hideBelow?: "sm" | "md" | "lg";
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Pagination (server-side). Omit total to hide the pager. */
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  /** Sort as "field" or "-field". */
  sort?: string;
  onSortChange?: (sort: string) => void;
  /** Debounced search. */
  search?: string;
  onSearchChange?: (q: string) => void;
  searchPlaceholder?: string;
  /** Extra filter controls rendered next to the search. */
  filters?: React.ReactNode;
  toolbarEnd?: React.ReactNode;
  /** Row selection for bulk actions. */
  selectable?: boolean;
  selected?: string[];
  onSelectedChange?: (ids: string[]) => void;
  bulkActions?: (ids: string[]) => React.ReactNode;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | undefined;
  empty?: { icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode };
  className?: string;
  dense?: boolean;
}

const HIDE = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell" } as const;

export function DataTable<T>(p: DataTableProps<T>) {
  const [q, setQ] = useState(p.search ?? "");
  const { onSearchChange, search } = p;
  useEffect(() => setQ(search ?? ""), [search]);
  useEffect(() => {
    if (!onSearchChange || q === (search ?? "")) return;
    const t = setTimeout(() => onSearchChange(q), 300);
    return () => clearTimeout(t);
  }, [q, onSearchChange, search]);

  const ids = useMemo(() => (p.rows ?? []).map(p.rowKey), [p.rows, p.rowKey]);
  const selected = p.selected ?? [];
  const allSelected = ids.length > 0 && ids.every((id) => selected.includes(id));
  const someSelected = ids.some((id) => selected.includes(id));
  const toggleAll = () =>
    p.onSelectedChange?.(allSelected ? selected.filter((s) => !ids.includes(s)) : Array.from(new Set([...selected, ...ids])));
  const toggle = (id: string) =>
    p.onSelectedChange?.(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);

  const pages = p.total !== undefined && p.pageSize ? Math.max(1, Math.ceil(p.total / p.pageSize)) : 1;
  const showToolbar = p.onSearchChange || p.filters || p.toolbarEnd;

  function sortIcon(key: string) {
    if (p.sort === key) return <ArrowUp className="size-3.5" />;
    if (p.sort === `-${key}`) return <ArrowDown className="size-3.5" />;
    return <ArrowUpDown className="size-3.5 opacity-40" />;
  }

  return (
    <div className={cn("space-y-3", p.className)}>
      {showToolbar && (
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          {p.onSearchChange && (
            <div className="relative w-full lg:max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={p.searchPlaceholder ?? "Search"}
                className="pl-8"
                aria-label="Search"
              />
              {q && (
                <button
                  type="button"
                  className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
                  onClick={() => setQ("")}
                  aria-label="Clear search"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>
          )}
          {p.filters && <div className="flex flex-wrap items-center gap-2">{p.filters}</div>}
          {p.toolbarEnd && <div className="flex flex-wrap items-center gap-2 lg:ml-auto">{p.toolbarEnd}</div>}
        </div>
      )}

      {p.selectable && selected.length > 0 && p.bulkActions && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/60 px-3 py-2 text-sm">
          <span className="font-medium tabular-nums">{selected.length} selected</span>
          <Button variant="ghost" size="xs" onClick={() => p.onSelectedChange?.([])}>
            Clear
          </Button>
          <div className="ml-auto flex flex-wrap items-center gap-2">{p.bulkActions(selected)}</div>
        </div>
      )}

      {p.error ? (
        <ErrorState error={p.error} retry={p.onRetry} />
      ) : p.isLoading && !p.rows ? (
        <div className="rounded-xl border p-4">
          <TableSkeleton cols={Math.min(p.columns.length, 6)} />
        </div>
      ) : !p.rows?.length ? (
        p.empty ? (
          <EmptyState {...p.empty} />
        ) : (
          <EmptyState title="Nothing here yet" />
        )
      ) : (
        <div className={cn("overflow-hidden rounded-xl border bg-card", p.isLoading && "opacity-70 transition-opacity")}>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {p.selectable && (
                  <TableHead className="w-10 pl-4">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={toggleAll}
                      aria-label="Select all on this page"
                    />
                  </TableHead>
                )}
                {p.columns.map((c) => (
                  <TableHead
                    key={c.key}
                    className={cn("h-10 text-xs font-medium text-muted-foreground", c.hideBelow && HIDE[c.hideBelow], c.headClassName)}
                    aria-sort={p.sort === c.sortKey ? "ascending" : p.sort === `-${c.sortKey}` ? "descending" : undefined}
                  >
                    {c.sortKey && p.onSortChange ? (
                      <button
                        type="button"
                        className="-ml-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-foreground"
                        onClick={() => p.onSortChange!(p.sort === `-${c.sortKey}` ? c.sortKey! : `-${c.sortKey}`)}
                      >
                        {c.header}
                        {sortIcon(c.sortKey)}
                      </button>
                    ) : (
                      c.header
                    )}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {p.rows.map((row) => {
                const id = p.rowKey(row);
                const isSel = selected.includes(id);
                return (
                  <TableRow
                    key={id}
                    data-state={isSel ? "selected" : undefined}
                    className={cn(p.onRowClick && "cursor-pointer", p.rowClassName?.(row))}
                    onClick={p.onRowClick ? (e) => {
                      const t = e.target as HTMLElement;
                      if (t.closest("a,button,input,[role=checkbox],[role=menuitem],label")) return;
                      p.onRowClick!(row);
                    } : undefined}
                  >
                    {p.selectable && (
                      <TableCell className="w-10 pl-4">
                        <Checkbox checked={isSel} onCheckedChange={() => toggle(id)} aria-label="Select row" />
                      </TableCell>
                    )}
                    {p.columns.map((c) => (
                      <TableCell key={c.key} className={cn(p.dense ? "py-2" : "py-2.5", c.hideBelow && HIDE[c.hideBelow], c.className)}>
                        {c.cell(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {p.total !== undefined && p.onPageChange && p.total > 0 && (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="tabular-nums">
            {((p.page ?? 1) - 1) * (p.pageSize ?? 25) + 1}–{Math.min((p.page ?? 1) * (p.pageSize ?? 25), p.total)} of {p.total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" disabled={(p.page ?? 1) <= 1} onClick={() => p.onPageChange!((p.page ?? 1) - 1)} aria-label="Previous page">
              <ChevronLeft />
            </Button>
            <span className="px-2 tabular-nums">
              {p.page ?? 1} / {pages}
            </span>
            <Button variant="outline" size="icon-sm" disabled={(p.page ?? 1) >= pages} onClick={() => p.onPageChange!((p.page ?? 1) + 1)} aria-label="Next page">
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
