import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import AuthForm from "./pages/AuthForm";
import Dashboard from "./pages/Dashboard";
import Editor from "./pages/Editor";
import Landing from "./pages/Landing";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="p-8 text-sm text-white/50">Loading…</div>;
  }
  return user ? children : <Navigate to="/signin" replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route
        path="/"
        element={loading ? null : user ? <Navigate to="/dashboard" replace /> : <Landing />}
      />
      <Route path="/signin" element={<AuthForm mode="signin" />} />
      <Route path="/signup" element={<AuthForm mode="signup" />} />
      <Route
        path="/dashboard"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/editor/:id"
        element={
          <RequireAuth>
            <Editor />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
