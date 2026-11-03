"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { Notice } from "@/components/shared/notice";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { AgencyProfileForm } from "@/components/settings/agency-profile-form";
import { useSaveSettings, useSettingsSection } from "@/components/settings/use-settings";
import { useCan } from "@/hooks/use-auth";
import type { AgencyProfile } from "@/lib/types";

export default function AgencySettingsPage() {
  const isAdmin = useCan("admin");
  const q = useSettingsSection<AgencyProfile>("agency_profile");
  const save = useSaveSettings<AgencyProfile>("agency_profile", "Agency profile saved");

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Agency profile"
        description="What every research brief, score and draft knows about your agency. Changes apply to drafts generated from now on."
        actions={
          <Button variant="outline" asChild>
            <Link href="/onboarding">Open setup wizard</Link>
          </Button>
        }
      />
      {!isAdmin && <Notice tone="warning" className="mb-6" title="Read only">Only admins can change the agency profile.</Notice>}
      {q.error ? (
        <ErrorState error={q.error} retry={() => q.refetch()} />
      ) : !q.data ? (
        <PageSkeleton />
      ) : (
        <AgencyProfileForm profile={q.data} disabled={!isAdmin} onSubmit={(v) => save.mutateAsync(v)} />
      )}
    </div>
  );
}
