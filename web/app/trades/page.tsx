"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetcher, PaperPosition, Trade } from "@/lib/api";
import { Loading, ErrorBox, Section, DexIcon, Reason, useSort, Th } from "@/components/ui";
import { short, signed, pct, hold, ago, usd } from "@/lib/format";
import { useSolPrice } from "@/lib/price";

const when = (s: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

function RoundTrip({ t, price }: { t: PaperPosition; price: number | null }) {
  const pnlClass = t.realized_pnl_sol == null ? "" : t.realized_pnl_sol >= 0 ? "text-good" : "text-bad";
  const u = usd(t.realized_pnl_sol, price);
  return (
    <div className="card">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="mono">{t.symbol || short(t.mint, 6)}<DexIcon mint={t.mint} /></span>
          {t.wallet && <span className="text-xs text-muted">via <span className="mono">{t.wallet}…</span></span>}
        </div>
        <div className="flex items-center gap-2 text-sm">
          {t.open ? (
            <span className="badge bg-good/10 text-good">OPEN</span>
          ) : (
            <span className={pnlClass}>
              {signed(t.realized_pnl_sol)}{u && <span className="text-muted"> · {u}</span>}
              {t.realized_return != null && <span> ({pct(t.realized_return)})</span>}
            </span>
          )}
          <span className="text-muted">{hold(t.hold_seconds)}</span>
        </div>
      </div>

      {/* the buy, then arrows down to each sell / the close */}
      <div className="mt-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="badge bg-good/15 text-good">▲ BUY</span>
          <span>{t.entry_sol != null ? `${t.entry_sol} ◎` : "—"}</span>
          {t.entry_price != null && <span className="text-muted text-xs">@ {t.entry_price.toExponential(2)}</span>}
          <span className="text-muted text-xs ml-auto">{when(t.open_ts)}</span>
        </div>
        <div className="border-l-2 border-edge/70 ml-3 pl-3 mt-1 space-y-1">
          {t.exits.map((e, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-muted">↳</span>
              <span className="badge bg-bad/10 text-bad">▼ SELL</span>
              <Reason r={e.reason} />
              <span>{e.sol != null ? `${e.sol} ◎` : "—"}</span>
              {e.fraction != null && <span className="text-muted text-xs">{(e.fraction * 100).toFixed(0)}%</span>}
              <span className="text-muted text-xs ml-auto">{when(e.ts)}</span>
            </div>
          ))}
          {!t.open && (
            <div className="flex items-center gap-2">
              <span className="text-muted">↳</span>
              <span className="badge bg-accent/15 text-accent">■ CLOSE</span>
              <Reason r={t.close_reason} />
              <span className={pnlClass}>{signed(t.realized_pnl_sol)}</span>
              <span className="text-muted text-xs ml-auto">{when(t.close_ts)}</span>
            </div>
          )}
          {t.open && t.exits.length === 0 && (
            <div className="text-muted text-xs">no sells yet — position still open</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TradesPage() {
  const price = useSolPrice();
  const [showFlat, setShowFlat] = useState(false);
  const { data: trips, error } = useSWR<PaperPosition[]>("/paper/positions", fetcher, { refreshInterval: 15000 });
  const { data: log } = useSWR<Trade[]>("/trades?limit=500", fetcher, { refreshInterval: 15000 });
  const { rows: logRows, sort: logSort } = useSort<Trade>(log || [], "ts", "desc");

  if (error) return <ErrorBox error={error} />;
  if (!trips) return <Loading what="trades" />;

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Trades</h1>
      <p className="text-sm text-muted mb-4">
        Every round trip, with each token&apos;s buy linked by arrows to the sells that closed it —
        and why. Toggle the flat event log for the raw, sortable feed.
      </p>

      <Section title={`Round trips (${trips.length})`}>
        <div className="grid gap-3">
          {trips.map((t, i) => <RoundTrip key={i} t={t} price={price} />)}
          {trips.length === 0 && <div className="card text-muted text-sm">No trades yet — the daemon arms on each followed wallet&apos;s next buy.</div>}
        </div>
      </Section>

      <Section
        title="Flat event log"
        action={<button onClick={() => setShowFlat((v) => !v)} className="text-xs text-muted hover:text-white">{showFlat ? "hide" : "show"}</button>}
      >
        {showFlat && (
          <div className="card overflow-x-auto p-0">
            <table className="grid-table">
              <thead><tr>
                <Th sort={logSort} field="ts">Time</Th>
                <Th sort={logSort} field="event">Event</Th>
                <Th sort={logSort} field="mint">Token</Th>
                <Th sort={logSort} field="reason">Why</Th>
                <Th sort={logSort} field="sol">SOL</Th>
                <Th sort={logSort} field="pnl_sol">PnL</Th>
              </tr></thead>
              <tbody>
                {logRows.map((e) => (
                  <tr key={e.id}>
                    <td className="text-muted whitespace-nowrap">{ago(e.ts)}</td>
                    <td><span className={`badge ${e.event === "CLOSE" ? "bg-accent/15 text-accent" : e.event === "ENTRY" ? "bg-good/10 text-good" : "bg-panel2 text-gray-300"}`}>{e.event}</span></td>
                    <td className="mono">{short(e.mint, 5)}<DexIcon mint={e.mint} /></td>
                    <td><Reason r={e.reason} /></td>
                    <td>{e.sol != null ? `${e.sol} ◎` : "—"}</td>
                    <td className={e.pnl_sol == null ? "" : e.pnl_sol >= 0 ? "text-good" : "text-bad"}>{e.pnl_sol == null ? "—" : signed(e.pnl_sol)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
