"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  ClipboardList,
  Compass,
  Inbox,
  KanbanSquare,
  LayoutDashboard,
  MailCheck,
  Megaphone,
  MessagesSquare,
  Plug,
  ScrollText,
  ShieldOff,
  SlidersHorizontal,
  UserRoundSearch,
  Users,
  Workflow,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import type { Page, Draft } from "@/lib/types";

type Item = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; admin?: boolean; badge?: "approvals" };

const WORK: Item[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/approvals", label: "Approvals", icon: MailCheck, badge: "approvals" },
  { href: "/pipeline", label: "Pipeline", icon: KanbanSquare },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/contacts", label: "Contacts", icon: UserRoundSearch },
  { href: "/research", label: "Research", icon: ClipboardList },
  { href: "/discovery", label: "Discovery", icon: Compass },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/conversations", label: "Conversations", icon: MessagesSquare },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/automation", label: "Automation", icon: Workflow },
];

const SETTINGS: Item[] = [
  { href: "/settings/agency", label: "Agency", icon: SlidersHorizontal },
  { href: "/settings/ai", label: "AI", icon: Bot },
  { href: "/settings/integrations", label: "Integrations", icon: Plug },
  { href: "/settings/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/settings/users", label: "Users", icon: Users },
  { href: "/suppression", label: "Suppression", icon: ShieldOff },
  { href: "/settings/audit", label: "Audit", icon: ScrollText, admin: true },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  if (href === "/analytics") return pathname === "/analytics" || pathname.startsWith("/analytics/");
  return pathname === href || pathname.startsWith(href + "/");
}

export function AppSidebar() {
  const pathname = usePathname();
  const isAdmin = useCan("admin");
  const { setOpenMobile } = useSidebar();
  const queue = useQuery({
    queryKey: ["approvals", "badge"],
    queryFn: () => api.get<Page<Draft> & { counts: Record<string, number> }>("/approvals/queue", { state: "pending", page_size: 1 }),
    refetchInterval: 60_000,
  });
  const pending = queue.data?.counts?.pending_approval ?? 0;

  const render = (items: Item[]) =>
    items
      .filter((i) => !i.admin || isAdmin)
      .map((i) => (
        <SidebarMenuItem key={i.href}>
          <SidebarMenuButton asChild isActive={isActive(pathname, i.href)} tooltip={i.label}>
            <Link href={i.href} onClick={() => setOpenMobile(false)}>
              <i.icon className="size-4" />
              <span>{i.label}</span>
            </Link>
          </SidebarMenuButton>
          {i.badge === "approvals" && pending > 0 && (
            <SidebarMenuBadge className="bg-brand text-brand-foreground! peer-data-active/menu-button:text-brand-foreground!">
              {pending > 99 ? "99+" : pending}
            </SidebarMenuBadge>
          )}
        </SidebarMenuItem>
      ));

  return (
    <Sidebar collapsible="icon" variant="sidebar">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Link href="/" className="flex items-center gap-2.5 rounded-md px-1 py-1 outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
          <Logo />
          <span className="truncate text-[0.95rem] font-semibold tracking-[-0.02em] group-data-[collapsible=icon]:hidden">
            Growth Engine
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>{render(WORK)}</SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Settings</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>{render(SETTINGS)}</SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="px-3 pb-3">
        <div className="flex items-center gap-2 rounded-md px-1 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <Inbox className="size-3.5 shrink-0" />
          <span>Never sends email. Approvals create unsent drafts.</span>
        </div>
        <div className="hidden group-data-[collapsible=icon]:flex justify-center text-muted-foreground" title="Never sends email">
          <Activity className="size-4" />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

/** Mark: two independent bars (the two services) rising from one baseline. */
export function Logo({ className = "size-7" }: { className?: string }) {
  return (
    <span className={`${className} inline-flex shrink-0 items-center justify-center rounded-lg bg-foreground text-background`} aria-hidden>
      <svg viewBox="0 0 24 24" className="size-4" fill="none">
        <rect x="5" y="9" width="4.5" height="10" rx="1.2" fill="currentColor" opacity="0.55" />
        <rect x="14.5" y="5" width="4.5" height="14" rx="1.2" fill="var(--brand)" />
      </svg>
    </span>
  );
}
