// Clipedics – Status badge chip
import { statusMeta } from "@/lib/utils";
import type { ProjectStatus } from "@/lib/types";

export function StatusBadge({ status }: { status: ProjectStatus }) {
  const { label, cls } = statusMeta(status);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border border-white/10 ${cls}`}>
      {status !== "done" && status !== "error" && status !== "pending" && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {label}
    </span>
  );
}

