"use client";
import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher, WalletAudit, WalletDetail } from "@/lib/api";
import { Loading, ErrorBox, Verdict, Section, DexIcon, WalletAddr } from "@/components/ui";
import { short, signed, pct, hold, ago, usd } from "@/lib/format";
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

function Detail({ wallet }: { wallet: string }) {
  const { data } = useSWR<WalletDetail>(`/wallets/${wallet}`, fetcher);
  if (!data) return <Loading what="audit" />;
  const { audit, positions } = data;
  return (
    <div>
      <div className="flex items-center gap-2">
        <Verdict code={audit.verdict_code} />
        {audit.decaying && <span className="badge bg-warn/15 text-warn">decaying</span>}
        <span className="text-xs text-muted">{audit.verdict_reason}</span>
      </div>
      <MetricRow a={audit} />
      {audit.old_avg != null && (
        <div className="text-xs text-muted mt-3">
          Decay check: older-half {signed(audit.old_avg)}/trade → newer-half {signed(audit.new_avg)}/trade
          {audit.concentration != null && ` · best trade = ${pct(audit.concentration)} of total PnL`}
        </div>
      )}
      <Section title={`Positions (${positions.length})`}>
        <div className="overflow-x-auto">
          <table className="grid-table">
            <thead><tr><th>Token</th><th>PnL</th><th>Return</th><th>Hold</th><th>Swaps</th><th>State</th></tr></thead>
            <tbody>
              {positions.slice(0, 30).map((p, i) => (
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
    <div className="mb-4">
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
            <button
              onClick={() => setTags(tags.filter((x) => x !== t))}
              className="ml-1 text-muted hover:text-bad"
              aria-label={`remove tag ${t}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag();
            }
          }}
          placeholder="add tag + Enter"
          className="bg-panel2 border border-edge rounded-md text-xs px-2 py-1 w-36"
        />
      </div>
      <button
        onClick={save}
        disabled={saving}
        className="rounded-md bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 text-sm font-medium px-3 py-1.5"
      >
        {saving ? "Saving…" : "Save label & tags"}
      </button>
    </div>
  );
}

export default function WalletsPage() {
  const { data, error } = useSWR<WalletAudit[]>("/wallets", fetcher, { refreshInterval: 30000 });
  const [sel, setSel] = useState<string | null>(null);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="wallet audits" />;
  if (data.length === 0)
    return (
      <div className="card text-muted text-sm">
        No wallets audited yet. Run <span className="mono text-gray-300">python3 audit_runner.py --follow</span> on
        the droplet (needs a Helius key) and they’ll appear here.
      </div>
    );

  const sorted = [...data].sort((a, b) => {
    const order = ["CANDIDATE", "DECAYING", "THIN", "TOOFAST", "LOSER", "INSIDER"];
    return order.indexOf(a.verdict_code) - order.indexOf(b.verdict_code);
  });

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Wallet analysis</h1>
      <p className="text-sm text-muted mb-4">
        Wallet selection is the product. Verdicts are computed from chain data — the auditor re-derives
        leaderboard claims and surfaces what they hide (decay, transfer-fed PnL, uncopyable launch entries).
      </p>
      <div className="grid md:grid-cols-2 gap-3">
        {sorted.map((a) => (
          <div
            key={a.wallet}
            role="button"
            tabIndex={0}
            onClick={() => setSel(sel === a.wallet ? null : a.wallet)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSel(sel === a.wallet ? null : a.wallet);
              }
            }}
            className={`card text-left transition cursor-pointer ${sel === a.wallet ? "border-accent/60" : "hover:border-edge"}`}
          >
            <div className="flex items-center justify-between gap-2">
              <WalletAddr wallet={a.wallet} len={6} />
              <div className="flex items-center gap-2 shrink-0">
                {a.in_follow_pool && <span className="badge bg-accent/15 text-accent">following</span>}
                <Verdict code={a.verdict_code} />
              </div>
            </div>
            <MetricRow a={a} />
            <div className="text-xs text-muted mt-2">audited {ago(a.ts)}</div>
            {sel === a.wallet && (
              <div
                className="mt-4 pt-4 border-t border-edge"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <LabelEditor wallet={a.wallet} />
                <Detail wallet={a.wallet} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
