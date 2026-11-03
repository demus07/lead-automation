/**
 * Thin fetch wrapper for the FastAPI backend.
 * The browser always calls relative /api/... (proxied by Next rewrites) so the
 * httpOnly session cookie is same-origin. Every non-GET request carries the
 * X-CSRF-Token header (double-submit cookie, bound to the session server-side).
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  errors?: { loc?: (string | number)[]; msg?: string }[];
  constructor(status: number, message: string, detail?: unknown, errors?: ApiError["errors"]) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.errors = errors;
  }
  /** 503 from AI-dependent endpoints when no LLM is configured, or similar. */
  get isUnavailable() {
    return this.status === 503;
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

function getCsrf(): string | null {
  return readCookie("csrf_token") || csrfToken;
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export function qs(params?: Query): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

function messageFrom(status: number, body: unknown): { message: string; errors?: ApiError["errors"] } {
  if (body && typeof body === "object") {
    const b = body as { detail?: unknown; errors?: ApiError["errors"] };
    if (Array.isArray(b.errors) && b.errors.length) {
      const msgs = b.errors.map((e) => {
        const field = (e.loc || []).filter((x) => x !== "body").join(".");
        return field ? `${field}: ${e.msg}` : e.msg;
      });
      return { message: msgs.join("; "), errors: b.errors };
    }
    if (typeof b.detail === "string") return { message: b.detail };
    if (Array.isArray(b.detail)) {
      return {
        message: b.detail
          .map((e: { msg?: string; loc?: unknown[] }) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`)
          .join("; "),
      };
    }
  }
  if (status === 401) return { message: "Your session has expired. Sign in again." };
  if (status === 403) return { message: "Your role doesn't allow this action." };
  if (status >= 500) return { message: `The server returned an error (${status}).` };
  return { message: `Request failed (${status})` };
}

function onUnauthorized() {
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/login?next=${next}`;
}

export interface RequestOptions {
  method?: string;
  query?: Query;
  body?: unknown;
  /** Skip 401 → /login redirect (used by the login/me probe). */
  noRedirect?: boolean;
  raw?: boolean;
  signal?: AbortSignal;
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = (opts.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) {
    body = opts.body;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (method !== "GET" && method !== "HEAD") {
    const t = getCsrf();
    if (t) headers["X-CSRF-Token"] = t;
  }
  const res = await fetch(`/api${path}${qs(opts.query)}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (res.status === 401 && !opts.noRedirect) onUnauthorized();
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* not JSON */
    }
    const { message, errors } = messageFrom(res.status, parsed);
    throw new ApiError(res.status, message, parsed, errors);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string, query?: Query, opts?: Omit<RequestOptions, "query">) =>
    request<T>(path, { ...opts, query }),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>(path, { method: "POST", body, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string, query?: Query) => request<T>(path, { method: "DELETE", query }),
};

/** Download a file (CSV/ZIP) from an authenticated GET endpoint. */
export async function download(path: string, query?: Query, fallbackName = "export") {
  const res = await request<Response>(path, { query, raw: true });
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const m = cd.match(/filename="?([^";]+)"?/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}
