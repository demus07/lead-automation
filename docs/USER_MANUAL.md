# User manual

## The daily loop

1. **Overnight / scheduled** — the automation engine discovers companies for active campaigns, researches
   their websites, finds decision-makers, scores both services, and drafts outreach for qualified leads.
2. **Morning** — open **Approvals**. Each card shows the company, contact (with email status), recommended
   service, both scores, the research brief, the evidence behind each claim, the quality score, and the
   email + LinkedIn drafts.
3. For each draft: **Approve** (creates an unsent draft in your mailbox), **Edit** then approve,
   **Save for later**, **Request regeneration** (tell the writer what to change), **Reject**, or **Do not contact**.
4. Open Gmail/Outlook → Drafts, review once more, and **send it yourself**.
5. Replies are picked up automatically, classified, and turned into tasks with suggested responses.

Keyboard shortcuts on the approval page: `j`/`k` next/previous, `e` edit, `a` approve.

## Pages

| Page | Use it to |
|---|---|
| Overview | KPIs, what needs attention, system status (limited mode banners) |
| Approvals | Review and approve drafts — the core human step |
| Pipeline | See leads by stage; compare Website vs Company Brain scores |
| Companies | Search, filter, bulk-tag, bulk research/qualify/draft, export; open a company for its full record |
| Contacts | Decision-makers with source URLs and honest email status |
| Research | Reports: pages crawled, measurable checks, categorised observations, signals |
| Discovery | Run ad-hoc searches, import CSVs, see provider status and search history |
| Campaigns | Define who to find: industries, geographies, sizes, roles, signal focus, sources, limits, target service |
| Conversations | Replies with classification, suggested reply, next action; log LinkedIn/phone replies manually |
| Analytics | Funnel, sources, campaign performance, reply rates, AI usage and cost |
| Automation | The 7 workflows: schedules, run now, pause/resume, job history, logs, retry |
| Settings | Agency profile, AI configuration, integrations, knowledge & connectors, users, suppression, audit |

## Reading research honestly

Every observation carries a category:

* **Verified fact** — stated on the company's site, quoted verbatim, with a link.
* **Direct observation** — objectively present/absent (e.g. “no meta description”, “viewport tag present”).
* **Hypothesis** — an interpretation or design judgement. Treat as a conversation starter, not a fact.
* **Unknown** — could not be assessed (e.g. visual consistency without a visual review).

Signals show freshness (*fresh* ≤ 90 days, *recent* ≤ 180, *stale*, *unknown*). Headline matches that
could not be verified are marked unverified and are not used for scoring.

## Scores and recommendations

Each company gets two independent 0–100 scores. The AI rates factors (0–5) and must cite evidence;
ratings without evidence are discarded. The system recommends **one** service only if its score is at
least the qualification threshold (default 60) with sufficient confidence — or **none**. A campaign can
restrict recommendations to one service.

## Email statuses

| Status | Meaning |
|---|---|
| verified | A verification provider confirmed the mailbox is deliverable |
| published | Found on the company's own website (not mailbox-verified) |
| domain_valid | The domain accepts email (MX records); mailbox not verified |
| unverified | Imported or entered manually, not checked |
| invalid | Syntax or domain check failed |

## Do-not-contact and opt-outs

* *Do not contact* on a contact suppresses their email; on a company it suppresses the domain.
* Replies such as “unsubscribe / remove me / stop emailing” suppress the sender automatically.
* Suppressed recipients cannot receive new drafts; pending drafts are blocked immediately.
* Opt-out entries cannot be deactivated.

## Roles

* **Viewer** — read everything.
* **Operator** — run research, edit/approve/reject drafts, manage companies, contacts, campaigns.
* **Admin** — settings, integrations, users, schedules, retention, exports and data erasure.

## Limited mode

If no LLM is configured, research still produces measurable audits and signals, scoring uses a
transparent heuristic, and replies are classified by rules — but drafts cannot be written. If no web
search provider is configured, discovery uses public directories, hiring threads, RSS and CSV only.
The dashboard and discovery page say so explicitly.
