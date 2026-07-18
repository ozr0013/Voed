import { useRef, useState } from "react";
import { api } from "../lib/api";

// Drag-and-drop (or click) video upload with a progress bar. Calls onDone with
// the new project id once the server accepts the file for processing.
export default function UploadDropzone({ onDone }: { onDone: (projectId: number) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async (file: File) => {
    setError(null);
    setProgress(0);
    try {
      const name = file.name.replace(/\.[^.]+$/, "");
      const project = await api.uploadVideo(name, file, setProgress);
      onDone(project.id);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setProgress(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) start(file);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => progress === null && inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed p-12 text-center font-mono transition ${
        dragging ? "border-flame bg-flame/5" : "border-coal/40 bg-paper2 hover:border-flame"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && start(e.target.files[0])}
      />
      {progress === null ? (
        <>
          <div className="font-display text-xl font-black uppercase tracking-tight text-coal">
            Drop a video to start a new project
          </div>
          <div className="text-xs uppercase tracking-[0.15em] text-coal/50">
            or click to browse — MP4, MOV, MKV, WEBM
          </div>
        </>
      ) : (
        <div className="w-full max-w-md">
          <div className="mb-2 text-xs uppercase tracking-widest text-coal/70">
            Uploading… {Math.round(progress * 100)}%
          </div>
          <div className="h-2.5 w-full overflow-hidden border border-coal bg-paper">
            <div
              className="h-full bg-flame transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>
      )}
      {error && (
        <div className="mt-2 border border-flame bg-flame/10 px-3 py-1.5 text-xs font-medium text-flame">
          {error}
        </div>
      )}
    </div>
  );
}
