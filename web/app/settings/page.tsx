"use client";
import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher, api, Settings } from "@/lib/api";
import { Loading, ErrorBox, Section } from "@/components/ui";
import { toast } from "@/lib/toast";

function Field({
  label, help, value, onChange, step = 1, min = 0,
}: {
  label: string; help: string; value: number;
  onChange: (v: number) => void; step?: number; min?: number;
}) {
  return (
    <label className="block py-2">
      <div className="text-sm text-gray-200">{label}</div>
      <div className="text-xs text-muted mb-1">{help}</div>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        onChange={(e) => onChange(e.target.value === "" ? 0 : parseFloat(e.target.value))}
        className="w-44 bg-panel2 border border-edge rounded-md text-sm px-2 py-1.5 tabular-nums"
      />
    </label>
  );
}

export default function SettingsPage() {
  const { data, error } = useSWR<Settings>("/settings", fetcher);
  const [cfg, setCfg] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data && !cfg) setCfg(JSON.parse(JSON.stringify(data)));
  }, [data, cfg]);

  if (error) return <ErrorBox error={error} />;
  if (!cfg) return <Loading what="settings" />;

  const a = cfg.audit, g = cfg.golive;
  const setA = (k: keyof Settings["audit"], v: number) => setCfg({ ...cfg, audit: { ...cfg.audit, [k]: v } });
  const setG = (k: keyof Settings["golive"], v: number) => setCfg({ ...cfg, golive: { ...cfg.golive, [k]: v } });

  async function save() {
    setSaving(true);
    try {
      const saved = await api<Settings>("/settings", { method: "POST", body: JSON.stringify(cfg) });
      setCfg(saved);
      mutate("/settings", saved, false);
      toast("Settings saved — applies on the next audit sweep", "success");
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="text-lg font-semibold mb-1">Settings — wallet criteria</h1>
      <p className="text-sm text-muted mb-4">
        These thresholds decide how the auditor judges wallets (which become CANDIDATE,
        THIN, TOOFAST, INSIDER, DECAYING) and the go-live gates on the dashboard. Changes
        apply on the next audit sweep — re-audit from the Discovery page to apply now.
      </p>

      <Section title="Finding & promoting wallets (audit verdict)">
        <div className="card grid sm:grid-cols-2 gap-x-8">
          <Field label="Min closed trades to judge" min={1}
            help="Fewer closed round-trips than this → THIN (not enough to judge)."
            value={a.min_closed} onChange={(v) => setA("min_closed", v)} />
          <Field label="Min median hold (seconds)" min={0} step={30}
            help="Median hold below this → TOOFAST (dies in our copy lag). 600 = 10 min."
            value={a.min_median_hold_s} onChange={(v) => setA("min_median_hold_s", v)} />
          <Field label="Insider return multiple (×)" min={1} step={1}
            help="Any single trade returning more than this × → INSIDER (launch-price entry)."
            value={a.insider_return_x} onChange={(v) => setA("insider_return_x", v)} />
          <Field label="Decay ratio" min={0} step={0.05}
            help="Newer-half avg PnL below this × the older half → DECAYING. 0.5 = halved."
            value={a.decay_ratio} onChange={(v) => setA("decay_ratio", v)} />
        </div>
      </Section>

      <Section title="Go-live gates">
        <div className="card grid sm:grid-cols-2 gap-x-8">
          <Field label="Min filled positions" min={1}
            help="Paper fills required before going live."
            value={g.min_filled} onChange={(v) => setG("min_filled", v)} />
          <Field label="Min weeks live" min={0} step={0.5}
            help="How long the paper run must have been active."
            value={g.min_weeks} onChange={(v) => setG("min_weeks", v)} />
          <Field label="Max drawdown (position-sizes)" min={0} step={0.5}
            help="Peak-to-trough realized drawdown ceiling."
            value={g.max_drawdown_sizes} onChange={(v) => setG("max_drawdown_sizes", v)} />
          <Field label="Min passing wallets" min={0}
            help="CANDIDATE-rated follow-pool wallets required."
            value={g.min_passing_wallets} onChange={(v) => setG("min_passing_wallets", v)} />
        </div>
      </Section>

      <div className="mt-4 flex items-center gap-3">
        <button onClick={save} disabled={saving}
          className="rounded-md bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-50 text-sm font-medium px-4 py-2">
          {saving ? "Saving…" : "Save settings"}
        </button>
        <button onClick={() => setCfg(data ? JSON.parse(JSON.stringify(data)) : null)}
          className="text-xs text-muted hover:text-white">reset</button>
      </div>
    </div>
  );
}
