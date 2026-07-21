import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeBlob } from "../lib/voice";

// Push-to-talk: hold the button (or the spacebar) to record, release to
// transcribe. Everything runs locally via /stt. Calls onTranscript with the
// recognized text.
interface Props {
  disabled?: boolean;
  hint?: string;
  onTranscript: (text: string) => void;
  onError?: (msg: string) => void;
}

type State = "idle" | "recording" | "transcribing";

export default function MicButton({ disabled = false, hint, onTranscript, onError }: Props) {
  const [state, setState] = useState<State>("idle");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const activeRef = useRef(false); // guards against double start/stop
  const stopRequestedRef = useRef(false); // release that arrived before the recorder was ready

  const start = useCallback(async () => {
    if (disabled || activeRef.current) return;
    activeRef.current = true;
    stopRequestedRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        if (blob.size < 1200) {
          setState("idle");
          activeRef.current = false;
          onError?.("Too short — hold the button (or Space) while you speak, then release.");
          return; // too short to be speech
        }
        setState("transcribing");
        try {
          const text = await transcribeBlob(blob);
          if (text.trim()) onTranscript(text.trim());
          else onError?.("I didn't catch that — try again.");
        } catch (e) {
          onError?.(String((e as Error).message ?? e));
        } finally {
          setState("idle");
          activeRef.current = false;
        }
      };
      recorderRef.current = mr;
      mr.start();
      setState("recording");
      // If the user already released during getUserMedia, stop now so the
      // release isn't lost (which would leave us recording forever).
      if (stopRequestedRef.current) mr.stop();
    } catch {
      activeRef.current = false;
      setState("idle");
      onError?.("Microphone unavailable — check browser permissions.");
    }
  }, [disabled, onTranscript, onError]);

  const stop = useCallback(() => {
    stopRequestedRef.current = true; // honored by start() if the recorder isn't ready yet
    const mr = recorderRef.current;
    if (mr && mr.state === "recording") mr.stop();
  }, []);

  // Keep the latest start/stop for the global spacebar listener.
  const startRef = useRef(start);
  const stopRef = useRef(stop);
  startRef.current = start;
  stopRef.current = stop;

  useEffect(() => {
    const isTyping = () => {
      const el = document.activeElement;
      return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
    };
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space" && !e.repeat && !isTyping()) {
        e.preventDefault();
        startRef.current();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space" && !isTyping()) {
        e.preventDefault();
        stopRef.current();
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  const recording = state === "recording";
  const label = disabled
    ? hint ?? "Unavailable"
    : recording
      ? "Listening… release to send"
      : state === "transcribing"
        ? "Transcribing…"
        : hint ?? "Hold to talk  ·  or hold Space";

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        disabled={disabled || state === "transcribing"}
        onPointerDown={(e) => {
          e.preventDefault();
          start();
        }}
        onPointerUp={(e) => {
          e.preventDefault();
          stop();
        }}
        onPointerLeave={() => recording && stop()}
        className={`flex h-16 w-16 select-none items-center justify-center rounded-full border-2 text-2xl transition ${
          disabled
            ? "cursor-not-allowed border-coal/30 bg-paper2 text-coal/30"
            : recording
              ? "scale-110 animate-pulse border-coal bg-coal text-paper shadow-hard"
              : "border-coal bg-flame text-coal shadow-hard hover:-translate-x-[1px] hover:-translate-y-[1px] active:scale-95"
        }`}
        aria-label="Push to talk"
      >
        {state === "transcribing" ? "…" : "🎙"}
      </button>
      <span className="text-[11px] uppercase tracking-[0.15em] text-coal/50">{label}</span>
    </div>
  );
}
