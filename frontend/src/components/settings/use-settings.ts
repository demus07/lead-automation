"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApiMutation } from "@/hooks/use-api-mutation";

export type SettingsSection =
  | "agency_profile"
  | "llm"
  | "discovery"
  | "enrichment"
  | "research"
  | "scoring"
  | "quality"
  | "retention";

export function useSettingsSection<T>(section: SettingsSection) {
  return useQuery({
    queryKey: ["settings", section],
    queryFn: () => api.get<T>(`/settings/${section}`),
  });
}

/** PUT /settings/{section}. Admin only (backend enforces). The response (full section) replaces the cache. */
export function useSaveSettings<T>(section: SettingsSection, success: string | false = "Settings saved") {
  const qc = useQueryClient();
  return useApiMutation((patch: Partial<T> | Record<string, unknown>) => api.put<T>(`/settings/${section}`, patch), {
    success,
    errorTitle: "Couldn't save settings",
    onSuccess: (data) => qc.setQueryData(["settings", section], data),
    invalidate: [["dashboard"], ["integrations"], ["ai"], ["discovery"]],
  });
}
