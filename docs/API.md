# API

Interactive documentation: **`/api/docs`** (Swagger UI) and `/api/redoc`; machine-readable spec at
`/api/openapi.json` (a snapshot is committed at `docs/openapi.json`).

## Authentication

```bash
# Browser clients: cookie session + CSRF header
curl -c jar -H 'content-type: application/json' \
     -d '{"email":"admin@example.com","password":"…"}' http://localhost:8000/api/auth/login
# → {"user": {...}, "csrf_token": "…"}  — send it as X-CSRF-Token on POST/PUT/PATCH/DELETE

# Scripts: Bearer token (no CSRF needed) — use the age_session cookie value
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/companies
```

Errors: `401` unauthenticated, `403` role/CSRF, `404`, `409` conflict (duplicate, invalid state
transition, suppression), `422` validation (`{"detail","errors":[…]}`), `429` rate limit / AI budget,
`503` AI not configured.

Lists are paginated: `?page=1&page_size=25` → `{items,total,page,page_size}`.

## Endpoint map

| Area | Endpoints |
|---|---|
| Auth & users | `POST /api/auth/login`, `/logout`, `GET /api/auth/me`, `POST /api/auth/change-password`; `/api/users` CRUD, `/{id}/revoke-sessions` |
| Settings | `GET /api/settings`, `GET/PUT /api/settings/{agency_profile|llm|discovery|enrichment|research|scoring|quality|retention}` |
| Campaigns | `/api/campaigns` CRUD, `GET /{id}/preview-queries`, `POST /{id}/run`, `GET /templates` |
| Discovery | `GET /api/discovery/providers`, `GET /history`, `POST /search`, `POST /import` (multipart CSV) |
| Companies | `GET /api/companies` (q, status[], campaign_id, service, min_website, min_brain, industry, tag, sort), `POST`, `GET/PATCH/DELETE /{id}`, `POST /{id}/status`, `POST /bulk`, `GET /export`, notes |
| Contacts | `GET/POST /api/contacts`, `GET/PATCH/DELETE /{id}`, `POST /{id}/verify-email`, `POST /{id}/do-not-contact`, `GET /export` |
| Research | `GET /api/research`, `GET /{id}`, `GET /signals`, `POST /company/{id}/run` |
| Opportunities | `GET /api/opportunities`, `GET /pipeline`, `GET /company/{id}`, `POST /company/{id}/score` |
| Drafts | `GET /api/drafts`, `GET/PATCH /{id}`, `POST /generate` |
| Approvals | `GET /api/approvals/queue`, `POST /{id}/approve` (`email_account_id`, `edits`, `override_quality`), `/reject`, `/save-for-later`, `/regenerate`, `/do-not-contact` |
| Email | `GET /api/email/accounts`, `GET /oauth/{gmail|outlook}/start`, `GET /oauth/{p}/callback`, `POST /accounts/{id}/default`, `POST /accounts/{id}/sync`, `DELETE /accounts/{id}` |
| Conversations | `GET /api/conversations`, `POST /inbound`, `POST /{id}/reclassify`, `/label`, `/handled` |
| Tasks | `/api/tasks` CRUD |
| Suppression | `GET/POST /api/suppression`, `POST /{id}/deactivate` (admin; not for opt-outs) |
| Workflows | `GET /api/workflows`, `POST /{name}/run`, `PATCH /{name}/schedule`, `POST /pause-all`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`, `/cancel` |
| AI | `GET /api/ai/status`, `POST /api/ai/test`, `GET /api/ai/usage`, `GET /api/ai/runs` |
| Knowledge / Company Brain | `/api/knowledge` CRUD, `GET/POST /api/knowledge/connectors`, `POST /connectors/{id}/test`, `/sync`, `DELETE` |
| Analytics & dashboard | `GET /api/analytics?days=`, `GET /api/dashboard`, `GET /api/integrations` |
| Admin | `GET /api/admin/audit`, `GET /api/admin/export/all`, `GET /api/admin/export/contact/{id}`, `POST /api/admin/erase/contact/{id}` |
| System | `GET /api/health` |

There is intentionally **no endpoint that sends email**.
