# Lead automation

A small, local dashboard that finds companies, works out what's wrong (their website, or how their team
works), finds who to contact, drafts a message, and **waits for your approval** before anything is sent.
It also works as a light CRM for everything that happens after you hit send.

```
find leads → research site → find email / profile → draft → you approve → send
           → replies, opt-outs and bounces update the CRM → one follow-up → you approve
```

Everything runs on your machine with free tools: Flask, SQLite, no paid APIs.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env        # fill in SMTP and an LLM
.venv/bin/python check.py   # tests every connection; sends nothing
.venv/bin/python app.py     # http://localhost:5050
```

Then open **Settings**, set your keywords, name and pitches, and click **Find leads now**.

## How each step works

| Step | How | Cost |
|---|---|---|
| Find leads | OpenStreetMap for local businesses by category and city (chains are filtered out where tagged). YC directory (with team-size filter) and HN “Who is hiring” for startups. You can also paste domains. | free, no key |
| Research | Opens the homepage in a headless browser at phone size, then reads about / team / contact / careers pages (respects robots.txt). Bot walls and empty pages are skipped, not reported as problems. | free |
| Fit | Website: sideways scrolling on phones, no call to action on the first screen, no contact path, placeholder text, stale ©, slow load, template builders, dated technology, no reviews. Systems: operational job titles on their careers page, many open roles, stated remote or multi-office teams, team size. Each problem adds its weight (×10) to a 0–100 score. Search-hygiene items barely score and are never mentioned to a prospect. | free |
| Contacts | Emails from visible text, mailto links and OpenStreetMap, plus social links. A person's address beats `hello@`; `support@`, `jobs@` etc. are skipped. Addresses are never guessed. Good fits with no contact go to `needs_contact`. | free |
| Draft | Any OpenAI-compatible LLM, given the problems and their site text. Every draft is checked by plain rules (length, banned phrases, invented numbers, links, unsupported names) and sent back for fixing up to twice. If it still fails, or no LLM is set, you get a template labelled “template, not AI”. | free tier |
| Send | Email over SMTP (a Gmail App Password works). DMs have no free, allowed API: click **Copy**, **Open profile**, send it yourself, then **I sent it**. | free |
| Replies | Each run reads your inbox over IMAP, read-only. Replies move the lead to `replied` with their words as a note. Opt-outs go on the do-not-contact list. Bounces block the address. Out-of-office mail is ignored. | free |
| Follow-up | One follow-up, in the same thread, drafted after the set number of days if there's no reply. It waits for approval too. | free |

## The dashboard

- **Dashboard**: pipeline counts, the approval queue (edit the subject and body inline, then approve, redraft or reject), follow-ups due, and the activity log.
- **Leads**: every company, filterable by stage. Add domains by hand here.
- **Lead page**: problems found with sources, contacts, the draft, sent messages, notes, stage and follow-up date.
- **Settings**: search keywords and sources, automatic runs (every N hours), daily email limit, minimum fit score, your pitches and signature, and the do-not-contact list.

Stages: `new → researched → drafted → contacted → replied → meeting → won / lost` (or `needs_contact` / `skipped` / `error`).
Replies update stages by themselves. `meeting`, `won` and `lost` are yours to set.

Most businesses have decent sites, so expect only a fraction of leads to become drafts (1 in 8 in the first test).
Set **New leads per run** with that in mind; each lead takes 10 to 20 seconds.

Automatic runs only happen while `app.py` is running and the computer is awake.

## Safety rails

Nothing is sent without your click. There's a daily send cap, a first message never goes to an address
already contacted, and the do-not-contact list (domains or addresses) is checked before every send.
Every email carries your opt-out line and postal address.

## Files

```
app.py              routes
leads/db.py         SQLite: leads, messages, notes, settings, do-not-contact
check.py            tests every connection
leads/discover.py   OpenStreetMap, YC, HN, manual add
leads/fetch.py      polite HTTP (robots.txt, user agent)
leads/render.py     headless browser at phone size
leads/research.py   crawl, checks, problems, scores
leads/contacts.py   emails, socials, MX check
leads/draft.py      LLM, draft checks, template, follow-ups
leads/send.py       SMTP
leads/inbox.py      replies, opt-outs, bounces (IMAP)
leads/pipeline.py   the run, the scheduler, approve / reject
templates/, static/ plain HTML + one CSS file
```
