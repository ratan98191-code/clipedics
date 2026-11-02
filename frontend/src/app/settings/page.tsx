// Clipedics – Settings page (plan status + social connections)
"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface BillingStatus {
  plan: string;
  subscription_status: string;
  clips_used_this_month: number;
  clips_limit: number;
  clips_remaining: number;
}

interface SocialConnection {
  platform: string;
  connected: boolean;
  connect_url: string;
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    const headers = { Authorization: `Bearer ${user.token}` };

    Promise.all([
      fetch(`${API}/api/billing/status`, { headers }).then((r) => r.json()),
      fetch(`${API}/api/social/connections`, { headers }).then((r) => r.json()),
    ]).then(([b, s]) => {
      setBilling(b);
      setConnections(s.connections ?? []);
      setLoading(false);
    });
  }, [user]);

  const handlePortal = async () => {
    if (!user) return;
    const res = await fetch(`${API}/api/billing/portal`, {
      method: "POST",
      headers: { Authorization: `Bearer ${user.token}` },
    });
    const { portal_url } = await res.json();
    window.open(portal_url, "_blank");
  };

  const handleConnect = (url: string) => {
    window.location.href = `${API}${url}`;
  };

  if (!user) return (
    <div className="text-center py-20">
      <p className="text-zinc-400">Please <Link href="/login" className="text-violet-400 underline">sign in</Link> to view settings.</p>
    </div>
  );

  const PLATFORM_ICONS: Record<string, string> = {
    youtube: "▶", tiktok: "♪", instagram: "📷",
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-black text-white">Settings</h1>

      {/* Account */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Account</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-white font-medium">{user.display_name || user.email}</p>
            <p className="text-zinc-500 text-sm">{user.email}</p>
          </div>
          <button
            onClick={logout}
            className="text-sm text-red-400 hover:text-red-300 transition px-3 py-1.5 rounded-lg hover:bg-red-900/20"
          >
            Sign out
          </button>
        </div>
      </section>

      {/* Plan & Usage */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Plan & Usage</h2>
        {loading ? (
          <div className="h-12 bg-zinc-800 rounded animate-pulse" />
        ) : billing ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-lg font-bold text-white capitalize">{billing.plan}</span>
                <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${billing.subscription_status === "active" ? "bg-green-500/20 text-green-300" : "bg-zinc-700 text-zinc-400"}`}>
                  {billing.subscription_status}
                </span>
              </div>
              {billing.plan === "free" ? (
                <Link href="/pricing" className="text-sm px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-medium transition">
                  Upgrade
                </Link>
              ) : (
                <button onClick={handlePortal} className="text-sm px-4 py-2 rounded-lg border border-zinc-700 hover:border-zinc-500 text-zinc-300 transition">
                  Manage
                </button>
              )}
            </div>

            {/* Usage bar */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>Clips this month</span>
                <span>{billing.clips_used_this_month} / {billing.clips_limit === -1 ? "∞" : billing.clips_limit}</span>
              </div>
              <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-500 rounded-full transition-all"
                  style={{
                    width: billing.clips_limit === -1
                      ? "10%"
                      : `${Math.min(100, (billing.clips_used_this_month / billing.clips_limit) * 100)}%`
                  }}
                />
              </div>
            </div>
          </div>
        ) : null}
      </section>

      {/* Social Connections */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Social Connections</h2>
        <p className="text-xs text-zinc-500">Connect your accounts to publish clips directly from Clipedics.</p>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => <div key={i} className="h-14 bg-zinc-800 rounded-xl animate-pulse" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {connections.map((c) => (
              <div key={c.platform} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-xl border border-zinc-700/50">
                <div className="flex items-center gap-3">
                  <span className="text-xl">{PLATFORM_ICONS[c.platform]}</span>
                  <div>
                    <p className="text-sm font-medium text-white capitalize">{c.platform}</p>
                    <p className="text-xs text-zinc-500">{c.connected ? "Connected" : "Not connected"}</p>
                  </div>
                </div>
                <button
                  onClick={() => handleConnect(c.connect_url)}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium transition
                    ${c.connected
                      ? "bg-green-500/20 text-green-300 border border-green-500/30 hover:bg-red-500/10 hover:text-red-400"
                      : "bg-violet-600 hover:bg-violet-500 text-white"}`}
                >
                  {c.connected ? "Connected ✓" : "Connect"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

