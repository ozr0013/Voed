import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

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

  return (
    <div className="mx-auto flex min-h-full max-w-sm flex-col justify-center gap-6 px-6 py-16">
      <div>
        <Link to="/" className="text-sm text-white/50 hover:text-white">
          ← VoiceCut
        </Link>
        <h1 className="mt-3 text-2xl font-semibold">
          {isSignup ? "Create your account" : "Welcome back"}
        </h1>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="text-sm text-white/70">
          Email
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-edge bg-panel px-3 py-2 outline-none focus:border-accent"
          />
        </label>
        <label className="text-sm text-white/70">
          Password
          <input
            type="password"
            required
            minLength={6}
            autoComplete={isSignup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-edge bg-panel px-3 py-2 outline-none focus:border-accent"
          />
        </label>

        {error && <div className="text-sm text-bad">{error}</div>}

        <button
          type="submit"
          disabled={busy}
          className="mt-2 rounded-lg bg-accent px-4 py-2.5 font-medium text-white hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "…" : isSignup ? "Sign up" : "Sign in"}
        </button>
      </form>

      <p className="text-sm text-white/50">
        {isSignup ? (
          <>
            Already have an account?{" "}
            <Link to="/signin" className="text-accent hover:underline">
              Sign in
            </Link>
          </>
        ) : (
          <>
            New here?{" "}
            <Link to="/signup" className="text-accent hover:underline">
              Create an account
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
