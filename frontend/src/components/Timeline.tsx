import { useMemo, useRef } from "react";
import type { Clip } from "../lib/api";
import { fmtTime } from "../lib/format";

interface Props {
  clips: Clip[];
  waveform: number[] | null; // peaks over the SOURCE video
  sourceDuration: number; // original length the waveform is indexed against
  timelineDuration: number; // current edited length (sum of clip durations)
  currentTime: number; // playhead position in edited-timeline seconds
  onSeek: (t: number) => void;
}

// Slice the source-aligned waveform for one clip's [start,end] source range.
function clipPeaks(
  waveform: number[] | null,
  srcStart: number,
  srcEnd: number,
  sourceDuration: number,
): number[] {
  if (!waveform || waveform.length === 0 || sourceDuration <= 0) return [];
  const n = waveform.length;
  const a = Math.max(0, Math.floor((srcStart / sourceDuration) * n));
  const b = Math.min(n, Math.ceil((srcEnd / sourceDuration) * n));
  return waveform.slice(a, Math.max(a + 1, b));
}

export default function Timeline({
  clips,
  waveform,
  sourceDuration,
  timelineDuration,
  currentTime,
  onSeek,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);

  const ticks = useMemo(() => {
    const dur = timelineDuration || 1;
    const count = 8;
    return Array.from({ length: count + 1 }, (_, i) => (dur * i) / count);
  }, [timelineDuration]);

  const playheadPct =
    timelineDuration > 0 ? Math.min(100, (currentTime / timelineDuration) * 100) : 0;

  const seekFromEvent = (e: React.MouseEvent) => {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    onSeek(frac * timelineDuration);
  };

  return (
    <div
      className="select-none border border-coal bg-paper2 p-3 font-mono"
      data-testid="timeline"
    >
      {/* ruler */}
      <div className="relative mb-1 h-4 text-[10px] tabular-nums text-coal/40">
        {ticks.map((t, i) => (
          <span
            key={i}
            className="absolute -translate-x-1/2 tabular-nums"
            style={{ left: `${(t / (timelineDuration || 1)) * 100}%` }}
          >
            {fmtTime(t)}
          </span>
        ))}
      </div>

      {/* clip track (click to seek) */}
      <div
        ref={trackRef}
        onClick={seekFromEvent}
        className="relative flex h-24 cursor-pointer items-stretch gap-[2px]"
      >
        {clips.length === 0 && (
          <div className="flex w-full items-center justify-center text-[11px] uppercase tracking-[0.15em] text-coal/30">
            timeline empty
          </div>
        )}
        {clips.map((c, i) => {
          const widthPct =
            timelineDuration > 0 ? (c.duration_s / timelineDuration) * 100 : 0;
          const peaks = clipPeaks(waveform, c.src_start_s, c.src_end_s, sourceDuration);
          return (
            <div
              key={c.id}
              className="relative flex min-w-[3px] flex-col overflow-hidden border border-coal bg-flame/15"
              style={{ width: `${widthPct}%` }}
              data-clip-id={c.id}
              title={`clip ${i + 1}: ${fmtTime(c.src_start_s, true)}–${fmtTime(
                c.src_end_s,
                true,
              )}`}
            >
              {/* waveform */}
              <div className="flex h-16 items-center gap-[1px] px-1 pt-1">
                {peaks.map((p, j) => (
                  <div
                    key={j}
                    className="flex-1 rounded-sm bg-flame"
                    style={{ height: `${Math.max(4, p * 100)}%` }}
                  />
                ))}
              </div>
              {/* label */}
              <div className="truncate px-1.5 pb-1 text-[10px] tabular-nums text-coal/60">
                {fmtTime(c.src_start_s)}–{fmtTime(c.src_end_s)}
              </div>
            </div>
          );
        })}

        {/* playhead */}
        <div
          className="pointer-events-none absolute top-0 z-10 h-full w-[2px] bg-coal"
          style={{ left: `${playheadPct}%` }}
        >
          <div className="absolute -left-[5px] -top-1 h-3 w-3 rotate-45 bg-coal" />
        </div>
      </div>

      {/* captions lane */}
      <div className="mt-2">
        <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-coal/40">
          Captions
        </div>
        <div className="relative flex h-7 items-stretch gap-[2px]">
          {clips.map((c) => {
            const widthPct =
              timelineDuration > 0 ? (c.duration_s / timelineDuration) * 100 : 0;
            return (
              <div
                key={c.id}
                className={`flex items-center justify-center overflow-hidden border px-1 text-[10px] ${
                  c.caption_text
                    ? "border-[#1f8a57]/50 bg-[#1f8a57]/15 text-[#1f8a57]"
                    : "border-coal/30 bg-paper text-coal/25"
                }`}
                style={{ width: `${widthPct}%` }}
                title={c.caption_text ?? "no caption"}
              >
                <span className="truncate">{c.caption_text ?? "—"}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
