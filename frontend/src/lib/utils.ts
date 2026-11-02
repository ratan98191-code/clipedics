// Clipedics – Utility helpers

import type { ProjectStatus } from "./types";

/** Format seconds as MM:SS */
export function fmtDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Virality score color class (Tailwind) */
export function viralityColor(score: number): string {
  if (score >= 80) return "text-green-400";
  if (score >= 55) return "text-yellow-400";
  return "text-red-400";
}

/** Virality score background badge class */
export function viralityBadge(score: number): string {
  if (score >= 80) return "bg-green-500/20 text-green-300 border-green-500/40";
  if (score >= 55) return "bg-yellow-500/20 text-yellow-300 border-yellow-500/40";
  return "bg-red-500/20 text-red-300 border-red-500/40";
}

/** Status → display label + Tailwind colour */
export function statusMeta(status: ProjectStatus): { label: string; cls: string } {
  const map: Record<ProjectStatus, { label: string; cls: string }> = {
    pending:      { label: "Pending",      cls: "bg-zinc-700 text-zinc-300" },
    queued:       { label: "Queued",       cls: "bg-blue-500/20 text-blue-300" },
    downloading:  { label: "Downloading",  cls: "bg-sky-500/20 text-sky-300" },
    transcribing: { label: "Transcribing", cls: "bg-violet-500/20 text-violet-300" },
    clipping:     { label: "AI Clipping",  cls: "bg-purple-500/20 text-purple-300" },
    rendering:    { label: "Rendering",    cls: "bg-orange-500/20 text-orange-300" },
    done:         { label: "Done",         cls: "bg-green-500/20 text-green-300" },
    error:        { label: "Error",        cls: "bg-red-500/20 text-red-300" },
  };
  return map[status] ?? { label: status, cls: "bg-zinc-700 text-zinc-300" };
}

/** Copy text to clipboard */
export async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

