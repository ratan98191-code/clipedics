// Clipedics – Pricing / Upgrade page
"use client";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PLANS = [
  {
    id: "free",
    name: "Free",
    price: 0,
    period: "forever",
    clips: "5 clips / month",
    features: ["720p output", "All 3 caption styles", "Download MP4", "Community support"],
    cta: "Current Plan",
    highlight: false,
  },
  {
    id: "pro",
    name: "Pro",
    price: 19,
    period: "per month",
    clips: "200 clips / month",
    features: ["1080p output", "Priority processing", "Batch ZIP export", "Social publish (YT/TikTok/IG)", "Email support"],
    cta: "Upgrade to Pro",
    highlight: true,
  },
  {
    id: "agency",
    name: "Agency",
    price: 79,
    period: "per month",
    clips: "Unlimited clips",
    features: ["4K output", "White-label export", "API access", "Dedicated processing lane", "Priority support"],
    cta: "Go Agency",
    highlight: false,
  },
];

export default function PricingPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleUpgrade = async (plan: string) => {
    if (!user) {
      window.location.href = "/login";
      return;
    }
    setLoading(plan);
    setError("");
    try {
      const res = await fetch(`${API}/api/billing/checkout/${plan}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Failed to start checkout");
      }
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setLoading(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-10 py-8">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-black text-white">Simple, transparent pricing</h1>
        <p className="text-zinc-400 text-lg">Start free. Upgrade when you need more.</p>
      </div>

      {error && (
        <div className="text-center text-red-400 bg-red-900/20 border border-red-800 rounded-xl p-4">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {PLANS.map((plan) => (
          <div
            key={plan.id}
            className={`relative flex flex-col p-6 rounded-2xl border transition
              ${plan.highlight
                ? "border-violet-500 bg-violet-500/5 shadow-xl shadow-violet-900/20"
                : "border-zinc-800 bg-zinc-900"}`}
          >
            {plan.highlight && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-violet-600 text-xs font-bold text-white">
                Most Popular
              </div>
            )}

            <div className="mb-6">
              <h2 className="text-lg font-bold text-white">{plan.name}</h2>
              <div className="mt-2 flex items-baseline gap-1">
                <span className="text-4xl font-black text-white">\${plan.price}</span>
                <span className="text-zinc-500 text-sm">/ {plan.period}</span>
              </div>
              <p className="mt-1 text-sm text-violet-400 font-medium">{plan.clips}</p>
            </div>

            <ul className="space-y-2 flex-1 mb-6">
              {plan.features.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-zinc-300">
                  <span className="text-green-400">✓</span>
                  {f}
                </li>
              ))}
            </ul>

            <button
              onClick={() => plan.id !== "free" && handleUpgrade(plan.id)}
              disabled={loading === plan.id || plan.id === "free"}
              className={`w-full py-3 rounded-xl font-semibold text-sm transition
                ${plan.id === "free"
                  ? "bg-zinc-800 text-zinc-500 cursor-default"
                  : plan.highlight
                    ? "bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white hover:opacity-90"
                    : "border border-zinc-700 text-white hover:border-zinc-500"}
                disabled:opacity-40`}
            >
              {loading === plan.id ? "Redirecting to Stripe…" : plan.cta}
            </button>
          </div>
        ))}
      </div>

      <p className="text-center text-xs text-zinc-600">
        Payments processed securely by Stripe. Cancel anytime from your settings.
      </p>
    </div>
  );
}

