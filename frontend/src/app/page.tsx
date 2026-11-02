// Clipedics – Landing page
import Link from "next/link";

export default function HomePage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center gap-8">
      {/* Hero */}
      <div className="space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-sm font-medium">
          <span className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-pulse" />
          Powered by Groq AI + Faster-Whisper
        </div>
        <h1 className="text-5xl md:text-7xl font-black tracking-tight bg-gradient-to-br from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
          Turn long videos into<br />
          <span className="bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
            viral short clips
          </span>
        </h1>
        <p className="text-xl text-zinc-400 max-w-2xl mx-auto">
          Drop a YouTube URL. Get AI-selected clips with kinetic captions,
          face-tracked 9:16 reframe, and virality scores. Ready for TikTok,
          Reels, and Shorts in minutes.
        </p>
      </div>

      {/* CTA */}
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <Link
          href="/upload"
          className="px-8 py-4 rounded-2xl bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white font-bold text-lg hover:opacity-90 transition shadow-lg shadow-violet-900/40"
        >
          🚀 Start for free
        </Link>
        <Link
          href="/dashboard"
          className="px-8 py-4 rounded-2xl border border-zinc-700 text-zinc-300 font-medium text-lg hover:border-zinc-500 hover:text-white transition"
        >
          View projects
        </Link>
      </div>

      {/* Feature grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8 w-full max-w-4xl">
        {[
          { icon: "⚡", title: "Groq LPU AI", desc: "Selects the most viral moments instantly" },
          { icon: "📐", title: "9:16 Reframe", desc: "Face-tracked vertical crop" },
          { icon: "✍️", title: "Kinetic Captions", desc: "Word-by-word ASS subtitles" },
          { icon: "🔥", title: "Virality Score", desc: "AI-rated 1–100 shareability" },
        ].map((f) => (
          <div
            key={f.title}
            className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl text-left"
          >
            <div className="text-3xl mb-2">{f.icon}</div>
            <p className="text-sm font-semibold text-white">{f.title}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
