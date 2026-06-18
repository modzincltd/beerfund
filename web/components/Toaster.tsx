"use client";
import { useEffect, useState } from "react";
import { subscribeToasts, ToastItem } from "@/lib/toast";

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(
    () =>
      subscribeToasts((t) => {
        setItems((xs) => [...xs, t]);
        setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== t.id)), 4500);
      }),
    [],
  );

  if (items.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-xs">
      {items.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`card text-sm shadow-lg ${
            t.kind === "error"
              ? "border-bad/50 text-bad"
              : t.kind === "success"
                ? "border-good/50 text-good"
                : "border-accent/40"
          }`}
        >
          {t.msg}
        </div>
      ))}
    </div>
  );
}
