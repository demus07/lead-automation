"use client";

import Link from "next/link";
import { Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { Notice } from "@/components/shared/notice";
import { Section } from "@/components/shared/section";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { useCampaigns, useProviders } from "@/components/campaigns/queries";
import { CsvImport } from "@/components/discovery/csv-import";
import { SearchHistoryTable } from "@/components/discovery/history-table";
import { ManualSearch } from "@/components/discovery/manual-search";
import { ProvidersPanel } from "@/components/discovery/providers-panel";
import { useCan } from "@/hooks/use-auth";

export default function DiscoveryPage() {
  const providers = useProviders();
  const campaigns = useCampaigns();
  const canRun = useCan("operator");
  const isAdmin = useCan("admin");

  if (providers.isLoading) return <PageSkeleton />;
  if (providers.error || !providers.data) return <ErrorState error={providers.error} retry={() => providers.refetch()} />;
  const d = providers.data;
  const camps = campaigns.data ?? [];

  return (
    <>
      <PageHeader
        title="Discovery"
        description="Find companies from public directories, hiring threads, feeds and web search, or import your own list."
        meta={
          <span className="text-sm text-muted-foreground tabular-nums">
            {d.searches_today} of {d.daily_search_quota ?? "∞"} web searches used today
          </span>
        }
        actions={
          isAdmin && (
            <Button variant="outline" size="sm" asChild>
              <Link href="/settings/integrations"><Settings2 /> Configure sources</Link>
            </Button>
          )
        }
      />

      {d.limited_mode && (
        <Notice
          tone="warning"
          title="Limited mode"
          action={isAdmin ? { href: "/settings/integrations", label: "Add a search provider" } : undefined}
          className="mb-6"
        >
          {d.limited_mode_reason}
        </Notice>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <ManualSearch providers={d.providers} campaigns={camps} canRun={canRun} />
        <CsvImport campaigns={camps} canRun={canRun} />
      </div>

      <Section title="Sources" description="What discovery can use right now." className="mt-6">
        <ProvidersPanel providers={d.providers} />
      </Section>

      <section className="mt-8 space-y-3">
        <h2 className="text-[0.95rem] font-semibold">Search history</h2>
        <SearchHistoryTable providers={d.providers} campaigns={camps} />
      </section>
    </>
  );
}
