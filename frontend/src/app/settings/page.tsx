// Clipedics – Settings page (Personal Studio Edition)
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SystemStatus {
  status: string;
  mode: string;
  groq_configured: boolean;
  default_whisper_model: string;
  output_dir: string;
}

export default function SettingsPage() {
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/system/status`)
      .then((r) => {
        if (!r.ok) throw new Error("Could not connect to API");
        return r.json();
      })
      .then((data) => {
        setSystem(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-black text-white">Studio Settings</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Your private, local Clipedics configuration and processing engine.
        </p>
      </div>

      {/* Mode Status */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Workspace Mode</h2>
            <p className="text-lg font-bold text-white mt-1">Personal Studio Edition</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              Direct access enabled — authentication and commercial billing limits disabled.
            </p>
          </div>
          <span className="text-xs px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
            Active
          </span>
        </div>
      </section>

      {/* Engine & Processing Config */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Engine Configuration</h2>

        {loading ? (
          <div className="h-20 bg-zinc-800/50 rounded-xl animate-pulse" />
        ) : error ? (
          <div className="p-4 bg-red-950/30 border border-red-800/40 rounded-xl text-red-300 text-sm">
            Backend API offline: {error}
          </div>
        ) : system ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3.5 bg-zinc-800/40 rounded-xl border border-zinc-700/40">
              <div>
                <p className="text-sm font-medium text-white">API Server</p>
                <p className="text-xs text-zinc-400">FastAPI backend running locally</p>
              </div>
              <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full">
                Connected
              </span>
            </div>

            <div className="flex items-center justify-between p-3.5 bg-zinc-800/40 rounded-xl border border-zinc-700/40">
              <div>
                <p className="text-sm font-medium text-white">Groq AI LPU</p>
                <p className="text-xs text-zinc-400">Model: qwen/qwen3.8-27b (Sliding token window)</p>
              </div>
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                system.groq_configured 
                  ? "text-emerald-400 bg-emerald-500/10 border border-emerald-500/20" 
                  : "text-amber-400 bg-amber-500/10 border border-amber-500/20"
              }`}>
                {system.groq_configured ? "Ready" : "Key Missing"}
              </span>
            </div>

            <div className="flex items-center justify-between p-3.5 bg-zinc-800/40 rounded-xl border border-zinc-700/40">
              <div>
                <p className="text-sm font-medium text-white">Faster-Whisper Model</p>
                <p className="text-xs text-zinc-400">Word-level transcription engine</p>
              </div>
              <span className="text-xs font-mono text-zinc-300 bg-zinc-800 px-2.5 py-1 rounded-md">
                {system.default_whisper_model}
              </span>
            </div>

            <div className="p-3.5 bg-zinc-800/40 rounded-xl border border-zinc-700/40 space-y-1">
              <p className="text-sm font-medium text-white">Output Clips Directory</p>
              <p className="text-xs font-mono text-zinc-400 break-all select-all">
                {system.output_dir}
              </p>
            </div>
          </div>
        ) : null}
      </section>

      {/* Usage & Quota Info */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Clip Generation Quota</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-lg font-bold text-white">Unlimited</p>
            <p className="text-xs text-zinc-500">
              No artificial clip caps or subscription paywalls.
            </p>
          </div>
          <Link
            href="/upload"
            className="text-xs font-medium px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white transition"
          >
            Create Clips
          </Link>
        </div>
      </section>
    </div>
  );
}
