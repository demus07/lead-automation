"use client";

import { Loader2 } from "lucide-react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useSession } from "@/hooks/use-auth";
import { ErrorState } from "@/components/shared/states";
import { ApiError } from "@/lib/api";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  if (session.isLoading || (session.error instanceof ApiError && session.error.status === 401)) {
    return (
      <div className="flex min-h-svh items-center justify-center text-muted-foreground" aria-busy="true">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }
  if (session.error) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <ErrorState error={session.error} retry={() => session.refetch()} title="Can't reach the API" />
      </div>
    );
  }
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader />
        <div className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8 md:py-8">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
