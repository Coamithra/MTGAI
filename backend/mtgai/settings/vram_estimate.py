"""VRAM-feasibility estimation for all-GPU llamacpp models.

In llama.cpp ``--n-gpu-layers -1`` means "place every layer on the GPU" — it is
*not* Ollama's "auto-place to fit VRAM" semantics. A registry entry with
``n_gpu_layers = -1`` whose weights + KV cache exceed available VRAM will OOM at
runtime, silently, mid-generation. This module estimates that load at registry
*load* time so the footgun surfaces at startup instead.

The estimate has two terms:

* **Weights** — the GGUF file size on disk (the dominant, reliably-known term).
* **KV cache** — a SWA-aware per-layer K+V sum derived from the GGUF header
  (block count, head dims, head_count_kv, sliding-window pattern) at the
  configured ``context_window`` and cache-type quantisation.

Everything degrades to ``unknown`` (a silent no-op) when an input can't be
measured — the GGUF file is missing, the header won't parse, or no NVIDIA GPU is
present. The check only ever warns or refuses where it can actually measure both
the load and the free VRAM, so it cannot brick startup on a guess.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgai.settings.model_registry import LLMModel

logger = logging.getLogger(__name__)

# Warn when the estimated load exceeds this fraction of *free* VRAM — that's the
# budget llama-server actually has at spawn, so a second GPU app holding memory
# correctly tightens it and surfaces a contention risk early. Refuse only when
# the load exceeds *total* VRAM, i.e. the model cannot physically fit on the card
# regardless of what else is running. Refusing against free VRAM would brick app
# startup over a transient dip (a browser holding 1 GB), so the hard stop is
# reserved for the unambiguous "this will always OOM" case.
WARN_FRACTION = 0.85
REFUSE_FRACTION = 1.0

# Multiplicative headroom on the raw weights+KV sum to cover llama.cpp's compute
# buffers, the CUDA context, and fragmentation. 1.10 ≈ the ~1 GB overhead the
# TC-2 benchmark observed on top of weights+cache on the 12 GB card.
_OVERHEAD_FACTOR = 1.10

# Bytes per KV-cache element by quantisation. q8_0/q4_0 carry block scales, so
# they're slightly above the nominal 1.0 / 0.5 bytes. f16 is the llama.cpp
# default when no cache_type is set.
_CACHE_TYPE_BYTES: dict[str, float] = {
    "f16": 2.0,
    "f32": 4.0,
    "bf16": 2.0,
    "q8_0": 1.0625,
    "q5_0": 0.6875,
    "q5_1": 0.75,
    "q4_0": 0.5625,
    "q4_1": 0.625,
}
_DEFAULT_CACHE_BYTES = _CACHE_TYPE_BYTES["f16"]

# Env knobs. The check defaults to *warn-only* — even an over-budget (refuse)
# verdict is logged at ERROR but does not raise, so a misestimate (or a config
# the operator knows is fine, like the production Gemma that lives right at the
# VRAM edge) can never brick app startup. Opt into a hard raise with the strict
# flag; disable the check entirely with the disable flag.
_STRICT_ENV = "MTGAI_VRAM_CHECK_STRICT"
_DISABLE_ENV = "MTGAI_DISABLE_VRAM_CHECK"


class VramRiskError(RuntimeError):
    """Raised at registry load when an all-GPU model cannot fit in VRAM."""


class Verdict(StrEnum):
    OK = "ok"
    WARN = "warn"
    REFUSE = "refuse"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VramEstimate:
    """Outcome of estimating one all-GPU llamacpp model's VRAM footprint.

    ``load_bytes`` is the estimated weights + KV + overhead. It's measured
    against both ``free_bytes`` (drives the WARN threshold) and
    ``total_bytes`` (drives the REFUSE threshold).
    """

    model_key: str
    verdict: Verdict
    weight_bytes: int | None = None
    kv_bytes: int | None = None
    load_bytes: int | None = None
    free_bytes: int | None = None
    total_bytes: int | None = None
    free_fraction: float | None = None
    total_fraction: float | None = None
    reason: str = ""

    def message(self) -> str:
        """Human-readable one-liner for logging."""
        if self.verdict is Verdict.UNKNOWN:
            return f"{self.model_key}: VRAM estimate skipped ({self.reason})"
        return (
            f"{self.model_key}: n_gpu_layers=-1 estimated load "
            f"{_gib(self.load_bytes)} "
            f"(weights {_gib(self.weight_bytes)} + KV {_gib(self.kv_bytes)}) "
            f"vs free {_gib(self.free_bytes)} ({_pct(self.free_fraction)}) / "
            f"total {_gib(self.total_bytes)} ({_pct(self.total_fraction)})"
        )


def _gib(n: int | None) -> str:
    if n is None:
        return "?"
    return f"{n / 1024**3:.2f} GiB"


def _pct(f: float | None) -> str:
    if f is None:
        return "?"
    return f"{f:.0%}"


# ---------------------------------------------------------------------------
# GGUF header parsing (minimal, dependency-free)
# ---------------------------------------------------------------------------

_GGUF_MAGIC = 0x46554747  # b"GGUF" little-endian

# GGUF metadata value type → (struct format, byte width). Type ids per the
# GGUF spec (ggml/docs/gguf.md). Type 8 = string, 9 = array (handled inline).
_GGUF_SCALAR = {
    0: ("<b", 1),
    1: ("<B", 1),
    2: ("<h", 2),
    3: ("<H", 2),
    4: ("<i", 4),
    5: ("<I", 4),
    6: ("<f", 4),
    7: ("<?", 1),
    10: ("<q", 8),
    11: ("<Q", 8),
    12: ("<d", 8),
}

# Metadata keys we care about, matched by suffix (the prefix is the architecture,
# e.g. "llama." / "gemma4."). Mapped to the canonical name we expose.
_WANTED_SUFFIXES = {
    "block_count": "block_count",
    "embedding_length": "embedding_length",
    "attention.head_count": "head_count",
    "attention.head_count_kv": "head_count_kv",
    "attention.key_length": "key_length",
    "attention.value_length": "value_length",
    "attention.sliding_window": "sliding_window",
    "attention.sliding_window_pattern": "sliding_window_pattern",
}

# Cap on metadata KV pairs / array lengths we'll read, so a corrupt header can't
# make us allocate or loop unboundedly.
_MAX_KV = 100_000
_MAX_ARRAY = 1_000_000


def _read_gguf_string(f) -> str:
    (n,) = struct.unpack("<Q", f.read(8))
    if n > _MAX_ARRAY:
        raise ValueError("gguf string too long")
    return f.read(n).decode("utf-8", "replace")


def _read_gguf_value(f, vtype: int, depth: int = 0):
    if vtype in _GGUF_SCALAR:
        fmt, width = _GGUF_SCALAR[vtype]
        return struct.unpack(fmt, f.read(width))[0]
    if vtype == 8:
        return _read_gguf_string(f)
    if vtype == 9:
        if depth > 0:
            raise ValueError("nested gguf arrays unsupported")
        (atype,) = struct.unpack("<I", f.read(4))
        (alen,) = struct.unpack("<Q", f.read(8))
        if alen > _MAX_ARRAY:
            raise ValueError("gguf array too long")
        return [_read_gguf_value(f, atype, depth + 1) for _ in range(alen)]
    raise ValueError(f"unknown gguf value type {vtype}")


def parse_gguf_metadata(path: str | Path) -> dict[str, object] | None:
    """Read the scalar architecture metadata we need from a GGUF header.

    Returns a dict keyed by the canonical names in :data:`_WANTED_SUFFIXES`
    (plus ``architecture``), or ``None`` if the file is missing, isn't a GGUF,
    or the header can't be parsed. Never raises — a malformed model file must
    not break registry load.
    """
    try:
        with open(path, "rb") as f:
            magic, version = struct.unpack("<II", f.read(8))
            if magic != _GGUF_MAGIC:
                return None
            if version not in (2, 3):
                # v1 used 32-bit counts; we only support v2/v3 (current).
                return None
            (_n_tensors,) = struct.unpack("<Q", f.read(8))
            (n_kv,) = struct.unpack("<Q", f.read(8))
            if n_kv > _MAX_KV:
                return None

            raw: dict[str, object] = {}
            for _ in range(n_kv):
                key = _read_gguf_string(f)
                (vtype,) = struct.unpack("<I", f.read(4))
                raw[key] = _read_gguf_value(f, vtype)
    except (OSError, ValueError, struct.error):
        return None

    meta: dict[str, object] = {}
    arch = raw.get("general.architecture")
    if isinstance(arch, str):
        meta["architecture"] = arch
    for key, value in raw.items():
        for suffix, canonical in _WANTED_SUFFIXES.items():
            if key.endswith(suffix) and canonical not in meta:
                meta[canonical] = value
    return meta or None


# ---------------------------------------------------------------------------
# KV cache estimate
# ---------------------------------------------------------------------------


def _cache_bytes_per_element(cache_type: str | None) -> float:
    if not cache_type:
        return _DEFAULT_CACHE_BYTES
    return _CACHE_TYPE_BYTES.get(cache_type.lower(), _DEFAULT_CACHE_BYTES)


def estimate_kv_cache_bytes(
    meta: dict[str, object],
    context_window: int,
    cache_type_k: str | None,
    cache_type_v: str | None,
) -> int | None:
    """SWA-aware estimate of the KV-cache footprint in bytes.

    For each layer the K and V caches hold ``head_count_kv * head_dim`` elements
    per token. Sliding-window layers cap their effective context at the window
    size rather than the full ``context_window``; global layers use the full
    context. Returns ``None`` if the header lacks the dims we need.
    """
    block_count = _as_int(meta.get("block_count"))
    if not block_count or context_window <= 0:
        return None

    head_dim_k = _head_dim(meta, "key_length")
    head_dim_v = _head_dim(meta, "value_length")
    if head_dim_k is None or head_dim_v is None:
        return None

    kv_heads = _per_layer(meta.get("head_count_kv"), block_count)
    if kv_heads is None:
        return None

    sliding_window = _as_int(meta.get("sliding_window"))
    pattern = meta.get("sliding_window_pattern")
    is_sliding = _sliding_flags(pattern, block_count)

    bytes_k = _cache_bytes_per_element(cache_type_k)
    bytes_v = _cache_bytes_per_element(cache_type_v)

    total = 0.0
    for layer in range(block_count):
        heads = kv_heads[layer]
        eff_ctx = context_window
        if sliding_window and is_sliding is not None and is_sliding[layer]:
            eff_ctx = min(context_window, sliding_window)
        total += heads * head_dim_k * eff_ctx * bytes_k
        total += heads * head_dim_v * eff_ctx * bytes_v
    return int(total)


def _head_dim(meta: dict[str, object], length_key: str) -> int | None:
    """Per-head K (or V) dimension.

    Prefers the explicit ``attention.key_length`` / ``value_length`` (some
    architectures like Gemma set a head dim independent of embedding/heads);
    falls back to ``embedding_length / head_count``.
    """
    explicit = _as_int(meta.get(length_key))
    if explicit:
        return explicit
    emb = _as_int(meta.get("embedding_length"))
    heads = _as_int(meta.get("head_count"))
    if emb and heads:
        return emb // heads
    return None


def _per_layer(value: object, block_count: int) -> list[int] | None:
    """Normalise a scalar-or-per-layer metadata value into a per-layer list."""
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        return None
    if isinstance(value, int):
        return [value] * block_count
    if isinstance(value, list) and len(value) == block_count:
        try:
            return [int(v) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def _sliding_flags(pattern: object, block_count: int) -> list[bool] | None:
    if isinstance(pattern, list) and len(pattern) == block_count:
        return [bool(v) for v in pattern]
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


# ---------------------------------------------------------------------------
# VRAM query
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VramInfo:
    """A GPU's free + total memory, in bytes."""

    free_bytes: int
    total_bytes: int


