// Right-side agent panel. In milestone 3 this is a static shell showing the
// idle state; milestone 7 wires it to live WebSocket run events (transcript,
// plan checklist, per-step screenshots, status).
export interface AgentStepView {
  index: number;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  observed?: string;
  shotIn?: string;
  shotOut?: string;
}

interface Props {
  transcript?: string | null;
  status?: string;
  steps?: AgentStepView[];
}

export default function AgentPanel({ transcript, status, steps = [] }: Props) {
  return (
    <aside className="flex h-full w-full flex-col rounded-xl border border-edge bg-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">Agent</h2>
        <span className="text-xs text-white/40">{status ?? "idle"}</span>
      </div>

      <div className="mb-3 rounded-lg border border-edge bg-ink/50 p-3 text-sm">
        <div className="text-[10px] uppercase tracking-wide text-white/30">
          You said
        </div>
        <div className="mt-1 text-white/80">
          {transcript || <span className="text-white/30">Hold the mic and speak a command…</span>}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mb-2 text-[10px] uppercase tracking-wide text-white/30">Plan</div>
        {steps.length === 0 ? (
          <p className="text-sm text-white/30">
            No active task. Try “cut the first ten seconds” once the agent is wired
            up.
          </p>
        ) : (
          <ol className="space-y-2">
            {steps.map((s) => (
              <li key={s.index} className="flex items-start gap-2 text-sm">
                <span
                  className={
                    s.status === "done"
                      ? "text-good"
                      : s.status === "failed"
                        ? "text-bad"
                        : s.status === "running"
                          ? "text-warn"
                          : "text-white/30"
                  }
                >
                  {s.status === "done" ? "✓" : s.status === "failed" ? "✗" : "○"}
                </span>
                <div>
                  <div>{s.label}</div>
                  {s.observed && (
                    <div className="text-xs text-white/40">{s.observed}</div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
