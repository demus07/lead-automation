"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";
import { fmtDate } from "@/lib/format";

export const RANGES = [7, 30, 90, 365] as const;

export function RangeToggle({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  return (
    <div className="inline-flex rounded-lg border p-0.5" role="radiogroup" aria-label="Time range">
      {RANGES.map((d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={value === d}
          onClick={() => onChange(d)}
          className={cn(
            "h-7 rounded-md px-2.5 text-xs font-medium tabular-nums transition-colors",
            value === d ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {d === 365 ? "1 year" : `${d} days`}
        </button>
      ))}
    </div>
  );
}

export function AnalyticsTabs() {
  const path = usePathname();
  const tabs = [
    { href: "/analytics", label: "Pipeline" },
    { href: "/analytics/ai", label: "AI usage" },
  ];
  return (
    <nav className="mb-6 flex gap-5 border-b" aria-label="Analytics sections">
      {tabs.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          className={cn(
            "-mb-px border-b-2 pb-2 text-sm transition-colors",
            path === t.href ? "border-brand font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

/** Horizontal bar list: label, bar, value. The most readable form for ranked categories. */
export function BarList({
  items,
  color = "var(--chart-1)",
  format = (n) => n.toLocaleString(),
  empty = "No data in this period.",
}: {
  items: { label: React.ReactNode; value: number; color?: string; hint?: React.ReactNode }[];
  color?: string;
  format?: (n: number) => string;
  empty?: string;
}) {
  if (!items.length || items.every((i) => !i.value)) return <p className="text-sm text-muted-foreground">{empty}</p>;
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="space-y-2.5">
      {items.map((it, i) => (
        <li key={i} className="grid grid-cols-[minmax(6rem,10rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-muted-foreground">{it.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span className="block h-full rounded-full" style={{ width: `${(it.value / max) * 100}%`, background: it.color ?? color }} />
          </span>
          <span className="min-w-10 text-right font-medium tabular-nums">
            {format(it.value)}
            {it.hint && <span className="ml-1.5 text-xs font-normal text-muted-foreground">{it.hint}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

const axis = { fill: "var(--muted-foreground)", fontSize: 11 };

/** Daily column chart (single series). Fills missing days with zero so gaps read as zero, not as missing. */
export function DailyBars({
  data,
  days,
  valueKey,
  label,
  color = "var(--chart-1)",
  format = (n: number) => n.toLocaleString(),
}: {
  data: { date: string; [k: string]: number | string }[];
  days: number;
  valueKey: string;
  label: string;
  color?: string;
  format?: (n: number) => string;
}) {
  const byDate = new Map(data.map((d) => [d.date, Number(d[valueKey]) || 0]));
  const series: { date: string; value: number }[] = [];
  const today = new Date();
  for (let i = Math.min(days, 90) - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - i));
    const key = d.toISOString().slice(0, 10);
    series.push({ date: key, value: byDate.get(key) ?? 0 });
  }
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="date" tick={axis} tickLine={false} axisLine={false} minTickGap={28} tickFormatter={(d: string) => fmtDate(d, "d MMM")} />
          <YAxis tick={axis} tickLine={false} axisLine={false} allowDecimals={false} width={44} tickFormatter={(v: number) => format(v)} />
          <Tooltip
            cursor={{ fill: "var(--muted)" }}
            contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--popover-foreground)" }}
            labelFormatter={(d) => fmtDate(String(d), "EEE d MMM yyyy")}
            formatter={(v) => [format(Number(v)), label]}
          />
          <Bar dataKey="value" fill={color} radius={[3, 3, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
