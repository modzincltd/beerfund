"use client";
import { useRef, useState } from "react";
import { api, ChatResponse } from "@/lib/api";

interface Msg {
  role: "user" | "assistant";
  content: string;
  trace?: { tool: string; input: unknown }[];
}

const SUGGESTIONS = [
  "Are we on track for the go-live criteria?",
  "Which followed wallet looks like it's decaying?",
  "Show our open positions and flag anything risky.",
  "Which coins have the most uncopyable-edge flags?",
];

export default function ChatPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setErr(null);
    const next: Msg[] = [...msgs, { role: "user", content: text }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    try {
      const resp = await api<ChatResponse>("/chat", {
        method: "POST",
        body: JSON.stringify({ messages: next.map((m) => ({ role: m.role, content: m.content })) }),
      });
      setMsgs((m) => [...m, { role: "assistant", content: resp.reply, trace: resp.trace }]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-lg font-semibold mb-1">AI analyst</h1>
      <p className="text-sm text-muted mb-4">
        Ask in plain English. The analyst has read-only tools over the live data (summary, criteria,
        wallet audits, coins, trades) and grounds every answer in the actual numbers.
      </p>

      {msgs.length === 0 && (
        <div className="grid sm:grid-cols-2 gap-2 mb-4">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} className="card text-left text-sm hover:border-accent/50">
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-3">
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div className={`rounded-xl px-4 py-3 max-w-[85%] text-sm whitespace-pre-wrap ${
              m.role === "user" ? "bg-accent/15 border border-accent/30" : "card"
            }`}>
              {m.content}
              {m.trace && m.trace.length > 0 && (
                <div className="text-[10px] text-muted mt-2 border-t border-edge pt-1">
                  read: {m.trace.map((t) => t.tool).join(", ")}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="card text-muted text-sm animate-pulse w-fit">reading the data…</div>}
        {err && <div className="text-bad text-sm">Error: {err} (is the API up + ANTHROPIC_API_KEY set?)</div>}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="sticky bottom-4 mt-4 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about wallets, coins, PnL, criteria…"
          className="flex-1 bg-panel border border-edge rounded-xl px-4 py-3 text-sm focus:border-accent/60 outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-accent text-ink font-medium rounded-xl px-5 disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
