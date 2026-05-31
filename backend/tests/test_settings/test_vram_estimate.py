"""Tests for the registry-load VRAM-feasibility estimator.

Covers GGUF header parsing, SWA-aware KV-cache estimation, the nvidia-smi free
VRAM query, per-model verdicts, and the registry-wide check (warn / refuse /
env escape hatches). All inputs are synthesised in-memory or via tmp files so
the suite runs anywhere (no GPU, no model files on disk).
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from mtgai.settings import vram_estimate as ve
from mtgai.settings.model_registry import LLMModel
from mtgai.settings.vram_estimate import (
    Verdict,
    VramInfo,
    VramRiskError,
    check_vram_risk,
    estimate_kv_cache_bytes,
    estimate_model_load,
    parse_gguf_metadata,
    query_free_vram_bytes,
    query_vram,
)

GIB = 1024**3


# ── GGUF header builder ───────────────────────────────────────────────

# Value type ids from the GGUF spec.
_T_UINT32 = 5
_T_STRING = 8
_T_ARRAY = 9
_T_BOOL = 7


def _gguf_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _gguf_kv(key: str, vtype: int, payload: bytes) -> bytes:
    return _gguf_str(key) + struct.pack("<I", vtype) + payload


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def _u32_array(values: list[int]) -> bytes:
    body = struct.pack("<I", _T_UINT32) + struct.pack("<Q", len(values))
    body += b"".join(struct.pack("<I", v) for v in values)
    return body


def _bool_array(values: list[bool]) -> bytes:
    body = struct.pack("<I", _T_BOOL) + struct.pack("<Q", len(values))
    body += b"".join(struct.pack("<?", v) for v in values)
    return body


def build_gguf(arch: str, scalars: dict[str, int], arrays: dict[str, object]) -> bytes:
    """Assemble a minimal valid GGUF v3 header (metadata only, 0 tensors).

    ``scalars`` are uint32 metadata values keyed by their full dotted name (e.g.
    ``"llama.block_count"``); ``arrays`` map a full key to a list of ints (uint32
    array) or bools (bool array).
    """
    kvs: list[bytes] = [_gguf_kv("general.architecture", _T_STRING, _gguf_str(arch))]
    for key, val in scalars.items():
        kvs.append(_gguf_kv(key, _T_UINT32, _u32(val)))
    for key, val in arrays.items():
        if val and isinstance(val[0], bool):
            kvs.append(_gguf_kv(key, _T_ARRAY, _bool_array(val)))  # type: ignore[arg-type]
        else:
            kvs.append(_gguf_kv(key, _T_ARRAY, _u32_array(val)))  # type: ignore[arg-type]

    header = struct.pack("<II", ve._GGUF_MAGIC, 3)  # magic + version
    header += struct.pack("<Q", 0)  # n_tensors
    header += struct.pack("<Q", len(kvs))  # n_kv
    return header + b"".join(kvs)


def write_gguf(tmp_path: Path, **kwargs) -> Path:
    blob = build_gguf(**kwargs)
    path = tmp_path / "model.gguf"
    path.write_bytes(blob)
    return path


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_vram_cache(monkeypatch):
    """Each test starts with a clean free-VRAM cache and no env overrides."""
    ve.reset_free_vram_cache()
    monkeypatch.delenv(ve._DISABLE_ENV, raising=False)
    monkeypatch.delenv(ve._STRICT_ENV, raising=False)
    yield
    ve.reset_free_vram_cache()


def _llamacpp_model(gguf_path: str | None, **overrides) -> LLMModel:
    base: dict[str, object] = dict(
        key="local",
        name="Local",
        provider="llamacpp",
        model_id="local-model",
        gguf_path=gguf_path,
        context_window=32768,
        n_gpu_layers=-1,
        cache_type_k="q8_0",
        cache_type_v="q8_0",
    )
    base.update(overrides)
    return LLMModel(**base)


# ── GGUF parsing ──────────────────────────────────────────────────────


class TestParseGguf:
    def test_round_trip_scalars_and_arrays(self, tmp_path):
        path = write_gguf(
            tmp_path,
            arch="llama",
            scalars={
                "llama.block_count": 28,
                "llama.embedding_length": 3072,
                "llama.attention.head_count": 24,
                "llama.attention.head_count_kv": 8,
                "llama.attention.key_length": 128,
                "llama.attention.value_length": 128,
            },
            arrays={},
        )
        meta = parse_gguf_metadata(path)
        assert meta is not None
        assert meta["architecture"] == "llama"
        assert meta["block_count"] == 28
        assert meta["embedding_length"] == 3072
        assert meta["head_count"] == 24
        assert meta["head_count_kv"] == 8
        assert meta["key_length"] == 128
        assert meta["value_length"] == 128

    def test_per_layer_arrays(self, tmp_path):
        path = write_gguf(
            tmp_path,
            arch="gemma4",
            scalars={"gemma4.block_count": 6, "gemma4.attention.sliding_window": 1024},
            arrays={
                "gemma4.attention.head_count_kv": [8, 8, 8, 8, 8, 2],
                "gemma4.attention.sliding_window_pattern": [
                    True,
                    True,
                    True,
                    True,
                    True,
                    False,
                ],
            },
        )
        meta = parse_gguf_metadata(path)
        assert meta is not None
        assert meta["head_count_kv"] == [8, 8, 8, 8, 8, 2]
        assert meta["sliding_window"] == 1024
        assert meta["sliding_window_pattern"] == [True, True, True, True, True, False]

    def test_missing_file_returns_none(self, tmp_path):
        assert parse_gguf_metadata(tmp_path / "nope.gguf") is None

    def test_wrong_magic_returns_none(self, tmp_path):
        path = tmp_path / "fake.gguf"
        path.write_bytes(b"NOTGGUF!" + b"\x00" * 64)
        assert parse_gguf_metadata(path) is None

    def test_truncated_header_returns_none(self, tmp_path):
        blob = build_gguf("llama", {"llama.block_count": 28}, {})
        path = tmp_path / "trunc.gguf"
        path.write_bytes(blob[:20])  # chop mid-metadata
        assert parse_gguf_metadata(path) is None

    def test_no_wanted_keys_returns_none(self, tmp_path):
        # Only architecture, none of the dims we look for → still returns arch.
        path = write_gguf(tmp_path, arch="llama", scalars={}, arrays={})
        meta = parse_gguf_metadata(path)
        assert meta == {"architecture": "llama"}


# ── KV cache estimate ─────────────────────────────────────────────────


class TestKvEstimate:
    def test_standard_gqa_matches_hand_computed(self):
        # 28 layers, 8 KV heads, head_dim 128, ctx 32768, q8_0 both (1.0625 B).
        meta = {
            "block_count": 28,
            "head_count_kv": 8,
            "key_length": 128,
            "value_length": 128,
        }
        kv = estimate_kv_cache_bytes(meta, 32768, "q8_0", "q8_0")
        expected = int(28 * 8 * (128 + 128) * 32768 * 1.0625)
        assert kv == expected

    def test_head_dim_falls_back_to_embedding_over_heads(self):
        meta = {"block_count": 4, "head_count_kv": 4, "embedding_length": 1024, "head_count": 8}
        kv = estimate_kv_cache_bytes(meta, 1000, "f16", "f16")
        head_dim = 1024 // 8  # 128
        expected = int(4 * 4 * (head_dim + head_dim) * 1000 * 2.0)
        assert kv == expected

    def test_sliding_window_caps_sliding_layers(self):
        meta = {
            "block_count": 6,
            "head_count_kv": [8, 8, 8, 8, 8, 2],
            "key_length": 64,
            "value_length": 64,
            "sliding_window": 1024,
            "sliding_window_pattern": [True, True, True, True, True, False],
        }
        ctx = 128000
        kv = estimate_kv_cache_bytes(meta, ctx, "q8_0", "q8_0")
        bpe = 1.0625
        expected = 0.0
        for i, heads in enumerate(meta["head_count_kv"]):
            sliding = meta["sliding_window_pattern"][i]
            eff = min(ctx, 1024) if sliding else ctx
            expected += heads * (64 + 64) * eff * bpe
        assert kv == int(expected)
        # Sliding cap must make this far smaller than the naive full-ctx sum.
        naive = int(sum(meta["head_count_kv"]) * (64 + 64) * ctx * bpe)
        assert kv < naive // 2

    def test_cache_type_byte_sizes(self):
        # K and V are summed as floats and truncated once, so the expectation
        # is int(K_bytes + V_bytes), not 2 * int(side) (which would double a
        # per-side truncation error).
        meta = {"block_count": 1, "head_count_kv": 1, "key_length": 1, "value_length": 1}
        f16 = estimate_kv_cache_bytes(meta, 1000, "f16", "f16")
        q8 = estimate_kv_cache_bytes(meta, 1000, "q8_0", "q8_0")
        q4 = estimate_kv_cache_bytes(meta, 1000, "q4_0", "q4_0")
        assert f16 == int(1000 * 2.0 + 1000 * 2.0)
        assert q8 == int(1000 * 1.0625 + 1000 * 1.0625)
        assert q4 == int(1000 * 0.5625 + 1000 * 0.5625)
        assert q4 < q8 < f16

    def test_unknown_cache_type_defaults_to_f16(self):
        meta = {"block_count": 1, "head_count_kv": 1, "key_length": 1, "value_length": 1}
        weird = estimate_kv_cache_bytes(meta, 1000, "iq3_xxs", None)
        f16 = estimate_kv_cache_bytes(meta, 1000, "f16", "f16")
        assert weird == f16

    def test_missing_dims_return_none(self):
        assert estimate_kv_cache_bytes({"block_count": 28}, 1000, "f16", "f16") is None
        assert estimate_kv_cache_bytes({"head_count_kv": 8}, 1000, "f16", "f16") is None

    def test_mismatched_array_length_returns_none(self):
        meta = {
            "block_count": 6,
            "head_count_kv": [8, 8, 8],  # wrong length
            "key_length": 64,
            "value_length": 64,
        }
        assert estimate_kv_cache_bytes(meta, 1000, "f16", "f16") is None


# ── Free VRAM query ───────────────────────────────────────────────────


class _FakeProc:
    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout


class TestVramQuery:
    def test_parses_single_gpu(self, monkeypatch):
        monkeypatch.setattr(ve.subprocess, "run", lambda *a, **k: _FakeProc(0, "10528, 12282\n"))
        info = query_vram(use_cache=False)
        assert info == VramInfo(10528 * 1024 * 1024, 12282 * 1024 * 1024)
        assert query_free_vram_bytes(use_cache=False) == 10528 * 1024 * 1024

    def test_picks_gpu_with_least_free(self, monkeypatch):
        monkeypatch.setattr(
            ve.subprocess, "run", lambda *a, **k: _FakeProc(0, "20000, 24000\n8000, 12000\n")
        )
        info = query_vram(use_cache=False)
        assert info == VramInfo(8000 * 1024 * 1024, 12000 * 1024 * 1024)

    def test_missing_nvidia_smi_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("nvidia-smi")

        monkeypatch.setattr(ve.subprocess, "run", boom)
        assert query_vram(use_cache=False) is None
        assert query_free_vram_bytes(use_cache=False) is None

    def test_nonzero_exit_returns_none(self, monkeypatch):
        monkeypatch.setattr(ve.subprocess, "run", lambda *a, **k: _FakeProc(9, ""))
        assert query_vram(use_cache=False) is None

    def test_unparseable_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(ve.subprocess, "run", lambda *a, **k: _FakeProc(0, "N/A, N/A\n"))
        assert query_vram(use_cache=False) is None

    def test_wrong_column_count_returns_none(self, monkeypatch):
        monkeypatch.setattr(ve.subprocess, "run", lambda *a, **k: _FakeProc(0, "8000\n"))
        assert query_vram(use_cache=False) is None

    def test_cache_avoids_resubprocess(self, monkeypatch):
        calls = {"n": 0}

        def counted(*a, **k):
            calls["n"] += 1
            return _FakeProc(0, "4096, 8192\n")

        monkeypatch.setattr(ve.subprocess, "run", counted)
        a = query_vram()
        b = query_vram()
        assert a == b == VramInfo(4096 * 1024 * 1024, 8192 * 1024 * 1024)
        assert calls["n"] == 1

    def test_cache_remembers_failure(self, monkeypatch):
        calls = {"n": 0}

        def counted(*a, **k):
            calls["n"] += 1
            raise FileNotFoundError("nvidia-smi")

        monkeypatch.setattr(ve.subprocess, "run", counted)
        assert query_vram() is None
        assert query_vram() is None
        assert calls["n"] == 1


# ── Per-model estimate ────────────────────────────────────────────────
#
# ``estimate_model_load`` reads the weight size via ``Path.stat().st_size``, so
# the tests need GGUF files that *report* multi-GiB sizes without actually
# writing gigabytes to disk (which would be filesystem-dependent and minutes
# slow). ``sized_gguf`` writes a tiny valid header and patches ``Path.stat`` to
# report the requested size for that one path, delegating every other path to
# the real stat. The header term and the KV term thus stay independently
# controllable and the suite runs in milliseconds anywhere.

_REAL_STAT = Path.stat


class _FakeSizeStat:
    """Stand-in stat result that only overrides ``st_size``.

    ``estimate_model_load`` reads just ``gguf.stat().st_size``; delegating every
    other attribute to the real stat keeps the stub honest if that ever changes.
    """

    def __init__(self, real: os.stat_result, size: int):
        self._real = real
        self.st_size = size

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def sized_gguf(tmp_path, monkeypatch):
    """Factory: ``make(weight_bytes, **gguf_kwargs) -> Path`` for a GGUF whose
    reported on-disk size is ``weight_bytes`` (real header, faked size)."""
    overrides: dict[str, int] = {}
    counter = {"n": 0}

    default_scalars = {
        "llama.block_count": 1,
        "llama.attention.head_count_kv": 1,
        "llama.attention.key_length": 1,
        "llama.attention.value_length": 1,
    }

    def patched_stat(self, *args, **kwargs):
        st = _REAL_STAT(self, *args, **kwargs)
        target = overrides.get(str(self))
        if target is None:
            return st
        return _FakeSizeStat(st, target)

    monkeypatch.setattr(Path, "stat", patched_stat)

    def make(weight_bytes: int, *, arch="llama", scalars=None, arrays=None) -> Path:
        counter["n"] += 1
        blob = build_gguf(arch=arch, scalars=scalars or default_scalars, arrays=arrays or {})
        path = tmp_path / f"sized_{counter['n']}.gguf"
        path.write_bytes(blob)
        overrides[str(path)] = weight_bytes
        return path

    return make


class TestEstimateModelLoad:
    def test_ok_when_well_under_budget(self, sized_gguf):
        gguf = sized_gguf(4 * GIB)
        model = _llamacpp_model(str(gguf))
        est = estimate_model_load(model, vram=VramInfo(12 * GIB, 12 * GIB))
        assert est.verdict is Verdict.OK
        assert est.weight_bytes == 4 * GIB
        assert est.kv_bytes is not None

    def test_warn_when_tight_against_free_but_fits_total(self, sized_gguf):
        gguf = sized_gguf(10 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)  # negligible KV
        # 10 GiB weights * 1.10 = 11 GiB load. free=11.5 → 0.96 (warn);
        # total=12 → 0.92 (does NOT refuse).
        est = estimate_model_load(model, vram=VramInfo(int(11.5 * GIB), 12 * GIB))
        assert est.verdict is Verdict.WARN
        assert 0.85 < est.free_fraction <= 1.0
        assert est.total_fraction <= 1.0

    def test_refuse_when_over_total(self, sized_gguf):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)
        est = estimate_model_load(model, vram=VramInfo(12 * GIB, 12 * GIB))
        assert est.verdict is Verdict.REFUSE
        assert est.total_fraction > 1.0

    def test_free_shorthand_defaults_total_to_free(self, sized_gguf):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)
        # Only free given → total defaults to free → over-budget refuses.
        est = estimate_model_load(model, free_bytes=12 * GIB)
        assert est.total_bytes == 12 * GIB
        assert est.verdict is Verdict.REFUSE

    def test_unknown_when_gguf_missing(self, tmp_path):
        model = _llamacpp_model(str(tmp_path / "absent.gguf"))
        est = estimate_model_load(model, vram=VramInfo(12 * GIB, 12 * GIB))
        assert est.verdict is Verdict.UNKNOWN
        assert "not found" in est.reason

    def test_unknown_when_no_vram(self, sized_gguf, monkeypatch):
        gguf = sized_gguf(4 * GIB)
        model = _llamacpp_model(str(gguf))
        # No vram supplied → live query; stub it to "no GPU".
        monkeypatch.setattr(ve, "query_vram", lambda *a, **k: None)
        est = estimate_model_load(model)
        assert est.verdict is Verdict.UNKNOWN

    def test_unknown_when_no_gguf_path(self):
        model = _llamacpp_model(None)  # gguf_path is the first positional arg
        assert model.gguf_path is None
        est = estimate_model_load(model, vram=VramInfo(12 * GIB, 12 * GIB))
        assert est.verdict is Verdict.UNKNOWN
        assert est.reason == "no gguf_path"

    def test_kv_term_pushes_over_budget(self, sized_gguf):
        # Weights alone fit; large full-ctx f16 KV tips total over budget.
        gguf = sized_gguf(
            8 * GIB,
            scalars={
                "llama.block_count": 40,
                "llama.attention.head_count_kv": 8,
                "llama.attention.key_length": 128,
                "llama.attention.value_length": 128,
            },
        )
        model = _llamacpp_model(
            str(gguf), context_window=128000, cache_type_k="f16", cache_type_v="f16"
        )
        est = estimate_model_load(model, vram=VramInfo(12 * GIB, 12 * GIB))
        assert est.kv_bytes is not None and est.kv_bytes > GIB
        assert est.verdict in (Verdict.WARN, Verdict.REFUSE)


# ── Registry-wide check ───────────────────────────────────────────────


class TestCheckVramRisk:
    def test_warn_logs_no_raise(self, sized_gguf, caplog):
        gguf = sized_gguf(10 * GIB)
        # fit=False so the all-on-GPU geometry IS the launch (hard WARN path).
        model = _llamacpp_model(str(gguf), context_window=1, fit=False)
        # 11 GiB load, free 11.5 (warn), total 12 (fits) → warn, no raise.
        ve._vram_cache = VramInfo(int(11.5 * GIB), 12 * GIB)
        with caplog.at_level("WARNING"):
            ests = check_vram_risk({"local": model})
        assert ests[0].verdict is Verdict.WARN
        assert any("VRAM risk" in r.message for r in caplog.records)

    def test_refuse_raises_only_in_strict_mode(self, sized_gguf, monkeypatch):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1, fit=False)
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        monkeypatch.setenv(ve._STRICT_ENV, "1")
        with pytest.raises(VramRiskError) as exc:
            check_vram_risk({"local": model})
        assert "OOM" in str(exc.value)

    def test_refuse_default_warn_only_no_raise(self, sized_gguf, caplog):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1, fit=False)
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        with caplog.at_level("ERROR"):
            ests = check_vram_risk({"local": model})  # no raise by default
        assert ests[0].verdict is Verdict.REFUSE
        assert any("VRAM over budget" in r.message for r in caplog.records)

    def test_fit_on_over_budget_logs_info_not_error(self, sized_gguf, caplog):
        """fit=True (the default): an over-budget all-GPU model logs an INFO
        autofit note, not an ERROR — llama-server re-fits at spawn (--fit on)
        and spills to CPU/RAM instead of OOMing. Geometry verdict is unchanged."""
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)  # fit defaults True
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        with caplog.at_level("INFO"):
            ests = check_vram_risk({"local": model})
        assert ests[0].verdict is Verdict.REFUSE  # geometry unchanged
        assert any("VRAM autofit" in r.message for r in caplog.records)
        # No ERROR-level "over budget" line for a fit=on entry.
        assert not any(r.levelname == "ERROR" for r in caplog.records)

    def test_fit_on_over_budget_never_raises_in_strict_mode(self, sized_gguf, monkeypatch):
        """Strict mode must NOT raise for a fit=on model — autofit prevents the
        OOM the strict raise guards against."""
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)  # fit defaults True
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        monkeypatch.setenv(ve._STRICT_ENV, "1")
        ests = check_vram_risk({"local": model})  # no raise
        assert ests[0].verdict is Verdict.REFUSE

    def test_ignores_non_all_gpu_entries(self, sized_gguf):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), n_gpu_layers=35)  # pinned, not -1
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        assert check_vram_risk({"local": model}) == []

    def test_ignores_anthropic_entries(self):
        anthropic = LLMModel(
            key="opus",
            name="Opus",
            provider="anthropic",
            model_id="claude-opus-4-6",
            n_gpu_layers=-1,  # nonsensical but should be ignored anyway
        )
        ve._vram_cache = VramInfo(1 * GIB, 1 * GIB)
        assert check_vram_risk({"opus": anthropic}) == []

    def test_disable_env_skips_even_in_strict_mode(self, sized_gguf, monkeypatch):
        gguf = sized_gguf(22 * GIB)
        model = _llamacpp_model(str(gguf), context_window=1)
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        monkeypatch.setenv(ve._STRICT_ENV, "1")
        monkeypatch.setenv(ve._DISABLE_ENV, "1")
        assert check_vram_risk({"local": model}) == []  # no estimate, no raise

    def test_unknown_models_never_raise(self, tmp_path):
        # gguf absent → unknown for every entry → load must stay clean.
        model = _llamacpp_model(str(tmp_path / "absent.gguf"))
        ve._vram_cache = VramInfo(12 * GIB, 12 * GIB)
        ests = check_vram_risk({"local": model})
        assert ests[0].verdict is Verdict.UNKNOWN


# ── Regression: real registry still loads ─────────────────────────────


def test_shipped_registry_loads_without_raising():
    """The shipped models.toml points at C:/Models/*.gguf which won't exist in
    CI — every llamacpp entry degrades to 'unknown', so load must not raise."""
    from mtgai.settings.model_registry import ModelRegistry

    ve.reset_free_vram_cache()
    registry = ModelRegistry.load()
    assert registry.llm_models  # sanity: models actually loaded
