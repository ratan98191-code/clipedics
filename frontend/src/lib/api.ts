// Clipedics – API client (wraps FastAPI backend)
import type {
  Project,
  ProjectListItem,
  Clip,
  Job,
  CreateProjectPayload,
  UpdateClipPayload,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const api = {
  projects: {
    list: (): Promise<ProjectListItem[]> =>
      request("/api/projects"),

    get: (id: string): Promise<Project> =>
      request(`/api/projects/${id}`),

    create: (payload: CreateProjectPayload): Promise<Project> =>
      request("/api/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    delete: (id: string): Promise<void> =>
      request(`/api/projects/${id}`, { method: "DELETE" }),
  },

  clips: {
    get: (id: string): Promise<Clip> =>
      request(`/api/clips/${id}`),

    update: (id: string, payload: UpdateClipPayload): Promise<Clip> =>
      request(`/api/clips/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),

    downloadUrl: (id: string): string =>
      `${BASE_URL}/api/clips/${id}/download`,

    trim: (id: string, start: number, end: number): Promise<Clip> =>
      request(`/api/clips/${id}/trim`, {
        method: "POST",
        body: JSON.stringify({ start_seconds: start, end_seconds: end, rerender: true }),
      }),

    swapBeats: (id: string, order: number[]): Promise<Clip> =>
      request(`/api/clips/${id}/swap-beats`, {
        method: "POST",
        body: JSON.stringify({ beat_order: order, rerender: true }),
      }),

    rerender: (id: string, style = "hormozi", layout = "center_crop"): Promise<Clip> =>
      request(`/api/clips/${id}/rerender`, {
        method: "POST",
        body: JSON.stringify({ subtitle_style: style, layout_mode: layout }),
      }),

    feedback: (id: string, action: string, rating?: number, notes?: string): Promise<{ status: string }> =>
      request(`/api/clips/${id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ action, rating, notes }),
      }),
  },

  jobs: {
    status: (id: string): Promise<Job> =>
      request(`/api/jobs/${id}/status`),

    /** Returns an EventSource for SSE real-time progress. */
    stream: (id: string): EventSource =>
      new EventSource(`${BASE_URL}/api/jobs/${id}`),
  },
};

