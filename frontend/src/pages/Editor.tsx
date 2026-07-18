import { useParams } from "react-router-dom";

// Placeholder — replaced in milestone 3 with the real editor (preview +
// timeline) and later wired to the voice agent.
export default function Editor() {
  const { id } = useParams();
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-xl font-semibold">Editor — project {id}</h1>
      <p className="mt-2 text-white/50">Coming in milestone 3.</p>
    </div>
  );
}
