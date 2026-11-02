// Clipedics – Login / Register page
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handle = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Auth failed");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="w-full max-w-md space-y-6">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="text-5xl">🎬</div>
          <h1 className="text-2xl font-black text-white">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="text-zinc-500 text-sm">
            {mode === "login" ? "Sign in to your Clipedics account" : "Start generating viral clips for free"}
          </p>
        </div>

        {/* Form */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
          <form onSubmit={handle} className="space-y-4">
            {mode === "register" && (
              <div className="space-y-1">
                <label className="text-xs text-zinc-400">Display Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Alex Smith"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-violet-500"
                />
              </div>
            )}
            <div className="space-y-1">
              <label className="text-xs text-zinc-400">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-zinc-400">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-violet-500"
              />
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-semibold hover:opacity-90 disabled:opacity-40 transition"
            >
              {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>

          <div className="pt-2 text-center text-sm text-zinc-500">
            {mode === "login" ? (
              <>Don&apos;t have an account?{" "}
                <button onClick={() => setMode("register")} className="text-violet-400 hover:underline">Sign up free</button>
              </>
            ) : (
              <>Already have an account?{" "}
                <button onClick={() => setMode("login")} className="text-violet-400 hover:underline">Sign in</button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

