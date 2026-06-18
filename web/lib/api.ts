// Typed client for the FastAPI read API. Base URL comes from the environment so
// the same build points at localhost in dev and the droplet in production.
// Default to 127.0.0.1 (not "localhost") so a Mac resolving localhost to IPv6
// ::1 can't miss the IPv4-bound API. Vercel/prod overrides via the env var.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  // Only send Content-Type when there's a body (POST). A GET carrying
  // Content-Type: application/json is a "non-simple" request and forces a CORS
  // preflight on every dashboard call — avoid it.
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

// SWR fetcher
export const fetcher = <T>(path: string) => api<T>(path);

// ---- shapes (mirror api/queries.py) ----
export interface Summary {
  realized_sol: number;
  n_closed: number;
  n_skipped: number;
  n_filled: number;
  n_open: number;
  position_size_sol: number;
  first_trade: string | null;
  last_trade: string | null;
  updated_at: string | null;
}

export interface Check {
  label: string;
  pass: boolean;
  [k: string]: unknown;
}
export interface Criteria {
  duration: Check & { weeks_live: number | null; n_filled: number };
  net_positive: Check & { realized_sol: number };
  drawdown: Check & { max_drawdown_sizes: number | null };
  follow_pool: Check & { n_passing: number; wallets: WalletAudit[] };
  all_pass: boolean;
}

export interface Position {
  mint: string;
  wallet: string;
  entry_ts: string;
  tokens: string;
  entry_price: number;
  peak: number;
  remaining: number;
  rung: number;
  banked_sol: number;
  cost_sol: number;
  age_seconds: number;
  symbol: string | null;
  risk_flags: string[];
}

export interface Trade {
  id: number;
  ts: string;
  event: "ENTRY" | "EXIT" | "CLOSE";
  mint: string;
  wallet: string | null;
  fraction: number | null;
  sol: number | null;
  tokens: string | null;
  price: number | null;
  reason: string | null;
  pnl_sol: number | null;
}

export interface WalletAudit {
  id: number;
  wallet: string;
  ts: string;
  n_swaps: number;
  n_closed: number;
  n_open: number;
  win_rate: number;
  total_realized_sol: number;
  median_pnl_sol: number | null;
  median_hold_s: number | null;
  best_trade_sol: number | null;
  concentration: number | null;
  old_avg: number | null;
  new_avg: number | null;
  decaying: boolean;
  verdict_code: string;
  verdict_reason: string | null;
  in_follow_pool: boolean;
}

export interface AuditPosition {
  mint: string;
  realized_pnl_sol: number;
  realized_return: number;
  hold_seconds: number;
  closed: boolean;
  transfer_fed: boolean;
  n_swaps: number;
}

export interface WalletDetail {
  audit: WalletAudit;
  positions: AuditPosition[];
  history: { ts: string; verdict_code: string; win_rate: number; total_realized_sol: number; decaying: boolean }[];
  active: { first: string | null; last: string | null };
}

export interface Balances {
  sol: number;
  tokens: { mint: string; amount: number }[];
  n_tokens: number;
}

export interface Settings {
  audit: {
    min_closed: number;
    insider_return_x: number;
    min_median_hold_s: number;
    decay_ratio: number;
  };
  golive: {
    min_filled: number;
    min_weeks: number;
    max_drawdown_sizes: number;
    min_passing_wallets: number;
  };
}

export interface Coin {
  mint: string;
  symbol: string | null;
  first_seen: string | null;
  last_seen: string | null;
  liquidity_sol: number | null;
  price_sol: number | null;
  n_audit_appearances: number;
  n_paper_trades: number;
  risk_flags: string[];
  n_wallets: number;
}

export interface DiscoveryRow {
  wallet: string;
  source: string;
  discovered_at: string;
  status: string;
  last_verdict: string | null;
  win_rate: number | null;
  total_realized_sol: number | null;
  verdict_reason: string | null;
}

export interface Insight {
  kind: string;
  body: string;
  model: string | null;
  created_at: string;
}

export interface ChatResponse {
  reply: string;
  trace: { tool: string; input: unknown }[];
  model: string;
}
