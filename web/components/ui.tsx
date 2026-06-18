"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { VERDICT_STYLE, short } from "@/lib/format";
import { toast } from "@/lib/toast";
import { useLabels } from "@/lib/labels";

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "bad" | "warn";
}) {
  const color =
    tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "";
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`stat mt-1 ${color}`}>{value}</div>
      {sub != null && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

export function Verdict({ code }: { code: string }) {
  return <span className={`badge ${VERDICT_STYLE[code] || "bg-muted/15 text-muted"}`}>{code}</span>;
}

export function Flag({ children }: { children: React.ReactNode }) {
  return <span className="badge bg-bad/15 text-bad border border-bad/30 mr-1">{children}</span>;
}

// Exit / entry reason badge (copy, tp1..tp4, trail, stop, max_hold, dead).
const REASON_STYLE: Record<string, string> = {
  tp1: "bg-good/15 text-good", tp2: "bg-good/15 text-good", tp3: "bg-good/15 text-good",
  tp4: "bg-good/15 text-good", trail: "bg-good/15 text-good",
  stop: "bg-bad/15 text-bad", dead: "bg-bad/15 text-bad",
  max_hold: "bg-warn/15 text-warn", copy: "bg-panel2 text-gray-300",
};
export function Reason({ r }: { r: string | null }) {
  return <span className={`badge ${REASON_STYLE[r || ""] || "bg-muted/15 text-muted"}`}>{r || "—"}</span>;
}

// Small chart icon that opens a token on DexScreener. stopPropagation keeps it
// from triggering row/card click handlers it may sit inside.
export function DexIcon({ mint }: { mint: string }) {
  return (
    <a
      href={`https://dexscreener.com/solana/${mint}`}
      target="_blank"
      rel="noopener noreferrer"
      title="View on DexScreener"
      aria-label="View on DexScreener"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex align-middle ml-1 text-muted hover:text-accent"
    >
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M3 3v18h18" />
        <path d="M7 14l4-4 3 3 5-6" />
      </svg>
    </a>
  );
}

// Copy-to-clipboard button with a brief check + toast. stopPropagation so it
// works inside clickable rows/cards.
export function CopyButton({ text, what = "address" }: { text: string; what?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      title={`Copy ${what}`}
      aria-label={`Copy ${what}`}
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          toast(`Copied ${what}`, "success");
          setTimeout(() => setDone(false), 1200);
        } catch {
          toast("Copy failed — clipboard unavailable", "error");
        }
      }}
      className="inline-flex align-middle text-muted hover:text-accent"
    >
      {done ? (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

export function Tag({ children }: { children: React.ReactNode }) {
  return <span className="badge bg-panel2 text-gray-300 border border-edge">{children}</span>;
}

// Wallet address with its user label (if set), a copy button, and tag chips.
// Pulls labels from the shared /labels fetch, so annotations show everywhere a
// wallet appears without each call site wiring them up.
export function WalletAddr({
  wallet,
  len = 6,
  showLabel = true,
  link = true,
}: {
  wallet: string;
  len?: number;
  showLabel?: boolean;
  link?: boolean;
}) {
  const labels = useLabels();
  const info = labels?.[wallet];
  const body = (
    <>
      {showLabel && info?.label && <span className="font-medium text-gray-200">{info.label}</span>}
      <span className="mono text-muted">{short(wallet, len)}</span>
    </>
  );
  return (
    <span className="inline-flex items-center gap-1.5 flex-wrap">
      {link ? (
        <Link
          href={`/wallets?w=${wallet}`}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1.5 hover:text-accent"
          title="Open wallet detail"
        >
          {body}
        </Link>
      ) : (
        <span className="inline-flex items-center gap-1.5">{body}</span>
      )}
      <CopyButton text={wallet} />
      {showLabel && (info?.tags || []).map((t) => <Tag key={t}>{t}</Tag>)}
    </span>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="text-muted text-sm py-8 animate-pulse">Loading {what}…</div>;
}

export function ErrorBox({ error }: { error: Error }) {
  return (
    <div className="card border-bad/40 text-bad text-sm">
      Couldn’t reach the API: {error.message}
      <div className="text-muted mt-1">
        Is the FastAPI server up and <span className="mono">NEXT_PUBLIC_API_BASE</span> pointed at it?
      </div>
    </div>
  );
}

// ---- sortable tables -------------------------------------------------------
// useSort(rows, key?, dir?) returns the sorted rows + a `sort` handle; render
// headers with <Th sort={sort} field="col">Label</Th> and map over the returned
// rows. Nulls sort last; numbers numeric; arrays by length; else locale string.
export type SortDir = "asc" | "desc";
export interface Sort {
  key: string | null;
  dir: SortDir;
  toggle: (k: string) => void;
}

export function useSort<T>(
  rows: T[],
  initialKey: string | null = null,
  initialDir: SortDir = "asc",
): { rows: T[]; sort: Sort } {
  const [key, setKey] = useState<string | null>(initialKey);
  const [dir, setDir] = useState<SortDir>(initialDir);
  const sorted = useMemo(() => {
    if (!key) return rows;
    const out = [...rows];
    out.sort((a, b) => {
      let x = (a as Record<string, unknown>)?.[key];
      let y = (b as Record<string, unknown>)?.[key];
      if (Array.isArray(x)) x = x.length;
      if (Array.isArray(y)) y = y.length;
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c =
        typeof x === "number" && typeof y === "number"
          ? x - y
          : String(x).localeCompare(String(y), undefined, { numeric: true });
      return dir === "asc" ? c : -c;
    });
    return out;
  }, [rows, key, dir]);
  const toggle = (k: string) =>
    key === k ? setDir((d) => (d === "asc" ? "desc" : "asc")) : (setKey(k), setDir("asc"));
  return { rows: sorted, sort: { key, dir, toggle } };
}

export function Th({
  sort, field, children, className = "",
}: {
  sort: Sort; field: string; children: React.ReactNode; className?: string;
}) {
  const active = sort.key === field;
  return (
    <th
      onClick={() => sort.toggle(field)}
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={`cursor-pointer select-none hover:text-gray-200 ${className}`}
    >
      {children}
      <span className="ml-1 text-[10px] text-accent">{active ? (sort.dir === "asc" ? "▲" : "▼") : ""}</span>
    </th>
  );
}

export function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-gray-300">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
