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
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => req<HealthReport>("/api/health"),
  ping: () => req<{ ok: boolean }>("/api/ping"),
};
