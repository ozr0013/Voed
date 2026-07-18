import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadDropzone from "../components/UploadDropzone";
import { api, type ProjectSummary } from "../lib/api";
import { useAuth } from "../lib/auth";

/* Four-point sparkle ornament (matches the landing aesthetic). */
function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
    </svg>
  );
}

const CORNERS = [
  "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
  "right-0 top-0 translate-x-1/2 -translate-y-1/2",
  "left-0 bottom-0 -translate-x-1/2 translate-y-1/2",
  "right-0 bottom-0 translate-x-1/2 translate-y-1/2",
];

function fmtDuration(s: number): string {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ready: "text-coal/70",
    processing: "text-flame",
    uploading: "text-flame",
    error: "text-flame font-bold",
  };
  return (
    <span className={`text-[11px] uppercase tracking-widest ${map[status] ?? "text-coal/40"}`}>
      [{status}]
    </span>
  );
}

/* Animated equalizer — the dashboard hero visual (mirrors the logo waveform). */
function Equalizer() {
  return (
    <div
      aria-hidden
      className="hidden h-40 items-end justify-center gap-[5px] sm:flex"
    >
      {Array.from({ length: 34 }).map((_, i) => (
        <span
          key={i}
          className="eq-bar w-[5px] rounded-full bg-flame"
          style={{
            height: "100%",
            opacity: 0.35 + (i % 4) * 0.2,
            animationDelay: `${((i * 7) % 20) * 0.06}s`,
            animationDuration: `${1 + ((i * 3) % 6) * 0.14}s`,
          }}
        />
      ))}
    </div>
  );
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

  const totalMin = Math.round(
    projects.reduce((a, p) => a + (p.timeline_duration_s || p.duration_s || 0), 0) / 60,
  );

  return (
    <div className="relative min-h-screen bg-paper font-mono text-coal">
      {/* matte grain overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-50 opacity-[0.05] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        {/* header — Voed logo + account */}
        <header className="flex items-center justify-between border-b border-coal py-5">
          <div className="flex items-center gap-3">
            <img src="/voed-mark.svg" alt="Voed" className="h-12 w-auto" />
            <div>
              <div className="font-display text-xl font-black lowercase leading-none tracking-tight">
                voed
              </div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-coal/45">
                {user?.email}
              </div>
            </div>
          </div>
          <button
            onClick={() => logout().then(() => nav("/"))}
            className="border border-coal bg-paper px-4 py-2 text-xs font-bold uppercase tracking-widest shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f]"
          >
            Sign out
          </button>
        </header>

        {/* hero — cool visual + what this is */}
        <section className="rise relative mt-8 overflow-hidden border border-coal bg-coal text-paper shadow-hard">
          <div className="relative z-10 grid gap-8 px-6 py-10 sm:grid-cols-[1.5fr_1fr] sm:items-center sm:px-10 sm:py-12">
            <div>
              <div className="inline-flex items-center gap-2 border border-paper/20 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em] text-flame">
                <Sparkle className="h-3 w-3" />
                Voice-to-action studio
              </div>
              <h1 className="mt-4 font-display text-4xl font-black uppercase leading-[0.92] tracking-tight sm:text-5xl">
                Edit video
                <br />
                <span className="text-flame">by talking.</span>
              </h1>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-paper/55">
                Drop a clip, hold the mic, and tell the agent what to change — cut,
                caption, colour, speed. It watches your screen and does the work.
              </p>
              <div className="mt-7 flex flex-wrap gap-x-9 gap-y-4">
                {[
                  [String(projects.length), "projects", "text-paper"],
                  [totalMin ? `${totalMin}` : "0", "min of footage", "text-paper"],
                  ["100%", "local · 0 cloud", "text-flame"],
                ].map(([n, label, cls]) => (
                  <div key={label}>
                    <div className={`font-display text-2xl font-black leading-none ${cls}`}>
                      {n}
                    </div>
                    <div className="mt-1.5 text-[10px] uppercase tracking-[0.16em] text-paper/40">
                      {label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <Equalizer />
          </div>
        </section>

        <div className="my-8">
          <UploadDropzone onDone={(id) => nav(`/editor/${id}`)} />
        </div>

        <h2 className="mb-4 flex items-center gap-2 font-display text-lg font-black uppercase tracking-tight">
          Your projects
          <span className="text-xs font-bold text-coal/35">({projects.length})</span>
        </h2>

        {projects.length === 0 ? (
          <p className="border border-dashed border-coal/40 py-16 text-center text-xs uppercase tracking-[0.15em] text-coal/40">
            No projects yet — upload a video to begin.
          </p>
        ) : (
          <div className="grid gap-5 pb-12 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <div
                key={p.id}
                onClick={() => nav(`/editor/${p.id}`)}
                className="group relative cursor-pointer border border-coal bg-paper transition-all hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-hard"
              >
                {CORNERS.map((pos) => (
                  <Sparkle
                    key={pos}
                    className={`pointer-events-none absolute z-10 h-2.5 w-2.5 text-coal ${pos}`}
                  />
                ))}
                <div className="aspect-video overflow-hidden border-b border-coal bg-paper2">
                  {p.thumb_url ? (
                    <img src={p.thumb_url} alt={p.name} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full items-center justify-center text-[11px] uppercase tracking-widest text-coal/30">
                      {p.status === "error" ? "failed" : "processing…"}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 p-3.5">
                  <div className="min-w-0">
                    <div className="truncate font-display text-sm font-bold uppercase tracking-tight">
                      {p.name}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[11px] uppercase tracking-widest text-coal/40">
                      <span>{fmtDuration(p.timeline_duration_s || p.duration_s)}</span>
                      <StatusPill status={p.status} />
                    </div>
                  </div>
                  <button
                    onClick={(e) => remove(e, p.id)}
                    className="shrink-0 text-[11px] font-bold uppercase tracking-widest text-coal/40 opacity-0 transition group-hover:opacity-100 hover:text-flame"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
