"use client";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, Summary, Criteria, Position, Trade } from "@/lib/api";
import { Stat, Loading, ErrorBox, Section, Flag, DexIcon, WalletAddr, useSort, Th } from "@/components/ui";
import { CriteriaPanel } from "@/components/CriteriaPanel";
import { PnlCurve } from "@/components/PnlCurve";
import { InsightPanels } from "@/components/InsightPanels";
import { short, signed, sol, ago, hold, pos, usd } from "@/lib/format";
import { useSolPrice } from "@/lib/price";

const POLL = { refreshInterval: 15000 };

export default function Dashboard() {
  const { data: s, error } = useSWR<Summary>("/summary", fetcher, POLL);
  const { data: c } = useSWR<Criteria>("/criteria", fetcher, POLL);
  const { data: positions } = useSWR<Position[]>("/positions", fetcher, POLL);
  const { data: trades } = useSWR<Trade[]>("/trades?limit=15", fetcher, POLL);
  const price = useSolPrice();
  const { rows: posRows, sort: posSort } = useSort<Position>(positions || []);
  const { rows: tradeRows, sort: tradeSort } = useSort<Trade>(trades || [], "ts", "desc");

  if (error) return <ErrorBox error={error} />;
  if (!s) return <Loading what="the live state" />;

  const realizedUsd = usd(s.realized_sol, price);

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Realized PnL"
          value={signed(s.realized_sol)}
          tone={s.realized_sol > 0 ? "good" : s.realized_sol < 0 ? "bad" : undefined}
          sub={realizedUsd ? `≈ ${realizedUsd} · ${s.n_closed} closed` : `${s.n_closed} closed`}
        />
        <Stat label="Open positions" value={s.n_open} sub={`size ${sol(s.position_size_sol, 2)}`} />
        <Stat label="Filled / target" value={`${s.n_filled} / 20`} sub={`${s.n_skipped} skipped`} />
        <Stat label="Last trade" value={ago(s.last_trade)} sub={`since ${s.first_trade ? new Date(s.first_trade).toLocaleDateString() : "—"}`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3 mt-3">
        {c && <CriteriaPanel c={c} />}
        <PnlCurve />
      </div>

      <Section title="AI analyst — auto insights">
        <InsightPanels />
      </Section>

      <Section
        title={`Open positions (${positions?.length ?? 0})`}
        action={<Link href="/coins" className="text-xs text-muted hover:text-white">all coins →</Link>}
      >
        <div className="card overflow-x-auto p-0">
          <table className="grid-table">
            <thead>
              <tr>
                <Th sort={posSort} field="mint">Token</Th>
                <Th sort={posSort} field="wallet">Wallet</Th>
                <Th sort={posSort} field="age_seconds">Age</Th>
                <Th sort={posSort} field="remaining">Remaining</Th>
                <Th sort={posSort} field="rung">Rung</Th>
                <Th sort={posSort} field="banked_sol">Banked</Th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {posRows.map((p) => (
                <tr key={p.mint}>
                  <td>
                    <Link href={`/coins?mint=${p.mint}`} className="mono hover:text-accent">
                      {p.symbol || short(p.mint, 5)}
                    </Link>
                    <DexIcon mint={p.mint} />
                  </td>
                  <td><WalletAddr wallet={p.wallet} len={4} /></td>
                  <td>{hold(Math.round(p.age_seconds))}</td>
                  <td>{(p.remaining * 100).toFixed(0)}%</td>
                  <td>{p.rung}</td>
                  <td>{sol(p.banked_sol)}</td>
                  <td>{(p.risk_flags || []).map((f) => <Flag key={f}>{f}</Flag>)}</td>
                </tr>
              ))}
              {positions?.length === 0 && (
                <tr><td colSpan={7} className="text-muted text-center py-6">No open positions right now.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Recent trade log" action={<Link href="/trades" className="text-xs text-muted hover:text-white">all trades →</Link>}>
        <div className="card overflow-x-auto p-0">
          <table className="grid-table">
            <thead>
              <tr>
                <Th sort={tradeSort} field="ts">Time</Th>
                <Th sort={tradeSort} field="event">Event</Th>
                <Th sort={tradeSort} field="mint">Token</Th>
                <Th sort={tradeSort} field="reason">Reason</Th>
                <Th sort={tradeSort} field="sol">SOL</Th>
                <Th sort={tradeSort} field="pnl_sol">PnL</Th>
              </tr>
            </thead>
            <tbody>
              {tradeRows.map((t) => (
                <tr key={t.id}>
                  <td className="text-muted">{ago(t.ts)}</td>
                  <td>
                    <span className={`badge ${t.event === "CLOSE" ? "bg-accent/15 text-accent" : t.event === "ENTRY" ? "bg-good/10 text-good" : "bg-panel2 text-gray-300"}`}>
                      {t.event}
                    </span>
                  </td>
                  <td className="mono">{short(t.mint, 5)}<DexIcon mint={t.mint} /></td>
                  <td className="text-muted">{t.reason}</td>
                  <td>{t.sol != null ? sol(t.sol) : "—"}</td>
                  <td className={t.pnl_sol == null ? "" : pos(t.pnl_sol) ? "text-good" : "text-bad"}>
                    {t.pnl_sol == null ? "—" : signed(t.pnl_sol)}
                  </td>
                </tr>
              ))}
              {trades?.length === 0 && (
                <tr><td colSpan={6} className="text-muted text-center py-6">No trades logged yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
