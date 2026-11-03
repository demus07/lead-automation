# Security & compliance

## Application security

| Control | Implementation |
|---|---|
| Authentication | bcrypt (cost 12) password hashes; password policy; lockout after 5 failures (15 min); login rate limit per IP |
| Sessions | signed JWT in httpOnly `SameSite=Lax` cookie (`Secure` with `COOKIE_SECURE=true`); `token_version` revokes sessions on password/role change |
| CSRF | double-submit token (`X-CSRF-Token`) HMAC-bound to the session for every cookie-authenticated mutation |
| RBAC | `admin` (settings, users, integrations, retention), `operator` (research, edit, approve), `viewer` (read-only) — enforced on every route |
| Rate limiting | Redis fixed-window per session/IP (`RATE_LIMIT_PER_MINUTE`), in-memory fallback |
| Input validation | Pydantic schemas with length/enum limits; CSV size/row caps; URL validation |
| SQL injection | SQLAlchemy parameterised queries only; `LIKE` patterns escaped |
| XSS | API returns JSON only with `Content-Security-Policy: default-src 'none'`; React escapes output; scraped HTML is never rendered |
| CSV injection | exported cells beginning with `= + - @` are prefixed |
| SSRF | crawler refuses private/loopback/link-local addresses |
| Secrets | `.env` for infrastructure; DB-stored API keys/OAuth tokens/connector credentials Fernet-encrypted with `ENCRYPTION_KEY`; never returned to clients |
| Headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS when secure |
| Audit | append-only `audit_logs`: logins, settings changes, approvals, edits, suppression, exports, erasures, status changes |
| Production guard | refuses to start with a default `SECRET_KEY` or missing `ENCRYPTION_KEY` |

## AI safety: untrusted content and prompt injection

1. Scraped pages and emails are cleaned (scripts, styles, comments, hidden elements, zero-width chars removed).
2. Heuristic injection detection flags pages/emails; flags are stored and shown on the research report.
3. Untrusted text is wrapped in `<untrusted_content>` blocks with forged delimiters neutralised; every
   agent's system prompt states that nothing inside is an instruction.
4. Agents have **no tools** and no database access. Output is JSON validated by Pydantic.
5. Deterministic code performs all writes, permissions, state transitions, deduplication and score maths.
6. Evidence validation: cited IDs must exist; “verified facts” must quote the cited source verbatim
   (otherwise rejected); factor ratings without valid evidence are discarded; contact names must appear
   on the page; numeric claims in outreach must appear in evidence.
7. Approval is a human action; no agent output can trigger sending (there is no send code path).

## Outreach compliance

The application provides controls; **you** are responsible for complying with the laws of the
jurisdictions you target (e.g. UK PECR + UK GDPR, EU ePrivacy + GDPR, US CAN-SPAM, Canada CASL,
Australia Spam Act). Practical guidance:

* B2B cold email to corporate addresses is permitted in some jurisdictions on a legitimate-interest basis
  but not in others (e.g. some EU member states require prior consent; CASL generally requires consent or
  a conspicuous publication exemption). Configure campaigns' geographies accordingly.
* Identify the sender, include a postal address where required (Agency profile → postal address) and a
  simple opt-out (Agency profile → opt-out line, included in drafts by default).
* Opt-outs are honoured immediately: replies asking to stop are detected by rules **and** the AI agent;
  either one adds the address to the suppression list, blocks pending drafts, and prevents new drafts.
* Data minimisation: only business contact data (name, job title, business email, public profile URL,
  source) is stored. No personal phone numbers, home addresses or social scraping.
* Record of processing: every contact has `source_url`, `source_type` and `discovered_at`.
* Data subject rights: Contacts → row menu (admin) → export a contact's data (JSON) or erase it (a suppression
  record is retained so the person is never contacted again).
* Retention: configurable windows (Settings → AI configuration → Retention) applied daily by the
  maintenance workflow. Suppression records are never deleted.

## Crawling etiquette

robots.txt is fetched and obeyed (including `Crawl-delay`); 401/403 robots responses are treated as
“disallow all”; per-host delays; max pages per company; HTML only, 2 MB cap; results cached; no login,
CAPTCHA, paywall or bot-challenge circumvention; LinkedIn is never scraped or automated.
