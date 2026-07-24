import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ModelCatalogEntry, type ModelsReport } from "../lib/api";

type Quality = "fast" | "balanced" | "best";
type Platform = "standard" | "mlx";

const QUALITY_OPTIONS: { id: Quality; label: string; hint: string }[] = [
  { id: "fast", label: "Fast", hint: "Laptops · quick tests" },
  { id: "balanced", label: "Balanced", hint: "Recommended default" },
  { id: "best", label: "Best", hint: "Max quality · more RAM" },
];

const PICK_TAGS: Record<Platform, Record<Quality, string>> = {
  standard: {
    fast: "gemma4:e4b",
    balanced: "gemma4:12b",
    best: "gemma4:31b",
  },
  mlx: {
    fast: "gemma4:e4b-mlx",
    balanced: "gemma4:12b-mlx",
    best: "gemma4:31b-mlx",
  },
};

const ADVANCED_TAGS = new Set([
  "gemma4:e2b",
  "gemma4:26b",
  "gemma4:e2b-mlx",
  "gemma4:26b-mlx",
]);

const IS_MAC =
  typeof navigator !== "undefined" &&
  (/Mac|iPhone|iPad|iPod/.test(navigator.platform) ||
    /Mac OS|iPhone|iPad/.test(navigator.userAgent));

function pullProgress(event: { completed?: number; total?: number; status?: string }): number | null {
  if (event.completed != null && event.total != null && event.total > 0) {
    return Math.min(1, event.completed / event.total);
  }
  if (event.status === "success") return 1;
  return null;
}

