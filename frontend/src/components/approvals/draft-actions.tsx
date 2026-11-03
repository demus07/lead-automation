"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Notice } from "@/components/shared/notice";
import { EmailStatusBadge } from "@/components/shared/status-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { ApiError, api } from "@/lib/api";
import type { ApproveResult, Draft, DraftStatus, EmailAccountsResponse } from "@/lib/types";

export const QUEUE_STATES: DraftStatus[] = ["pending_approval", "needs_review", "saved_for_later"];

export interface DraftEdits {
  subject?: string;
  body?: string;
  linkedin_connection_note?: string;
  linkedin_message?: string;
  comment?: string;
}

/** All draft mutations. Each invalidates the approval queue, the sidebar badge and the draft itself. */
export function useDraftMutations(draftId: string | undefined) {
  const invalidate = [["approvals"], ["drafts"], ["draft", draftId], ["dashboard"]];
  const edit = useApiMutation((v: DraftEdits) => api.patch<Draft>(`/drafts/${draftId}`, v), {
    success: "Changes saved — quality re-checked",
    invalidate,
  });
  const approve = useApiMutation(
    (v: { email_account_id?: string | null; edits?: DraftEdits | null; override_quality?: boolean; comment?: string }) =>
      api.post<ApproveResult>(`/approvals/${draftId}/approve`, v),
    { success: false, invalidate },
  );
  const reject = useApiMutation((comment: string) => api.post<Draft>(`/approvals/${draftId}/reject`, { comment: comment || null }), {
    success: "Draft rejected",
    invalidate,
  });
  const saveForLater = useApiMutation(
    (comment: string) => api.post<Draft>(`/approvals/${draftId}/save-for-later`, { comment: comment || null }),
    { success: "Saved for later", invalidate },
  );
  const regenerate = useApiMutation(
    (comment: string) => api.post<Draft>(`/approvals/${draftId}/regenerate`, { comment: comment || null }),
    { success: "New version generated", invalidate, errorTitle: "Regeneration didn't run" },
  );
  const dnc = useApiMutation((comment: string) => api.post<Draft>(`/approvals/${draftId}/do-not-contact`, { comment: comment || null }), {
    success: "Marked do not contact",
    invalidate: [...invalidate, ["companies"], ["contacts"]],
  });
  return { edit, approve, reject, saveForLater, regenerate, dnc };
}

export function useEmailAccounts() {
  return useQuery({
    queryKey: ["email", "accounts"],
    queryFn: () => api.get<EmailAccountsResponse>("/email/accounts"),
    staleTime: 60_000,
  });
}

const DEFAULT_ACCOUNT = "__default__";

export function ApproveDialog({
  draft,
  open,
  onOpenChange,
  edits,
  onApproved,
}: {
  draft: Draft;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  edits?: DraftEdits | null;
  onApproved: (r: ApproveResult) => void;
}) {
  const { approve } = useDraftMutations(draft.id);
  const accounts = useEmailAccounts();
  const [account, setAccount] = useState(DEFAULT_ACCOUNT);
  const [override, setOverride] = useState(false);
  const failed = draft.quality_report ? draft.quality_report.passed === false : false;
  const connected = (accounts.data?.accounts ?? []).filter((a) => a.status === "connected");
  const def = connected.find((a) => a.is_default);
  const noEmail = !draft.contact?.email;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setOverride(false);
        onOpenChange(v);
      }}
      title="Approve this draft?"
      description="Creates an unsent draft in your mailbox — you send it yourself. Nothing is emailed by this app."
      confirmLabel={failed ? "Approve anyway" : "Approve and create draft"}
      confirmDisabled={noEmail || (failed && !override)}
      onConfirm={async () => {
        const r = await approve.mutateAsync({
          email_account_id: account === DEFAULT_ACCOUNT ? null : account,
          edits: edits && Object.keys(edits).length ? edits : null,
          override_quality: failed ? override : false,
        });
        onApproved(r);
      }}
    >
      <div className="space-y-4 text-sm">
        <div className="space-y-1 rounded-lg border px-3 py-2.5">
          <p className="text-xs text-muted-foreground">To</p>
          {draft.contact ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{draft.contact.full_name}</span>
              <span className="text-muted-foreground">{draft.contact.email ?? "no email"}</span>
              {draft.contact.email && <EmailStatusBadge status={draft.contact.email_status} />}
            </div>
          ) : (
            <p className="text-muted-foreground">No contact selected</p>
          )}
          <p className="truncate pt-1 text-xs text-muted-foreground">Subject: {edits?.subject ?? draft.subject}</p>
        </div>
        {noEmail && <Notice tone="danger" title="This draft has no recipient email">Add an email to the contact before approving.</Notice>}
        {edits && Object.keys(edits).length > 0 && (
          <p className="text-xs text-muted-foreground">Your unsaved edits will be saved and approved together.</p>
        )}
        <div className="space-y-1.5">
          <Label className="text-sm">Mailbox</Label>
          {connected.length ? (
            <Select value={account} onValueChange={setAccount}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_ACCOUNT}>Default{def ? ` (${def.email})` : ""}</SelectItem>
                {connected.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.email} · {a.provider === "gmail" ? "Gmail" : "Outlook"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <p className="text-xs text-muted-foreground">
              No mailbox connected. The draft is approved now and created automatically once you{" "}
              <Link href="/settings/integrations" className="underline underline-offset-4">connect Gmail or Outlook</Link>.
            </p>
          )}
        </div>
        {failed && (
          <div className="tone tone-warning space-y-2 rounded-lg border p-3">
            <p className="font-medium text-foreground">
              Below the quality threshold ({draft.quality_score ?? "—"} / {draft.quality_report?.threshold ?? "—"})
            </p>
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
              {(draft.quality_report?.issues ?? []).slice(0, 4).map((i, n) => (
                <li key={n}>{i.text}</li>
              ))}
            </ul>
            <label className="flex items-start gap-2 text-foreground">
              <Checkbox checked={override} onCheckedChange={(v) => setOverride(v === true)} className="mt-0.5" />
              <span className="text-sm">I&apos;ve read these issues and want to approve anyway.</span>
            </label>
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}

/** Reject / save for later / regenerate / do-not-contact share this: an optional or required comment. */
export function CommentActionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  placeholder,
  required,
  destructive,
  onConfirm,
  limitedModeHint,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel: string;
  placeholder?: string;
  required?: boolean;
  destructive?: boolean;
  onConfirm: (comment: string) => Promise<unknown>;
  limitedModeHint?: boolean;
}) {
  const [comment, setComment] = useState("");
  const [unavailable, setUnavailable] = useState<string | null>(null);
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setComment("");
          setUnavailable(null);
        }
        onOpenChange(v);
      }}
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      confirmDisabled={required && !comment.trim()}
      onConfirm={async () => {
        try {
          await onConfirm(comment.trim());
          setComment("");
        } catch (e) {
          if (limitedModeHint && e instanceof ApiError && e.status === 503) setUnavailable(e.message);
          throw e;
        }
      }}
    >
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={placeholder}
        rows={3}
        maxLength={2000}
        aria-label="Comment"
      />
      {unavailable && (
        <Notice tone="warning" title="Limited mode: no AI model is configured" action={{ href: "/settings/ai", label: "Configure AI" }}>
          {unavailable}
        </Notice>
      )}
    </ConfirmDialog>
  );
}
