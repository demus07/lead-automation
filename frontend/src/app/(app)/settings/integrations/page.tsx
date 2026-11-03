"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field } from "@/components/shared/field";
import { Notice } from "@/components/shared/notice";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState, TableSkeleton } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmailAccountsPanel } from "@/components/settings/email-accounts";
import { SearchProviderForm } from "@/components/settings/search-provider-form";
import { SecretInput } from "@/components/settings/secret-input";
import { SettingsBlock } from "@/components/settings/settings-block";
import { useSaveSettings, useSettingsSection } from "@/components/settings/use-settings";
import { useCan } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import type { DiscoverySettings, EnrichmentSettings, IntegrationRow } from "@/lib/types";

const CATEGORY_LABEL: Record<string, string> = {
  ai: "AI",
  discovery: "Discovery sources",
  enrichment: "Enrichment",
  email: "Mailboxes",
  company_brain: "Company Brain connectors",
  research: "Research",
};
const PROVIDER_LABEL: Record<string, string> = { gmail: "Gmail", outlook: "Outlook" };

const OAUTH_ERRORS: Record<string, string> = {
  missing_code: "The provider didn't return an authorisation code. Try connecting again.",
  invalid_state: "The sign-in link was invalid. Start the connection again from this page.",
  expired_state: "The sign-in took longer than 15 minutes. Start again.",
  invalid_user: "Your user account couldn't be matched. Sign in again and retry.",
  exchange_failed: "The provider rejected the token exchange.",
  access_denied: "Access was not granted.",
};

/** Reads ?connected= / ?error= after the OAuth redirect, toasts, then cleans the URL. */
function OAuthResult() {
  const params = useSearchParams();
  const router = useRouter();
  const [shown, setShown] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    const connected = params.get("connected");
    const error = params.get("error");
    if (!connected && !error) return;
    if (connected) {
      const text = `${PROVIDER_LABEL[connected] ?? connected} connected. Approved drafts will be created in this mailbox.`;
      toast.success("Mailbox connected");
      setShown({ ok: true, text });
    } else if (error) {
      const detail = params.get("detail");
      const text = `${OAUTH_ERRORS[error] ?? `Connection failed (${error}).`}${detail ? ` ${detail}` : ""}`;
      toast.error("Mailbox connection failed", { description: text });
      setShown({ ok: false, text });
    }
    router.replace("/settings/integrations", { scroll: false });
  }, [params, router]);
  if (!shown) return null;
  return (
    <Notice tone={shown.ok ? "info" : "danger"} className="mb-6" title={shown.ok ? "Mailbox connected" : "Mailbox connection failed"}>
      {shown.text}
    </Notice>
  );
}

