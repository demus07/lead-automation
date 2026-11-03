"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Ban,
  Bookmark,
  Check,
  ChevronLeft,
  ExternalLink as ExternalIcon,
  FileSearch,
  Loader2,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ClaimList } from "@/components/shared/evidence-list";
import { ServiceBadge } from "@/components/shared/score";
import { StatusBadge } from "@/components/shared/status-badge";
import { useCan } from "@/hooks/use-auth";
import { fmtRelative } from "@/lib/format";
import type { ApproveResult, Draft } from "@/lib/types";
import { CompanyBlock, QualitySummary, RailBlock, RecipientBlock } from "./context-panels";
import { ApproveDialog, CommentActionDialog, QUEUE_STATES, useDraftMutations } from "./draft-actions";
import { Letter, diffEdits, valuesFrom, type LetterValues } from "./letter";

type DialogKind = null | "approve" | "reject" | "later" | "regenerate" | "dnc";

export function isTypingTarget(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || !!el.closest("[role=dialog],[role=menu],[role=listbox]");
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="ml-1 hidden h-4 min-w-4 items-center justify-center rounded border border-current/25 px-1 font-sans text-[0.65rem] leading-none opacity-70 lg:inline-flex">
      {children}
    </kbd>
  );
}

export function ReviewDetail({
  draft,
  onApproved,
  onBack,
  showFullEditorLink = true,
}: {
  draft: Draft;
  onApproved: (r: ApproveResult, d: Draft) => void;
  onBack?: () => void;
  showFullEditorLink?: boolean;
}) {
  const canAct = useCan("operator");
  const m = useDraftMutations(draft.id);
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<LetterValues>(() => valuesFrom(draft));
  const [dialog, setDialog] = useState<DialogKind>(null);
  const actionable = canAct && QUEUE_STATES.includes(draft.status);
  const edits = editing ? diffEdits(draft, values) : {};
  const dirty = Object.keys(edits).length > 0;

  // Keyboard: a approve, e edit, r reject, s save for later, Esc cancels editing.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape" && editing && !document.querySelector("[role=dialog]")) {
        setEditing(false);
        setValues(valuesFrom(draft));
        return;
      }
      if (isTypingTarget(e.target) || document.querySelector("[role=dialog]")) return;
      if (!actionable) return;
      const k = e.key.toLowerCase();
      if (k === "a") setDialog("approve");
      else if (k === "e") {
        e.preventDefault();
        setEditing(true);
      } else if (k === "r") setDialog("reject");
      else if (k === "s" && draft.status !== "saved_for_later") setDialog("later");
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [actionable, draft, editing]);

  async function saveEdits() {
    if (!dirty) {
      setEditing(false);
      return;
    }
    await m.edit.mutateAsync(edits);
    setEditing(false);
  }

  const researchId = draft.research_report_id;

  return (
    <div className="space-y-6">
      {/* Title row */}
      <div className="space-y-3">
        {onBack && (
          <Button variant="ghost" size="sm" className="-ml-2 lg:hidden" onClick={onBack}>
            <ChevronLeft /> Queue
          </Button>
        )}
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 space-y-1.5">
            <h2 className="truncate text-xl font-semibold tracking-[-0.02em]">{draft.company?.name ?? "Draft"}</h2>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <StatusBadge kind="draft" value={draft.status} />
              <ServiceBadge service={draft.service} />
              <span>Generated {fmtRelative(draft.created_at)}</span>
              {draft.regeneration_count > 0 && <span>· regenerated {draft.regeneration_count}×</span>}
            </div>
          </div>

          {actionable ? (
            <div className="flex flex-wrap items-center gap-2">
              {editing ? (
                <>
                  <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setValues(valuesFrom(draft)); }}>
                    Cancel
                  </Button>
                  <Button variant="outline" size="sm" onClick={saveEdits} disabled={m.edit.isPending || !dirty}>
                    {m.edit.isPending && <Loader2 className="animate-spin" />}
                    Save changes
                  </Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                  <Pencil /> Edit <Kbd>E</Kbd>
                </Button>
              )}
              {draft.status !== "saved_for_later" && (
                <Button variant="outline" size="sm" onClick={() => setDialog("later")}>
                  <Bookmark /> Later <Kbd>S</Kbd>
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setDialog("reject")}>
                <X /> Reject <Kbd>R</Kbd>
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon-sm" aria-label="More actions">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuItem onSelect={() => setDialog("regenerate")}>
                    <RefreshCw /> Request regeneration
                  </DropdownMenuItem>
                  {researchId && (
                    <DropdownMenuItem asChild>
                      <Link href={`/research/${researchId}`}><FileSearch /> View research</Link>
                    </DropdownMenuItem>
                  )}
                  {showFullEditorLink && (
                    <DropdownMenuItem asChild>
                      <Link href={`/drafts/${draft.id}`}><ExternalIcon /> Open full editor</Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setDialog("dnc")}>
                    <Ban /> Mark do not contact
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <Button
                size="sm"
                className="bg-brand text-brand-foreground hover:bg-brand/90"
                onClick={() => setDialog("approve")}
              >
                <Check /> {dirty ? "Approve with edits" : "Approve"} <Kbd>A</Kbd>
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {researchId && (
                <Button variant="outline" size="sm" asChild>
                  <Link href={`/research/${researchId}`}><FileSearch /> View research</Link>
                </Button>
              )}
              {showFullEditorLink && (
                <Button variant="outline" size="sm" asChild>
                  <Link href={`/drafts/${draft.id}`}>Open draft</Link>
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-8 2xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-6">
          <Letter draft={draft} editing={editing} values={values} onChange={setValues} />
          {(draft.personalisation_explanation || draft.recommended_offer) && (
            <div className="grid gap-4 text-sm md:grid-cols-2">
              {draft.personalisation_explanation && (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Why it&apos;s personalised</p>
                  <p className="text-pretty">{draft.personalisation_explanation}</p>
                </div>
              )}
              {draft.recommended_offer && (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Recommended offer</p>
                  <p className="text-pretty">{draft.recommended_offer}</p>
                </div>
              )}
            </div>
          )}
          <RailBlock title="Claims and evidence">
            <p className="-mt-1 text-xs text-muted-foreground">Every factual claim the draft makes, with the sources it was checked against.</p>
            <ClaimList claims={draft.evidence} />
          </RailBlock>
        </div>

        <aside className="min-w-0 space-y-5 2xl:border-l 2xl:pl-6">
          <RailBlock title="Quality">
            <QualitySummary score={draft.quality_score} report={draft.quality_report} />
          </RailBlock>
          <RecipientBlock draft={draft} />
          <CompanyBlock draft={draft} researchSummary={draft.research_summary} researchId={researchId} />
        </aside>
      </div>

      {actionable && (
        <>
          <ApproveDialog
            draft={draft}
            open={dialog === "approve"}
            onOpenChange={(v) => setDialog(v ? "approve" : null)}
            edits={dirty ? edits : null}
            onApproved={(r) => {
              setEditing(false);
              onApproved(r, draft);
            }}
          />
          <CommentActionDialog
            open={dialog === "reject"}
            onOpenChange={(v) => setDialog(v ? "reject" : null)}
            title="Reject this draft?"
            description="The company returns to Qualified so a new draft can be generated later."
            confirmLabel="Reject draft"
            placeholder="What was wrong? (optional, helps the next draft)"
            destructive
            onConfirm={(c) => m.reject.mutateAsync(c)}
          />
          <CommentActionDialog
            open={dialog === "later"}
            onOpenChange={(v) => setDialog(v ? "later" : null)}
            title="Save for later?"
            description="Moves the draft to the Later tab. You can approve it from there any time."
            confirmLabel="Save for later"
            placeholder="Note to self (optional)"
            onConfirm={(c) => m.saveForLater.mutateAsync(c)}
          />
          <CommentActionDialog
            open={dialog === "regenerate"}
            onOpenChange={(v) => setDialog(v ? "regenerate" : null)}
            title="Request regeneration"
            description="The AI writes a new version using your comment. This version is superseded if it succeeds."
            confirmLabel="Regenerate draft"
            placeholder="e.g. Shorter, lead with the hiring signal, drop the pricing line"
            limitedModeHint
            onConfirm={(c) => m.regenerate.mutateAsync(c)}
          />
          <CommentActionDialog
            open={dialog === "dnc"}
            onOpenChange={(v) => setDialog(v ? "dnc" : null)}
            title={`Never contact ${draft.company?.name ?? "this company"}?`}
            description="Adds the contact's email and the company domain to the suppression list. Drafts are blocked and the company is marked do not contact."
            confirmLabel="Mark do not contact"
            placeholder="Reason (optional)"
            destructive
            onConfirm={(c) => m.dnc.mutateAsync(c)}
          />
        </>
      )}
    </div>
  );
}
