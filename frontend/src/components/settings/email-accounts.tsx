"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Mail, RefreshCw, Star, Unplug } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CopyButton } from "@/components/shared/copy-button";
import { Notice } from "@/components/shared/notice";
import { ErrorState, TableSkeleton } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan } from "@/hooks/use-auth";
import { api, errorMessage } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import { jobStartedToast } from "@/lib/jobs";
import type { EmailAccount, EmailAccountsResponse, Msg } from "@/lib/types";

const PROVIDER_LABEL: Record<string, string> = { gmail: "Gmail", outlook: "Microsoft Outlook" };

export function EmailAccountsPanel() {
  const isAdmin = useCan("admin");
  const isOperator = useCan("operator");
  const q = useQuery({ queryKey: ["email", "accounts"], queryFn: () => api.get<EmailAccountsResponse>("/email/accounts") });
  const [connecting, setConnecting] = useState<string | null>(null);

  const setDefault = useApiMutation((id: string) => api.post<Msg>(`/email/accounts/${id}/default`), {
    success: (r) => r.message || "Default account set",
    invalidate: [["email"], ["integrations"]],
  });
  const sync = useApiMutation((id: string) => api.post<{ job_id: string; status: string }>(`/email/accounts/${id}/sync`), {
    onSuccess: (r) => jobStartedToast("Sync started", r),
    invalidate: [["email"]],
  });
  const disconnect = useApiMutation((id: string) => api.delete<Msg>(`/email/accounts/${id}`), {
    success: (r) => r.message || "Account disconnected",
    invalidate: [["email"], ["integrations"], ["dashboard"]],
  });

  async function connect(provider: string) {
    setConnecting(provider);
    try {
      const { url } = await api.get<{ url: string }>(`/email/oauth/${provider}/start`);
      window.location.href = url;
    } catch (e) {
      toast.error(`Couldn't start ${PROVIDER_LABEL[provider] ?? provider} sign-in`, { description: errorMessage(e) });
      setConnecting(null);
    }
  }

  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <TableSkeleton rows={3} cols={3} />;
  const { accounts, providers } = q.data;

  return (
    <div className="space-y-5">
      <Notice tone="neutral" title="Sending is disabled">
        The app only creates unsent drafts in your mailbox and reads replies. You send every email yourself.
      </Notice>

      {accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">No mailbox connected yet. Approved drafts wait until you connect one.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {accounts.map((a: EmailAccount) => (
            <li key={a.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-1 items-start gap-3">
                <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium">{a.email}</span>
                    <StatusBadge kind="integration" value={a.status} />
                    {a.is_default && <ToneBadge tone="brand">Default</ToneBadge>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {PROVIDER_LABEL[a.provider] ?? a.provider}
                    {a.display_name ? `, ${a.display_name}` : ""}. Last synced {fmtRelative(a.last_synced_at)}
                  </p>
                  {a.last_error && <p className="text-xs text-destructive">{a.last_error}</p>}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {isAdmin && !a.is_default && (
                  <Button variant="outline" size="sm" onClick={() => setDefault.mutate(a.id)} disabled={setDefault.isPending}>
                    <Star /> Make default
                  </Button>
                )}
                {isOperator && (
                  <Button variant="outline" size="sm" onClick={() => sync.mutate(a.id)} disabled={sync.isPending}>
                    <RefreshCw /> Sync now
                  </Button>
                )}
                {isAdmin && (
                  <ConfirmDialog
                    trigger={
                      <Button variant="ghost" size="sm">
                        <Unplug /> Disconnect
                      </Button>
                    }
                    title={`Disconnect ${a.email}?`}
                    description="Stored tokens are deleted. Approved drafts won't reach this mailbox until you reconnect. You can also revoke access in your Google or Microsoft account."
                    confirmLabel="Disconnect"
                    destructive
                    onConfirm={() => disconnect.mutateAsync(a.id)}
                  />
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {providers.map((p) => (
          <div key={p.key} className="space-y-3 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{PROVIDER_LABEL[p.key] ?? p.key}</span>
              {p.configured ? <ToneBadge tone="success">OAuth ready</ToneBadge> : <ToneBadge tone="neutral">Not configured</ToneBadge>}
            </div>
            {p.configured ? (
              isAdmin ? (
                <Button size="sm" onClick={() => connect(p.key)} disabled={connecting !== null}>
                  {connecting === p.key && <Loader2 className="animate-spin" />}
                  Connect {PROVIDER_LABEL[p.key] ?? p.key}
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground">An admin can connect a mailbox.</p>
              )
            ) : (
              <p className="text-xs text-muted-foreground">
                Set <code className="font-mono">{p.requires}</code> in the server <code className="font-mono">.env</code> and restart the API.
              </p>
            )}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Authorised redirect URI</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded border bg-muted px-2 py-1 font-mono text-xs">{p.redirect_uri}</code>
                <CopyButton text={p.redirect_uri} size="xs" label="Copy" />
              </div>
            </div>
            {p.scopes?.length > 0 && (
              <p className="text-xs break-words text-muted-foreground">Scopes: {p.scopes.join(", ")}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
