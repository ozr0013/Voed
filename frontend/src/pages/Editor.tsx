import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AgentPanel from "../components/AgentPanel";
import MicButton from "../components/MicButton";
import Timeline from "../components/Timeline";
import VideoPreview from "../components/VideoPreview";
import { api, type ProjectDetail } from "../lib/api";
import { fmtTime } from "../lib/format";

function TranscriptionChip({ status }: { status: string }) {
  if (status === "ready") {
    return (
      <span className="rounded-full border border-good/40 bg-good/10 px-3 py-1 text-xs text-good">
        transcript ready
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="rounded-full border border-bad/40 bg-bad/10 px-3 py-1 text-xs text-bad">
        transcript failed
      </span>
    );
  }
  return (
    <span className="rounded-full border border-warn/40 bg-warn/10 px-3 py-1 text-xs text-warn">
      transcribing audio… (time-based edits work now)
    </span>
  );
}

export default function Editor() {
  const { id } = useParams();
  const projectId = Number(id);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  const load = useCallback(() => {
    api.getProject(projectId).then(setProject).catch((e) => setError(String(e.message)));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // While the project is still processing/transcribing, poll for updates.
  useEffect(() => {
    if (!project) return;
    if (project.status === "ready" && project.transcript_status === "ready") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [project, load]);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setCurrentTime(t);
  };

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link to="/dashboard" className="text-sm text-white/50 hover:text-white">
          ← Dashboard
        </Link>
        <p className="mt-4 text-bad">{error}</p>
      </div>
    );
  }
  if (!project) {
    return <div className="p-8 text-sm text-white/50">Loading editor…</div>;
  }

  const processing = project.status !== "ready";

  return (
    <div className="flex h-screen flex-col">
      {/* top bar */}
      <header className="flex items-center justify-between border-b border-edge px-5 py-3">
        <div className="flex items-center gap-3">
          <Link to="/dashboard" className="text-sm text-white/50 hover:text-white">
            ← Dashboard
          </Link>
          <span className="font-medium">{project.name}</span>
          <span className="text-xs text-white/40">
            {project.width}×{project.height} · {fmtTime(project.timeline_duration_s, true)}
          </span>
        </div>
        <TranscriptionChip status={project.transcript_status} />
      </header>

      {/* editor capture region — this is what the agent screenshots */}
      <div id="editor-capture" className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {processing ? (
            <div className="flex flex-1 items-center justify-center rounded-xl border border-edge bg-panel text-sm text-white/40">
              {project.status === "error"
                ? `Processing failed: ${project.error}`
                : "Processing video…"}
            </div>
          ) : (
            <VideoPreview
              ref={videoRef}
              src={project.preview_url}
              onTime={setCurrentTime}
              onDuration={() => {}}
            />
          )}
          <Timeline
            clips={project.clips}
            waveform={project.waveform}
            sourceDuration={project.duration_s}
            timelineDuration={project.timeline_duration_s}
            currentTime={currentTime}
            onSeek={seek}
          />
        </div>

        <div className="w-80 shrink-0">
          <AgentPanel />
        </div>
      </div>

      {/* mic */}
      <div className="flex items-center justify-center border-t border-edge py-4">
        <MicButton
          disabled
          hint={processing ? "Waiting for video to finish processing" : "Voice control arrives in milestone 4"}
        />
      </div>
    </div>
  );
}
