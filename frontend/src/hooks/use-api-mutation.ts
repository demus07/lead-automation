"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";

interface Options<TVars, TData> {
  /** Toast on success. String, or function of the result. Omit/false for no toast. */
  success?: string | ((data: TData, vars: TVars) => string | false) | false;
  /** Query keys (prefixes) to invalidate on success. */
  invalidate?: QueryKey[];
  onSuccess?: (data: TData, vars: TVars) => void;
  onError?: (err: unknown) => void;
  /** Prefix for the error toast. */
  errorTitle?: string;
}

/** useMutation + toast on success/error + invalidation. Every mutation in the app goes through this. */
export function useApiMutation<TVars = void, TData = unknown>(
  fn: (vars: TVars) => Promise<TData>,
  opts: Options<TVars, TData> = {},
) {
  const qc = useQueryClient();
  return useMutation<TData, unknown, TVars>({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      const msg = typeof opts.success === "function" ? opts.success(data, vars) : opts.success;
      if (msg) toast.success(msg);
      opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      opts.onSuccess?.(data, vars);
    },
    onError: (err) => {
      toast.error(opts.errorTitle ?? "Action failed", { description: errorMessage(err) });
      opts.onError?.(err);
    },
  });
}
