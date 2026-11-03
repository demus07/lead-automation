"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Campaign, DiscoveryProvider } from "@/lib/types";

export interface CampaignTemplates {
  signal_templates: Record<string, string[]>;
  sizes: string[];
}

export interface ProvidersResponse {
  providers: DiscoveryProvider[];
  limited_mode: boolean;
  limited_mode_reason: string | null;
  searches_today: number;
  daily_search_quota: number | null;
}

export function useCampaigns() {
  return useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns") });
}

export function useCampaignTemplates() {
  return useQuery({
    queryKey: ["campaigns", "templates"],
    queryFn: () => api.get<CampaignTemplates>("/campaigns/templates"),
    staleTime: 10 * 60_000,
  });
}

export function useProviders() {
  return useQuery({ queryKey: ["discovery", "providers"], queryFn: () => api.get<ProvidersResponse>("/discovery/providers") });
}

/** Providers that can actually run right now. */
export function usableProviders(p: DiscoveryProvider[] | undefined) {
  return (p ?? []).filter((x) => ["available", "connected", "configured"].includes(x.status));
}
