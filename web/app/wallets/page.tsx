"use client";
import { Suspense, useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { fetcher, WalletAudit, WalletDetail, Balances } from "@/lib/api";
import {
  Loading, ErrorBox, Verdict, Section, DexIcon, WalletAddr, CopyButton, Tag,
} from "@/components/ui";
import { short, signed, pct, hold, ago, usd, num } from "@/lib/format";
import { useSolPrice } from "@/lib/price";
import { useLabels, saveLabel } from "@/lib/labels";
import { toast } from "@/lib/toast";

function MetricRow({ a }: { a: WalletAudit }) {
  const price = useSolPrice();
  const u = usd(a.total_realized_sol, price);
  return (
    <div className="grid grid-cols-4 gap-2 text-sm mt-3">
      <div><div className="label">Win rate</div>{pct(a.win_rate)}</div>
      <div><div className="label">Realized</div>{signed(a.total_realized_sol)}{u && <span className="text-muted"> · {u}</span>}</div>
      <div><div className="label">Closed</div>{a.n_closed}</div>
      <div><div className="label">Med. hold</div>{hold(a.median_hold_s)}</div>
    </div>
  );
}

function LabelEditor({ wallet }: { wallet: string }) {
  const labels = useLabels();
  const cur = labels?.[wallet];
  const [label, setLabel] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (labels && !loaded) {
      setLabel(cur?.label || "");
      setTags(cur?.tags || []);
      setLoaded(true);
    }
  }, [labels, cur, loaded]);

  function addTag() {
    const t = tagInput.trim();
    if (t && !tags.some((x) => x.toLowerCase() === t.toLowerCase())) setTags([...tags, t]);
    setTagInput("");
  }
  async function save() {
    setSaving(true);
    try {
      await saveLabel(wallet, label.trim(), tags);
      await mutate("/labels");
      toast("Label saved", "success");
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card mt-3">
      <div className="label mb-1">Label &amp; tags</div>
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="e.g. Telegram alpha, Whale #1"
        className="w-full bg-panel2 border border-edge rounded-md text-sm px-2 py-1.5 mb-2"
      />
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {tags.map((t) => (
          <span key={t} className="badge bg-panel2 text-gray-300 border border-edge">
            {t}
            <button onClick={() => setTags(tags.filter((x) => x !== t))} className="ml-1 text-muted hover:text-bad" aria-label={`remove ${t}`}>×</button>
          </span>
        ))}
        <input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
          placeholder="add tag + Enter"
          className="bg-panel2 border border-edge rounded-md text-xs px-2 py-1 w-36"
        />
      </div>
      <button onClick={save} disabled={saving} className="rounded-md bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 text-sm font-medium px-3 py-1.5">
        {saving ? "Saving…" : "Save label & tags"}
      </button>
    </div>
  );
}

function activeRange(active: WalletDetail["active"]): string {
  if (!active?.first || !active?.last) return "—";
  const d = (new Date(active.last).getTime() - new Date(active.first).getTime()) / 86400000;
  const span = d >= 1 ? `${d.toFixed(0)}d` : "<1d";
  const fmt = (s: string) => new Date(s).toLocaleDateString();
  return `${span} · ${fmt(active.first)} → ${fmt(active.last)}`;
}

