import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

/* Four-point sparkle ornament (matches the landing aesthetic). */
function Sparkle({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
    </svg>
  );
}

const CORNERS = [
  "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
  "right-0 top-0 translate-x-1/2 -translate-y-1/2",
  "left-0 bottom-0 -translate-x-1/2 translate-y-1/2",
  "right-0 bottom-0 translate-x-1/2 translate-y-1/2",
];

export default function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const { login, signup } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (isSignup) await signup(email, password);
      else await login(email, password);
      nav("/dashboard");
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setBusy(false);
    }
  };

  const inputCls =
    "mt-1.5 w-full border border-coal bg-paper2 px-3 py-2.5 font-mono text-sm text-coal outline-none transition-colors placeholder:text-coal/30 focus:border-flame focus:bg-paper";

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-paper px-5 py-16 font-mono text-coal">
      {/* matte grain overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-50 opacity-[0.05] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <div className="w-full max-w-md">
        <Link
          to="/"
          className="mb-5 inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-coal/60 transition-colors hover:text-coal"
        >
          ← voicecut
        </Link>

        {/* framed card */}
        <div className="relative border border-coal bg-paper shadow-hard">
          {CORNERS.map((pos) => (
            <Sparkle
              key={pos}
              className={`pointer-events-none absolute z-10 h-3 w-3 text-coal ${pos}`}
            />
          ))}

          <div className="p-7 sm:p-9">
            <div className="mb-5 inline-flex items-center gap-2 border border-coal bg-paper2 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em]">
              <Sparkle className="h-3 w-3 text-flame" />
              {isSignup ? "New account" : "Sign in"}
            </div>

            <h1 className="font-display text-3xl font-black uppercase leading-none tracking-tight sm:text-4xl">
              {isSignup ? (
                <>
                  Create
                  <br />
                  <span className="text-flame">account.</span>
                </>
              ) : (
                <>
                  Welcome
                  <br />
                  <span className="text-flame">back.</span>
                </>
              )}
            </h1>

            <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
              <label className="block">
                <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-coal/60">
                  Email
                </span>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputCls}
                />
              </label>
              <label className="block">
                <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-coal/60">
                  Password
                </span>
                <input
                  type="password"
                  required
                  minLength={6}
                  autoComplete={isSignup ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputCls}
                />
              </label>

              {error && (
                <div className="border border-flame bg-flame/10 px-3 py-2 text-xs font-medium text-flame">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={busy}
                className="group mt-1 flex items-center justify-center gap-2 bg-flame px-5 py-3 text-sm font-bold uppercase tracking-widest text-coal shadow-hard transition-transform hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[6px_6px_0_0_#17150f] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-x-0 disabled:hover:translate-y-0"
              >
                {busy ? "…" : isSignup ? "Create account" : "Sign in"}
                {!busy && <span className="transition-transform group-hover:translate-x-1">→</span>}
              </button>
            </form>
          </div>
        </div>

        <p className="mt-5 text-center text-xs uppercase tracking-[0.12em] text-coal/60">
          {isSignup ? (
            <>
              Already have an account?{" "}
              <Link to="/signin" className="font-bold text-coal underline underline-offset-4 hover:text-flame">
                Sign in
              </Link>
            </>
          ) : (
            <>
              New here?{" "}
              <Link to="/signup" className="font-bold text-coal underline underline-offset-4 hover:text-flame">
                Create an account
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
