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
    <aside className="flex h-full w-full flex-col border border-coal bg-paper2 p-4 font-mono text-coal">
      <div className="mb-3 flex items-center justify-between border-b border-coal/30 pb-3">
        <h2 className="font-display text-lg font-black uppercase tracking-tight">Agent</h2>
        <span className="text-[11px] uppercase tracking-widest text-flame">[{status ?? "idle"}]</span>
      </div>

      <div className="mb-4 border border-coal bg-paper p-3 text-sm">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
          You said
        </div>
        <div className="mt-1 text-coal/80">
          {transcript || <span className="text-coal/30">Hold the mic and speak a command…</span>}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">Plan</div>
        {steps.length === 0 ? (
          <p className="text-sm leading-relaxed text-coal/40">
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
                      ? "text-[#1f8a57]"
                      : s.status === "failed"
                        ? "text-flame"
                        : s.status === "running"
                          ? "text-flame"
                          : "text-coal/30"
                  }
                >
                  {s.status === "done" ? "✓" : s.status === "failed" ? "✗" : "○"}
                </span>
                <div>
                  <div className="text-coal/80">{s.label}</div>
                  {s.observed && (
                    <div className="text-xs text-coal/40">{s.observed}</div>
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
