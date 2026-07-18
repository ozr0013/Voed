import { Route, Routes } from "react-router-dom";
import SystemStatus from "./components/SystemStatus";

// Milestone 1: a single scaffold screen that proves the FastAPI <-> Vite wiring
// and the local-service health checks work. Real routes (Landing, SignIn,
// SignUp, Dashboard, Editor) land in later milestones.
function Scaffold() {
  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">VoiceCut</h1>
        <p className="mt-1 text-white/60">
          Edit video by talking. 100% local — Gemma, Whisper, Piper, ffmpeg on
          this machine. Nothing leaves your computer.
        </p>
      </header>
      <SystemStatus />
      <p className="text-xs text-white/30">
        Scaffold build (milestone 1). Auth, upload, editor, and the voice agent
        arrive in the next milestones.
      </p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="*" element={<Scaffold />} />
    </Routes>
  );
}
