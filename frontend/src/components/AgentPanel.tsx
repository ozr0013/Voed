// Right-side agent panel. In milestone 3 this is a static shell showing the
// idle state; milestone 7 wires it to live WebSocket run events (transcript,
// plan checklist, per-step screenshots, status).
export interface AgentStepView {
  index: number;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  thought?: string;
  plan?: string[];
  expectedResult?: string;
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
  // The planner emits the overall plan on its first call; surface it once.
  const planItems = steps.find((s) => s.plan && s.plan.length > 0)?.plan ?? [];

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
        {planItems.length > 0 && (
          <div className="mb-4">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
              Reasoning plan
            </div>
            <ul className="space-y-1 text-xs text-coal/50">
              {planItems.map((item, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-coal/25">{i + 1}.</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
          Steps
        </div>
        {steps.length === 0 ? (
          <p className="text-sm leading-relaxed text-coal/40">
            No active task. Try “cut the first ten seconds” once the agent is wired
            up.
          </p>
        ) : (
          <ol className="space-y-3">
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
                <div className="min-w-0 flex-1">
                  <div className="text-coal/80">{s.label}</div>

                  {s.thought && (
                    <div className="mt-1 border-l border-coal/20 pl-2 text-xs italic text-coal/50">
                      {s.thought}
                    </div>
                  )}

                  {s.expectedResult && (
                    <div className="mt-1 text-xs text-coal/40">
                      <span className="text-coal/30">Expecting: </span>
                      {s.expectedResult}
                    </div>
                  )}

                  {s.observed && (
                    <div className="mt-1 text-xs text-coal/40">
                      <span className="text-coal/30">Observed: </span>
                      {s.observed}
                    </div>
                  )}

                  {(s.shotIn || s.shotOut) && (
                    <div className="mt-2 flex gap-2">
                      {s.shotIn && (
                        <img
                          src={s.shotIn}
                          alt="before"
                          className="h-16 rounded border border-coal/30 object-cover"
                        />
                      )}
                      {s.shotOut && (
                        <img
                          src={s.shotOut}
                          alt="after"
                          className="h-16 rounded border border-coal/30 object-cover"
                        />
                      )}
                    </div>
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
