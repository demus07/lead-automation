"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useSession } from "@/hooks/use-auth";
import { api, setCsrfToken } from "@/lib/api";
import { humanize } from "@/lib/format";

export function AppHeader() {
  const { data } = useSession();
  const { theme, setTheme } = useTheme();
  const router = useRouter();
  const qc = useQueryClient();
  const user = data?.user;
  const initials = (user?.full_name || user?.email || "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  async function signOut() {
    try {
      await api.post("/auth/logout");
    } finally {
      setCsrfToken(null);
      qc.clear();
      router.replace("/login");
    }
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/70 md:px-6">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
      <div className="flex-1" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Theme">
            <Sun className="dark:hidden" />
            <Moon className="hidden dark:block" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
            <DropdownMenuRadioItem value="light"><Sun /> Light</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark"><Moon /> Dark</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system"><Monitor /> System</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 gap-2 px-1.5" aria-label="Account">
            <span className="flex size-6 items-center justify-center rounded-full bg-secondary text-[0.7rem] font-semibold">{initials}</span>
            <span className="hidden max-w-40 truncate text-sm sm:inline">{user?.full_name || user?.email}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="font-normal">
            <div className="truncate text-sm font-medium">{user?.full_name || "Signed in"}</div>
            <div className="truncate text-xs text-muted-foreground">{user?.email}</div>
            <div className="mt-1 text-xs text-muted-foreground">Role: {humanize(user?.role)}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/settings/users#password"><KeyRound /> Change password</Link>
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={signOut}>
            <LogOut /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
