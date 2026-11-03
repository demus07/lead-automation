// Response shapes mirror backend/app/api/*.py (many endpoints return plain dicts).

export type UUID = string;
export type ISODate = string;

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type Role = "admin" | "operator" | "viewer";

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: ISODate | null;
  created_at: ISODate;
}

export interface Session {
  user: User;
  csrf_token: string;
}

export interface Msg {
  ok: boolean;
  message: string;
  data?: Record<string, unknown>;
}

export type LeadStatus =
  | "NEW"
  | "RESEARCHING"
  | "RESEARCHED"
  | "QUALIFIED"
  | "DRAFT_GENERATED"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "EMAIL_DRAFT_CREATED"
  | "CONTACTED"
  | "REPLIED"
  | "INTERESTED"
  | "MEETING_REQUESTED"
  | "NOT_INTERESTED"
  | "DISQUALIFIED"
  | "DO_NOT_CONTACT";

export type DraftStatus =
  | "generating"
  | "needs_review"
  | "pending_approval"
  | "saved_for_later"
  | "approved"
  | "email_draft_created"
  | "rejected"
  | "superseded"
  | "blocked";

export type JobStatus = "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled" | "skipped";

export type EmailStatus = "none" | "unverified" | "published" | "domain_valid" | "invalid" | "verified";

export type ServiceKey = "website" | "company_brain";

export type ObservationCategory = "verified_fact" | "direct_observation" | "hypothesis" | "unknown";

