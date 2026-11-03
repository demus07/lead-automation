"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function CopyButton({ text, label = "Copy", size = "sm" }: { text: string; label?: string; size?: "sm" | "xs" | "default" }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      variant="outline"
      size={size}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          toast.success("Copied to clipboard");
          setTimeout(() => setDone(false), 1500);
        } catch {
          toast.error("Couldn't access the clipboard");
        }
      }}
    >
      {done ? <Check /> : <Copy />}
      {label}
    </Button>
  );
}
