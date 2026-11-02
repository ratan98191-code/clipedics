// Clipedics – Upload form (URL paste + options)
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function UploadForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [clips, setClips] = useState(5);
  const [minSec, setMinSec] = useState(30);
  const [maxSec, setMaxSec] = useState(90);
  const [style, setStyle] = useState("hormozi");
  const [reframe, setReframe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    try {
      const project = await api.projects.create({
        input_source: url.trim(),
        num_clips: clips,
        min_seconds: minSec,
        max_seconds: maxSec,
        subtitle_style: style,
        reframe,
      });
      router.push(`/projects/${project.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* URL input */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-zinc-300">
          YouTube URL or Video URL
        </label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          required
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-3 text-white placeholder-zinc-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition"
        />
      </div>

      {/* Options grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Number of clips</label>
          <input
            type="number" min={1} max={20}
            value={clips}
            onChange={(e) => setClips(+e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Min duration (s)</label>
          <input
            type="number" min={10} max={300}
            value={minSec}
            onChange={(e) => setMinSec(+e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-zinc-400">Max duration (s)</label>
          <input
            type="number" min={10} max={600}
            value={maxSec}
            onChange={(e) => setMaxSec(+e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500"
          />
        </div>
      </div>

      {/* Subtitle style */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-300">Caption Style</label>
        <div className="flex gap-3">
          {["hormozi", "minimal", "neon"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStyle(s)}
              className={`flex-1 py-2.5 rounded-lg border text-sm font-medium capitalize transition
                ${style === s
                  ? "border-violet-500 bg-violet-500/20 text-violet-200"
                  : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500"}`}
            >
              {s === "hormozi" ? "⚡ Hormozi" : s === "minimal" ? "✦ Minimal" : "🌈 Neon"}
            </button>
          ))}
        </div>
      </div>

      {/* Reframe toggle */}
      <div className="flex items-center justify-between py-3 px-4 bg-zinc-900 rounded-lg border border-zinc-800">
        <div>
          <p className="text-sm font-medium text-white">Auto-Reframe to 9:16</p>
          <p className="text-xs text-zinc-500 mt-0.5">Face-tracked vertical crop for TikTok / Reels</p>
        </div>
        <button
          type="button"
          onClick={() => setReframe(!reframe)}
          className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none
            ${reframe ? "bg-violet-600" : "bg-zinc-700"}`}
        >
          <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200
            ${reframe ? "translate-x-5" : "translate-x-0"}`} />
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || !url.trim()}
        className="w-full py-3.5 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-semibold text-base hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition"
      >
        {loading ? "Creating project…" : "🚀 Generate Clips"}
      </button>
    </form>
  );
}

