// Push-to-talk button. Milestone 3 renders it as a visual placeholder; the
// recording pipeline (MediaRecorder -> /stt) and spacebar hold are wired in
// milestone 4.
interface Props {
  disabled?: boolean;
  hint?: string;
}

export default function MicButton({ disabled = true, hint }: Props) {
  return (
    <div className="flex flex-col items-center gap-2">
      <button
        disabled={disabled}
        className={`flex h-16 w-16 items-center justify-center rounded-full border text-2xl transition ${
          disabled
            ? "cursor-not-allowed border-edge bg-panel text-white/30"
            : "border-accent bg-accent text-white hover:brightness-110 active:scale-95"
        }`}
        aria-label="Push to talk"
      >
        🎙
      </button>
      <span className="text-xs text-white/40">{hint ?? "Hold to talk"}</span>
    </div>
  );
}
