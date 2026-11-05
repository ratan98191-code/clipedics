// Clipedics – Navbar (Personal Studio)
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function Navbar() {
  const pathname = usePathname();

  const isActive = (path: string) => pathname === path;

  return (
    <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg text-white hover:text-violet-300 transition">
          <span className="text-2xl">🎬</span>
          <span>Clipedics</span>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-400 border border-violet-500/30">
            Studio
          </span>
        </Link>
        <nav className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className={`text-sm px-3 py-1.5 rounded-lg transition ${
              isActive("/dashboard")
                ? "text-white bg-zinc-800 font-medium"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
          >
            Dashboard
          </Link>
          <Link
            href="/settings"
            className={`text-sm px-3 py-1.5 rounded-lg transition ${
              isActive("/settings")
                ? "text-white bg-zinc-800 font-medium"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
          >
            Settings
          </Link>
          <Link
            href="/upload"
            className="text-sm font-medium px-4 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition shadow-sm shadow-violet-900/30"
          >
            + New Project
          </Link>
        </nav>
      </div>
    </header>
  );
}

