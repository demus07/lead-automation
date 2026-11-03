"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Check, Circle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { Notice } from "@/components/shared/notice";
import { ErrorState, PageSkeleton } from "@/components/shared/states";
import { AgencyProfileForm, type AgencySectionKey } from "@/components/settings/agency-profile-form";
import { EmailAccountsPanel } from "@/components/settings/email-accounts";
import { LLMForm, TestConnection } from "@/components/settings/llm-form";
import { SearchProviderForm } from "@/components/settings/search-provider-form";
import { useSaveSettings, useSettingsSection } from "@/components/settings/use-settings";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import type { AgencyProfile, DiscoverySettings, EmailAccountsResponse, LLMSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = {
  key: string;
  title: string;
  intro: string;
  sections?: AgencySectionKey[];
};

const STEPS: Step[] = [
  { key: "basics", title: "Agency", intro: "Start with who you are. This is the context every agent works from.", sections: ["basics"] },
  {
    key: "services",
    title: "Services and targeting",
    intro: "Describe the two services and the clients you want. Each lead is scored for both, independently.",
    sections: ["services", "targeting"],
  },
  {
    key: "proof",
    title: "Proof",
    intro: "Case studies and testimonials the writer may reference. Nothing here is quoted unless it's real and approved.",
    sections: ["proof"],
  },
  {
    key: "voice",
    title: "Voice and sender",
    intro: "How drafts sound, who they're from and what they ask for.",
    sections: ["voice", "sender"],
  },
  {
    key: "email",
    title: "Mailbox",
    intro: "Connect Gmail or Outlook so approved drafts appear in your drafts folder. You can skip this and connect later.",
  },
  {
    key: "search",
    title: "Search provider",
    intro: "Optional. Without one, discovery uses public directories, hiring threads and RSS feeds.",
  },
  {
    key: "ai",
    title: "AI provider",
    intro: "Optional. Without one the app runs in limited mode and can't write drafts.",
  },
  { key: "finish", title: "Finish", intro: "Review what's set up. You can change everything later in Settings." },
];

export default function OnboardingPage() {
  const router = useRouter();
  const isAdmin = useCan("admin");
  const [step, setStep] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const profile = useSettingsSection<AgencyProfile>("agency_profile");
  const discovery = useSettingsSection<DiscoverySettings>("discovery");
  const llm = useSettingsSection<LLMSettings>("llm");
  const accounts = useQuery({ queryKey: ["email", "accounts"], queryFn: () => api.get<EmailAccountsResponse>("/email/accounts") });
  const saveProfile = useSaveSettings<AgencyProfile>("agency_profile", "Progress saved");
  const finish = useSaveSettings<AgencyProfile>("agency_profile", "Setup complete");

  const s = STEPS[step];
  const next = () => {
    setDone((d) => new Set(d).add(step));
    setStep((x) => Math.min(x + 1, STEPS.length - 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const back = () => setStep((x) => Math.max(0, x - 1));

  const loadError = profile.error || discovery.error || llm.error;
  const loading = !profile.data || !discovery.data || !llm.data;

  const backBtn =
    step > 0 ? (
      <Button type="button" variant="ghost" onClick={back}>
        Back
      </Button>
    ) : null;

  function body() {
    if (s.sections) {
      return (
        <AgencyProfileForm
          key={s.key}
          profile={profile.data}
          sections={s.sections}
          disabled={!isAdmin}
          submitLabel="Save and continue"
          secondaryAction={backBtn}
          onSubmit={async (v) => {
            await saveProfile.mutateAsync(v);
            next();
          }}
        />
      );
    }
    if (s.key === "email") {
      return (
        <div className="space-y-6">
          <EmailAccountsPanel />
          <p className="text-xs text-muted-foreground">
            Connecting opens Google or Microsoft sign-in, then returns you to Settings, Integrations. Come back here afterwards to finish setup.
          </p>
          <StepNav back={backBtn} onNext={next} nextLabel={(accounts.data?.accounts.length ?? 0) > 0 ? "Continue" : "Skip for now"} />
        </div>
      );
    }
    if (s.key === "search") {
      return (
        <div className="space-y-6">
          <SearchProviderForm settings={discovery.data!} compact disabled={!isAdmin} onSaved={next} submitLabel="Save and continue" />
          <StepNav back={backBtn} onNext={next} nextLabel="Skip for now" variant="outline" />
        </div>
      );
    }
    if (s.key === "ai") {
      return (
        <div className="space-y-6">
          <LLMForm settings={llm.data!} compact disabled={!isAdmin} submitLabel="Save AI provider" />
          {llm.data!.provider !== "none" && <TestConnection disabled={!isAdmin} />}
          <StepNav back={backBtn} onNext={next} nextLabel="Continue" />
        </div>
      );
    }
    // finish
    const p = profile.data!;
    const checks = [
      { ok: !!p.agency_name, label: "Agency name", detail: p.agency_name || "Not set" },
      {
        ok: p.services.some((x) => x.enabled && x.description),
        label: "Services described",
        detail: p.services.filter((x) => x.enabled).map((x) => x.name).join(", ") || "None enabled",
      },
      { ok: !!p.sender_name, label: "Sender", detail: p.sender_name ? `${p.sender_name}${p.sender_title ? `, ${p.sender_title}` : ""}` : "Not set" },
      {
        ok: (accounts.data?.accounts.length ?? 0) > 0,
        label: "Mailbox",
        detail: accounts.data?.accounts.map((a) => a.email).join(", ") || "Not connected. Approved drafts will wait until you connect one.",
      },
      {
        ok: discovery.data!.web_search_provider !== "none",
        label: "Search provider",
        detail: discovery.data!.web_search_provider === "none" ? "None. Limited discovery." : discovery.data!.web_search_provider,
      },
      {
        ok: llm.data!.provider !== "none",
        label: "AI provider",
        detail: llm.data!.provider === "none" ? "None. Limited mode, no drafts." : `${llm.data!.provider}: ${llm.data!.model_smart}`,
      },
    ];
    return (
      <div className="space-y-6">
        <ul className="divide-y rounded-xl border">
          {checks.map((c) => (
            <li key={c.label} className="flex items-start gap-3 p-4">
              {c.ok ? <Check className="mt-0.5 size-4 shrink-0 text-brand" /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
              <div className="min-w-0">
                <p className="text-sm font-medium">{c.label}</p>
                <p className="text-sm break-words text-muted-foreground">{c.detail}</p>
              </div>
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted-foreground">
          Optional items can be set up later in Settings. The app never sends email: approving a draft creates an unsent draft in your mailbox.
        </p>
        <div className="flex flex-wrap justify-end gap-2">
          {backBtn}
          <Button
            disabled={!isAdmin || finish.isPending}
            onClick={async () => {
              try {
                await finish.mutateAsync({ onboarding_completed: true });
                router.push("/");
              } catch {
                /* toast shown */
              }
            }}
          >
            {finish.isPending && <Loader2 className="animate-spin" />}
            Finish setup
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl">
      <PageHeader title="Set up your agency" description="Eight short steps. Progress is saved as you go." />
      {!isAdmin && (
        <Notice tone="warning" className="mb-6" title="Admin access needed">
          Only admins can change agency settings. Ask an admin to complete setup.
        </Notice>
      )}
      <div className="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav aria-label="Setup steps">
          <p className="mb-3 text-sm text-muted-foreground lg:hidden">
            Step {step + 1} of {STEPS.length}
          </p>
          <ol className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
            {STEPS.map((x, i) => {
              const active = i === step;
              const complete = done.has(i);
              return (
                <li key={x.key} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => setStep(i)}
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                      active ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center rounded-full border text-[0.7rem] font-semibold tabular-nums",
                        complete && "border-brand bg-brand text-brand-foreground",
                        active && !complete && "border-foreground text-foreground",
                      )}
                    >
                      {complete ? <Check className="size-3" /> : i + 1}
                    </span>
                    <span className="hidden whitespace-nowrap sm:inline">{x.title}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        <div className="min-w-0">
          <div className="mb-6 space-y-1">
            <h2 className="text-lg font-semibold tracking-[-0.01em]">{s.title}</h2>
            <p className="max-w-[64ch] text-sm text-muted-foreground">{s.intro}</p>
          </div>
          {loadError ? <ErrorState error={loadError} /> : loading ? <PageSkeleton /> : body()}
        </div>
      </div>
    </div>
  );
}

function StepNav({
  back,
  onNext,
  nextLabel,
  variant = "default",
}: {
  back: React.ReactNode;
  onNext: () => void;
  nextLabel: string;
  variant?: "default" | "outline";
}) {
  return (
    <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
      {back}
      <Button type="button" variant={variant} onClick={onNext}>
        {nextLabel}
      </Button>
    </div>
  );
}
