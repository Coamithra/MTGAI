# Registry-load OOM warning for n_gpu_layers = -1

Card 69f86d59 (infra). Source: `learnings/llamacpp-tc2-benchmark.md`.

## Context

`n_gpu_layers = -1` in llama.cpp means "ALL layers on GPU" (not Ollama's
"auto-place"). A llamacpp registry entry with `-1` plus a KV-cache config that,
combined with the GGUF weight size and `context_window`, exceeds available VRAM
will OOM at runtime — silently, mid-extraction. This card catches that footgun
at `ModelRegistry` load time with a warning (or refusal), instead of waiting for
the runtime crash. It is the *cheaper sibling* of the auto-placement card
(`dybBBMjM`) — it does NOT fix placement, only flags the risk.

## Design

New self-contained module `backend/mtgai/settings/vram_estimate.py`:

- `parse_gguf_metadata(path)` — minimal GGUF v2/v3 header reader (no deps).
  Returns a small dict of the scalars we need: `block_count`, `key_length`,
  `value_length`, `embedding_length`, `head_count`, `head_count_kv`
  (scalar or per-layer list), `sliding_window`, `sliding_window_pattern`.
  Tolerant: returns `None` on any parse failure / missing magic.
- `estimate_kv_cache_bytes(meta, context_window, cache_type_k, cache_type_v)` —
  SWA-aware per-layer K+V sum. Sliding layers cap effective ctx at the window.
  Per-element bytes by cache type (f16=2, q8_0≈1.0625, q4_0≈0.5625, else f16).
  Returns `None` if the metadata is insufficient.
- `query_free_vram_bytes()` — shells out to
  `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits`
  (MiB). Returns the min free across GPUs, or `None` if nvidia-smi is absent /
  errors / non-NVIDIA. Cached per-process.
- `estimate_model_load(model, ...)` — for one llamacpp `LLMModel` with
  `n_gpu_layers == -1`: weights = GGUF file size on disk; KV from above;
  overhead fudge factor. Returns a `VramEstimate` dataclass with
  `weight_bytes`, `kv_bytes`, `total_bytes`, `free_bytes`, `fraction`,
  and a `verdict` (`ok` / `warn` / `refuse` / `unknown`).
- Thresholds: warn at >0.85 of free VRAM, refuse at >1.0. `unknown` whenever
  weights OR free VRAM can't be determined (file missing, no nvidia-smi) — we
  never warn/refuse on a guess.

Wire into `ModelRegistry.load()` (`model_registry.py`): after building the
registry, call `check_vram_risk(registry)` which iterates llamacpp entries with
`n_gpu_layers == -1`, logs `logger.warning(...)` for `warn`, and raises
`VramRiskError` for `refuse`. An env escape hatch `MTGAI_DISABLE_VRAM_CHECK=1`
skips the whole check (and a softer `MTGAI_VRAM_CHECK_WARN_ONLY=1` downgrades
refuse→warn) so a misestimate can never brick startup.

Because every shipped `models.toml` entry points at `C:/Models/*.gguf` and CI /
other machines won't have those files (or nvidia-smi), the check degrades to
`unknown` and is a silent no-op everywhere except a real local GPU box. This is
intentional — the check only fires where it can actually measure.

## Tests (`backend/tests/test_settings/test_vram_estimate.py`)

- GGUF parse round-trip: build a tiny in-memory GGUF blob, assert metadata.
- GGUF parse tolerates garbage / wrong magic / truncation → `None`.
- KV estimate: standard GQA (no SWA) matches hand-computed bytes.
- KV estimate: SWA caps sliding layers at the window (array head_count_kv).
- KV estimate: cache-type byte sizes (f16 vs q8_0 vs q4_0) scale correctly.
- `query_free_vram_bytes` monkeypatched: parses nvidia-smi csv, picks min,
  returns None on FileNotFoundError / non-zero exit.
- `estimate_model_load` verdicts: ok / warn / refuse / unknown via monkeypatched
  free VRAM + a temp gguf file of a chosen size.
- `check_vram_risk`: warn → logs warning, no raise; refuse → raises
  `VramRiskError`; `MTGAI_DISABLE_VRAM_CHECK` skips; `WARN_ONLY` downgrades.
- `ModelRegistry.load()` still succeeds with the shipped models.toml (files
  absent → unknown → no raise) — regression guard.

## Out of scope

- Auto-placement / picking the right `n_gpu_layers` (card `dybBBMjM`).
- Replacing the `-1` values in models.toml with measured numbers (card
  `69f9d4a0`). This card only WARNS; it does not edit the toml values.
- `--n-cpu-moe`, mmproj, flash-attn knobs.
