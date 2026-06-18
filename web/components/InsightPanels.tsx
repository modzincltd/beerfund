"use client";
import { useState } from "react";
import useSWR from "swr";
import { api, fetcher, Insight } from "@/lib/api";
import { ago } from "@/lib/format";

const KINDS: [string, string][] = [
  ["summary", "Status read"],
  ["wallet_health", "Wallet health"],
  ["coin_risk", "Coin risk"],
  ["decay_alert", "Decay alert"],
];

export function InsightPanels() {
  const { data, mutate } = useSWR<Insight[]>("/insights", fetcher);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const byKind = Object.fromEntries((data || []).map((i) => [i.kind, i]));

  async function gen(kind: string) {
    setBusy(kind);
    setErr(null);
    try {
      await api("/insights/generate", { method: "POST", body: JSON.stringify({ kind }) });
      await mutate();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid md:grid-cols-2 gap-3">
      {KINDS.map(([kind, title]) => {
        const ins = byKind[kind];
        return (
          <div key={kind} className="card">
            <div className="flex items-center justify-between mb-2">
              <div className="label flex items-center gap-2">
                <span className="text-accent">✦</span> {title}
              </div>
              <button
                onClick={() => gen(kind)}
                disabled={busy === kind}
                className="text-xs text-muted hover:text-white disabled:opacity-50"
              >
                {busy === kind ? "thinking…" : ins ? "refresh" : "generate"}
              </button>
            </div>
            {ins ? (
              <>
                <p className="text-sm text-gray-300 whitespace-pre-wrap">{ins.body}</p>
                <div className="text-[10px] text-muted mt-2">
                  {ins.model} · {ago(ins.created_at)}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted">
                No insight yet. Hit <span className="text-gray-300">generate</span> — the analyst reads
                the live data and writes a short take.
              </p>
            )}
          </div>
        );
      })}
      {err && <div className="text-bad text-xs md:col-span-2">AI error: {err} (set ANTHROPIC_API_KEY on the API)</div>}
    </div>
  );
}
