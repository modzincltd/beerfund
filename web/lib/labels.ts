"use client";
import useSWR from "swr";
import { api, fetcher } from "./api";

export interface WalletLabel {
  wallet: string;
  label: string | null;
  tags: string[];
}

// One shared fetch of all wallet labels, keyed so every WalletAddr reuses it.
// Returns a wallet -> label map (undefined while loading).
export function useLabels(): Record<string, WalletLabel> | undefined {
  const { data } = useSWR<WalletLabel[]>("/labels", fetcher, { refreshInterval: 30000 });
  if (!data) return undefined;
  return Object.fromEntries(data.map((l) => [l.wallet, l]));
}

export async function saveLabel(wallet: string, label: string, tags: string[]) {
  return api<WalletLabel>("/labels", {
    method: "POST",
    body: JSON.stringify({ wallet, label, tags }),
  });
}
