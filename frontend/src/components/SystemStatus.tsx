import { useEffect, useState } from "react";
import { api, type HealthReport } from "../lib/api";

// A dependency banner. During the hackathon this is the first thing to check
// when something misbehaves: it shows whether ffmpeg / ollama / the model are
// live, and the exact command to fix whatever is missing.
export default function SystemStatus() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .health()
        .then((r) => alive && (setReport(r), setError(null)))
        .catch((e) => alive && setError(String(e.message ?? e)));
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm">
        Backend unreachable: {error}
      </div>
    );
  }
  if (!report) {
    return <div className="text-sm text-white/50">Checking local services…</div>;
  }

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-medium">
          Local services{" "}
          <span className={report.ok ? "text-good" : "text-warn"}>
            {report.ok ? "ready" : "needs attention"}
          </span>
        </span>
        <span className="text-xs text-white/40">model: {report.model}</span>
      </div>
      <ul className="space-y-2">
        {report.checks.map((c) => (
          <li key={c.name} className="text-sm">
            <span className={c.ok ? "text-good" : "text-bad"}>
              {c.ok ? "●" : "○"}
            </span>{" "}
            <span className="font-mono">{c.name}</span>{" "}
            <span className="text-white/50">— {c.detail}</span>
            {!c.ok && c.fix && (
              <div className="ml-4 mt-0.5 text-xs text-warn">{c.fix}</div>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 text-xs text-white/40">LAN: {report.lan_url}</div>
    </div>
  );
}
