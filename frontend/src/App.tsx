import { Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Editor from "./pages/Editor";

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={<Navigate to="/dashboard" replace />}
      />
      <Route
        path="/dashboard"
        element={<Dashboard />}
      />
      <Route
        path="/editor/:id"
        element={<Editor />}
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