_UNQUERIED = object()
_vram_cache: VramInfo | None | object = _UNQUERIED


def query_vram(*, use_cache: bool = True) -> VramInfo | None:
    """Free + total VRAM via ``nvidia-smi``. ``None`` if it can't be queried.

    Returns the GPU with the *least* free memory (the tightest budget for an
    all-GPU placement, which targets a single device). Cached per-process by
    default — including a failed query (``None``) — so we don't re-spawn
    nvidia-smi for every model on a machine that has none.
    """
    global _vram_cache
    if use_cache and _vram_cache is not _UNQUERIED:
        return _vram_cache  # type: ignore[return-value]
    result = _query_vram_uncached()
    if use_cache:
        _vram_cache = result
    return result


def query_free_vram_bytes(*, use_cache: bool = True) -> int | None:
    """Free VRAM in bytes (min across GPUs), or ``None``. Thin wrapper."""
    info = query_vram(use_cache=use_cache)
    return info.free_bytes if info else None


def _query_vram_uncached() -> VramInfo | None:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    gpus: list[VramInfo] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            return None
        try:
            free_mib, total_mib = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        gpus.append(VramInfo(free_mib * 1024 * 1024, total_mib * 1024 * 1024))
    if not gpus:
        return None
    return min(gpus, key=lambda g: g.free_bytes)


