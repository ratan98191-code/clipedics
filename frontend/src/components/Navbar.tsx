// Clipedics – Navbar (with auth)
"use client";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";

export function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg text-white hover:text-violet-300 transition">
          <span className="text-2xl">🎬</span>
          <span>Clipedics</span>
        </Link>
        <nav className="flex items-center gap-2">
          {user ? (
            <>
              <Link href="/dashboard" className="text-sm text-zinc-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition">
                Dashboard
              </Link>
              <Link href="/settings" className="text-sm text-zinc-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition">
                Settings
              </Link>
              <Link href="/upload" className="text-sm font-medium px-4 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition">
                New Project
              </Link>
            </>
          ) : (
            <>
              <Link href="/pricing" className="text-sm text-zinc-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition">
                Pricing
              </Link>
              <Link href="/login" className="text-sm text-zinc-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition">
                Sign In
              </Link>
              <Link href="/login" className="text-sm font-medium px-4 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition">
                Get Started Free
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

