# Agency Growth Engine — frontend

Next.js 15 (App Router) dashboard for the Agency Growth Engine API. TypeScript (strict), Tailwind CSS v4,
shadcn/ui (Radix), TanStack Query, react-hook-form + zod, sonner, recharts, lucide-react.

## Development

```bash
cp .env.example .env.local      # API_INTERNAL_URL=http://localhost:8100 (the FastAPI backend)
npm install
npm run dev -- -p 3100          # http://localhost:3100
```

Other scripts:

```bash
npm run build       # production build (output: "standalone")
npm run start       # serve the build on :3000
npm run lint        # eslint
npm run typecheck   # tsc --noEmit
```

## How the browser talks to the API

The browser only ever calls relative `/api/...`. `next.config.ts` rewrites `/api/:path*` to
`${API_INTERNAL_URL}/api/:path*`, so the API is same-origin: the httpOnly `age_session` cookie and the
`csrf_token` cookie are set on the dashboard's origin and no CORS is needed.

* Every non-GET request sends `X-CSRF-Token` (read from the `csrf_token` cookie, or from the login / `/auth/me` response).
* A 401 redirects to `/login?next=…`. `src/middleware.ts` also redirects to `/login` when there's no session cookie.
* Roles (admin > operator > viewer) hide or disable actions in the UI; the backend enforces the same rules.

**`API_INTERNAL_URL` is read at build time.** With `output: "standalone"`, rewrites are compiled into the
server during `next build`, so changing the variable at runtime has no effect. The Dockerfile takes it as a
build arg (default `http://api:8000`, the compose service). Rebuild the image to point at a different backend.

## Docker

```bash
docker build -t age-frontend --build-arg API_INTERNAL_URL=http://api:8000 .
docker run -p 3000:3000 age-frontend
```

`docker compose up` builds it with context `./frontend`. For Gmail/Outlook OAuth, set the backend's
`PUBLIC_APP_URL` to the dashboard URL so the callback redirects back to `/settings/integrations`.

## Layout

```
src/app/login                 sign-in
src/app/(app)/…               authenticated pages (sidebar shell)
src/components/ui             shadcn/ui primitives
src/components/shared         DataTable, PageHeader, StatusBadge, ScoreBar, EvidenceList, ObservationBadge,
                              EmptyState/ErrorState/skeletons, ConfirmDialog, Notice, TagInput, …
src/components/<area>         page-specific components
src/lib                       api client, types (mirroring backend/app/api), formatting, status metadata
src/hooks                     session/role, mutations with toasts, table state
```

The app never sends email. Approving a draft creates an **unsent** draft in the connected Gmail/Outlook
mailbox; the user sends it from their mail client.
