"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface DrawdownResp {
  max_drawdown_sol: number;
  max_drawdown_sizes: number | null;
  curve: { ts: string; cum_sol: number }[];
}

export function PnlCurve() {
  const { data } = useSWR<DrawdownResp>("/drawdown", fetcher, { refreshInterval: 15000 });
  const curve = (data?.curve || []).map((p) => ({
    t: new Date(p.ts).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    cum: p.cum_sol,
  }));

  return (
    <div className="card h-full">
      <div className="label">Realized PnL curve</div>
      {curve.length === 0 ? (
        <div className="text-muted text-sm py-12 text-center">
          No closed positions yet — the curve appears once the daemon banks its first round trip.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={curve} margin={{ top: 12, right: 8, bottom: 0, left: -16 }}>
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f5b301" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#f5b301" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" stroke="#8a94a6" fontSize={11} tickLine={false} />
            <YAxis stroke="#8a94a6" fontSize={11} tickLine={false} width={48} />
            <Tooltip
              contentStyle={{ background: "#1c2230", border: "1px solid #2a3242", borderRadius: 8 }}
              labelStyle={{ color: "#8a94a6" }}
              formatter={(v: number) => [`${v.toFixed(3)} ◎`, "cumulative"]}
            />
            <Area type="monotone" dataKey="cum" stroke="#f5b301" fill="url(#g)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
