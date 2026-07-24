"""Curated Gemma 4 tags exposed in the model picker."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelEntry:
    tag: str
    label: str
    size_gb: float
    context: str
    modalities: str
    tier: str
    notes: str = ""


# Local pulls only — cloud tags are intentionally omitted (local-first app).
GEMMA4_CATALOG: tuple[ModelEntry, ...] = (
    ModelEntry(
        tag="gemma4:e2b",
        label="Gemma 4 E2B",
        size_gb=7.2,
        context="128K",
        modalities="Text, Image, Audio",
        tier="edge",
        notes="Lightest edge model; good for quick tests on modest hardware.",
    ),
    ModelEntry(
        tag="gemma4:e4b",
        label="Gemma 4 E4B",
        size_gb=9.6,
        context="128K",
        modalities="Text, Image, Audio",
        tier="edge",
        notes="Default Ollama tag (gemma4:latest); best laptop balance.",
    ),
    ModelEntry(
        tag="gemma4:12b",
        label="Gemma 4 12B",
        size_gb=7.6,
        context="256K",
        modalities="Text, Image",
        tier="workstation",
        notes="Project default; strong reasoning with a 256K context window.",
    ),
    ModelEntry(
        tag="gemma4:26b",
        label="Gemma 4 26B MoE",
        size_gb=18.0,
        context="256K",
        modalities="Text, Image",
        tier="workstation",
        notes="Mixture-of-experts; ~3.8B active params per token.",
    ),
    ModelEntry(
        tag="gemma4:31b",
        label="Gemma 4 31B Dense",
        size_gb=20.0,
        context="256K",
        modalities="Text, Image",
        tier="workstation",
        notes="Highest local quality; needs ~20GB+ disk/RAM headroom.",
    ),
    ModelEntry(
        tag="gemma4:e2b-mlx",
        label="Gemma 4 E2B (MLX)",
        size_gb=6.5,
        context="128K",
        modalities="Text, Image",
        tier="apple-silicon",
        notes="Apple Silicon optimized build.",
    ),
    ModelEntry(
        tag="gemma4:e4b-mlx",
        label="Gemma 4 E4B (MLX)",
        size_gb=8.8,
        context="128K",
        modalities="Text, Image",
        tier="apple-silicon",
        notes="Apple Silicon optimized build.",
    ),
    ModelEntry(
        tag="gemma4:12b-mlx",
        label="Gemma 4 12B (MLX)",
        size_gb=7.7,
        context="256K",
        modalities="Text, Image",
        tier="apple-silicon",
        notes="Apple Silicon optimized build.",
    ),
    ModelEntry(
        tag="gemma4:26b-mlx",
        label="Gemma 4 26B (MLX)",
        size_gb=18.0,
        context="256K",
        modalities="Text, Image",
        tier="apple-silicon",
        notes="Apple Silicon optimized build.",
    ),
    ModelEntry(
        tag="gemma4:31b-mlx",
        label="Gemma 4 31B (MLX)",
        size_gb=19.0,
        context="256K",
        modalities="Text, Image",
        tier="apple-silicon",
        notes="Apple Silicon optimized build.",
    ),
)

_CATALOG_TAGS = {e.tag for e in GEMMA4_CATALOG}


def catalog_tags() -> set[str]:
    return set(_CATALOG_TAGS)


def is_catalog_tag(tag: str) -> bool:
    return tag in _CATALOG_TAGS


def catalog_as_dicts() -> list[dict]:
    return [asdict(e) for e in GEMMA4_CATALOG]
