import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { Toaster } from "@/components/Toaster";

export const metadata: Metadata = {
  title: "Beer Fund Bot",
  description: "Live dashboard + AI analyst for the zero-capital Solana copy-trade research bot.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <Nav />
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
          <footer className="max-w-7xl mx-auto px-4 py-8 text-xs text-muted">
            Zero capital at risk — research/simulation only. Paper fills marked at live Jupiter quotes.
          </footer>
        </div>
        <Toaster />
      </body>
    </html>
  );
}