function tagToPick(tag: string): { quality: Quality; platform: Platform } | null {
  for (const platform of ["standard", "mlx"] as const) {
    for (const quality of ["fast", "balanced", "best"] as const) {
      if (PICK_TAGS[platform][quality] === tag) return { quality, platform };
    }
  }
  return null;
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
  disabled,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { id: T; label: string }[];
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex border border-coal">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.id)}
          className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest transition-colors disabled:opacity-40 ${
            value === opt.id ? "bg-coal text-paper" : "bg-paper text-coal hover:bg-paper2"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function ModelRow({
  entry,
  compact,
  pulling,
  busy,
  ollamaUp,
  onDownload,
  onSelect,
  onRemove,
}: {
  entry: ModelCatalogEntry;
  compact?: boolean;
  pulling: string | null;
  busy: string | null;
  ollamaUp: boolean;
  onDownload: (e: ModelCatalogEntry) => void;
  onSelect: (tag: string) => void;
  onRemove: (tag: string) => void;
}) {
  return (
    <li
      className={`flex flex-wrap items-center justify-between gap-2 border px-3 py-2 ${
        entry.active ? "border-flame bg-flame/5" : "border-coal/25 bg-paper2/40"
      }`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold uppercase tracking-tight">{entry.label}</span>
          {entry.active && (
            <span className="text-[10px] font-bold uppercase tracking-widest text-flame">Active</span>
          )}
        </div>
        <div className="text-xs text-coal/45">
          {entry.size_gb} GB · {entry.context}
          {!compact && ` · ${entry.modalities}`}
        </div>
      </div>
      <div className="flex shrink-0 gap-2">
        {!entry.installed && (
          <button
            type="button"
            disabled={!ollamaUp || pulling != null}
            onClick={() => onDownload(entry)}
            className="border border-coal bg-flame px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest disabled:opacity-40"
          >
            Download
          </button>
        )}
        {entry.installed && !entry.active && (
          <>
            <button
              type="button"
              disabled={busy != null}
              onClick={() => onSelect(entry.tag)}
              className="border border-coal bg-paper px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest disabled:opacity-40"
            >
              {busy === entry.tag ? "…" : "Use"}
            </button>
            <button
              type="button"
              disabled={busy != null}
              onClick={() => onRemove(entry.tag)}
              className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-coal/40 hover:text-flame disabled:opacity-40"
            >
              Remove
            </button>
          </>
        )}
      </div>
    </li>
  );
}

export default function ModelManager() {
  const [report, setReport] = useState<ModelsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulling, setPulling] = useState<string | null>(null);
  const [pullPct, setPullPct] = useState<number | null>(null);
  const [pullStatus, setPullStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [quality, setQuality] = useState<Quality>("balanced");
  const [platform, setPlatform] = useState<Platform>("standard");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [syncedFromActive, setSyncedFromActive] = useState(false);

  const refresh = useCallback(() => {
    api
      .models()
      .then((r) => {
        setReport(r);
        setError(null);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!report || syncedFromActive) return;
    const pick = tagToPick(report.active);
    if (pick) {
      setQuality(pick.quality);
      setPlatform(pick.platform);
    } else if (ADVANCED_TAGS.has(report.active)) {
      setAdvancedOpen(true);
    }
    setSyncedFromActive(true);
  }, [report, syncedFromActive]);

  const catalogByTag = useMemo(() => {
    const map = new Map<string, ModelCatalogEntry>();
    report?.catalog.forEach((e) => map.set(e.tag, e));
    return map;
  }, [report]);

  const selectedTag = PICK_TAGS[platform][quality];
  const selected = catalogByTag.get(selectedTag);
  const advancedEntries =
    report?.catalog.filter((e) => ADVANCED_TAGS.has(e.tag)) ?? [];

  const activeEntry = catalogByTag.get(report?.active ?? "");

  const download = async (entry: ModelCatalogEntry) => {
    setPulling(entry.tag);
    setPullPct(null);
    setPullStatus("Starting download…");
    setError(null);
    try {
      await api.pullModel(entry.tag, (ev) => {
        setPullStatus(ev.status ?? "Downloading…");
        const pct = pullProgress(ev);
        if (pct != null) setPullPct(pct);
      });
      refresh();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setPulling(null);
      setPullPct(null);
      setPullStatus(null);
    }
  };

  const select = async (tag: string) => {
    setBusy(tag);
    setError(null);
    try {
      await api.selectModel(tag);
      refresh();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (tag: string) => {
    if (!confirm(`Remove ${tag} from this machine?`)) return;
    setBusy(tag);
    setError(null);
    try {
      await api.deleteModel(tag);
      refresh();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  if (!report) {
    return (
      <div className="border border-coal bg-paper px-4 py-3 text-sm text-coal/50">
        Loading Gemma 4 models…
      </div>
    );
  }

  const qualityHint = QUALITY_OPTIONS.find((q) => q.id === quality)?.hint ?? "";

  return (
    <div className="border border-coal bg-paper p-4 shadow-hard">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-black uppercase tracking-tight">AI model</h2>
          <p className="mt-1 text-xs text-coal/50">Local Gemma 4 used by the editing agent.</p>
        </div>
        {activeEntry && (
          <div className="text-right text-xs">
            <div className="uppercase tracking-widest text-coal/45">Active</div>
            <div className="font-mono text-coal">{report.active}</div>
            <div className={activeEntry.installed ? "text-coal/50" : "text-flame"}>
              {activeEntry.installed ? "Ready" : "Not downloaded"}
            </div>
          </div>
        )}
      </div>

      {!report.ollama_up && (
        <div className="mb-4 border border-flame/40 bg-flame/10 px-3 py-2 text-sm text-coal">
          Ollama is not running. Start Ollama, then refresh.
        </div>
      )}

      {error && (
        <div className="mb-4 border border-flame/40 bg-flame/10 px-3 py-2 text-sm text-coal">
          {error}
        </div>
      )}

      {pulling && (
        <div className="mb-4 border border-coal/30 bg-paper2 px-3 py-3">
          <div className="mb-2 text-xs uppercase tracking-widest text-coal/50">
            Downloading {pulling}
          </div>
          <div className="h-2 overflow-hidden border border-coal/20 bg-paper">
            <div
              className="h-full bg-flame transition-all duration-300"
              style={{ width: `${Math.round((pullPct ?? 0.08) * 100)}%` }}
            />
          </div>
          <div className="mt-2 text-xs text-coal/45">
            {pullStatus}
            {pullPct != null ? ` · ${Math.round(pullPct * 100)}%` : ""}
          </div>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-coal/45">
            Quality
          </div>
          <Segmented
            value={quality}
            onChange={setQuality}
            options={QUALITY_OPTIONS.map((q) => ({ id: q.id, label: q.label }))}
            disabled={pulling != null}
          />
          <p className="mt-2 text-xs text-coal/40">{qualityHint}</p>
        </div>

        {IS_MAC && (
          <div>
            <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-coal/45">
              Platform
            </div>
            <Segmented
              value={platform}
              onChange={setPlatform}
              options={[
                { id: "standard", label: "Standard" },
                { id: "mlx", label: "Apple Silicon" },
              ]}
              disabled={pulling != null}
            />
          </div>
        )}

        {selected && (
          <div className="border border-coal/25 bg-paper2/40 px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-display text-sm font-bold uppercase tracking-tight">
                  {selected.label}
                </div>
                <div className="mt-1 text-xs text-coal/45">
                  {selected.size_gb} GB · {selected.context} context
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-coal/35">{selected.tag}</div>
              </div>
              <div>
                {selected.active ? (
                  <span className="text-[10px] font-bold uppercase tracking-widest text-flame">
                    In use
                  </span>
                ) : selected.installed ? (
                  <button
                    type="button"
                    disabled={busy != null || pulling != null}
                    onClick={() => select(selected.tag)}
                    className="border border-coal bg-flame px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-coal disabled:opacity-40"
                  >
                    {busy === selected.tag ? "…" : "Use this model"}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={!report.ollama_up || pulling != null}
                    onClick={() => download(selected)}
                    className="border border-coal bg-flame px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-coal disabled:opacity-40"
                  >
                    Download
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div>
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            className="flex w-full items-center justify-between border border-coal/25 px-3 py-2 text-left text-[11px] font-bold uppercase tracking-[0.18em] text-coal/45 hover:bg-paper2"
          >
            <span>Advanced models</span>
            <span>{advancedOpen ? "−" : "+"}</span>
          </button>
          {advancedOpen && (
            <ul className="mt-2 space-y-1.5">
              {advancedEntries.map((entry) => (
                <ModelRow
                  key={entry.tag}
                  entry={entry}
                  compact
                  pulling={pulling}
                  busy={busy}
                  ollamaUp={report.ollama_up}
                  onDownload={download}
                  onSelect={select}
                  onRemove={remove}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
