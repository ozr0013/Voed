import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadDropzone from "../components/UploadDropzone";
import { api, type ProjectSummary } from "../lib/api";
import { useAuth } from "../lib/auth";

function fmtDuration(s: number): string {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ready: "text-good",
    processing: "text-warn",
    uploading: "text-warn",
    error: "text-bad",
  };
  return <span className={`text-xs ${map[status] ?? "text-white/50"}`}>{status}</span>;
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  const refresh = () => api.listProjects().then(setProjects).catch(() => {});

  useEffect(() => {
    refresh();
    // poll so processing thumbnails/status update live
    const id = setInterval(refresh, 2500);
    return () => clearInterval(id);
  }, []);

  const remove = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (!confirm("Delete this project and its files?")) return;
    await api.deleteProject(id);
    refresh();
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Your projects</h1>
          <p className="text-sm text-white/50">{user?.email}</p>
        </div>
        <button
          onClick={() => logout().then(() => nav("/"))}
          className="rounded-lg border border-edge px-3 py-1.5 text-sm hover:bg-panel"
        >
          Sign out
        </button>
      </header>

      <div className="mb-10">
        <UploadDropzone onDone={(id) => nav(`/editor/${id}`)} />
      </div>

      {projects.length === 0 ? (
        <p className="text-sm text-white/40">No projects yet. Upload a video to begin.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <div
              key={p.id}
              onClick={() => nav(`/editor/${p.id}`)}
              className="group cursor-pointer overflow-hidden rounded-xl border border-edge bg-panel transition hover:border-accent/60"
            >
              <div className="aspect-video bg-ink">
                {p.thumb_url ? (
                  <img src={p.thumb_url} alt={p.name} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-white/30">
                    {p.status === "error" ? "failed" : "processing…"}
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between p-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="flex gap-2 text-xs text-white/40">
                    <span>{fmtDuration(p.duration_s)}</span>
                    <StatusPill status={p.status} />
                  </div>
                </div>
                <button
                  onClick={(e) => remove(e, p.id)}
                  className="opacity-0 transition group-hover:opacity-100 text-xs text-white/40 hover:text-bad"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
