// Tiny fetch wrapper. All requests are same-origin (Vite proxies /api to the
// backend in dev; in production the backend serves the built frontend), and
// credentials are included so the httpOnly JWT cookie rides along.

export interface HealthCheck {
  name: string;
  ok: boolean;
  detail: string;
  fix: string;
}
export interface HealthReport {
  ok: boolean;
  model: string;
  lan_url: string;
  checks: HealthCheck[];
}

export interface User {
  id: number;
  email: string;
}

export interface Clip {
  id: number;
  order_index: number;
  src_start_s: number;
  src_end_s: number;
  duration_s: number;
  caption_text: string | null;
  muted?: boolean;
}

export interface ProjectSummary {
  id: number;
  name: string;
  status: string;
  error: string | null;
  duration_s: number;
  timeline_duration_s: number;
  width: number;
  height: number;
  thumb_url: string | null;
  transcript_status: string;
  updated_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  fps: number;
  waveform: number[] | null;
  clips: Clip[];
  muted_ranges?: { start: number; end: number }[];
  preview_url: string | null;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Chunked upload: init -> send N chunks -> complete. onProgress in 0..1.
const CHUNK = 4 * 1024 * 1024; // 4 MB

async function uploadVideo(
  name: string,
  file: File,
  onProgress?: (frac: number) => void,
): Promise<ProjectSummary> {
  const initForm = new FormData();
  initForm.append("name", name);
  initForm.append("filename", file.name);
  const init = await fetch("/api/projects/upload/init", {
    method: "POST",
    credentials: "include",
    body: initForm,
  });
  if (!init.ok) throw new Error((await init.json()).detail ?? "Upload init failed");
  const { project_id, ext } = await init.json();

  let sent = 0;
  for (let start = 0; start < file.size; start += CHUNK) {
    const blob = file.slice(start, start + CHUNK);
    const form = new FormData();
    form.append("project_id", String(project_id));
    form.append("ext", ext);
    form.append("chunk", blob, `chunk-${start}`);
    const r = await fetch("/api/projects/upload/chunk", {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!r.ok) throw new Error("Upload failed mid-transfer");
    sent += blob.size;
    onProgress?.(Math.min(1, sent / file.size));
  }

  const done = new FormData();
  done.append("project_id", String(project_id));
  done.append("ext", ext);
  const complete = await fetch("/api/projects/upload/complete", {
    method: "POST",
    credentials: "include",
    body: done,
  });
  if (!complete.ok) throw new Error((await complete.json()).detail ?? "Finalize failed");
  return complete.json();
}

export const api = {
  health: () => req<HealthReport>("/api/health"),
  ping: () => req<{ ok: boolean }>("/api/ping"),

  // auth
  me: () => req<User>("/api/auth/me"),
  signup: (email: string, password: string) =>
    req<User>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    req<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => req<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  googleAvailable: () => req<{ configured: boolean }>("/api/auth/google/available"),

  // projects
  listProjects: () => req<ProjectSummary[]>("/api/projects"),
  getProject: (id: number) => req<ProjectDetail>(`/api/projects/${id}`),
  transcribe: (id: number) =>
    req<{ status: string }>(`/api/projects/${id}/transcribe`, { method: "POST" }),
  deleteProject: (id: number) =>
    req<{ ok: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),
  uploadVideo,

  // Same-origin URL for the current edited render (the JWT cookie rides along).
  exportUrl: (id: number) => `/api/projects/${id}/export`,

  // Google Drive integration
  driveStatus: () =>
    req<{ configured: boolean; connected: boolean; email: string | null }>(
      "/api/integrations/drive/status",
    ),
  driveConnectUrl: () => "/api/integrations/drive/connect",
  driveDisconnect: () =>
    req<{ ok: boolean }>("/api/integrations/drive/disconnect", { method: "POST" }),
  sendToDrive: (id: number) =>
    req<{ ok: boolean; name: string; link: string | null }>(
      `/api/integrations/drive/export/${id}`,
      { method: "POST" },
    ),
};
