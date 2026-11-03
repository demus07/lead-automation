// Labels, tones and explanations for every status enum the backend uses.
import type { DraftStatus, EmailStatus, JobStatus, LeadStatus } from "./types";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "violet" | "brand";

export const LEAD_STATUSES: LeadStatus[] = [
  "NEW",
  "RESEARCHING",
  "RESEARCHED",
  "QUALIFIED",
  "DRAFT_GENERATED",
  "PENDING_APPROVAL",
  "APPROVED",
  "EMAIL_DRAFT_CREATED",
  "CONTACTED",
  "REPLIED",
  "INTERESTED",
  "MEETING_REQUESTED",
  "NOT_INTERESTED",
  "DISQUALIFIED",
  "DO_NOT_CONTACT",
];

export const LEAD_STATUS_META: Record<LeadStatus, { label: string; tone: Tone }> = {
  NEW: { label: "New", tone: "neutral" },
  RESEARCHING: { label: "Researching", tone: "info" },
  RESEARCHED: { label: "Researched", tone: "info" },
  QUALIFIED: { label: "Qualified", tone: "brand" },
  DRAFT_GENERATED: { label: "Draft generated", tone: "violet" },
  PENDING_APPROVAL: { label: "Pending approval", tone: "warning" },
  APPROVED: { label: "Approved", tone: "success" },
  EMAIL_DRAFT_CREATED: { label: "Draft in mailbox", tone: "success" },
  CONTACTED: { label: "Contacted", tone: "info" },
  REPLIED: { label: "Replied", tone: "violet" },
  INTERESTED: { label: "Interested", tone: "success" },
  MEETING_REQUESTED: { label: "Meeting requested", tone: "success" },
  NOT_INTERESTED: { label: "Not interested", tone: "neutral" },
  DISQUALIFIED: { label: "Disqualified", tone: "neutral" },
  DO_NOT_CONTACT: { label: "Do not contact", tone: "danger" },
};

export const DRAFT_STATUS_META: Record<DraftStatus, { label: string; tone: Tone }> = {
  generating: { label: "Generating", tone: "info" },
  needs_review: { label: "Needs review", tone: "warning" },
  pending_approval: { label: "Pending approval", tone: "warning" },
  saved_for_later: { label: "Saved for later", tone: "neutral" },
  approved: { label: "Approved", tone: "success" },
  email_draft_created: { label: "Draft in mailbox", tone: "success" },
  rejected: { label: "Rejected", tone: "neutral" },
  superseded: { label: "Superseded", tone: "neutral" },
  blocked: { label: "Blocked", tone: "danger" },
};

export const JOB_STATUS_META: Record<JobStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  succeeded: { label: "Succeeded", tone: "success" },
  partial: { label: "Partial", tone: "warning" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  skipped: { label: "Skipped", tone: "neutral" },
};

export const EMAIL_STATUS_META: Record<EmailStatus, { label: string; tone: Tone; help: string }> = {
  verified: {
    label: "Verified",
    tone: "success",
    help: "Mailbox confirmed by a verification provider (Hunter). The only status that means the address accepts mail.",
  },
  published: {
    label: "Published",
    tone: "info",
    help: "Found verbatim on the company's own public pages. Real and public, but the mailbox has not been verified.",
  },
  domain_valid: {
    label: "Domain valid",
    tone: "warning",
    help: "Syntax is correct and the domain accepts mail (MX records). The individual mailbox has not been verified.",
  },
  unverified: {
    label: "Unverified",
    tone: "warning",
    help: "Entered or imported but not checked yet. Run “Verify email” to check syntax and domain.",
  },
  invalid: {
    label: "Invalid",
    tone: "danger",
    help: "Failed the syntax or domain check. Don't use this address.",
  },
  none: { label: "No email", tone: "neutral", help: "No email address is known for this contact." },
};

export const OBSERVATION_META: Record<string, { label: string; tone: Tone; help: string }> = {
  verified_fact: {
    label: "Verified fact",
    tone: "success",
    help: "Stated by an authoritative source and checked against it.",
  },
  direct_observation: {
    label: "Observed",
    tone: "info",
    help: "Measured or seen directly on the company's website.",
  },
  hypothesis: {
    label: "Hypothesis",
    tone: "violet",
    help: "An inference from evidence. Plausible, not confirmed — don't state it as fact in outreach.",
  },
  unknown: { label: "Unknown", tone: "neutral", help: "Not enough evidence to categorise." },
};

export const INTERACTION_LABELS = [
  "interested",
  "meeting_requested",
  "needs_information",
  "objection",
  "not_interested",
  "unsubscribe",
  "out_of_office",
  "automatic_reply",
  "unknown",
] as const;

export const CLASSIFICATION_TONE: Record<string, Tone> = {
  interested: "success",
  meeting_requested: "success",
  needs_information: "info",
  objection: "warning",
  not_interested: "neutral",
  unsubscribe: "danger",
  out_of_office: "neutral",
  automatic_reply: "neutral",
  unknown: "neutral",
};

export function integrationTone(status: string): Tone {
  if (["connected", "available", "configured"].includes(status)) return "success";
  if (["expired", "revoked"].includes(status)) return "warning";
  if (status === "error") return "danger";
  return "neutral";
}
