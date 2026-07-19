import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import AgentPanel, { type AgentRunView } from "../components/AgentPanel";
import ExportPanel from "../components/ExportPanel";
import MicButton from "../components/MicButton";
import Timeline from "../components/Timeline";
import VideoPreview from "../components/VideoPreview";
import { runAgent, type StepEvent } from "../lib/agent";
import { captureEditor } from "../lib/screenshot";
import { api, ApiError, type ProjectDetail } from "../lib/api";
import { fmtTime } from "../lib/format";
import { isSpeechMuted, setSpeechMuted, speak } from "../lib/voice";

function TranscriptionChip({ status }: { status: string }) {
  const base = "border px-3 py-1 text-[11px] font-bold uppercase tracking-widest";
  if (status === "ready") {
    return (
      <span className={`${base} border-[#1f8a57]/50 bg-[#1f8a57]/10 text-[#1f8a57]`}>
        transcript ready
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className={`${base} border-flame/60 bg-flame/10 text-flame`}>
        transcript failed
      </span>
    );
  }
  return (
    <span className={`${base} border-flame/50 bg-flame/10 text-flame`}>
      transcribing audio… (time-based edits work now)
    </span>
  );
}

export default function Editor() {
  const { id } = useParams();
  const nav = useNavigate();
  const projectId = Number(id);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [runs, setRuns] = useState<AgentRunView[]>([]);
  const [agentStatus, setAgentStatus] = useState("idle");
  const [running, setRunning] = useState(false);
  const [muted, setMuted] = useState(isSpeechMuted());
  const videoRef = useRef<HTMLVideoElement>(null);
  const cancelRef = useRef(false);
  const runningRef = useRef(false);
  const transcribeReq = useRef(false);
  const runKey = useRef(0);

  // Update the CURRENT (last) run in the conversation.
  const patchCurrentRun = (fn: (r: AgentRunView) => AgentRunView) =>
    setRuns((prev) =>
      prev.length ? [...prev.slice(0, -1), fn(prev[prev.length - 1])] : prev,
    );

  const load = useCallback(async () => {
    try {
      setProject(await api.getProject(projectId));
      setError(null);
    } catch (e) {
      // Session expired or no access: stop polling and go to sign-in instead of
      // hammering the API with 401s forever.
      if (e instanceof ApiError && e.status === 401) {
        nav("/signin", { replace: true });
        return;
      }
      setError(String((e as Error).message));
    }
  }, [projectId, nav]);

  useEffect(() => {
    setProject(null);
    load();
  }, [load]);

  // Reset agent panel immediately when the route project id changes (Editor can
  // be reused across /editor/:id without unmounting, e.g. browser history).
  useEffect(() => {
    cancelRef.current = true;
    runningRef.current = false;
    setRunning(false);
    setRuns([]);
    setAgentStatus("idle");
    runKey.current = 0;
  }, [projectId]);

  // Restore agent conversation for THIS project only. Skips while a run is active.
  useEffect(() => {
    if (runningRef.current) return;
    let cancelled = false;
    const pid = projectId;
    api
      .agentRuns(pid)
      .then(({ runs: hist }) => {
        if (cancelled || runningRef.current || pid !== projectId) return;
        setRuns(
          hist.map((r) => ({
            key: `srv-${r.id}`,
            goal: r.goal,
            status: r.status,
            steps: Object.fromEntries(
              r.steps.map((s) => [
                s.index,
                {
                  index: s.index,
                  label: s.label,
                  status: s.status,
                  thought: s.thought ?? undefined,
                  expectedResult: s.expectedResult ?? undefined,
                  observed: s.observed ?? undefined,
                  shotIn: s.shotIn ?? undefined,
                  shotOut: s.shotOut ?? undefined,
                },
              ]),
            ),
          })),
        );
        setAgentStatus(hist.length ? hist[hist.length - 1].status : "idle");
      })
      .catch(() => {
        if (!cancelled && pid === projectId) setRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Self-heal: if a video's speech was never transcribed, kick it off once on
  // open. The endpoint is idempotent, and the poll below picks up "ready".
  useEffect(() => {
    if (project?.transcript_status === "pending" && !transcribeReq.current) {
      transcribeReq.current = true;
      api.transcribe(projectId).catch(() => {
        transcribeReq.current = false;
      });
    }
  }, [project, projectId]);

  // Poll only while processing/transcribing AND no agent run is active (a run
  // manages its own refetches; polling mid-run would fight the timeline render).
  useEffect(() => {
    if (!project || running) return;
    if (project.status === "ready" && project.transcript_status === "ready") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [project, running, load]);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
    setCurrentTime(t);
  };

  // The plan->act->verify agent loop, driven by a spoken (or typed) command.
  const onCommand = async (text: string) => {
    if (runningRef.current) return;
    // Append a new turn — previous turns stay in the conversation above.
    setRuns((prev) => [
      ...prev,
      { key: `local-${runKey.current++}`, goal: text, status: "running", steps: {} },
    ]);
    setAgentStatus("running");
    setRunning(true);
    runningRef.current = true;
    cancelRef.current = false;
    try {
      await runAgent(projectId, text, {
        onStatus: (s) => {
          setAgentStatus(s);
          patchCurrentRun((r) => ({ ...r, status: s }));
        },
        onStep: (e: StepEvent) =>
          patchCurrentRun((r) => ({
            ...r,
            steps: { ...r.steps, [e.index]: { ...r.steps[e.index], ...e } },
          })),
        onSeek: seek,
        refetchProject: load,
        shouldCancel: () => cancelRef.current,
      });
    } finally {
      setRunning(false);
      runningRef.current = false;
    }
  };

  const stopRun = () => {
    cancelRef.current = true;
    setAgentStatus("stopping…");
  };

  const onMicError = (msg: string) => {
    setAgentStatus("error");
    speak(msg);
  };

  // Test hook: trigger the loop by text when a real mic isn't available
  // (headless verification). Harmless in production.
  useEffect(() => {
    const w = window as unknown as {
      __voicecutRun?: (g: string) => void;
      __capTest?: () => Promise<number | string>;
    };
    w.__voicecutRun = (g) => onCommand(g);
    w.__capTest = async () => {
      try {
        const t0 = performance.now();
        const blob = await captureEditor();
        return `ok ${blob.size} bytes in ${Math.round(performance.now() - t0)}ms`;
      } catch (e) {
        return `err ${String((e as Error).message ?? e)}`;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  if (error) {
    return (
      <div className="min-h-screen bg-paper font-mono text-coal">
        <div className="mx-auto max-w-3xl px-6 py-16">
          <Link
            to="/dashboard"
            className="text-xs font-bold uppercase tracking-[0.18em] text-coal/60 hover:text-coal"
          >
            ← Dashboard
          </Link>
          <p className="mt-4 border border-flame bg-flame/10 px-3 py-2 text-sm text-flame">{error}</p>
        </div>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="grid min-h-screen place-items-center bg-paper font-mono text-xs uppercase tracking-[0.18em] text-coal/50">
        Loading editor…
      </div>
    );
  }

  const processing = project.status !== "ready";

  return (
    <div className="flex h-screen flex-col bg-paper font-mono text-coal">
      {/* top bar */}
      <header className="flex items-center justify-between border-b border-coal px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/dashboard"
            className="shrink-0 text-xs font-bold uppercase tracking-[0.15em] text-coal/60 hover:text-coal"
          >
            ← Dashboard
          </Link>
          <span className="truncate font-display text-base font-bold uppercase tracking-tight">
            {project.name}
          </span>
          <span className="shrink-0 text-[11px] uppercase tracking-widest text-coal/40">
            {project.width}×{project.height} · {fmtTime(project.timeline_duration_s, true)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              const next = !muted;
              setMuted(next);
              setSpeechMuted(next);
            }}
            title={muted ? "Spoken output off — click to enable" : "Spoken output on — click to mute"}
            className={`border px-3 py-1 text-[11px] font-bold uppercase tracking-widest transition-colors ${
              muted
                ? "border-coal/40 bg-paper2 text-coal/50"
                : "border-flame bg-flame/10 text-flame"
            }`}
          >
            {muted ? "🔇 voice off" : "🔊 voice on"}
          </button>
          <TranscriptionChip status={project.transcript_status} />
        </div>
      </header>

      {/* editor capture region — this is what the agent screenshots */}
      <div id="editor-capture" className="flex min-h-0 flex-1 gap-4 bg-paper p-4">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {processing ? (
            <div className="flex flex-1 items-center justify-center border border-coal bg-paper2 text-xs uppercase tracking-[0.15em] text-coal/40">
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

        <div className="flex w-80 shrink-0 flex-col gap-4">
          <div className="min-h-0 flex-1">
            <AgentPanel runs={runs} status={agentStatus} />
          </div>
          <ExportPanel projectId={projectId} ready={!processing} />
        </div>
      </div>

      {/* mic */}
      <div className="flex items-center justify-center gap-6 border-t border-coal py-4">
        <MicButton
          disabled={processing || running}
          hint={
            processing
              ? "Waiting for video to finish processing"
              : running
                ? "Working…"
                : undefined
          }
          onTranscript={onCommand}
          onError={onMicError}
        />
        {running && (
          <button
            onClick={stopRun}
            className="border border-flame bg-flame/10 px-4 py-2 text-xs font-bold uppercase tracking-widest text-flame transition-colors hover:bg-flame/20"
          >
            Stop
          </button>
        )}
      </div>
    </div>
  );
}
