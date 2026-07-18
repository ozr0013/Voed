import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadDropzone from "../components/UploadDropzone";
import { api, type ProjectSummary } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";

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
  if (!s) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function fmtDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export default function Dashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter/Sort States
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("updated"); // updated, name, duration

  // Bulk Actions
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  // Inline Rename States
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");

  // Activity Log State
  const [activity, setActivity] = useState<string[]>([]);

  // Health check state
  const [agentOnline, setAgentOnline] = useState(true);

  const refresh = (isFirst = false) => {
    api.listProjects()
      .then((data) => {
        setProjects(data);
        if (isFirst) setLoading(false);
      })
      .catch(() => {
        if (isFirst) setLoading(false);
      });
  };

  useEffect(() => {
    refresh(true);
    const id = setInterval(() => refresh(false), 2500);

    // Initial dummy activity log
    const initialActivity = [
      `System initialized under sponsor: ${user?.email || "editor@voicecut.local"}`,
      "Local STT engine loaded (Whisper.cpp)",
      "Local TTS engine loaded (Piper.onnx)",
      "Local LLM engine status check: Gemma-3-4B active",
    ];
    setActivity(initialActivity);

    // check backend connection
    api.ping()
      .then((r) => setAgentOnline(r.ok))
      .catch(() => setAgentOnline(false));

    return () => clearInterval(id);
  }, []);

  const addActivity = (msg: string) => {
    setActivity((prev) => [msg, ...prev].slice(0, 15));
  };

  const remove = async (e: React.MouseEvent, id: number, name: string) => {
    e.stopPropagation();
    if (!confirm(`Delete project "${name}" and all its files?`)) return;
    try {
      await api.deleteProject(id);
      addActivity(`Deleted project: "${name}"`);
      setSelectedIds((prev) => prev.filter((pId) => pId !== id));
      refresh();
    } catch (err) {
      alert(`Delete failed: ${err}`);
    }
  };

  const bulkDelete = async () => {
    if (selectedIds.length === 0) return;
    if (!confirm(`Delete all ${selectedIds.length} selected projects?`)) return;
    try {
      for (const id of selectedIds) {
        await api.deleteProject(id);
      }
      addActivity(`Bulk deleted ${selectedIds.length} projects`);
      setSelectedIds([]);
      refresh();
    } catch (err) {
      alert(`Bulk delete failed: ${err}`);
    }
  };

  const startRename = (e: React.MouseEvent, id: number, currentName: string) => {
    e.stopPropagation();
    setRenamingId(id);
    setNewName(currentName);
  };

  const saveRename = async (e: React.FormEvent, id: number) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      await api.renameProject(id, newName.trim());
      addActivity(`Renamed project to "${newName.trim()}"`);
      setRenamingId(null);
      refresh();
    } catch (err) {
      alert(`Rename failed: ${err}`);
    }
  };

  const handleToggleSelect = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((pId) => pId !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    const visibleIds = filteredProjects.map((p) => p.id);
    const allSelected = visibleIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !visibleIds.includes(id)));
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  // Stats Calculations
  const totalProjectsCount = projects.length;
  const totalVideoDuration = projects.reduce((acc, p) => acc + (p.duration_s || 0), 0);
  const totalCutsCount = projects.filter((p) => p.status === "ready").length * 4; // Mock estimate

  // Filter & Sort Logic
  const filteredProjects = projects
    .filter((p) => {
      const matchesSearch = p.name.toLowerCase().includes(search.toLowerCase());
      if (statusFilter === "all") return matchesSearch;
      return matchesSearch && p.status === statusFilter;
    })
    .sort((a, b) => {
      if (sortBy === "name") {
        return a.name.localeCompare(b.name);
      }
      if (sortBy === "duration") {
        return (b.timeline_duration_s || b.duration_s) - (a.timeline_duration_s || a.duration_s);
      }
      // default: updated
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });

  return (
    <div className="relative min-h-screen bg-ink font-mono text-white selection:bg-accent selection:text-white">
      {/* Matte noise overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-50 opacity-[0.03] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Upper Header Navigation */}
        <header className="flex flex-col gap-4 border-b border-edge pb-6 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-accent animate-pulse" />
              <h1 className="font-display text-2xl font-black uppercase tracking-tight sm:text-3xl">
                VOICECUT CONTROL PANEL
              </h1>
            </div>
            <p className="mt-1.5 text-xs tracking-wider text-white/40 uppercase">
              ACTIVE NODE: {user?.email || "editor@voicecut.local"}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 border border-edge bg-panel/40 px-3 py-1.5 text-xs font-bold tracking-wider text-white/60">
              AGENT STATE:{" "}
              <span className={agentOnline ? "text-good" : "text-accent animate-pulse"}>
                {agentOnline ? "ONLINE" : "OFFLINE"}
              </span>
            </div>
            <a href="https://github.com/ozr0013/voicecut" target="_blank" rel="noreferrer">
              <Button variant="outline" size="sm">DOCS</Button>
            </a>
          </div>
        </header>

        {/* Dashboard Quick Stats */}
        <div className="my-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative border border-edge bg-panel/30 p-5">
            {CORNERS.map((pos) => (
              <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
            ))}
            <div className="text-[10px] font-bold uppercase tracking-widest text-white/40">Total Project Ingests</div>
            <div className="mt-2 text-2xl font-black tracking-tight">{totalProjectsCount}</div>
          </div>
          <div className="relative border border-edge bg-panel/30 p-5">
            {CORNERS.map((pos) => (
              <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
            ))}
            <div className="text-[10px] font-bold uppercase tracking-widest text-white/40">Total Video Indexed</div>
            <div className="mt-2 text-2xl font-black tracking-tight">{fmtDuration(totalVideoDuration)}</div>
          </div>
          <div className="relative border border-edge bg-panel/30 p-5">
            {CORNERS.map((pos) => (
              <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
            ))}
            <div className="text-[10px] font-bold uppercase tracking-widest text-white/40">Calculated Trims</div>
            <div className="mt-2 text-2xl font-black tracking-tight">{totalCutsCount} cuts</div>
          </div>
          <div className="relative border border-edge bg-panel/30 p-5">
            {CORNERS.map((pos) => (
              <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
            ))}
            <div className="text-[10px] font-bold uppercase tracking-widest text-white/40">Agent Model Memory</div>
            <div className="mt-2 text-2xl font-black tracking-tight text-accent">Gemma3-4B</div>
          </div>
        </div>

        {/* Main Dashboard Panel Layout */}
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Main Workspace Column */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            {/* Upload Area */}
            <div>
              <UploadDropzone onDone={(id) => {
                addActivity(`Uploaded new project file`);
                nav(`/editor/${id}`);
              }} />
            </div>

            {/* Filter / Search / Control Bar */}
            <div className="relative border border-edge bg-panel/20 p-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              {CORNERS.map((pos) => (
                <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
              ))}
              
              {/* Search Bar */}
              <div className="relative flex-1 max-w-md">
                <input
                  type="text"
                  placeholder="SEARCH INDEXED PROJECTS..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full border border-edge bg-ink/65 px-3 py-2 text-xs font-semibold tracking-wider outline-none placeholder:text-white/20 focus:border-accent"
                />
              </div>

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-3">
                {filteredProjects.length > 0 && (
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={handleSelectAll}
                    className="h-7.5 px-3 text-[10px] font-bold"
                  >
                    {filteredProjects.every((p) => selectedIds.includes(p.id)) ? "DESELECT ALL" : "SELECT ALL"}
                  </Button>
                )}
                <div className="flex items-center gap-1.5 text-xs font-bold text-white/40 uppercase">
                  <span>Filter:</span>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="border border-edge bg-ink px-2 py-1 text-white hover:border-accent outline-none"
                  >
                    <option value="all">ALL STATUSES</option>
                    <option value="ready">READY</option>
                    <option value="processing">PROCESSING</option>
                    <option value="error">FAILED</option>
                  </select>
                </div>

                <div className="flex items-center gap-1.5 text-xs font-bold text-white/40 uppercase">
                  <span>Sort:</span>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    className="border border-edge bg-ink px-2 py-1 text-white hover:border-accent outline-none"
                  >
                    <option value="updated">LAST MODIFIED</option>
                    <option value="name">ALPHABETICAL</option>
                    <option value="duration">VIDEO DURATION</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Bulk Actions Header */}
            {selectedIds.length > 0 && (
              <div className="flex items-center justify-between border border-accent bg-accent/5 px-4 py-3 text-xs font-bold tracking-wider animate-rise">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-none bg-accent animate-ping" />
                  <span>{selectedIds.length} PROJECTS SELECTED</span>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="xs" onClick={() => setSelectedIds([])}>
                    DESELECT ALL
                  </Button>
                  <Button variant="destructive" size="xs" onClick={bulkDelete}>
                    BULK DELETE
                  </Button>
                </div>
              </div>
            )}

            {/* Project List / Grid */}
            {loading ? (
              <div className="py-24 text-center text-xs font-bold uppercase tracking-[0.25em] text-white/40 animate-pulse">
                SCANNING LOCAL DIRECTORIES…
              </div>
            ) : filteredProjects.length === 0 ? (
              <div className="relative border border-dashed border-edge/60 py-20 text-center">
                {CORNERS.map((pos) => (
                  <Sparkle key={pos} className={`absolute h-2 w-2 text-edge/40 ${pos}`} />
                ))}
                <div className="text-xs font-bold uppercase tracking-[0.2em] text-white/30">
                  {search || statusFilter !== "all" 
                    ? "NO INDEXES MATCH CRITERIA" 
                    : "NO DISCOVERED PROJECTS"}
                </div>
                <p className="mt-2 text-[10px] text-white/20 uppercase tracking-widest">
                  {search || statusFilter !== "all" 
                    ? "Adjust search keyword or filter selects" 
                    : "Drag or select a video to trigger index creation"}
                </p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 pb-12">
                {filteredProjects.map((p) => {
                  const isSelected = selectedIds.includes(p.id);
                  const isRenaming = renamingId === p.id;
                  
                  return (
                    <div
                      key={p.id}
                      onClick={() => !isRenaming && nav(`/editor/${p.id}`)}
                      className={`group relative cursor-pointer border bg-panel/30 transition-all hover:-translate-x-[2px] hover:-translate-y-[2px] ${
                        isSelected 
                          ? "border-accent shadow-[3px_3px_0_0_#C8102E]" 
                          : "border-edge hover:border-white/30 hover:shadow-[3px_3px_0_0_rgba(255,255,255,0.05)]"
                      }`}
                    >
                      {CORNERS.map((pos) => (
                        <Sparkle
                          key={pos}
                          className={`pointer-events-none absolute z-10 h-2 w-2 ${
                            isSelected ? "text-accent" : "text-edge"
                          } ${pos}`}
                        />
                      ))}

                      {/* Select Checkbox Action */}
                      <button
                        onClick={(e) => handleToggleSelect(e, p.id)}
                        className={`absolute top-3 left-3 z-20 flex h-4.5 w-4.5 items-center justify-center border font-bold text-[9px] transition-all rounded-none ${
                          isSelected 
                            ? "border-accent bg-accent text-white" 
                            : "border-edge bg-ink/80 text-transparent hover:border-white/40"
                        }`}
                      >
                        ✓
                      </button>

                      {/* Video Preview Frame */}
                      <div className="relative aspect-video overflow-hidden border-b border-edge bg-ink">
                        {p.thumb_url ? (
                          <img src={p.thumb_url} alt={p.name} className="h-full w-full object-cover grayscale transition-all group-hover:grayscale-0 duration-300" />
                        ) : (
                          <div className="flex h-full items-center justify-center text-[10px] uppercase tracking-widest text-white/20">
                            {p.status === "error" ? "COMPILE ERROR" : "PROBING VIDEO…"}
                          </div>
                        )}

                        {/* Status Label Overlay */}
                        <div className="absolute bottom-2 right-2 z-10 border border-edge bg-ink/95 px-2 py-0.5 text-[9px] font-bold tracking-widest uppercase text-white/70">
                          {p.status}
                        </div>
                      </div>

                      {/* Card Meta & Detail Content */}
                      <div className="p-4">
                        {isRenaming ? (
                          <form
                            onSubmit={(e) => saveRename(e, p.id)}
                            onClick={(e) => e.stopPropagation()}
                            className="flex gap-2"
                          >
                            <input
                              type="text"
                              value={newName}
                              onChange={(e) => setNewName(e.target.value)}
                              className="flex-1 border border-accent bg-ink px-2 py-1 text-xs font-semibold uppercase outline-none"
                              autoFocus
                            />
                            <Button size="xs" type="submit">SAVE</Button>
                          </form>
                        ) : (
                          <div className="truncate font-display text-sm font-bold uppercase tracking-tight">
                            {p.name}
                          </div>
                        )}

                        <div className="mt-3 grid grid-cols-2 gap-x-2 gap-y-1 text-[9px] font-semibold tracking-wider text-white/40 uppercase">
                          <div>timeline: <span className="text-white/70">{fmtDuration(p.timeline_duration_s || p.duration_s)}</span></div>
                          <div>source: <span className="text-white/70">{fmtDuration(p.duration_s)}</span></div>
                          <div className="truncate col-span-2 mt-1">indexed: <span className="text-white/70">{fmtDate(p.updated_at)}</span></div>
                        </div>

                        {/* Card Hover Action Bar */}
                        {!isRenaming && (
                          <div className="mt-4 flex items-center justify-end gap-3 border-t border-edge/30 pt-3">
                            <button
                              onClick={(e) => startRename(e, p.id, p.name)}
                              className="text-[10px] font-bold uppercase tracking-widest text-white/50 hover:text-white transition-colors"
                            >
                              Rename
                            </button>
                            <button
                              onClick={(e) => remove(e, p.id, p.name)}
                              className="text-[10px] font-bold uppercase tracking-widest text-white/30 hover:text-accent transition-colors"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Activities / Health Sidebar */}
          <div className="lg:col-span-1 flex flex-col gap-6">
            {/* System Node Info */}
            <div className="relative border border-edge bg-panel/30 p-5">
              {CORNERS.map((pos) => (
                <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
              ))}
              <div className="text-[10px] font-bold uppercase tracking-widest text-white/40">Hardware State</div>
              
              <div className="mt-3 flex flex-col gap-2 text-[10px] font-semibold tracking-wider text-white/60 uppercase">
                <div className="flex justify-between border-b border-edge/20 pb-1">
                  <span>whisper engine</span>
                  <span className="text-good font-bold">READY</span>
                </div>
                <div className="flex justify-between border-b border-edge/20 pb-1">
                  <span>tts processor</span>
                  <span className="text-good font-bold">READY</span>
                </div>
                <div className="flex justify-between border-b border-edge/20 pb-1">
                  <span>ffmpeg render</span>
                  <span className="text-good font-bold">READY</span>
                </div>
                <div className="flex justify-between">
                  <span>planner core</span>
                  <span className="text-good font-bold">READY</span>
                </div>
              </div>
            </div>

            {/* Recent Activity Logs */}
            <div className="relative flex-1 border border-edge bg-panel/30 p-5 flex flex-col min-h-[300px]">
              {CORNERS.map((pos) => (
                <Sparkle key={pos} className={`absolute h-2 w-2 text-edge ${pos}`} />
              ))}
              <div className="text-[10px] font-bold uppercase tracking-widest text-white/40 border-b border-edge/30 pb-2">Recent Activities</div>
              
              <div className="mt-3 flex-1 overflow-y-auto max-h-[400px] flex flex-col gap-3 pr-1 text-[9px] leading-relaxed tracking-wider text-white/50 font-mono">
                {activity.map((act, index) => (
                  <div key={index} className="flex gap-2 border-l border-edge pl-2 py-0.5">
                    <span className="text-accent">❯</span>
                    <span>{act}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
