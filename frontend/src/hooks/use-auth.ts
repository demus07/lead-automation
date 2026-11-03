"use client";

import { useQuery } from "@tanstack/react-query";
import { api, setCsrfToken } from "@/lib/api";
import type { Role, Session } from "@/lib/types";

const RANK: Record<Role, number> = { viewer: 0, operator: 1, admin: 2 };

export function useSession() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const s = await api.get<Session>("/auth/me");
      setCsrfToken(s.csrf_token);
      return s;
    },
    staleTime: 5 * 60_000,
  });
}

/** Role check for hiding/disabling actions. The backend enforces the same rules. */
export function useCan(min: Role): boolean {
  const { data } = useSession();
  if (!data) return false;
  return RANK[data.user.role] >= RANK[min];
}
