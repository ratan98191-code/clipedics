// Clipedics – Live progress tracker (SSE-driven)
"use client";
import { useJobProgress } from "@/hooks/useJobProgress";

interface Props {
  jobId: string;
  onDone?: () => void;
}

const STEPS = [
  "downloading",
  "transcribing",
  "clipping",
  "rendering",
];

export function ProgressTracker({ jobId, onDone }: Props) {
  const event = useJobProgress({ jobId, onDone });

  const progress = event?.progress ?? 0;
  const step = event?.step ?? "Waiting…";
  const status = event?.status ?? "queued";

  return (
    <div className="w-full space-y-4">
      {/* Step breadcrumb */}
      <div className="flex items-center gap-2 flex-wrap">
        {STEPS.map((s, i) => {
          const idx = STEPS.indexOf(status);
          const done = idx > i;
          const active = idx === i;
          return (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className="w-4 h-px bg-zinc-600" />}
              <span className={`text-xs font-medium capitalize px-2 py-0.5 rounded-full
                ${done ? "bg-green-500/20 text-green-300" :
                  active ? "bg-violet-500/30 text-violet-200 ring-1 ring-violet-500" :
                  "text-zinc-500"}`}>
                {s}
              </span>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-violet-600 to-fuchsia-500 rounded-full transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Step label + percent */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-zinc-400">{step}</span>
        <span className="text-zinc-300 font-mono">{progress}%</span>
      </div>
    </div>
  );
}

