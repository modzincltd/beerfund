"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Dashboard"],
  ["/paper", "Paper"],
  ["/trades", "Trades"],
  ["/wallets", "Wallets"],
  ["/coins", "Coins"],
  ["/discovery", "Discovery"],
  ["/chat", "AI Analyst"],
  ["/settings", "Settings"],
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="border-b border-edge bg-panel/60 backdrop-blur sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-1 h-14">
        <Link href="/" className="font-semibold mr-4 flex items-center gap-2">
          <span className="text-accent">🍺</span> Beer Fund Bot
        </Link>
        {LINKS.map(([href, label]) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 py-1.5 rounded-md text-sm ${
                active ? "bg-panel2 text-white" : "text-muted hover:text-white"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
