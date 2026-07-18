// Browser-side voice helpers: record a command, transcribe it via /stt, and
// speak text via /tts (Piper). All processing happens on the backend/host.

let currentAudio: HTMLAudioElement | null = null;

// Speak text through Piper. Resolves when playback finishes (or fails silently
// so a TTS hiccup never blocks the agent). Interrupts any in-flight speech.
export async function speak(text: string): Promise<void> {
  try {
    stopSpeaking();
    const res = await fetch("/api/tts", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return;
    const url = URL.createObjectURL(await res.blob());
    const audio = new Audio(url);
    currentAudio = audio;
    await new Promise<void>((resolve) => {
      audio.onended = audio.onerror = () => {
        URL.revokeObjectURL(url);
        if (currentAudio === audio) currentAudio = null;
        resolve();
      };
      audio.play().catch(() => resolve());
    });
  } catch {
    /* TTS is best-effort */
  }
}

export function stopSpeaking(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
}

export async function transcribeBlob(blob: Blob): Promise<string> {
  const form = new FormData();
  form.append("audio", blob, "command.webm");
  const res = await fetch("/api/stt", {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? "Transcription failed");
  }
  return (await res.json()).text as string;
}