def reset_free_vram_cache() -> None:
    """Drop the cached VRAM reading (used by tests)."""
    global _vram_cache
    _vram_cache = _UNQUERIED


# ---------------------------------------------------------------------------
# Per-model estimate + registry-wide check
# ---------------------------------------------------------------------------


def estimate_model_load(
    model: LLMModel,
    *,
    vram: VramInfo | None = None,
    free_bytes: int | None = None,
    total_bytes: int | None = None,
) -> VramEstimate:
    """Estimate one all-GPU llamacpp model's VRAM footprint and verdict.

    Pass ``vram`` (or the ``free_bytes`` / ``total_bytes`` shorthand) to supply
    the GPU budget; otherwise it's queried live via :func:`query_vram`. When
    only ``free_bytes`` is given, ``total_bytes`` defaults to it (so a caller
    that knows only free VRAM gets a free-vs-free comparison). The model is
    assumed to be an ``n_gpu_layers == -1`` llamacpp entry (the caller filters).
    """
    if not model.gguf_path:
        return VramEstimate(model.key, Verdict.UNKNOWN, reason="no gguf_path")

    gguf = Path(model.gguf_path)
    try:
        weight_bytes = gguf.stat().st_size
    except OSError:
        return VramEstimate(
            model.key, Verdict.UNKNOWN, reason=f"gguf not found at {model.gguf_path}"
        )

    if vram is None and free_bytes is not None:
        vram = VramInfo(free_bytes=free_bytes, total_bytes=total_bytes or free_bytes)
    if vram is None:
        vram = query_vram()
    if vram is None:
        return VramEstimate(
            model.key,
            Verdict.UNKNOWN,
            weight_bytes=weight_bytes,
            reason="VRAM unavailable (no nvidia-smi?)",
        )

    meta = parse_gguf_metadata(gguf)
    kv_bytes: int | None = None
    if meta is not None:
        kv_bytes = estimate_kv_cache_bytes(
            meta, model.context_window, model.cache_type_k, model.cache_type_v
        )

    raw_total = weight_bytes + (kv_bytes or 0)
    load_bytes = int(raw_total * _OVERHEAD_FACTOR)
    free_fraction = load_bytes / vram.free_bytes if vram.free_bytes > 0 else float("inf")
    total_fraction = load_bytes / vram.total_bytes if vram.total_bytes > 0 else float("inf")

    # Refuse only when the load can't fit on the card at all (vs total VRAM);
    # warn when it's tight against the free VRAM llama-server actually has.
    if total_fraction > REFUSE_FRACTION:
        verdict = Verdict.REFUSE
    elif free_fraction > WARN_FRACTION:
        verdict = Verdict.WARN
    else:
        verdict = Verdict.OK

    return VramEstimate(
        model_key=model.key,
        verdict=verdict,
        weight_bytes=weight_bytes,
        kv_bytes=kv_bytes,
        load_bytes=load_bytes,
        free_bytes=vram.free_bytes,
        total_bytes=vram.total_bytes,
        free_fraction=free_fraction,
        total_fraction=total_fraction,
    )


