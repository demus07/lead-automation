# Integration configuration

Every integration is optional. Settings → **Integrations** shows each one as *Connected*, *Not
configured*, *Authentication expired* or *Error*. API keys entered in the dashboard are stored
Fernet-encrypted and are never returned to the browser (only “set” + last 4 characters).

## LLM providers (Settings → AI configuration)

| Provider | Settings | Notes |
|---|---|---|
| OpenAI-compatible | Base URL, API key, models | Works with OpenAI (`https://api.openai.com/v1`), Azure OpenAI-compatible gateways, OpenRouter, Together, Groq, **Ollama** (`http://host:11434/v1`, no key), vLLM, LM Studio. JSON mode is used when supported, with automatic fallback. |
| Anthropic | API key, models | Uses the official SDK with prompt caching on agent instructions. Suggested: fast = `claude-haiku-5-5`, smart = `claude-sonnet-5-5` or `claude-opus-5-5`. Effort per tier is configurable; temperature is ignored for current Claude models. |

* **Fast model** — extraction & classification (contacts, signals, replies, orchestrator brief).
* **Smart model** — website analysis, scoring, writing, quality review.
* Budgets: `daily_budget_usd` (hard stop for the day), `max_calls_per_company` (per 24 h), `max_retries`.
* Pricing table (USD per 1M tokens) drives cost tracking — update it for your models.

Without an LLM: research uses deterministic checks only, scoring uses the transparent heuristic scorer,
replies are classified by rules, and **outreach drafts cannot be generated** (the UI says so).

## Discovery sources (Settings → Integrations)

| Source | Key needed | What it provides |
|---|---|---|
| YC company directory | no | ~6k venture-backed startups: website, industry, regions, team size, batch, hiring flag |
| Wikidata | no key, but `CRAWLER_CONTACT` required | Companies by industry & country with official website and headcount |
| HN “Who is hiring?” | no | Companies currently hiring (monthly thread via the official HN Algolia API) |
| RSS / Atom | no | Per-campaign feeds (funding news, accelerator announcements, job boards that offer RSS) |
| Brave Search | API key | Web search (free tier available) |
| Tavily | API key | Web search for agents |
| SerpAPI | API key | Google results |
| SearXNG | your instance URL | Open-source self-hosted metasearch; enable `json` in `settings.yml` (`search.formats: [html, json]`) |
| Company Brain | connector | Target accounts from a Notion database or your Company Brain API |
| CSV | — | Discovery → Import CSV (company + optional contact columns, auto-mapped) |

Only one web-search provider is active at a time (`web_search_provider`), with a daily query quota.
LinkedIn is never scraped; CAPTCHAs, paywalls and logins are never bypassed.

**What needs a paid provider:** broad open-web discovery by arbitrary query (any of Brave/Tavily/SerpAPI,
or free self-hosted SearXNG), and mailbox-level email verification (Hunter). Everything else works with
public sources.

## Email verification (optional)

Settings → Integrations → Enrichment: `verification_provider = hunter` + API key. Only a provider result of
*deliverable/valid* marks an email **verified**. Without it the best status is **published** (found on
the company's own site) or **domain_valid** (domain has MX records). Guessed addresses are never created.

## Gmail

1. Google Cloud console → APIs & Services → enable **Gmail API**.
2. OAuth consent screen (Internal for Workspace, or External + test users). Scopes:
   `gmail.compose`, `gmail.metadata`, `openid`, `email`.
3. Credentials → OAuth client ID → *Web application*. Authorised redirect URI:
   `{PUBLIC_API_URL}/api/email/oauth/gmail/callback`.
4. Put `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`, restart `api`.
5. Settings → Integrations → Connect Gmail.

`gmail.compose` is the narrowest Google scope that allows creating drafts (Google bundles send
permission into it); the application contains no send call — enforced by an automated test.

## Microsoft Outlook / 365

1. Entra ID → App registrations → New. Redirect URI (Web):
   `{PUBLIC_API_URL}/api/email/oauth/outlook/callback`.
2. API permissions (delegated): `offline_access`, `openid`, `email`, `User.Read`, `Mail.ReadWrite`.
   **Do not add `Mail.Send`** — without it the app cannot send mail at all.
3. Certificates & secrets → new client secret.
4. `.env`: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT` (`common`, `organizations`
   or your tenant ID). Restart `api`, then Connect Outlook.

Tokens are encrypted; expired refresh tokens set the account to *Authentication expired* and drafts wait
until you reconnect. Disconnecting deletes the tokens (also revoke in your Google/Microsoft account).

## Company Brain connectors (Settings → Knowledge)

| Connector | Credentials | Config | Notes |
|---|---|---|---|
| Notion | internal integration secret | page IDs, database IDs, optional target-accounts DB | Share the pages/databases with the integration. Database properties `Type`/`Service` (select) map to kind/service. |
| Slack | bot token (`channels:history`, `pins:read`) | channel IDs, pinned-only | Pinned messages are a good place for approved positioning/case studies. |
| Microsoft Teams | tenant, client ID, secret (app permission `ChannelMessage.Read.All`, admin consent) | team ID, channel IDs | |
| Company Brain API | bearer token | base URL | `GET /knowledge` → `[{id,title,content,url,kind,service}]`; optional `GET /companies` → `[{id,name,website}]` |

Imported items are **not approved for outreach** by default. Approve individual items (and never mark
client-confidential material as approved — the API rejects approved+confidential). Agents only see
approved, non-confidential items; the quality gate blocks drafts that mention confidential item titles.
Gmail/Outlook mailboxes are not used as knowledge sources.
