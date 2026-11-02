// Clipedics – Virality score badge
import { viralityBadge } from "@/lib/utils";

export function ViralityBadge({ score }: { score: number }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold border ${viralityBadge(score)}`}>
      🔥 {score}
    </span>
  );
}

