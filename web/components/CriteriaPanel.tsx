"use client";
import { Criteria } from "@/lib/api";
import { signed, usd } from "@/lib/format";
import { useSolPrice } from "@/lib/price";
import { WalletAddr } from "@/components/ui";

function Row({ ok, label, detail }: { ok: boolean; label: string; detail: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-edge/50 last:border-0">
      <span className={`mt-0.5 ${ok ? "text-good" : "text-muted"}`}>{ok ? "✓" : "○"}</span>
      <div>
        <div className="text-sm">{label}</div>
        <div className="text-xs text-muted">{detail}</div>
      </div>
    </div>
  );
}

export function CriteriaPanel({ c }: { c: Criteria }) {
  const price = useSolPrice();
  const realizedUsd = usd(c.net_positive.realized_sol, price);
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-1">
        <div className="label">Go-live criteria</div>
        <span className={`badge ${c.all_pass ? "bg-good/15 text-good" : "bg-warn/15 text-warn"}`}>
          {c.all_pass ? "ALL MET" : "NOT YET"}
        </span>
      </div>
      <Row
        ok={c.duration.pass}
        label="≥2 weeks live & ≥20 filled positions"
        detail={`${c.duration.weeks_live ?? 0} weeks live · ${c.duration.n_filled} filled`}
      />
      <Row
        ok={c.net_positive.pass}
        label="Net-positive realized PnL after costs"
        detail={`${signed(c.net_positive.realized_sol)}${realizedUsd ? ` (≈ ${realizedUsd})` : ""} realized`}
      />
      <Row
        ok={c.drawdown.pass}
        label="Max drawdown ≤ 6 position-sizes"
        detail={`${c.drawdown.max_drawdown_sizes ?? 0} position-sizes peak-to-trough`}
      />
      <Row
        ok={c.follow_pool.pass}
        label="≥2 follow-pool wallets passing audit"
        detail={
          c.follow_pool.n_passing ? (
            <span className="inline-flex flex-wrap gap-x-3 gap-y-1">
              {c.follow_pool.wallets.map((w) => (
                <WalletAddr key={w.wallet} wallet={w.wallet} len={4} />
              ))}
            </span>
          ) : (
            "no follow-pool wallet currently rated CANDIDATE"
          )
        }
      />
    </div>
  );
}
