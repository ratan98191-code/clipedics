// Clipedics – Project detail page (clip grid + live progress)
"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { ClipCard } from "@/components/ClipCard";
import { StatusBadge } from "@/components/StatusBadge";
import type { Project } from "@/lib/types";

const TERMINAL = ["done", "error"];

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.projects.get(id);
      setProject(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 3s while in-progress
  useEffect(() => {
    if (!project || TERMINAL.includes(project.status)) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [project, load]);

  if (loading) return (
    <div className="flex items-center justify-center py-32 text-zinc-500">
      <div className="w-6 h-6 border-2 border-zinc-600 border-t-violet-500 rounded-full animate-spin mr-3" />
      Loading project…
    </div>
  );

  if (error || !project) return (
    <div className="text-center py-20">
      <p className="text-red-400">{error || "Project not found"}</p>
      <Link href="/dashboard" className="text-violet-400 text-sm mt-4 inline-block hover:underline">
        ← Back to Dashboard
      </Link>
    </div>
  );

  const isProcessing = !TERMINAL.includes(project.status);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        <div className="flex-1 min-w-0">
          <Link href="/dashboard" className="text-xs text-zinc-500 hover:text-zinc-300 transition mb-2 inline-block">
            ← Dashboard
          </Link>
          <h1 className="text-2xl font-black text-white leading-tight truncate">
            {project.video_title || project.title}
          </h1>
          <p className="text-xs text-zinc-500 mt-1 truncate">{project.input_source}</p>
        </div>
        <StatusBadge status={project.status} />
      </div>

      {/* Live progress (while processing) */}
      {isProcessing && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-zinc-300">Processing Video</h2>
            <span className="text-xs font-mono font-medium text-violet-400">
              {project.job_progress ? `${project.job_progress}%` : "Starting..."}
            </span>
          </div>
          <div className="space-y-3">
            <div className="relative h-2.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-violet-600 to-fuchsia-500 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.max(project.job_progress || 5, 5)}%`,
                }}
              />
            </div>
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
              <span>{project.job_step || `${project.status}...`}</span>
            </div>
          </div>
        </div>
      )}

      {/* Error state */}
      {project.status === "error" && project.error_message && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-4">
          <p className="text-sm text-red-300">
            <span className="font-semibold">Error: </span>{project.error_message}
          </p>
        </div>
      )}

      {/* Clips grid */}
      {project.clips.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-white mb-4">
            {project.clips.length} Clips Generated
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {project.clips.map((clip) => (
              <ClipCard key={clip.id} clip={clip} projectId={project.id} />
            ))}
          </div>
        </div>
      )}

      {project.status === "done" && project.clips.length === 0 && (
        <div className="text-center py-16 text-zinc-500">
          <p>Processing finished but no clips were generated.</p>
          <p className="text-xs mt-2">Check the API logs for details.</p>
        </div>
      )}
    </div>
  );
}
