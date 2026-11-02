// Clipedics – Project list card
import Link from "next/link";
import { StatusBadge } from "./StatusBadge";
import type { ProjectListItem } from "@/lib/types";

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function ProjectCard({ project }: { project: ProjectListItem }) {
  return (
    <Link
      href={`/projects/${project.id}`}
      className="flex items-center gap-4 p-4 bg-zinc-900 border border-zinc-800 rounded-xl hover:border-violet-500/50 hover:bg-zinc-800/60 transition group"
    >
      {/* Icon */}
      <div className="w-12 h-12 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-2xl flex-shrink-0">
        🎬
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white truncate group-hover:text-violet-300 transition">
          {project.video_title || project.title}
        </p>
        <p className="text-xs text-zinc-500 mt-0.5">{fmtDate(project.created_at)}</p>
      </div>

      {/* Right side */}
      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
        <StatusBadge status={project.status} />
        {project.clips_count > 0 && (
          <span className="text-xs text-zinc-500">{project.clips_count} clips</span>
        )}
      </div>
    </Link>
  );
}