function StatusTable() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<{ integrations: IntegrationRow[] }>("/integrations") });
  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <TableSkeleton rows={8} cols={3} />;
  const groups = new Map<string, IntegrationRow[]>();
  for (const r of q.data.integrations) groups.set(r.category, [...(groups.get(r.category) ?? []), r]);
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Integration</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="hidden md:table-cell">Detail</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...groups.entries()].map(([cat, rows]) => (
            <Group key={cat} label={CATEGORY_LABEL[cat] ?? cat} rows={rows} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Group({ label, rows }: { label: string; rows: IntegrationRow[] }) {
  return (
    <>
      <TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableCell colSpan={4} className="py-1.5 text-xs font-medium text-muted-foreground">
          {label}
        </TableCell>
      </TableRow>
      {rows.map((r) => (
        <TableRow key={r.key}>
          <TableCell className="py-2.5 font-medium">
            {r.label}
            <p className="mt-0.5 text-xs font-normal whitespace-normal text-muted-foreground md:hidden">{r.detail}</p>
          </TableCell>
          <TableCell className="py-2.5">
            <StatusBadge kind="integration" value={r.status} />
            <span className="sr-only">{r.status_label}</span>
          </TableCell>
          <TableCell className="hidden max-w-md py-2.5 text-sm whitespace-normal text-muted-foreground md:table-cell">{r.detail}</TableCell>
          <TableCell className="py-2.5 text-right">
            {r.configure_at && (
              <Button variant="ghost" size="sm" asChild>
                <Link href={r.configure_at === "/settings/integrations" ? `#${anchorFor(r.category)}` : r.configure_at}>Configure</Link>
              </Button>
            )}
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

function anchorFor(cat: string) {
  if (cat === "email") return "mailboxes";
  if (cat === "enrichment") return "enrichment";
  return "search";
}

function EnrichmentForm({ settings, disabled }: { settings: EnrichmentSettings; disabled?: boolean }) {
  const [provider, setProvider] = useState(settings.verification_provider);
  const [key, setKey] = useState("");
  const [mx, setMx] = useState(settings.allow_mx_check);
  const save = useSaveSettings<EnrichmentSettings>("enrichment", "Enrichment settings saved");
  return (
    <form
      className="space-y-5"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await save.mutateAsync({ verification_provider: provider, hunter_api_key: key, allow_mx_check: mx });
          setKey("");
        } catch {
          /* toast */
        }
      }}
    >
      <fieldset disabled={disabled} className="space-y-5">
        <Field label="Mailbox verification" htmlFor="verif" hint="Only a verification provider can mark an email as verified.">
          <Select value={provider} onValueChange={(v) => setProvider(v as EnrichmentSettings["verification_provider"])} disabled={disabled}>
            <SelectTrigger id="verif" className="w-full sm:w-80">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              <SelectItem value="hunter">Hunter</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {provider === "hunter" && (
          <Field label="Hunter API key" htmlFor="hunter-key">
            <SecretInput
              id="hunter-key"
              value={key}
              onChange={setKey}
              isSet={settings.hunter_api_key_is_set}
              masked={settings.hunter_api_key_masked}
              disabled={disabled}
            />
          </Field>
        )}
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={mx} onCheckedChange={setMx} disabled={disabled} />
            Check domains for mail servers (MX)
          </label>
          <p className="pl-10 text-xs text-muted-foreground">Marks addresses as “domain valid”. This never verifies the mailbox itself.</p>
        </div>
      </fieldset>
      <Button type="submit" disabled={disabled || save.isPending}>
        {save.isPending && <Loader2 className="animate-spin" />}
        Save enrichment settings
      </Button>
    </form>
  );
}

export default function IntegrationsPage() {
  const isAdmin = useCan("admin");
  const discovery = useSettingsSection<DiscoverySettings>("discovery");
  const enrichment = useSettingsSection<EnrichmentSettings>("enrichment");

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Integrations"
        description="Every optional connection in one place. Anything not configured degrades to a clearly reported limited mode."
      />
      <Suspense>
        <OAuthResult />
      </Suspense>
      {!isAdmin && (
        <Notice tone="warning" className="mb-6" title="Read only">
          Only admins can connect mailboxes or change provider keys.
        </Notice>
      )}

      <div className="mb-10">
        <StatusTable />
      </div>

      <SettingsBlock
        id="mailboxes"
        title="Mailboxes"
        description="Gmail and Outlook are used to create unsent drafts after you approve them, and to read replies. Nothing is ever sent."
      >
        <EmailAccountsPanel />
      </SettingsBlock>

      <SettingsBlock
        id="search"
        title="Web search"
        description="Used by discovery to find companies matching your campaigns. Keys are write-only; leave blank to keep the stored key."
      >
        {discovery.error ? (
          <ErrorState error={discovery.error} retry={() => discovery.refetch()} />
        ) : !discovery.data ? (
          <TableSkeleton rows={3} cols={2} />
        ) : (
          <SearchProviderForm settings={discovery.data} disabled={!isAdmin} />
        )}
      </SettingsBlock>

      <SettingsBlock id="enrichment" title="Email verification" description="Optional Hunter integration for checking that a mailbox exists.">
        {enrichment.error ? (
          <ErrorState error={enrichment.error} retry={() => enrichment.refetch()} />
        ) : !enrichment.data ? (
          <TableSkeleton rows={2} cols={2} />
        ) : (
          <EnrichmentForm settings={enrichment.data} disabled={!isAdmin} />
        )}
      </SettingsBlock>
    </div>
  );
}