function BalancesCard({ wallet }: { wallet: string }) {
  const { data, error } = useSWR<Balances>(`/wallets/${wallet}/balances`, fetcher, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  return (
    <Section title="Current holdings (live)">
      <div className="card">
        {error ? (
          <div className="text-muted text-sm">balances unavailable ({error.message})</div>
        ) : !data ? (
          <Loading what="balances" />
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <span className="stat">{data.sol.toFixed(3)} ◎</span>
              <span className="text-muted text-sm">SOL · {data.n_tokens} token{data.n_tokens === 1 ? "" : "s"}</span>
            </div>
            {data.tokens.length > 0 ? (
              <div className="mt-3 grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
                {data.tokens.slice(0, 12).map((t) => (
                  <div key={t.mint} className="flex justify-between border-b border-edge/40 py-1">
                    <span className="mono text-muted">{short(t.mint, 5)}<DexIcon mint={t.mint} /></span>
                    <span className="tabular-nums">{num(Math.round(t.amount))}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted text-sm mt-2">No token holdings — wallet is flat right now.</div>
            )}
          </>
        )}
      </div>
    </Section>
  );
}

function WalletDetailView({ wallet }: { wallet: string }) {
  const { data, error } = useSWR<WalletDetail>(`/wallets/${wallet}`, fetcher, { refreshInterval: 30000 });
  const price = useSolPrice();

  return (
    <div>
      <Link href="/wallets" className="text-xs text-muted hover:text-white">← all wallets</Link>
      <div className="card mt-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <WalletAddr wallet={wallet} len={10} link={false} />
          {data && (
            <div className="flex items-center gap-2">
              {data.audit.in_follow_pool && <span className="badge bg-accent/15 text-accent">following</span>}
              {data.audit.decaying && <span className="badge bg-warn/15 text-warn">decaying</span>}
              <Verdict code={data.audit.verdict_code} />
            </div>
          )}
        </div>
        {error ? (
          <div className="text-muted text-sm mt-3">No audit for this wallet yet. Audit it from the Discovery page.</div>
        ) : !data ? (
          <Loading what="wallet" />
        ) : (
          <>
            <div className="text-xs text-muted mt-1">{data.audit.verdict_reason}</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm mt-4">
              <div><div className="label">Win rate</div>{pct(data.audit.win_rate)}</div>
              <div><div className="label">Realized</div>{signed(data.audit.total_realized_sol)}{usd(data.audit.total_realized_sol, price) && <span className="text-muted"> · {usd(data.audit.total_realized_sol, price)}</span>}</div>
              <div><div className="label">Closed / open</div>{data.audit.n_closed} / {data.audit.n_open}</div>
              <div><div className="label">Median hold</div>{hold(data.audit.median_hold_s)}</div>
              <div><div className="label">Best trade</div>{signed(data.audit.best_trade_sol)}</div>
              <div><div className="label">Concentration</div>{data.audit.concentration != null ? pct(data.audit.concentration) : "—"}</div>
              <div><div className="label">Swaps</div>{num(data.audit.n_swaps)}</div>
              <div><div className="label">Active</div><span className="text-xs">{activeRange(data.active)}</span></div>
            </div>
            {data.audit.old_avg != null && (
              <div className="text-xs text-muted mt-3">
                Decay: older-half {signed(data.audit.old_avg)}/trade → newer-half {signed(data.audit.new_avg)}/trade
              </div>
            )}
          </>
        )}
      </div>

      <LabelEditor wallet={wallet} />
      <BalancesCard wallet={wallet} />

      {data && (
        <>
          <Section title={`Audited positions (${data.positions.length})`}>
            <div className="card overflow-x-auto p-0">
              <table className="grid-table">
                <thead><tr><th>Token</th><th>PnL</th><th>Return</th><th>Hold</th><th>Swaps</th><th>State</th></tr></thead>
                <tbody>
                  {data.positions.slice(0, 50).map((p, i) => (
                    <tr key={i}>
                      <td className="mono">{short(p.mint, 5)}<DexIcon mint={p.mint} /></td>
                      <td className={p.realized_pnl_sol >= 0 ? "text-good" : "text-bad"}>{signed(p.realized_pnl_sol)}</td>
                      <td>{pct(p.realized_return)}</td>
                      <td>{hold(p.hold_seconds)}</td>
                      <td>{p.n_swaps}</td>
                      <td className="text-xs">
                        {p.transfer_fed && <span className="badge bg-bad/15 text-bad mr-1">transfer-fed</span>}
                        {p.closed ? "closed" : "open"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {data.history.length > 1 && (
            <Section title="Verdict history">
              <div className="card overflow-x-auto p-0">
                <table className="grid-table">
                  <thead><tr><th>When</th><th>Verdict</th><th>Win</th><th>Realized</th><th>Decay</th></tr></thead>
                  <tbody>
                    {data.history.map((h, i) => (
                      <tr key={i}>
                        <td className="text-muted">{ago(h.ts)}</td>
                        <td><Verdict code={h.verdict_code} /></td>
                        <td>{pct(h.win_rate)}</td>
                        <td className={h.total_realized_sol >= 0 ? "text-good" : "text-bad"}>{signed(h.total_realized_sol)}</td>
                        <td className="text-xs">{h.decaying ? "decaying" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}
        </>
      )}
    </div>
  );
}

function WalletsList() {
  const { data, error } = useSWR<WalletAudit[]>("/wallets", fetcher, { refreshInterval: 30000 });
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="wallet audits" />;
  if (data.length === 0)
    return (
      <div className="card text-muted text-sm">
        No wallets audited yet. Use the <Link href="/discovery" className="text-accent">Discovery</Link> page to add and audit some.
      </div>
    );

  const order = ["CANDIDATE", "DECAYING", "THIN", "TOOFAST", "LOSER", "INSIDER"];
  const sorted = [...data].sort((a, b) => order.indexOf(a.verdict_code) - order.indexOf(b.verdict_code));

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Wallet analysis</h1>
      <p className="text-sm text-muted mb-4">
        Wallet selection is the product. Click any wallet to see its full record, holdings, and verdict history.
      </p>
      <div className="grid md:grid-cols-2 gap-3">
        {sorted.map((a) => (
          <div key={a.wallet} className="card">
            <div className="flex items-center justify-between gap-2">
              <WalletAddr wallet={a.wallet} len={6} />
              <div className="flex items-center gap-2 shrink-0">
                {a.in_follow_pool && <span className="badge bg-accent/15 text-accent">following</span>}
                <Verdict code={a.verdict_code} />
              </div>
            </div>
            <MetricRow a={a} />
            <div className="text-xs text-muted mt-2">audited {ago(a.ts)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WalletsInner() {
  const w = useSearchParams().get("w");
  return w ? <WalletDetailView wallet={w} /> : <WalletsList />;
}

export default function WalletsPage() {
  return (
    <Suspense fallback={<Loading what="wallets" />}>
      <WalletsInner />
    </Suspense>
  );
}
