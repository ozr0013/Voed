import { useState } from "react";
import { Link } from "react-router-dom";

/* Four-point sparkle ornament that sits on panel corners (Cimento signature). */
function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
    </svg>
  );
}

/* Bordered box with a sparkle pinned to each corner. */
function Framed({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const corners = [
    "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
    "right-0 top-0 translate-x-1/2 -translate-y-1/2",
    "left-0 bottom-0 -translate-x-1/2 translate-y-1/2",
    "right-0 bottom-0 translate-x-1/2 translate-y-1/2",
  ];
  return (
    <div className={`relative border border-coal ${className}`}>
      {corners.map((pos) => (
        <Sparkle
          key={pos}
          className={`pointer-events-none absolute z-10 h-3 w-3 text-coal ${pos}`}
        />
      ))}
      {children}
    </div>
  );
}

const FEATURES = [
  {
    n: "01",
    title: "100% Local",
    body: "Gemma, Whisper, Piper & ffmpeg all run on this machine. No cloud, no API keys, no telemetry — it works with the internet unplugged.",
  },
  {
    n: "02",
    title: "Sees Your Screen",
    body: "A multimodal agent reads a live screenshot of your timeline before every edit, so it acts on what is actually there.",
  },
  {
    n: "03",
    title: "Speaks Back",
    body: "Every change is re-checked, confirmed out loud, and marked with a checkmark you can verify. No silent edits.",
  },
];

/* --- environment detection (client-side only) --- */
const IS_BROWSER = typeof window !== "undefined";
// The public site is served from a real domain; a local install runs on
// localhost. On localhost the user already has a backend, so we point them at
// sign-in; on the public site we point them at the installer.
const IS_LOCAL =
  IS_BROWSER && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
const ORIGIN = IS_BROWSER ? window.location.origin : "https://voed.vercel.app";

type OS = "windows" | "mac";
function detectOS(): OS {
  if (!IS_BROWSER) return "windows";
  const ua = `${navigator.userAgent} ${navigator.platform}`.toLowerCase();
  return /mac|iphone|ipad|ipod/.test(ua) ? "mac" : "windows";
}

const INSTALL = {
  windows: {
    label: "Windows",
    shell: "PowerShell",
    cmd: `irm ${ORIGIN}/install.ps1 | iex`,
    script: "/install.ps1",
  },
  mac: {
    label: "macOS",
    shell: "Terminal",
    cmd: `curl -fsSL ${ORIGIN}/install.sh | bash`,
    script: "/install.sh",
  },
} as const;

/* One-line install command with copy + raw-script download. */
function InstallSection() {
  const [os, setOs] = useState<OS>(detectOS());
  const [copied, setCopied] = useState(false);
  const active = INSTALL[os];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(active.cmd);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the command is still selectable on screen */
    }
  };

  return (
    <section id="install" className="border-x border-b border-coal px-5 py-12 sm:px-10 sm:py-14">
      <div className="mb-6 flex items-center gap-3">
        <Sparkle className="h-4 w-4 text-flame" />
        <h2 className="font-display text-2xl font-black uppercase tracking-tight sm:text-3xl">
          Install Voed
        </h2>
      </div>
      <p className="mb-7 max-w-2xl text-[13px] leading-relaxed text-coal/65">
        One command sets up everything — ffmpeg, Ollama, the AI models, and the
        app — and launches Voed on your machine. It runs entirely locally; you
        only need to do this once.
      </p>

      {/* OS switch */}
      <div className="mb-5 inline-flex border border-coal">
        {(Object.keys(INSTALL) as OS[]).map((key) => (
          <button
            key={key}
            onClick={() => setOs(key)}
            className={`px-5 py-2 text-xs font-bold uppercase tracking-widest transition-colors ${
              os === key ? "bg-coal text-paper" : "bg-paper text-coal hover:bg-paper2"
            }`}
          >
            {INSTALL[key].label}
          </button>
        ))}
      </div>

      {/* command block */}
      <Framed className="bg-coal">
        <div className="flex items-center justify-between gap-4 px-4 py-2">
          <span className="text-[10px] uppercase tracking-[0.2em] text-paper/50">
            Paste into {active.shell}
          </span>
          <button
            onClick={copy}
            className="border border-paper/30 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-paper transition-colors hover:bg-paper hover:text-coal"
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <pre className="overflow-x-auto border-t border-paper/15 px-4 py-4 text-left text-[13px] leading-relaxed text-flame">
          <code>{active.cmd}</code>
        </pre>
      </Framed>

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] uppercase tracking-[0.15em] text-coal/50">
        <a href={active.script} download className="underline underline-offset-4 hover:text-coal">
          Or download the {active.label} script
        </a>
        <span className="hidden sm:inline">·</span>
        <span>Already installed?</span>
        <a
          href="http://localhost:5173"
          className="border border-coal bg-paper px-3 py-1 font-bold text-coal shadow-hard transition-transform hover:-translate-x-[1px] hover:-translate-y-[1px]"
        >
          Launch app →
        </a>
      </div>
    </section>
  );
}

