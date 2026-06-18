"use client";
import { Suspense, useState } from "react";
import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { fetcher, Coin } from "@/lib/api";
import { Loading, ErrorBox, Flag, Section, DexIcon, WalletAddr, useSort, Th } from "@/components/ui";
import { short, signed, pct, hold, ago } from "@/lib/format";

interface CoinDetailResp {
  coin: Coin | null;
  wallet_appearances: {
    wallet: string;
    realized_pnl_sol: number;
    realized_return: number;
    hold_seconds: number;
    closed: boolean;
    transfer_fed: boolean;
  }[];
  paper_trades: { id: number; ts: string; event: string; reason: string | null; sol: number | null; pnl_sol: number | null }[];
}

function CoinDetail({ mint }: { mint: string }) {
  const { data } = useSWR<CoinDetailResp>(`/coins/${mint}`, fetcher);
  const { rows: appRows, sort: appSort } = useSort(data?.wallet_appearances || []);
  const { rows: ptRows, sort: ptSort } = useSort(data?.paper_trades || []);
  if (!data) return <Loading what="coin" />;
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <span className="mono">{short(mint, 8)}<DexIcon mint={mint} /></span>
        <div>{(data.coin?.risk_flags || []).map((f) => <Flag key={f}>{f}</Flag>)}</div>
      </div>
      <Section title={`Smart wallets that traded it (${data.wallet_appearances.length})`}>
        <table className="grid-table">
          <thead><tr>
            <Th sort={appSort} field="wallet">Wallet</Th>
            <Th sort={appSort} field="realized_pnl_sol">PnL</Th>
            <Th sort={appSort} field="realized_return">Return</Th>
            <Th sort={appSort} field="hold_seconds">Hold</Th>
            <th>State</th>
          </tr></thead>
          <tbody>
            {appRows.map((w, i) => (
              <tr key={i}>
                <td><WalletAddr wallet={w.wallet} len={4} /></td>
                <td className={w.realized_pnl_sol >= 0 ? "text-good" : "text-bad"}>{signed(w.realized_pnl_sol)}</td>
                <td>{pct(w.realized_return)}</td>
                <td>{hold(w.hold_seconds)}</td>
                <td className="text-xs">{w.transfer_fed ? "transfer-fed" : w.closed ? "closed" : "open"}</td>
              </tr>
            ))}
            {data.wallet_appearances.length === 0 && (
              <tr><td colSpan={5} className="text-muted py-4 text-center">No audited wallet has traded this token.</td></tr>
            )}
          </tbody>
        </table>
      </Section>
      {data.paper_trades.length > 0 && (
        <Section title="Our paper trades">
          <table className="grid-table">
            <thead><tr>
              <Th sort={ptSort} field="ts">Time</Th>
              <Th sort={ptSort} field="event">Event</Th>
              <Th sort={ptSort} field="reason">Reason</Th>
              <Th sort={ptSort} field="sol">SOL</Th>
              <Th sort={ptSort} field="pnl_sol">PnL</Th>
            </tr></thead>
            <tbody>
              {ptRows.map((t) => (
                <tr key={t.id}>
                  <td className="text-muted">{ago(t.ts)}</td>
                  <td>{t.event}</td>
                  <td className="text-muted">{t.reason}</td>
                  <td>{t.sol != null ? signed(t.sol) : "—"}</td>
                  <td>{t.pnl_sol != null ? signed(t.pnl_sol) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </div>
  );
}

function CoinsInner() {
  const params = useSearchParams();
  const initial = params.get("mint");
  const [sel, setSel] = useState<string | null>(initial);
  const { data, error } = useSWR<Coin[]>("/coins?limit=300", fetcher, { refreshInterval: 30000 });
  const { rows: coinRows, sort: coinSort } = useSort<Coin>(data || []);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="coins" />;

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Coin analysis</h1>
      <p className="text-sm text-muted mb-4">
        Every token our followed/audited wallets touched, plus our own paper trades. Risk flags mark
        structurally uncopyable patterns (transfer-fed supply, launch-price entries).
      </p>
      {sel && (
        <div className="mb-4">
          <button onClick={() => setSel(null)} className="text-xs text-muted hover:text-white mb-2">← back to list</button>
          <CoinDetail mint={sel} />
        </div>
      )}
      {!sel && (
        <div className="card overflow-x-auto p-0">
          <table className="grid-table">
            <thead>
              <tr>
                <Th sort={coinSort} field="mint">Token</Th>
                <Th sort={coinSort} field="n_wallets">Wallets</Th>
                <Th sort={coinSort} field="n_audit_appearances">Audit hits</Th>
                <Th sort={coinSort} field="n_paper_trades">Paper trades</Th>
                <th>Flags</th>
                <Th sort={coinSort} field="last_seen">Last seen</Th>
              </tr>
            </thead>
            <tbody>
              {coinRows.map((c) => (
                <tr key={c.mint} className="cursor-pointer" onClick={() => setSel(c.mint)}>
                  <td className="mono hover:text-accent">{c.symbol || short(c.mint, 6)}<DexIcon mint={c.mint} /></td>
                  <td>{c.n_wallets}</td>
                  <td>{c.n_audit_appearances}</td>
                  <td>{c.n_paper_trades}</td>
                  <td>{(c.risk_flags || []).map((f) => <Flag key={f}>{f}</Flag>)}</td>
                  <td className="text-muted">{ago(c.last_seen)}</td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={6} className="text-muted text-center py-6">No coins yet — appears after trades or audits run.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CoinsPage() {
  return (
    <Suspense fallback={<Loading what="coins" />}>
      <CoinsInner />
    </Suspense>
  );
}
