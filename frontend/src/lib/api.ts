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
  },

  jobs: {
    status: (id: string): Promise<Job> =>
      request(`/api/jobs/${id}/status`),

    /** Returns an EventSource for SSE real-time progress. */
    stream: (id: string): EventSource =>
      new EventSource(`${BASE_URL}/api/jobs/${id}`),
  },
};

