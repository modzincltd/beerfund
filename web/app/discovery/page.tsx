"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetcher, api, DiscoveryRow } from "@/lib/api";
import { Loading, ErrorBox, Verdict, WalletAddr } from "@/components/ui";
import { signed, pct, ago, usd } from "@/lib/format";
import { useSolPrice } from "@/lib/price";
import { toast } from "@/lib/toast";

const STATUS_STYLE: Record<string, string> = {
  promoted: "bg-good/15 text-good",
  audited: "bg-muted/15 text-muted",
  new: "bg-accent/15 text-accent",
  rejected: "bg-bad/15 text-bad",
};

const BTN =
  "rounded-md bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 " +
  "disabled:cursor-not-allowed text-sm font-medium px-3 py-1.5 transition";

interface RunResp { started: boolean; running?: boolean; message: string }
interface StatusResp { running: boolean; last: string | null; added: number }

export default function DiscoveryPage() {
  const price = useSolPrice();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [window_, setWindow] = useState("7d");
  const [manual, setManual] = useState("");
  const [showManual, setShowManual] = useState(false);

  const { data, error, mutate } = useSWR<DiscoveryRow[]>("/discovery", fetcher, {
    refreshInterval: busy ? 4000 : 30000,
  });

  // Poll run status only while a run is active; stop + refresh when it finishes.
  useSWR<StatusResp>(busy ? "/discovery/status" : null, fetcher, {
    refreshInterval: 3000,
    onSuccess: (s) => {
      if (s && !s.running) {
        setBusy(false);
        setMsg(s.last);
        toast(s.last || "Discovery finished", "success");
        mutate();
      }
    },
  });

  async function run(useGmgn: boolean) {
    const wallets = manual.split(/\s+/).map((s) => s.trim()).filter(Boolean);
    if (!useGmgn && wallets.length === 0) {
      setMsg("Paste at least one wallet address first.");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<RunResp>("/discovery/run", {
        method: "POST",
        body: JSON.stringify({ gmgn: useGmgn ? window_ : null, wallets }),
      });
      setMsg(r.message);
      toast(r.message, r.started ? "info" : "error");
      if (!r.started) setBusy(false);
      mutate();
    } catch (e) {
      setBusy(false);
      const m = `Failed: ${(e as Error).message}`;
      setMsg(m);
      toast(m, "error");
    }
  }

  if (error) return <ErrorBox error={error} />;

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Wallet discovery</h1>
      <p className="text-sm text-muted mb-4">
        Candidate wallets flow in from GMGN leaderboards / manual adds, get auto-audited, and only a
        CANDIDATE verdict promotes one toward the follow pool. Discovery never makes us follow a wallet —
        the auditor decides.
      </p>

      <div className="card mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-gray-300 mr-1">Find new wallets</span>
          <select
            value={window_}
            onChange={(e) => setWindow(e.target.value)}
            disabled={busy}
            className="bg-panel2 border border-edge rounded-md text-sm px-2 py-1.5"
          >
            <option value="1d">GMGN 1d</option>
            <option value="7d">GMGN 7d</option>
            <option value="30d">GMGN 30d</option>
          </select>
          <button className={BTN} disabled={busy} onClick={() => run(true)}>
            {busy ? "Discovering…" : "Auto-discover"}
          </button>
          <button
            className="text-xs text-muted hover:text-white"
            onClick={() => setShowManual((v) => !v)}
          >
            {showManual ? "hide manual add" : "paste addresses"}
          </button>
        </div>

        {showManual && (
          <div className="mt-3">
            <textarea
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              rows={3}
              placeholder="One Solana wallet address per line (e.g. from the GMGN leaderboard in your browser)"
              className="w-full bg-panel2 border border-edge rounded-md text-sm p-2 mono"
            />
            <button className={`${BTN} mt-2`} disabled={busy} onClick={() => run(false)}>
              Add &amp; audit pasted
            </button>
          </div>
        )}

        {msg && <div className="text-xs text-muted mt-3">{msg}</div>}
        <div className="text-xs text-muted mt-2">
          GMGN is Cloudflare-protected and often blocks servers — if auto-discover returns 0 added,
          paste addresses from the leaderboard instead.
        </div>
      </div>

      {!data ? (
        <Loading what="discovery pipeline" />
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="grid-table">
            <thead>
              <tr><th>Wallet</th><th>Source</th><th>Status</th><th>Verdict</th><th>Win</th><th>Realized</th><th>Found</th></tr>
            </thead>
            <tbody>
              {data.map((d) => {
                const u = usd(d.total_realized_sol, price);
                return (
                  <tr key={d.wallet}>
                    <td><WalletAddr wallet={d.wallet} len={6} /></td>
                    <td className="text-muted">{d.source}</td>
                    <td><span className={`badge ${STATUS_STYLE[d.status] || "bg-muted/15 text-muted"}`}>{d.status}</span></td>
                    <td>{d.last_verdict ? <Verdict code={d.last_verdict} /> : <span className="text-muted">—</span>}</td>
                    <td>{d.win_rate != null ? pct(d.win_rate) : "—"}</td>
                    <td>
                      {d.total_realized_sol != null ? signed(d.total_realized_sol) : "—"}
                      {u && <span className="text-muted"> · {u}</span>}
                    </td>
                    <td className="text-muted">{ago(d.discovered_at)}</td>
                  </tr>
                );
              })}
              {data.length === 0 && (
                <tr><td colSpan={7} className="text-muted text-center py-6">No candidates yet — use “Auto-discover” above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
