"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmDialogProps {
  /** Element that opens the dialog (uncontrolled). */
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  /** Ask the user to type this text before confirming (for irreversible actions). */
  requireText?: string;
  /** Extra form content (e.g. a reason field). */
  children?: React.ReactNode;
  /** Disable confirm (e.g. until a required field is filled). */
  confirmDisabled?: boolean;
  onConfirm: () => unknown | Promise<unknown>;
}

/** Confirmation for destructive or consequential actions. Stays open (spinner) while onConfirm runs. */
export function ConfirmDialog({
  trigger,
  open: openProp,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive,
  requireText,
  children,
  confirmDisabled,
  onConfirm,
}: ConfirmDialogProps) {
  const [inner, setInner] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const open = openProp ?? inner;
  const setOpen = (v: boolean) => {
    if (busy) return;
    if (!v) setTyped("");
    onOpenChange?.(v);
    if (openProp === undefined) setInner(v);
  };
  const blocked = confirmDisabled || (requireText ? typed.trim() !== requireText : false);

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
      setBusy(false);
      setOpen(false);
    } catch {
      // Error toasts come from the mutation; keep dialog open so the user can retry.
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription asChild><div className="text-sm text-muted-foreground">{description}</div></DialogDescription>}
        </DialogHeader>
        {children}
        {requireText && (
          <div className="space-y-1.5">
            <Label htmlFor="confirm-text" className="text-xs text-muted-foreground">
              Type <span className="font-semibold text-foreground">{requireText}</span> to confirm
            </Label>
            <Input id="confirm-text" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            className={destructive ? "bg-destructive text-white hover:bg-destructive/90 dark:bg-destructive dark:hover:bg-destructive/90" : undefined}
            onClick={confirm}
            disabled={busy || blocked}
          >
            {busy && <Loader2 className="animate-spin" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
