// Clipedics – SSE Job progress hook
"use client";
import { useEffect, useRef, useState } from "react";
import type { JobSSEEvent } from "@/lib/types";

export interface UseJobProgressOptions {
  jobId: string | null;
  onDone?: () => void;
  onError?: (msg: string) => void;
}

export function useJobProgress({ jobId, onDone, onError }: UseJobProgressOptions) {
  const [event, setEvent] = useState<JobSSEEvent | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const es = new EventSource(`${apiUrl}/api/jobs/${jobId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data: JobSSEEvent = JSON.parse(e.data);
        setEvent(data);
        if (data.status === "done") {
          es.close();
          onDone?.();
        } else if (data.status === "error") {
          es.close();
          onError?.(data.step);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [jobId, onDone, onError]);

  return event;
}

