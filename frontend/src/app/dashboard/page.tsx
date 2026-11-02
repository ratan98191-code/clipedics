// Clipedics – Dashboard (project list)
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ProjectCard } from "@/components/ProjectCard";
import type { ProjectListItem } from "@/lib/types";

export default function DashboardPage() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await api.projects.list();
      setProjects(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // Auto-refresh every 5s if any project is in-progress
    const interval = setInterval(() => {
      setProjects((prev) => {
        const hasActive = prev.some(
          (p) => !["done", "error"].includes(p.status)
        );
        if (hasActive) load();
        return prev;
      });
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-white">Your Projects</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            {projects.length} project{projects.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/upload"
          className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition"
        >
          + New Project
        </Link>
      </div>

      {/* States */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-zinc-500">
          <div className="w-6 h-6 border-2 border-zinc-600 border-t-violet-500 rounded-full animate-spin mr-3" />
          Loading…
        </div>
      )}

      {!loading && error && (
        <div className="text-center py-16 space-y-3">
          <p className="text-red-400">{error}</p>
          <p className="text-xs text-zinc-600">Make sure the Clipedics API is running on port 8000.</p>
          <button onClick={load} className="text-sm text-violet-400 hover:underline">
            Retry
          </button>
        </div>
      )}

      {!loading && !error && projects.length === 0 && (
        <div className="text-center py-20 space-y-4">
          <div className="text-6xl">🎬</div>
          <p className="text-zinc-400 text-lg font-medium">No projects yet</p>
          <p className="text-zinc-600 text-sm">Paste a YouTube URL to generate your first clips.</p>
          <Link
            href="/upload"
            className="inline-block mt-2 px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition"
          >
            Create First Project
          </Link>
        </div>
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="space-y-2">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}

