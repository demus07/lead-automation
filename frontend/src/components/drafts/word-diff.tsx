import { cn } from "@/lib/utils";

type Part = { type: "same" | "add" | "del"; text: string };

/** Word-level LCS diff (whitespace kept as tokens so line breaks survive). */
export function wordDiff(a: string, b: string): Part[] {
  const A = a.split(/(\s+)/).filter((t) => t !== "");
  const B = b.split(/(\s+)/).filter((t) => t !== "");
  const n = A.length;
  const m = B.length;
  // Guard against pathological sizes: fall back to whole-text replace.
  if (n * m > 6_000_000) return [{ type: "del", text: a }, { type: "add", text: b }];
  const dp: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: Part[] = [];
  const push = (type: Part["type"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += text;
    else out.push({ type, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      push("same", A[i]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) push("del", A[i++]);
    else push("add", B[j++]);
  }
  while (i < n) push("del", A[i++]);
  while (j < m) push("add", B[j++]);
  return out;
}

export function WordDiff({ before, after, className }: { before: string; after: string; className?: string }) {
  if (before === after) return <p className={cn("text-sm whitespace-pre-wrap text-muted-foreground", className)}>{after || "Empty"}</p>;
  return (
    <p className={cn("text-sm leading-7 whitespace-pre-wrap", className)}>
      {wordDiff(before, after).map((p, i) =>
        p.type === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.type === "add" ? (
          <ins key={i} className="tone tone-success rounded-sm no-underline">
            {p.text}
          </ins>
        ) : (
          <del key={i} className="tone tone-danger rounded-sm decoration-1">
            {p.text}
          </del>
        ),
      )}
    </p>
  );
}
