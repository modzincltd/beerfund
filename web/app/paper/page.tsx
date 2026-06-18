"use client";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, PaperPosition, Summary } from "@/lib/api";
import { Stat, Loading, ErrorBox, Section, DexIcon, WalletAddr, Reason, useSort, Th } from "@/components/ui";
import { PnlCurve } from "@/components/PnlCurve";
import { short, signed, pct, hold, ago, usd, num } from "@/lib/format";
import { useSolPrice } from "@/lib/price";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const POLL = { refreshInterval: 15000 };
const GOOD = "#3fb950", BAD = "#f85149", WARN = "#f5b301";

const when = (s: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

export default function PaperPage() {
  const price = useSolPrice();
  const { data: trips, error } = useSWR<PaperPosition[]>("/paper/positions", fetcher, POLL);
  const { data: summary } = useSWR<Summary>("/summary", fetcher, POLL);
  const { rows: tripRows, sort: tripSort } = useSort<PaperPosition>(trips || [], "open_ts", "desc");

  if (error) return <ErrorBox error={error} />;
  if (!trips) return <Loading what="paper trades" />;

  const closed = trips.filter((t) => !t.open);
  const open = trips.filter((t) => t.open);
  const realized = closed.reduce((s, t) => s + (t.realized_pnl_sol || 0), 0);
  const wins = closed.filter((t) => (t.realized_pnl_sol || 0) > 0).length;
  const winRate = closed.length ? wins / closed.length : 0;
  const holds = closed.map((t) => t.hold_seconds || 0).filter(Boolean);
  const avgHold = holds.length ? holds.reduce((a, b) => a + b, 0) / holds.length : null;
  const pnls = closed.map((t) => t.realized_pnl_sol || 0);
  const best = pnls.length ? Math.max(...pnls) : 0;
  const worst = pnls.length ? Math.min(...pnls) : 0;

  // exit-reason breakdown (closed trips)
  const byReason: Record<string, { count: number; pnl: number }> = {};
  for (const t of closed) {
    const r = t.close_reason || "?";
    (byReason[r] ??= { count: 0, pnl: 0 });
    byReason[r].count++;
    byReason[r].pnl += t.realized_pnl_sol || 0;
  }
  const reasonData = Object.entries(byReason)
    .map(([reason, v]) => ({ reason, count: v.count, pnl: +v.pnl.toFixed(3) }))
    .sort((a, b) => b.count - a.count);

  const ru = usd(realized, price);

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Paper trading</h1>
      <p className="text-sm text-muted mb-4">
        Every round trip the daemon took — when it opened, when and <em>why</em> it closed, and the
        realized result. Fills are marked at live Jupiter quotes; exits are the rules engine&apos;s.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Realized PnL" value={signed(realized)}
          tone={realized > 0 ? "good" : realized < 0 ? "bad" : undefined}
          sub={ru ? `≈ ${ru}` : `${closed.length} closed`} />
        <Stat label="Win rate" value={pct(winRate)} sub={`${wins}/${closed.length} closed`} />
        <Stat label="Open / closed" value={`${open.length} / ${closed.length}`}
          sub={summary ? `${summary.n_skipped} skipped` : undefined} />
        <Stat label="Avg hold" value={hold(avgHold)} sub={`best ${signed(best)} · worst ${signed(worst)}`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3 mt-3">
        <PnlCurve />
        <div className="card">
          <div className="label mb-1">Why positions closed</div>
          {reasonData.length === 0 ? (
            <div className="text-muted text-sm py-12 text-center">No closed round trips yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={reasonData} margin={{ top: 12, right: 8, bottom: 0, left: -20 }}>
                <XAxis dataKey="reason" stroke="#8a94a6" fontSize={11} tickLine={false} />
                <YAxis stroke="#8a94a6" fontSize={11} tickLine={false} allowDecimals={false} width={32} />
                <Tooltip
                  contentStyle={{ background: "#1c2230", border: "1px solid #2a3242", borderRadius: 8 }}
                  labelStyle={{ color: "#8a94a6" }}
                  formatter={(v: number, _n: string, p: any) => [`${v} trades · ${p.payload.pnl >= 0 ? "+" : ""}${p.payload.pnl} ◎`, p.payload.reason]}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {reasonData.map((d, i) => (
                    <Cell key={i} fill={d.pnl > 0 ? GOOD : d.pnl < 0 ? BAD : WARN} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <Section title={`Round trips (${trips.length})`}>
        <div className="card overflow-x-auto p-0">
          <table className="grid-table">
            <thead>
              <tr>
                <Th sort={tripSort} field="mint">Token</Th>
                <Th sort={tripSort} field="wallet">Wallet</Th>
                <Th sort={tripSort} field="open_ts">Opened</Th>
                <Th sort={tripSort} field="close_ts">Closed</Th>
                <Th sort={tripSort} field="hold_seconds">Hold</Th>
                <Th sort={tripSort} field="entry_sol">Entry</Th>
                <Th sort={tripSort} field="close_reason">Why</Th>
                <Th sort={tripSort} field="realized_pnl_sol">PnL</Th>
                <Th sort={tripSort} field="realized_return">Return</Th>
              </tr>
            </thead>
            <tbody>
              {tripRows.map((t, i) => (
                <tr key={i}>
                  <td className="mono">{t.symbol || short(t.mint, 5)}<DexIcon mint={t.mint} /></td>
                  <td>{t.wallet ? <WalletAddr wallet={t.wallet} len={4} showLabel={false} /> : "—"}</td>
                  <td className="text-muted whitespace-nowrap">{when(t.open_ts)}</td>
                  <td className="whitespace-nowrap">
                    {t.open ? <span className="badge bg-good/10 text-good">OPEN</span> : <span className="text-muted">{when(t.close_ts)}</span>}
                  </td>
                  <td>{hold(t.hold_seconds)}</td>
                  <td>{t.entry_sol != null ? `${t.entry_sol} ◎` : "—"}</td>
                  <td>{t.open ? <span className="text-muted text-xs">{t.n_exits} exit{t.n_exits === 1 ? "" : "s"}</span> : <Reason r={t.close_reason} />}</td>
                  <td className={t.realized_pnl_sol == null ? "" : t.realized_pnl_sol >= 0 ? "text-good" : "text-bad"}>
                    {t.realized_pnl_sol == null ? "—" : signed(t.realized_pnl_sol)}
                  </td>
                  <td className={t.realized_return == null ? "" : t.realized_return >= 0 ? "text-good" : "text-bad"}>
                    {t.realized_return == null ? "—" : pct(t.realized_return)}
                  </td>
                </tr>
              ))}
              {trips.length === 0 && (
                <tr><td colSpan={9} className="text-muted text-center py-6">No paper trades yet — the daemon arms on each followed wallet&apos;s next buy.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="mt-6">
        <Link href="/trades" className="text-sm text-accent hover:underline">
          View the full trade log with buy → sell arrows →
        </Link>
      </div>
    </div>
  );
}