def check_vram_risk(models: dict[str, LLMModel]) -> list[VramEstimate]:
    """Estimate every all-GPU llamacpp model and log/raise on the verdict.

    For each ``n_gpu_layers == -1`` llamacpp entry: a ``warn`` verdict (load
    tight against *free* VRAM) logs a WARNING; a ``refuse`` verdict (load over
    *total* VRAM — a guaranteed OOM) logs an ERROR. By default the check is
    warn-only, so even a refuse verdict does **not** raise — a misestimate or a
    config the operator knowingly runs at the VRAM edge can never brick startup.
    Set ``MTGAI_VRAM_CHECK_STRICT`` to make a refuse verdict raise
    :class:`VramRiskError`; ``MTGAI_DISABLE_VRAM_CHECK`` skips the check entirely.

    Returns the estimates for every all-GPU entry (for inspection/testing).
    """
    if _env_flag(_DISABLE_ENV):
        logger.debug("VRAM risk check disabled via %s", _DISABLE_ENV)
        return []

    strict = _env_flag(_STRICT_ENV)
    estimates: list[VramEstimate] = []
    refusal: VramEstimate | None = None

    for model in models.values():
        if model.provider != "llamacpp" or model.n_gpu_layers != -1:
            continue
        est = estimate_model_load(model)
        estimates.append(est)
        if est.verdict is Verdict.WARN:
            logger.warning(
                "VRAM risk: %s. Pin n_gpu_layers explicitly in models.toml or "
                "lower context_window / KV cache quant.",
                est.message(),
            )
        elif est.verdict is Verdict.REFUSE:
            logger.error(
                "VRAM over budget: %s. n_gpu_layers=-1 places all layers on the "
                "GPU but the estimated load exceeds total VRAM, so this config "
                "will OOM at runtime; pin n_gpu_layers in models.toml.",
                est.message(),
            )
            if refusal is None:
                refusal = est

    if strict and refusal is not None:
        raise VramRiskError(
            f"{refusal.message()}. n_gpu_layers=-1 places all layers on the GPU "
            f"but the estimated load exceeds total VRAM, so this model will OOM "
            f"at runtime. Pin n_gpu_layers to a fitting value in "
            f"backend/mtgai/settings/models.toml, lower its context_window or KV "
            f"cache quant, or unset {_STRICT_ENV} (or set {_DISABLE_ENV}=1) to "
            f"downgrade this to a warning."
        )
    return estimates


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
