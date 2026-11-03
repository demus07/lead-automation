import type {
  Company,
  CompanyBrief,
  Contact,
  DraftBrief,
  LeadSource,
  LeadStatus,
  Note,
  Opportunity,
  ResearchReport,
  ScoreHistoryItem,
  Signal,
  Task,
} from "@/lib/types";

export interface CompanyDetail {
  company: Company;
  data: { brief?: CompanyBrief; public_emails?: string[]; [k: string]: unknown } | null;
  allowed_transitions: LeadStatus[];
  disqualified_reason: string | null;
  contacts: Contact[];
  sources: LeadSource[];
  signals: Signal[];
  research: ResearchReport | null;
  opportunity: Opportunity | null;
  score_history: ScoreHistoryItem[];
  drafts: DraftBrief[];
  interactions: {
    id: string;
    channel: string;
    direction: string;
    subject: string | null;
    snippet: string | null;
    occurred_at: string | null;
    classification: string | null;
  }[];
  notes: Note[];
  tasks: Task[];
}

export interface OpportunityDetail {
  opportunity: Opportunity | null;
  scores: (ScoreHistoryItem & { id: string })[];
}
