import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center gap-10 px-6 py-16">
      <div>
        <h1 className="text-5xl font-semibold tracking-tight">VoiceCut</h1>
        <p className="mt-4 max-w-xl text-lg text-white/70">
          Edit video by talking. Upload a clip, hold the mic, and say
          <span className="text-white"> “cut the first ten seconds” </span>
          or <span className="text-white">“remove all the silences.”</span> A
          local AI agent watches your editor, makes the edit, and shows its work.
        </p>
      </div>

      <div className="flex gap-3">
        <Link
          to="/signup"
          className="rounded-lg bg-accent px-5 py-3 font-medium text-white hover:brightness-110"
        >
          Get started
        </Link>
        <Link
          to="/signin"
          className="rounded-lg border border-edge px-5 py-3 font-medium hover:bg-panel"
        >
          Sign in
        </Link>
      </div>

      <ul className="grid gap-3 text-sm text-white/60 sm:grid-cols-3">
        <li className="rounded-lg border border-edge bg-panel p-4">
          <div className="font-medium text-white">100% local</div>
          Gemma, Whisper, Piper &amp; ffmpeg run on this machine. Nothing is
          uploaded to the cloud.
        </li>
        <li className="rounded-lg border border-edge bg-panel p-4">
          <div className="font-medium text-white">Sees your screen</div>
          The agent reads a live screenshot of the timeline before every edit.
        </li>
        <li className="rounded-lg border border-edge bg-panel p-4">
          <div className="font-medium text-white">Speaks back</div>
          Every change is confirmed out loud and with a checkmark you can verify.
        </li>
      </ul>
    </div>
  );
}
