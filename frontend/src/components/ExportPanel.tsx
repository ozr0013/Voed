import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

/* Four-point sparkle ornament (matches the app aesthetic). */
function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
    </svg>
  );
}

interface Props {
  projectId: number;
  /* Disable while the video is still processing / no render exists yet. */
  ready: boolean;
}

type DriveStatus = { configured: boolean; connected: boolean; email: string | null };

// Destinations that aren't wired to real credentials yet.
const SOON: { key: string; label: string; icon: string; needs: string }[] = [
  {
    key: "email",
    label: "Email",
    icon: "✉",
    needs: "Email export needs an SMTP server or email API configured. Not set up yet.",
  },
  {
    key: "slack",
    label: "Slack",
    icon: "#",
    needs: "Slack needs a bot token / MCP server connected. Not set up yet.",
  },
];

export default function ExportPanel({ projectId, ready }: Props) {
  const [note, setNote] = useState<string | null>(null);
  const [drive, setDrive] = useState<DriveStatus | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ name: string; link: string | null } | null>(null);

  const refreshDrive = useCallback(() => {
    api.driveStatus().then(setDrive).catch(() => setDrive(null));
  }, []);

  useEffect(() => {
    if (ready) refreshDrive();
  }, [ready, refreshDrive]);

  // The OAuth popup posts back here when it finishes.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.source === "voicecut-drive") {
        refreshDrive();
        setNote(e.data.ok ? "Google Drive connected." : "Drive connection was cancelled.");
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [refreshDrive]);

  const connectDrive = () => {
    setNote(null);
    window.open(
      api.driveConnectUrl(),
      "voicecut-drive",
      "width=520,height=660,menubar=no,toolbar=no",
    );
  };

  const sendToDrive = async () => {
    setSending(true);
    setNote(null);
    setResult(null);
    try {
      const r = await api.sendToDrive(projectId);
      setResult({ name: r.name, link: r.link });
    } catch (e) {
      setNote(String((e as Error).message ?? e));
    } finally {
      setSending(false);
    }
  };

  const driveLabel = () => {
    if (!drive) return "Drive";
    if (!drive.configured) return "Drive";
    if (!drive.connected) return "Connect Drive";
    return sending ? "Sending…" : "Send to Drive";
  };

  const onDriveClick = () => {
    if (!drive) {
      setNote(
        "Can't reach the export service — the backend needs a restart to load the " +
          "Drive routes. Restart start.ps1, then reopen this project.",
      );
      refreshDrive();
      return;
    }
    if (!drive.configured) {
      setNote(
        "Google Drive isn't configured on the server. Set VOICECUT_GOOGLE_CLIENT_ID " +
          "and VOICECUT_GOOGLE_CLIENT_SECRET, then restart.",
      );
      return;
    }
    if (!drive.connected) return connectDrive();
    if (!sending) sendToDrive();
  };

  return (
    <div className="border border-coal bg-paper2 p-4 font-mono text-coal">
      <div className="mb-3 flex items-center justify-between border-b border-coal/30 pb-2">
        <h2 className="font-display text-sm font-black uppercase tracking-tight">Export</h2>
        <Sparkle className="h-3 w-3 text-flame" />
      </div>

      {!ready ? (
        <p className="text-xs uppercase tracking-[0.12em] text-coal/40">
          Available once the render is ready.
        </p>
      ) : (
        <>
          {/* primary: local download (works now) */}
          <a
            href={api.exportUrl(projectId)}
            download
            className="group flex items-center justify-center gap-2 border border-coal bg-flame px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-coal shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f]"
          >
            <span className="text-sm">↓</span>
            Download .mp4
          </a>

          {/* Google Drive */}
          <button
            onClick={onDriveClick}
            disabled={sending}
            className="mt-2 flex w-full items-center justify-center gap-2 border border-coal bg-paper px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-coal transition-colors hover:border-flame hover:text-flame disabled:opacity-60"
          >
            <span className="text-sm">▲</span>
            {driveLabel()}
          </button>
          {drive?.connected && drive.email && (
            <div className="mt-1 truncate text-[10px] uppercase tracking-widest text-coal/40">
              as {drive.email} ·{" "}
              <button
                className="underline hover:text-flame"
                onClick={() => api.driveDisconnect().then(refreshDrive)}
              >
                disconnect
              </button>
            </div>
          )}

          {result && (
            <p className="mt-2 border-l-2 border-[#1f8a57] bg-[#1f8a57]/5 py-1.5 pl-2 text-[11px] leading-snug text-coal/70">
              Uploaded “{result.name}” to Drive.
              {result.link && (
                <>
                  {" "}
                  <a
                    href={result.link}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold text-[#1f8a57] underline"
                  >
                    Open →
                  </a>
                </>
              )}
            </p>
          )}

          {/* not-yet-wired destinations */}
          <div className="mt-4 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
            More
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {SOON.map((d) => (
              <button
                key={d.key}
                onClick={() => setNote(d.needs)}
                title={`Send to ${d.label}`}
                className="flex items-center justify-center gap-1.5 border border-coal/40 bg-paper px-2 py-2 text-[10px] font-bold uppercase tracking-widest text-coal/70 transition-colors hover:border-flame hover:text-flame"
              >
                <span className="text-sm leading-none">{d.icon}</span>
                {d.label}
              </button>
            ))}
          </div>

          {note && (
            <p className="mt-3 border-l-2 border-flame bg-flame/5 py-1.5 pl-2 text-[11px] leading-snug text-coal/70">
              {note}
            </p>
          )}
        </>
      )}
    </div>
  );
}
