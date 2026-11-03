import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";

function toDate(v: string | Date | null | undefined): Date | null {
  if (!v) return null;
  const d = typeof v === "string" ? parseISO(v) : v;
  return isValid(d) ? d : null;
}

export function fmtDate(v: string | Date | null | undefined, pattern = "d MMM yyyy"): string {
  const d = toDate(v);
  return d ? format(d, pattern) : "—";
}

export function fmtDateTime(v: string | Date | null | undefined): string {
  return fmtDate(v, "d MMM yyyy, HH:mm");
}

export function fmtRelative(v: string | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "—";
  return formatDistanceToNowStrict(d, { addSuffix: true });
}

export function fmtNumber(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtPercent(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function fmtUsd(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toFixed(n !== 0 && Math.abs(n) < 0.01 ? 4 : digits)}`;
}

export function fmtMs(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n)}ms`;
}

/** "PENDING_APPROVAL" / "pending_approval" → "Pending approval" */
export function humanize(s: string | null | undefined): string {
  if (!s) return "—";
  const t = s.replace(/[_:.-]+/g, " ").trim().toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function hostname(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function serviceLabel(s: string | null | undefined): string {
  if (s === "website") return "Website";
  if (s === "company_brain") return "Company Brain";
  if (!s || s === "none") return "No fit yet";
  if (s === "any") return "Any service";
  return humanize(s);
}

export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
