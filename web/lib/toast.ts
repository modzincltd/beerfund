"use client";
// Minimal toast bus — no dependency. Call toast(msg) from anywhere; <Toaster/>
// (mounted once in the layout) subscribes and renders. Module-level pub/sub
// keeps it usable outside the React tree without prop drilling or context.

export type ToastKind = "info" | "success" | "error";
export interface ToastItem {
  id: number;
  msg: string;
  kind: ToastKind;
}

type Listener = (t: ToastItem) => void;

let nextId = 0;
const listeners = new Set<Listener>();

export function toast(msg: string, kind: ToastKind = "info"): void {
  const item: ToastItem = { id: ++nextId, msg, kind };
  listeners.forEach((l) => l(item));
}

export function subscribeToasts(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
