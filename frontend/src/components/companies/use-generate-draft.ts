"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api, ApiError } from "@/lib/api";
import type { Draft } from "@/lib/types";

type Result = { draft: Draft } | { limited: string };

/**
 * POST /drafts/generate. A 503 (no LLM configured) is limited mode, not a failure:
 * show it as a warning with a link to AI settings instead of an error toast.
 */
export function useGenerateDraft(companyId: string) {
  const router = useRouter();
  return useApiMutation<{ contact_id?: string | null }, Result>(
    async (v) => {
      try {
        const draft = await api.post<Draft>("/drafts/generate", { company_id: companyId, contact_id: v.contact_id ?? null });
        return { draft };
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) return { limited: e.message };
        throw e;
      }
    },
    {
      errorTitle: "Couldn't generate a draft",
      success: false,
      invalidate: [["company", companyId], ["approvals"]],
      onSuccess: (r) => {
        if ("limited" in r) {
          toast.warning("Drafting needs an AI provider", {
            description: `${r.limited}. Configure one in AI settings — research and scoring keep working without it.`,
            action: { label: "AI settings", onClick: () => router.push("/settings/ai") },
          });
          return;
        }
        const ok = r.draft.status === "pending_approval";
        toast.success(ok ? "Draft generated and queued for approval" : "Draft generated — it needs review", {
          action: { label: "Open draft", onClick: () => router.push(`/drafts/${r.draft.id}`) },
        });
      },
    },
  );
}
