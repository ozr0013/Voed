import { useEffect, useRef } from "react";

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

// One command and everything the agent did for it. Runs stack in the panel as a
// conversation — a new command appends a turn, it never wipes the history.
export interface AgentRunView {
  key: string;
  goal: string;
  status: string;
  steps: Record<number, AgentStepView>;
}

interface Props {
  runs?: AgentRunView[];
  status?: string;
}

function StepRow({ s }: { s: AgentStepView }) {
  const color =
    s.status === "done"
      ? "text-[#1f8a57]"
      : s.status === "failed"
        ? "text-flame"
        : s.status === "running"
          ? "text-flame"
          : "text-coal/30";
  const glyph = s.status === "done" ? "✓" : s.status === "failed" ? "✗" : "○";
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className={color}>{glyph}</span>
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
  );
}

export default function AgentPanel({ runs = [], status }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the newest turn in view as steps stream / new commands arrive.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [runs]);

  return (
    <aside className="flex h-full w-full flex-col border border-coal bg-paper2 p-4 font-mono text-coal">
      <div className="mb-3 flex items-center justify-between border-b border-coal/30 pb-3">
        <h2 className="font-display text-lg font-black uppercase tracking-tight">Agent</h2>
        <span className="text-[11px] uppercase tracking-widest text-flame">
          [{status ?? "idle"}]
        </span>
      </div>

      <div ref={scrollRef} className="scroll-slim -mr-1.5 flex-1 space-y-5 overflow-y-auto pr-1.5">
        {runs.length === 0 ? (
          <p className="text-sm leading-relaxed text-coal/40">
            No commands yet. Hold the mic (or press space) and say something like
            “cut the first ten seconds” or “add subtitles.”
          </p>
        ) : (
          runs.map((run) => {
            const steps = Object.values(run.steps).sort((a, b) => a.index - b.index);
            const plan = steps.find((s) => s.plan && s.plan.length > 0)?.plan ?? [];
            return (
              <div key={run.key} className="border-b border-coal/15 pb-5 last:border-b-0">
                <div className="border border-coal bg-paper p-3 text-sm">
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
                    You said
                  </div>
                  <div className="mt-1 text-coal/80">{run.goal}</div>
                </div>

                {plan.length > 0 && (
                  <div className="mt-3">
                    <div className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
                      Reasoning plan
                    </div>
                    <ul className="space-y-1 text-xs text-coal/50">
                      {plan.map((item, i) => (
                        <li key={i} className="flex gap-1.5">
                          <span className="text-coal/25">{i + 1}.</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {steps.length > 0 && (
                  <ol className="mt-3 space-y-3">
                    {steps.map((s) => (
                      <StepRow key={s.index} s={s} />
                    ))}
                  </ol>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
