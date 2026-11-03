"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Ban, FileSearch, Gauge, Loader2, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { ServiceBadge, DualScore } from "@/components/shared/score";
import { ExternalLink } from "@/components/shared/external-link";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Field } from "@/components/shared/field";
import { Notice } from "@/components/shared/notice";
import { OverviewTab } from "@/components/companies/overview-tab";
import {
  ContactsTab,
  DraftsTab,
  InteractionsTab,
  NotesTab,
  OpportunityTab,
  ResearchTab,
  SignalsTab,
  SourcesTab,
  TasksTab,
} from "@/components/companies/detail-tabs";
import { useGenerateDraft } from "@/components/companies/use-generate-draft";
import type { CompanyDetail } from "@/components/companies/types";
import { useCan } from "@/hooks/use-auth";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { api } from "@/lib/api";
import { jobStartedToast } from "@/lib/jobs";
import type { AIStatus, Campaign, Company } from "@/lib/types";

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const canEdit = useCan("operator");
  const [tab, setTab] = useState("overview");
  const [dncOpen, setDncOpen] = useState(false);
  const [dncReason, setDncReason] = useState("");

  const q = useQuery({
    queryKey: ["company", id],
    queryFn: () => api.get<CompanyDetail>(`/companies/${id}`),
  });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get<Campaign[]>("/campaigns") });
  const ai = useQuery({ queryKey: ["ai", "status"], queryFn: () => api.get<AIStatus & { mode: string }>("/ai/status"), staleTime: 60_000 });

  const research = useApiMutation(() => api.post<{ job_id: string; status: string }>(`/research/company/${id}/run`), {
    success: false,
    invalidate: [["company", id]],
    onSuccess: (r) => jobStartedToast("Research started", r),
  });
  const rescore = useApiMutation(() => api.post<{ job_id: string; status: string }>(`/opportunities/company/${id}/score`), {
    success: false,
    invalidate: [["company", id]],
    onSuccess: (r) => jobStartedToast("Scoring started", r),
  });
  const gen = useGenerateDraft(id);
  const dnc = useApiMutation(
    () => api.post<Company>(`/companies/${id}/status`, { status: "DO_NOT_CONTACT", reason: dncReason || null }),
    { success: "Marked do not contact", invalidate: [["company", id], ["companies"]] },
  );

  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data;
  const c = d.company;
  const suppressed = c.status === "DO_NOT_CONTACT";
  const limited = ai.data && !ai.data.available;
  const openTasks = d.tasks.filter((t) => t.status === "open").length;

  const tabs: { value: string; label: string; count?: number }[] = [
    { value: "overview", label: "Overview" },
    { value: "contacts", label: "Contacts", count: d.contacts.length },
    { value: "research", label: "Research" },
    { value: "signals", label: "Signals", count: d.signals.length },
    { value: "opportunity", label: "Opportunity" },
    { value: "drafts", label: "Drafts", count: d.drafts.length },
    { value: "interactions", label: "Interactions", count: d.interactions.length },
    { value: "notes", label: "Notes", count: d.notes.length },
    { value: "tasks", label: "Tasks", count: openTasks },
    { value: "sources", label: "Sources", count: d.sources.length },
  ];

  return (
    <>
      <PageHeader
        back={{ href: "/companies", label: "Companies" }}
        title={c.name}
        meta={
          <>
            <StatusBadge kind="lead" value={c.status} />
            <ServiceBadge service={c.recommended_service} />
            <DualScore compact website={c.website_score} brain={c.brain_score} recommended={c.recommended_service} />
            {c.website && <ExternalLink href={c.website} className="text-sm" />}
          </>
        }
        actions={
          canEdit && (
            <>
              <Button variant="outline" disabled={research.isPending} onClick={() => research.mutate()}>
                {research.isPending ? <Loader2 className="animate-spin" /> : <FileSearch />} Run research
              </Button>
              <Button variant="outline" disabled={rescore.isPending} onClick={() => rescore.mutate()}>
                {rescore.isPending ? <Loader2 className="animate-spin" /> : <Gauge />} Rescore
              </Button>
              <Button
                disabled={gen.isPending || suppressed}
                onClick={() => gen.mutate({})}
                title={limited ? "No AI provider configured — drafting is unavailable in limited mode" : undefined}
              >
                {gen.isPending ? <Loader2 className="animate-spin" /> : <PenLine />} Generate draft
              </Button>
              {!suppressed && (
                <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => { setDncReason(""); setDncOpen(true); }}>
                  <Ban /> Do not contact
                </Button>
              )}
            </>
          )
        }
      />

      {suppressed && (
        <Notice tone="danger" title="Do not contact" className="mb-6">
          This company&apos;s domain is on the suppression list. Drafts can&apos;t be generated or approved.
        </Notice>
      )}
      {!suppressed && limited && canEdit && (
        <Notice tone="info" className="mb-6" action={{ href: "/settings/ai", label: "Configure AI" }}>
          Limited mode: research and scoring use deterministic checks; drafts need an AI provider.
        </Notice>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
          <TabsList variant="line" className="mb-6 w-max border-b pb-1">
            {tabs.map((t) => (
              <TabsTrigger key={t.value} value={t.value} className="px-2.5">
                {t.label}
                {!!t.count && <span className="ml-0.5 text-xs tabular-nums text-muted-foreground">{t.count}</span>}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="overview"><OverviewTab d={d} canEdit={canEdit} campaigns={campaigns.data ?? []} /></TabsContent>
        <TabsContent value="contacts"><ContactsTab d={d} canEdit={canEdit && !suppressed} /></TabsContent>
        <TabsContent value="research"><ResearchTab d={d} canEdit={canEdit} /></TabsContent>
        <TabsContent value="signals"><SignalsTab d={d} /></TabsContent>
        <TabsContent value="opportunity"><OpportunityTab d={d} canEdit={canEdit} /></TabsContent>
        <TabsContent value="drafts"><DraftsTab d={d} canEdit={canEdit && !suppressed} /></TabsContent>
        <TabsContent value="interactions"><InteractionsTab d={d} /></TabsContent>
        <TabsContent value="notes"><NotesTab d={d} canEdit={canEdit} /></TabsContent>
        <TabsContent value="tasks"><TasksTab d={d} canEdit={canEdit} /></TabsContent>
        <TabsContent value="sources"><SourcesTab d={d} /></TabsContent>
      </Tabs>

      <ConfirmDialog
        open={dncOpen}
        onOpenChange={setDncOpen}
        title={`Mark ${c.name} as do not contact?`}
        description={`${c.domain ?? "The domain"} goes on the suppression list. Pending drafts are blocked and no new outreach can be generated. This can only be undone by an admin on the Suppression page.`}
        confirmLabel="Mark do not contact"
        destructive
        onConfirm={() => dnc.mutateAsync()}
      >
        <Field label="Reason" htmlFor="dnc-reason" hint="Optional — e.g. asked not to be contacted, existing client">
          <Textarea id="dnc-reason" rows={2} value={dncReason} onChange={(e) => setDncReason(e.target.value)} />
        </Field>
      </ConfirmDialog>
    </>
  );
}
