import { useRef, useState } from "react";
import { api } from "../lib/api";

const MAX_FILE_SIZE_MB = 300;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const VALID_VIDEO_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".avi"];

function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
    </svg>
  );
}

export default function UploadDropzone({ onDone }: { onDone: (projectId: number) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<{ name: string; size: string } | null>(null);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const validateFile = (file: File): string | null => {
    // Check file type
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const isValidType = file.type.startsWith("video/") || VALID_VIDEO_EXTENSIONS.includes(ext);
    if (!isValidType) {
      return `Invalid file format. Please upload a video file (${VALID_VIDEO_EXTENSIONS.join(", ").toUpperCase()})`;
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `File is too large (${formatBytes(file.size)}). Max allowed size is ${MAX_FILE_SIZE_MB}MB.`;
    }

    return null;
  };

  const start = async (file: File) => {
    setError(null);
    setFileDetails(null);

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setFileDetails({ name: file.name, size: formatBytes(file.size) });
    setProgress(0);
    try {
      const name = file.name.replace(/\.[^.]+$/, "");
      const project = await api.uploadVideo(name, file, setProgress);
      onDone(project.id);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setProgress(null);
      setFileDetails(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) start(file);
  };

  const corners = [
    "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
    "right-0 top-0 translate-x-1/2 -translate-y-1/2",
    "left-0 bottom-0 -translate-x-1/2 translate-y-1/2",
    "right-0 bottom-0 translate-x-1/2 translate-y-1/2",
  ];

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => progress === null && inputRef.current?.click()}
      className={`group relative flex cursor-pointer flex-col items-center justify-center gap-3 border border-dashed p-10 text-center font-mono transition-all hover:bg-panel2 ${
        dragging ? "border-accent bg-accent/5" : "border-coal/40 bg-panel hover:border-accent"
      }`}
    >
      {corners.map((pos) => (
        <Sparkle
          key={pos}
          className={`pointer-events-none absolute z-10 h-2.5 w-2.5 text-coal transition-all group-hover:scale-110 ${pos}`}
        />
      ))}
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && start(e.target.files[0])}
      />
      {progress === null ? (
        <>
          <div className="flex h-10 w-10 items-center justify-center border border-coal/50 bg-paper/5 text-coal transition-all group-hover:-translate-y-0.5 group-hover:border-accent group-hover:text-accent">
            <span className="text-lg">↑</span>
          </div>
          <div className="font-display text-base font-black uppercase tracking-tight text-coal">
            Drop a video to compile a project
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-coal/40">
            Click to browse — Max {MAX_FILE_SIZE_MB}MB — MP4, MOV, MKV, WEBM
          </div>
        </>
      ) : (
        <div className="w-full max-w-md p-4">
          <div className="mb-1 text-xs font-bold uppercase tracking-widest text-coal">
            Uploading Pipeline
          </div>
          <div className="mb-3 truncate text-[10px] uppercase tracking-wider text-coal/50">
            {fileDetails?.name} ({fileDetails?.size})
          </div>
          <div className="h-4 w-full overflow-hidden border border-coal bg-panel">
            <div
              className="h-full bg-accent transition-all duration-150"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className="mt-2 text-right text-[10px] font-bold tracking-widest text-accent">
            {Math.round(progress * 100)}% COMPLETE
          </div>
        </div>
      )}
      {error && (
        <div className="mt-1 border border-accent bg-accent/5 px-3.5 py-2 text-xs font-semibold text-accent shadow-hard animate-shake">
          ERROR: {error}
        </div>
      )}
    </div>
  );
}
