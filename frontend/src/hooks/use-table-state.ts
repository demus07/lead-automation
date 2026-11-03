"use client";

import { useCallback, useState } from "react";

/** Page/sort/search/filter state for server-paginated tables. Changing filters resets to page 1. */
export function useTableState<F extends Record<string, unknown>>(initial: {
  sort?: string;
  pageSize?: number;
  filters?: F;
} = {}) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(initial.pageSize ?? 25);
  const [sort, setSortRaw] = useState(initial.sort ?? "");
  const [q, setQRaw] = useState("");
  const [filters, setFiltersRaw] = useState<F>((initial.filters ?? {}) as F);
  const setSort = useCallback((s: string) => {
    setSortRaw(s);
    setPage(1);
  }, []);
  const setQ = useCallback((s: string) => {
    setQRaw(s);
    setPage(1);
  }, []);
  const setFilter = useCallback(<K extends keyof F>(k: K, v: F[K]) => {
    setFiltersRaw((f) => ({ ...f, [k]: v }));
    setPage(1);
  }, []);
  const resetFilters = useCallback(() => {
    setFiltersRaw((initial.filters ?? {}) as F);
    setQRaw("");
    setPage(1);
  }, [initial.filters]);
  return { page, setPage, pageSize, sort, setSort, q, setQ, filters, setFilter, resetFilters };
}
