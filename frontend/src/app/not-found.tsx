import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-5xl font-semibold tracking-[-0.04em] tabular-nums">404</p>
      <p className="text-sm text-muted-foreground">This page doesn&apos;t exist or was moved.</p>
      <Button asChild variant="outline">
        <Link href="/">Go to overview</Link>
      </Button>
    </main>
  );
}
