export const short = (addr: string, n = 4) =>
  addr.length > 2 * n + 1 ? `${addr.slice(0, n)}…${addr.slice(-n)}` : addr;

export const sol = (v: number | null | undefined, dp = 3) =>
  v == null ? "—" : `${v >= 0 ? "" : ""}${v.toFixed(dp)} ◎`;

export const signed = (v: number | null | undefined, dp = 3) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)} ◎`;

export const pct = (v: number | null | undefined, dp = 0) =>
  v == null ? "—" : `${(v * 100).toFixed(dp)}%`;

// USD value of a SOL amount given a SOL/USD price. Returns null (renders as
// nothing) when either input is missing, so callers degrade to SOL-only.
export const usd = (
  solAmount: number | null | undefined,
  price: number | null | undefined,
  dp = 0,
): string | null => {
  if (solAmount == null || price == null) return null;
  const v = solAmount * price;
  return `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: dp })}`;
};

export const num = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString();

export function hold(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 90) return `${seconds}s`;
  if (seconds < 5400) return `${(seconds / 60).toFixed(0)}m`;
  if (seconds < 172800) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  return hold(Math.max(0, Math.round(s))) + " ago";
}

export const pos = (v: number | null | undefined) => (v ?? 0) >= 0;

export const VERDICT_STYLE: Record<string, string> = {
  CANDIDATE: "bg-good/15 text-good border border-good/30",
  DECAYING: "bg-warn/15 text-warn border border-warn/30",
  THIN: "bg-muted/15 text-muted border border-muted/30",
  TOOFAST: "bg-warn/15 text-warn border border-warn/30",
  LOSER: "bg-bad/15 text-bad border border-bad/30",
  INSIDER: "bg-bad/15 text-bad border border-bad/30",
};
