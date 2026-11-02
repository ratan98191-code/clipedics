// Clipedics – Shared TypeScript types (mirrors Python Pydantic schemas)

export type ProjectStatus =
  | "pending"
  | "queued"
  | "downloading"
  | "transcribing"
  | "clipping"
  | "rendering"
  | "done"
  | "error";

export interface Clip {
  id: string;
  project_id: string;
  clip_number: number;
  title: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  virality_score: number;
  virality_rationale: string;
  hook_sentence: string;
  suggested_caption: string;
  hashtags: string[];
  raw_mp4_path: string;
  output_mp4_path: string;
  thumbnail_path: string;
  success: boolean;
  error: string;
  created_at: string;
}

export interface Project {
  id: string;
  title: string;
  input_source: string;
  video_title: string;
  status: ProjectStatus;
  error_message?: string | null;
  job_progress?: number;
  job_step?: string;
  created_at: string;
  updated_at: string;
  clips: Clip[];
}

export interface ProjectListItem {
  id: string;
  title: string;
  video_title: string;
  status: ProjectStatus;
  created_at: string;
  clips_count: number;
}

export interface Job {
  id: string;
  project_id: string;
  celery_task_id?: string | null;
  status: string;
  progress: number;
  step: string;
  created_at: string;
  updated_at: string;
}

export interface JobSSEEvent {
  job_id: string;
  project_id: string;
  status: string;
  progress: number;
  step: string;
  updated_at: string;
}

export interface CreateProjectPayload {
  input_source: string;
  num_clips?: number | null;
  min_seconds?: number | null;
  max_seconds?: number | null;
  subtitle_style?: string;
  reframe?: boolean;
  whisper_model?: string | null;
}

export interface UpdateClipPayload {
  title?: string;
  suggested_caption?: string;
  hashtags?: string[];
}