export default function Landing() {
  return (
    <div className="relative min-h-screen cursor-default select-none bg-paper font-mono text-coal">
      {/* matte grain overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-50 opacity-[0.05] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      {/* announcement bar */}
      <div className="flex items-center justify-center gap-3 bg-flame px-4 py-2 text-center text-[11px] font-medium uppercase tracking-[0.12em] text-coal sm:text-xs">
        <Sparkle className="h-3 w-3 shrink-0" />
        <span>
          Runs 100% on your machine — nothing ever touches the cloud
        </span>
        <a href="#install" className="hidden font-bold underline underline-offset-4 hover:opacity-70 sm:inline">
          Install →
        </a>
      </div>

      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        {/* header */}
        <header className="flex items-center justify-between border-b border-coal py-5">
          <Link to="/" className="flex items-center gap-2">
            <img src="/voed-mark.svg" alt="Voed" className="h-16 w-auto" />
            <span className="text-2xl font-black lowercase tracking-tight text-coal">voed</span>
          </Link>
          <Link
            to="/signin"
            className="border border-coal bg-paper px-4 py-2 text-xs font-bold uppercase tracking-widest shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f]"
          >
            Sign in
          </Link>
        </header>

        {/* powered-by strip */}
        <Framed className="rise mt-0 flex flex-wrap items-center gap-x-8 gap-y-2 border-t-0 px-5 py-4 sm:px-8" >
          <span className="text-[11px] uppercase tracking-[0.2em] text-coal/50">
            Powered by
          </span>
          {["Gemma", "Whisper", "Piper", "ffmpeg"].map((t) => (
            <span key={t} className="text-sm font-bold uppercase tracking-wide text-coal/70">
              {t}
            </span>
          ))}
        </Framed>

        {/* hero */}
        <section className="relative border-x border-b border-coal px-5 pb-16 pt-14 sm:px-10 sm:pt-20">
          <div
            className="rise mb-7 inline-flex items-center gap-2 border border-coal bg-paper2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em]"
            style={{ animationDelay: "60ms" }}
          >
            <Sparkle className="h-3 w-3 text-flame" />
            The Voed way
          </div>

          <h1
            className="rise font-display text-[15vw] font-black uppercase leading-[0.86] tracking-tight sm:text-[104px]"
            style={{ animationDelay: "120ms" }}
          >
            Edit video
            <br />
            by <span className="text-flame">talking.</span>
          </h1>

          <p
            className="rise mt-7 max-w-2xl text-sm leading-relaxed text-coal/70 sm:text-base"
            style={{ animationDelay: "220ms" }}
          >
            Upload a clip, hold the mic, and say{" "}
            <span className="bg-coal px-1.5 py-0.5 font-bold text-paper">
              "cut the first ten seconds"
            </span>{" "}
            or{" "}
            <span className="bg-coal px-1.5 py-0.5 font-bold text-paper">
              "remove all the silences."
            </span>{" "}
            A local AI agent watches your editor, makes the edit, and shows its work.
          </p>

          <div
            className="rise mt-9 flex flex-wrap gap-4"
            style={{ animationDelay: "320ms" }}
          >
            {/* On localhost the user has a backend → sign up. On the public
                site → jump to the installer. */}
            {IS_LOCAL ? (
              <Link
                to="/signup"
                className="group flex items-center gap-2 bg-flame px-7 py-3.5 text-sm font-bold uppercase tracking-widest text-coal shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f]"
              >
                Get started
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </Link>
            ) : (
              <a
                href="#install"
                className="group flex items-center gap-2 bg-flame px-7 py-3.5 text-sm font-bold uppercase tracking-widest text-coal shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f]"
              >
                Install Voed
                <span className="transition-transform group-hover:translate-x-1">↓</span>
              </a>
            )}
            <Link
              to="/signin"
              className="flex items-center border border-coal bg-paper px-7 py-3.5 text-sm font-bold uppercase tracking-widest text-coal transition-colors hover:bg-paper2"
            >
              Sign in
            </Link>
          </div>
        </section>

        {/* install / download front door */}
        <InstallSection />

        {/* feature cards */}
        <section className="grid gap-0 border-x border-b border-coal sm:grid-cols-3">
          {FEATURES.map((f, i) => (
            <div
              key={f.n}
              className={`rise relative p-6 sm:p-7 ${
                i > 0 ? "border-t border-coal sm:border-l sm:border-t-0" : ""
              }`}
              style={{ animationDelay: `${420 + i * 90}ms` }}
            >
              <div className="mb-6 flex items-center justify-between">
                <span className="font-display text-2xl font-black text-flame">{f.n}</span>
                <Sparkle className="h-3.5 w-3.5 text-coal/40" />
              </div>
              <h3 className="font-display text-xl font-bold uppercase tracking-tight">
                {f.title}
              </h3>
              <p className="mt-3 text-[13px] leading-relaxed text-coal/65">{f.body}</p>
            </div>
          ))}
        </section>

        {/* footer */}
        <footer className="flex flex-wrap items-center justify-between gap-3 py-6 text-[11px] uppercase tracking-[0.15em] text-coal/50">
          <div className="flex items-center gap-2">
            <Sparkle className="h-3 w-3 text-flame" />
            Voed — voice-to-action video editing
          </div>
          <div>No cloud · No keys · No telemetry</div>
        </footer>
      </div>
    </div>
  );
}
