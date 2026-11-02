// Clipedics – Clip card for project grid
"use client";
import Link from "next/link";
import { fmtDuration, viralityBadge } from "@/lib/utils";
import type { Clip } from "@/lib/types";

interface Props {
  clip: Clip;
  projectId: string;
}

export function ClipCard({ clip, projectId }: Props) {
  const duration = fmtDuration(clip.duration_seconds);
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <Link
      href={`/projects/${projectId}/clips/${clip.id}`}
      className="group relative flex flex-col bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-violet-500/60 hover:shadow-lg hover:shadow-violet-900/20 transition-all duration-200"
    >
      {/* Thumbnail / video preview */}
      <div className="relative aspect-[9/16] bg-zinc-950 flex items-center justify-center overflow-hidden max-h-60">
        {clip.output_mp4_path ? (
          <video
            src={`${apiBase}/output/${clip.output_mp4_path.split("/output/")[1] ?? clip.output_mp4_path}`}
            className="w-full h-full object-cover"
            muted
            loop
            onMouseEnter={(e) => (e.currentTarget as HTMLVideoElement).play()}
            onMouseLeave={(e) => {
              const v = e.currentTarget as HTMLVideoElement;
              v.pause();
              v.currentTime = 0;
            }}
          />
        ) : (
          <div className="text-4xl opacity-20">🎬</div>
        )}

        {/* Duration pill */}
        <span className="absolute bottom-2 right-2 bg-black/70 text-white text-xs font-mono px-1.5 py-0.5 rounded">
          {duration}
        </span>

        {/* Virality badge */}
        <span className={`absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border ${viralityBadge(clip.virality_score)}`}>
          🔥 {clip.virality_score}
        </span>
      </div>

      {/* Metadata */}
      <div className="p-3 flex flex-col gap-1 flex-1">
        <p className="text-sm font-medium text-white leading-snug line-clamp-2">
          {clip.title}
        </p>
        <p className="text-xs text-zinc-500 line-clamp-2 mt-0.5">
          {clip.hook_sentence}
        </p>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {clip.hashtags.slice(0, 3).map((h) => (
            <span key={h} className="text-xs text-violet-400">#{h.replace(/^#/, "")}</span>
          ))}
        </div>
      </div>
    </Link>
  );
}

