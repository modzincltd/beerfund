"use client";
import useSWR from "swr";

// Live SOL/USD price for showing realized PnL in dollars. Fetched client-side
// from CoinGecko (CORS-enabled, no key) so it works on Vercel without touching
// the API. Degrades gracefully: on any failure we return null and the UI shows
// SOL only. One shared SWR key means a single request across all components.
async function fetchSolPrice(): Promise<number | null> {
  try {
    const r = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
      { cache: "no-store" },
    );
    if (!r.ok) return null;
    const j = await r.json();
    const p = j?.solana?.usd;
    return typeof p === "number" ? p : null;
  } catch {
    return null;
  }
}

export function useSolPrice(): number | null {
  const { data } = useSWR<number | null>("sol-usd-price", fetchSolPrice, {
    refreshInterval: 60_000,
    revalidateOnFocus: false,
    dedupingInterval: 60_000,
    shouldRetryOnError: false,
  });
  return data ?? null;
}
