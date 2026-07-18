import { forwardRef, useState } from "react";
import { fmtTime } from "../lib/format";

interface Props {
  src: string | null;
  onTime: (t: number) => void;
  onDuration: (d: number) => void;
}

// HTML5 preview player (plays the 720p proxy / current rendered version).
// The <video> element is exposed via ref so the timeline can seek it and the
// agent can auto-play the edited region after a task completes.
const VideoPreview = forwardRef<HTMLVideoElement, Props>(function VideoPreview(
  { src, onTime, onDuration },
  ref,
) {
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0);
  const [dur, setDur] = useState(0);

  const toggle = () => {
    const v = (ref as React.RefObject<HTMLVideoElement>).current;
    if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  };

  return (
    <div className="relative flex-1 overflow-hidden rounded-xl border border-edge bg-black">
      {src ? (
        <video
          ref={ref}
          src={src}
          className="h-full w-full object-contain"
          onTimeUpdate={(e) => {
            const t = e.currentTarget.currentTime;
            setCur(t);
            onTime(t);
          }}
          onLoadedMetadata={(e) => {
            const d = e.currentTarget.duration;
            setDur(d);
            onDuration(d);
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onClick={toggle}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-white/40">
          Preview not ready…
        </div>
      )}

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-3 bg-gradient-to-t from-black/70 to-transparent px-4 py-3 text-sm">
        <button
          onClick={toggle}
          className="pointer-events-auto rounded-md bg-white/10 px-3 py-1 hover:bg-white/20"
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="tabular-nums text-white/70">
          {fmtTime(cur, true)} / {fmtTime(dur, true)}
        </span>
      </div>
    </div>
  );
});

export default VideoPreview;