export interface Company {
  id: UUID;
  name: string;
  domain: string | null;
  website: string | null;
  industry: string | null;
  location: string | null;
  country: string | null;
  size_range: string | null;
  description: string | null;
  status: LeadStatus;
  campaign_id: UUID | null;
  website_score: number | null;
  brain_score: number | null;
  recommended_service: string | null;
  tags: string[];
  last_researched_at: ISODate | null;
  last_scored_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface Contact {
  id: UUID;
  company_id: UUID | null;
  full_name: string;
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  seniority_rank: number;
  email: string | null;
  email_status: EmailStatus;
  email_checked_at: ISODate | null;
  email_check_detail: Record<string, unknown>;
  profile_url: string | null;
  source_url: string | null;
  source_type: string;
  discovered_at: ISODate | null;
  confidence: number;
  is_primary: boolean;
  status: string;
  created_at: ISODate;
  company_name?: string | null;
  company_domain?: string | null;
}

export interface LeadSource {
  id: UUID;
  provider: string;
  source_type: string;
  source_url: string | null;
  title: string | null;
  snippet: string | null;
  created_at: ISODate;
}

export interface Signal {
  id: UUID;
  company_id: UUID;
  signal_type: string;
  description: string;
  source_url: string;
  source_name: string | null;
  published_at: ISODate | null;
  discovered_at: ISODate;
  evidence: string | null;
  confidence: number;
  freshness: string;
  method: string;
  company_name?: string | null;
}

export interface Note {
  id: UUID;
  company_id: UUID | null;
  contact_id: UUID | null;
  author_id: UUID | null;
  body: string;
  created_at: ISODate;
}

export interface Task {
  id: UUID;
  title: string;
  description: string | null;
  company_id: UUID | null;
  contact_id: UUID | null;
  assignee_id: UUID | null;
  due_at: ISODate | null;
  status: "open" | "done" | "cancelled" | string;
  kind: string;
  completed_at: ISODate | null;
  created_at: ISODate;
  company_name?: string | null;
}

export interface EvidenceItem {
  id: string;
  url?: string | null;
  kind?: string;
  title?: string | null;
  excerpt?: string | null;
  page_kind?: string;
  signal_id?: string;
}

export interface Observation {
  area: string;
  text: string;
  source?: string;
  category: ObservationCategory | string;
  evidence_ids?: string[];
  quote?: string;
}

export interface AuditCheck {
  id: string;
  area: string;
  label: string;
  value: unknown;
  detail: string;
  passed: boolean | null;
  category: string;
  evidence_url?: string;
}

export interface ResearchPage {
  id: string;
  kind: string;
  final_url: string;
  title: string | null;
  meta_description: string | null;
  word_count: number | null;
  headings: { text: string; level: string }[] | null;
  nav_items: string[] | null;
  ctas: string[] | null;
  tools_mentioned: string[] | null;
  tech: string[] | null;
  rendered: boolean | null;
}

export interface ResearchReport {
  id: UUID;
  company_id: UUID;
  version: number;
  status: string;
  summary: string | null;
  researched_at: ISODate | null;
  created_at: ISODate;
  pages: ResearchPage[];
  audit: {
    tech?: string[];
    checks?: AuditCheck[];
    summary?: { score?: number; passed?: number; measured?: number; by_area?: Record<string, number> };
    not_measured?: unknown[];
    pages_analyzed?: number;
    tools_mentioned?: string[];
  } | null;
  analysis: Record<string, unknown> | null;
  observations: Observation[];
  evidence: EvidenceItem[];
  business_info: Record<string, unknown> | null;
  robots: Record<string, unknown> | null;
  injection_flags: unknown[] | null;
  errors: unknown[] | null;
  rejected_observations?: unknown[];
  company?: { id: UUID; name: string; domain: string | null; website: string | null; status: LeadStatus };
}

export interface ResearchListItem {
  id: UUID;
  company_id: UUID;
  company_name: string | null;
  domain: string | null;
  version: number;
  status: string;
  summary: string | null;
  pages: number;
  audit_score: number | null;
  observations: number;
  method: string | null;
  injection_flags: number;
  created_at: ISODate;
}

export interface Opportunity {
  id: UUID;
  company_id: UUID;
  website_score: number | null;
  website_confidence: number | null;
  website_explanation: string | null;
  brain_score: number | null;
  brain_confidence: number | null;
  brain_explanation: string | null;
  recommended_service: string | null;
  recommendation_reason: string | null;
  sales_angle: string | null;
  evidence: { id?: string; text?: string; url?: string; [k: string]: unknown }[] | null;
  method: string | null;
  stage: string | null;
  updated_at: ISODate;
  company?: { id: UUID; name: string; domain: string | null; industry: string | null; status: LeadStatus };
}

export interface ScoreHistoryItem {
  id?: UUID;
  service: string;
  score: number;
  confidence: number;
  method: string;
  created_at: ISODate;
  factors?: unknown;
  explanation?: string | null;
  evidence?: unknown;
  sales_angle?: string | null;
}

export interface DraftClaim {
  text: string;
  evidence_ids: string[];
  declared_ids?: string[];
  sources?: { id: string; url?: string | null; excerpt?: string | null }[];
}

export interface QualityIssue {
  check: string;
  severity: "high" | "medium" | "low" | string;
  text: string;
  source: "deterministic" | "ai" | string;
}

export interface QualityReport {
  deterministic_score?: number;
  issues?: QualityIssue[];
  threshold?: number;
  score?: number;
  passed?: boolean;
  ai_scores?: Record<string, unknown>;
  ai_note?: string;
  after_human_edit?: boolean;
  previous_ai_review?: unknown;
}

export interface DraftBrief {
  id: UUID;
  company_id: UUID;
  contact_id: UUID | null;
  service: string;
  status: DraftStatus;
  version: number;
  subject: string;
  quality_score: number | null;
  confidence: number | null;
  created_at: ISODate;
  updated_at: ISODate;
  edited_by_user: boolean;
  approved_at: ISODate | null;
  company_name?: string | null;
  contact_name?: string | null;
}

export interface CompanyBrief {
  next_action?: string;
  reason?: string;
  method?: string;
  at?: string;
  lead_summary?: string;
  open_questions?: string[];
  ai_suggestion?: { next_action?: string; reason?: string };
}

export interface Draft extends DraftBrief {
  body: string;
  opening_line: string | null;
  linkedin_connection_note: string | null;
  linkedin_message: string | null;
  recommended_offer: string | null;
  personalisation_explanation: string | null;
  evidence: DraftClaim[] | null;
  quality_report: QualityReport | null;
  regeneration_count: number;
  regeneration_notes: string | null;
  original: Partial<Record<"subject" | "body" | "linkedin_connection_note" | "linkedin_message", string | null>> | null;
  company?: {
    id: UUID;
    name: string;
    domain: string | null;
    website: string | null;
    status: LeadStatus;
    website_score: number | null;
    brain_score: number | null;
    recommended_service: string | null;
    brief: CompanyBrief | null;
  };
  contact?: {
    id: UUID;
    full_name: string;
    job_title: string | null;
    email: string | null;
    email_status: EmailStatus;
    profile_url: string | null;
    source_url: string | null;
  } | null;
  history?: {
    action: string;
    user_id: UUID | null;
    comment: string | null;
    changes: Record<string, unknown> | null;
    created_at: ISODate;
  }[];
  email_drafts?: {
    id: UUID;
    status: string;
    external_draft_id: string | null;
    email_account_id: UUID | null;
    to_email: string | null;
    attempts: number;
    last_error: string | null;
    created_at: ISODate;
    sent_detected_at: ISODate | null;
  }[];
  research_summary?: string | null;
  research_report_id?: UUID | null;
}

export interface ApproveResult {
  approved: boolean;
  email_draft: { id: string; external_draft_id: string | null; provider: string; account: string; status: string } | null;
  message: string;
  draft: Draft;
}

export interface Interaction {
  id: UUID;
  company_id: UUID | null;
  company_name: string | null;
  contact_id: UUID | null;
  contact_name: string | null;
  channel: string;
  direction: "inbound" | "outbound" | string;
  from_email: string | null;
  to_email: string | null;
  subject: string | null;
  snippet: string | null;
  occurred_at: ISODate | null;
  classification: string | null;
  classification_confidence: number | null;
  classification_detail: Record<string, unknown>;
  suggested_reply: string | null;
  suggested_action: string | null;
  handled: boolean;
  external_thread_id: string | null;
}

export interface Campaign {
  id: UUID;
  name: string;
  description: string;
  is_active: boolean;
  target_service: "any" | "website" | "company_brain";
  industries: string[];
  geographies: string[];
  company_sizes: string[];
  target_roles: string[];
  keywords: string[];
  query_templates: string[];
  signal_focus: string[];
  sources: string[];
  rss_feeds: string[];
  daily_company_limit: number;
  daily_query_limit: number;
  auto_research: boolean;
  created_at: ISODate;
  updated_at: ISODate;
  stats: {
    companies?: number;
    by_status?: Record<string, number>;
    qualified?: number;
    email_drafts?: number;
    replied?: number;
  };
}

export interface DiscoveryProvider {
  key: string;
  label: string;
  kind: string;
  status: string;
  requires_auth: boolean;
  description: string;
  detail: string;
  selected: boolean | null;
}

export interface Job {
  id: UUID;
  workflow: string;
  trigger: string;
  status: JobStatus;
  params: Record<string, unknown>;
  stats: Record<string, unknown>;
  errors: unknown[];
  log: unknown[];
  attempts: number;
  max_attempts: number;
  started_at: ISODate | null;
  finished_at: ISODate | null;
  next_retry_at: ISODate | null;
  company_id: UUID | null;
  campaign_id: UUID | null;
  parent_id: UUID | null;
  created_at: ISODate;
}

export interface WorkflowSchedule {
  workflow: string;
  cron: string;
  enabled: boolean;
  paused: boolean;
  batch_size: number;
  params: Record<string, unknown>;
  last_run_at: ISODate | null;
  next_run_at: ISODate | null;
}

export interface WorkflowInfo {
  workflow: string;
  label: string;
  description: string;
  schedule: WorkflowSchedule | null;
  last_job: Job | null;
  counts: Partial<Record<JobStatus, number>>;
}

export interface AIStatus {
  available: boolean;
  provider: string;
  spent_today_usd: number;
  daily_budget_usd: number;
  budget_remaining_usd: number;
}

export interface EmailAccount {
  id: UUID;
  provider: "gmail" | "outlook" | string;
  email: string;
  display_name: string | null;
  status: string;
  scopes: string[] | null;
  is_default: boolean;
  last_error: string | null;
  last_synced_at: ISODate | null;
  token_expires_at: ISODate | null;
  created_at: ISODate;
}

export interface EmailAccountsResponse {
  accounts: EmailAccount[];
  providers: { key: string; configured: boolean; scopes: string[]; redirect_uri: string; requires: string }[];
  sending: string;
}

export interface Suppression {
  id: UUID;
  kind: "email" | "domain" | string;
  value: string;
  reason: string;
  source: string | null;
  active: boolean;
  contact_id: UUID | null;
  company_id: UUID | null;
  created_at: ISODate;
}

export interface KnowledgeItem {
  id: UUID;
  kind: string;
  title: string;
  content: string;
  url: string | null;
  service: string | null;
  tags: string[];
  source: string;
  source_ref: string | null;
  connection_id: UUID | null;
  approved_for_outreach: boolean;
  confidential: boolean;
  updated_at: ISODate;
}

export interface ConnectorField {
  name: string;
  label: string;
  secret?: string;
}

export interface ConnectorDescription {
  key: string;
  label: string;
  description: string;
  credential_fields: ConnectorField[];
  config_fields: ConnectorField[];
  requires_auth: boolean;
  supports_companies: boolean;
}

export interface Connection {
  id: UUID;
  provider: string;
  name: string;
  status: string;
  config: Record<string, string>;
  credentials_set: boolean;
  last_synced_at: ISODate | null;
  last_error: string | null;
  connector: ConnectorDescription | null;
  created_at: ISODate;
}

export interface IntegrationRow {
  key: string;
  label: string;
  category: string;
  status: string;
  status_label: string;
  detail: string;
  requires_auth: boolean;
  configure_at: string;
}

export interface AgencyService {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface AgencyProfile {
  onboarding_completed: boolean;
  agency_name: string;
  website: string;
  description: string;
  sender_name: string;
  sender_title: string;
  signature: string;
  services: AgencyService[];
  target_industries: string[];
  target_geographies: string[];
  ideal_client_profile: string;
  typical_budgets: string;
  case_studies: { title: string; summary: string; url: string; service: string }[];
  portfolio_links: string[];
  testimonials: { quote: string; author: string; company: string; approved: boolean }[];
  tone: string;
  call_to_action: string;
  postal_address: string;
  include_opt_out_line: boolean;
  opt_out_line: string;
}

export interface LLMSettings {
  provider: "none" | "openai_compatible" | "anthropic";
  base_url: string;
  api_key: string;
  api_key_is_set?: boolean;
  api_key_masked?: string;
  model_fast: string;
  model_smart: string;
  temperature: number;
  effort_fast: string;
  effort_smart: string;
  max_output_tokens: number;
  daily_budget_usd: number;
  max_calls_per_company: number;
  max_retries: number;
  timeout_seconds: number;
  json_mode: boolean;
  pricing: Record<string, { input: number; output: number; cache_read?: number }>;
}

export interface DiscoverySettings {
  web_search_provider: "none" | "brave" | "tavily" | "serpapi" | "searxng";
  brave_api_key: string;
  brave_api_key_is_set?: boolean;
  brave_api_key_masked?: string;
  tavily_api_key: string;
  tavily_api_key_is_set?: boolean;
  tavily_api_key_masked?: string;
  serpapi_api_key: string;
  serpapi_api_key_is_set?: boolean;
  serpapi_api_key_masked?: string;
  searxng_url: string;
  daily_search_quota: number;
  default_country: string;
  results_per_query: number;
  excluded_domains: string[];
  sec_user_agent_contact: string;
}

export interface EnrichmentSettings {
  verification_provider: "none" | "hunter";
  hunter_api_key: string;
  hunter_api_key_is_set?: boolean;
  hunter_api_key_masked?: string;
  allow_mx_check: boolean;
}

export interface Dashboard {
  onboarding_completed: boolean;
  kpis: {
    companies: number;
    discovered_today: number;
    discovered_week: number;
    qualified: number;
    pending_approval: number;
    needs_review: number;
    contacts_with_email: number;
    unhandled_replies: number;
    open_tasks: number;
    failed_jobs_week: number;
  };
  by_status: Partial<Record<LeadStatus, number>>;
  pending_drafts: {
    id: UUID;
    company_id: UUID;
    company_name: string | null;
    subject: string;
    service: string;
    quality_score: number | null;
  }[];
  top_opportunities: {
    id: UUID;
    name: string;
    domain: string | null;
    status: LeadStatus;
    website_score: number | null;
    brain_score: number | null;
    recommended_service: string | null;
  }[];
  recent_signals: {
    id: UUID;
    company_id: UUID;
    company_name: string | null;
    signal_type: string;
    description: string;
    freshness: string;
    source_url: string;
    published_at: ISODate | null;
  }[];
  recent_jobs: { id: UUID; workflow: string; status: JobStatus; trigger: string; created_at: ISODate; stats: Record<string, unknown> }[];
  recent_replies: { id: UUID; company_name: string | null; subject: string | null; classification: string | null; occurred_at: ISODate | null }[];
  system: {
    ai: AIStatus;
    web_search: { provider: string; configured: boolean };
    email_accounts: number;
  };
}
