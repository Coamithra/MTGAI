"""Theme extraction from uploaded documents.

Handles PDF/text reading, token-aware chunking, per-section streaming
extraction with a compaction guard so accumulated state stays bounded,
and constraint + card-suggestion follow-up calls.

Single-extraction model: only one extraction can run at a time.
:func:`request_cancel` aborts the current run from any thread.
"""

from __future__ import annotations

import datetime
import json as _json
import logging
import math
import re
import threading
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llmfacade import SystemBlock

from mtgai.runtime import ai_lock

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# Tokens reserved for LLM output. Used both for budget calculations and as the
# concrete max_tokens / num_predict on each call - keep these in sync.
_OUTPUT_BUDGET = 16384
_LOG_DIR = Path("C:/Programming/MTGAI/output/extraction_logs")

# Cap how many lines of each message llmfacade dumps into its JSONL/HTML logs.
# Theme extraction sends the entire source PDF as the user message; without
# this, every per-section call would re-quote the whole document into the log.
_LOG_MAX_MESSAGE_LINES = 50

# Stop sequences keep the model from echoing the source-text divider markers
# back into the extraction (a real failure mode on weaker local models).
_LLAMACPP_STOP_SEQUENCES = [
    "--- START OF SOURCE TEXT ---",
    "--- END OF SOURCE TEXT ---",
]

# Hard cap on JSON subcall output (constraints / card_suggestions). Without
# this, a model in a repetition loop can fill the entire context window
# before the post-hoc detector runs. Mid-stream repetition detection
# (`_detect_tandem_repeat`, run every 64 chars of new content) is the primary
# runaway guard; this cap is just a backstop.
# Constraints output is tiny (3-8 short strings). Card suggestions (3-5 cards
# with descriptions) needs more room - local models sometimes pad descriptions
# or emit extra cards before the JSON closes.
_JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS = 4096
_JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS = 8192

# Per-attempt repeat_penalty escalation for the JSON subcall retry loop.
# Index = attempt-1. None means "use provider default" (1.1).
#
# Now that we're on llama.cpp via llmfacade's llamacpp provider, repeat_penalty
# actually moves the sampler — Ollama's Go-native sampler silently ignored it
# on Gemma-class models (ollama#15783). >1.20 noticeably degrades JSON token
# output, so that's the ceiling. Temperature is intentionally not escalated:
# higher temperatures produce malformed JSON structure on smaller models, and
# repeat_penalty alone breaks loops in practice.
_RETRY_REPEAT_PENALTIES: list[float | None] = [None, 1.15, 1.20]

# Compaction threshold. Per-section "next" chunks pass back the accumulated
# section text so far. If accumulated grows beyond this fraction of the chunk
# token budget, we run a compaction call to shrink it back. Keeps total per
# call input within the chunk budget even on long documents.
_COMPACT_AT_FRACTION = 0.40


# The section system prompt asks for exactly "No information found." but local
# models emit many near-misses ("no relevant information", "I found no
# information in this portion.", "nothing to report", etc.). We treat ANY
# short response (<= 200 chars, after stripping markdown fencing) that
# matches a "no info" semantic marker as empty. Long outputs are always
# treated as real content even if they start with "No information
# found..." because that pattern appears legitimately in narrative writing.
_NO_INFO_RE = re.compile(
    r"("
    r"no\s+(?:relevant\s+|new\s+|further\s+|additional\s+|other\s+|"
    r"specific\s+|explicit\s+)?information"
    r"|nothing\s+(?:to\s+)?(?:report|extract|note|add|found|mentioned)"
    r"|(?:did\s*n'?t|could\s*n'?t|cannot|can'?t|unable\s+to)\s+find"
    r"|no\s+(?:entries|matches|details|mentions)\s+found"
    r"|not\s+(?:enough|any|mentioned)"
    r"|none\s+(?:found|mentioned|present)"
    r"|n/?a\b"
    r")",
    re.IGNORECASE,
)


def _looks_like_no_info(text: str) -> bool:
    """True if the model effectively said "nothing to extract here"."""
    if not text:
        return True
    # Strip common markdown / fencing noise before matching.
    stripped = text.strip("` \n\r\t*_#")
    if len(stripped) > 200:
        return False
    return bool(_NO_INFO_RE.search(stripped))


# =============================================================================
# Cancellation + run lock (single extraction at a time)
# =============================================================================
#
# The lock + cancel signal are owned by ``mtgai.runtime.ai_lock`` so every
# AI-touching action across the app is mutually exclusive. The wrappers below
# preserve the historical theme_extractor surface (``request_cancel``,
# ``is_running``) so existing callers don't have to be rewritten.


def request_cancel() -> bool:
    """Signal the active extraction to abort.

    Returns True if a run was active, False if there was nothing to cancel.
    """
    return ai_lock.request_cancel()


def is_running() -> bool:
    return ai_lock.is_running()


class _CancelledError(Exception):
    """Internal: raised when the AI cancel event is set, to unwind the call stack."""


def _check_cancelled() -> None:
    if ai_lock.is_cancelled():
        raise _CancelledError("user cancelled")


# =============================================================================
# Phase telemetry (drives the live progress banner)
# =============================================================================
#
# The streaming generator yields ``status``, ``theme_chunk`` and terminal
# events back to its caller. Phase events ride a separate side-channel so
# they can flow even when the main generator is blocked on TTFT (no token
# arrives during prompt-eval, so a yield-based design would freeze the
# banner exactly when the user most needs feedback).
#
# Mechanics:
#   - ``_phase_emit_fn`` is set by :func:`set_phase_emitter` (the
#     extraction worker plugs ``extraction_run.append_event`` in).
#   - :func:`_emit_phase` builds + publishes a phase event using whatever
#     fields are non-None. Consumers (this module + the prompt-eval
#     poller thread) call it with whatever they have.
#   - When no emitter is registered (e.g. the section-refresh path's
#     non-streaming wrapper), phase events are dropped silently.

_phase_emit_fn: Callable[[dict], None] | None = None


def set_phase_emitter(fn: Callable[[dict], None] | None) -> None:
    """Register the SSE sink phase events should be published to.

    Pass ``None`` (or call :func:`clear_phase_emitter`) to disable phase
    emission for the next call to :func:`_emit_phase`. Only the extraction
    worker should set this — every other AI-touching code path runs
    without phase telemetry today.
    """
    global _phase_emit_fn
    _phase_emit_fn = fn


def clear_phase_emitter() -> None:
    """Drop the active phase emitter. Safe to call when none is set."""
    global _phase_emit_fn
    _phase_emit_fn = None


@dataclass
class _StructuralState:
    """Where in the multi-section / multi-chunk grid we are.

    ``None`` fields mean "not applicable" (e.g. a single-pass extraction
    has no section index; a JSON subcall has neither). The poller and
    state-transition emitters merge this into every phase event so the
    banner can render "Section 3/7, chunk 2/4" without recomputing.
    """

    section_index: int | None = None
    section_name: str | None = None
    section_total: int | None = None
    chunk_index: int | None = None
    chunk_total: int | None = None

    def snapshot(self) -> dict[str, Any] | None:
        if self.section_index is None and self.chunk_index is None:
            return None
        out: dict[str, Any] = {}
        if self.section_index is not None:
            out["section_index"] = self.section_index
        if self.section_name is not None:
            out["section_name"] = self.section_name
        if self.section_total is not None:
            out["section_total"] = self.section_total
        if self.chunk_index is not None:
            out["chunk_index"] = self.chunk_index
        if self.chunk_total is not None:
            out["chunk_total"] = self.chunk_total
        return out

    def reset(self) -> None:
        self.section_index = None
        self.section_name = None
        self.section_total = None
        self.chunk_index = None
        self.chunk_total = None


_structural = _StructuralState()


def _emit_phase(
    *,
    phase: str,
    activity: str,
    prompt_eval: dict[str, Any] | None = None,
    generation: dict[str, Any] | None = None,
    structural_override: dict[str, Any] | None = None,
) -> None:
    """Build + publish a phase event. No-op if no emitter is registered.

    ``structural_override`` lets a caller override the module-level
    :class:`_StructuralState` snapshot for a single emit (used to tag
    JSON-subcall phases with no section grid even mid-extraction).
    """
    fn = _phase_emit_fn
    if fn is None:
        return
    structural = structural_override if structural_override is not None else _structural.snapshot()
    elapsed = time.monotonic() - (_run_stats.started_at if _run_stats else time.monotonic())
    event: dict[str, Any] = {
        "type": "phase",
        "phase": phase,
        "activity": activity,
        "elapsed_s": round(elapsed, 2),
    }
    if structural is not None:
        event["structural"] = structural
    if prompt_eval is not None:
        event["prompt_eval"] = prompt_eval
    if generation is not None:
        event["generation"] = generation
    try:
        fn(event)
    except Exception as e:
        # Never let telemetry crash the run.
        logger.warning("phase emit failed: %s", e)


# =============================================================================
# Run statistics (drives the log footer)
# =============================================================================


@dataclass
class _RunStats:
    started_at: float = field(default_factory=time.monotonic)
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    retries: int = 0
    sections_with_content: int = 0
    sections_empty: int = 0
    cancelled: bool = False
    aborted_reason: str | None = None


# Module-global: safe because the shared AI lock enforces a single active run. Tests
# or ad-hoc scripts that bypass the lock MUST NOT touch this concurrently.
_run_stats: _RunStats | None = None


def _record_call(input_tokens: int, output_tokens: int, cost: float = 0.0) -> None:
    if _run_stats is not None:
        _run_stats.total_calls += 1
        _run_stats.total_input_tokens += input_tokens
        _run_stats.total_output_tokens += output_tokens
        _run_stats.total_cost_usd += cost


def _record_retry() -> None:
    if _run_stats is not None:
        _run_stats.retries += 1


# =============================================================================
# Per-run log directory
# =============================================================================
#
# llmfacade writes one JSONL (and HTML twin) per Conversation. We give every
# extraction its own subdirectory under output/extraction_logs/ so all of a
# run's calls live together and can be tail-ed / browsed as a unit. The UI
# /api/pipeline/theme/status endpoint exposes this directory path.

_run_log_dir: Path | None = None
_run_call_counter: int = 0


def _init_run_log_dir() -> Path:
    """Create a fresh per-run log directory. Resets _run_stats and the
    per-run call counter used to disambiguate per-call log filenames."""
    global _run_log_dir, _run_stats, _run_call_counter
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _run_log_dir = _LOG_DIR / f"extraction_{ts}"
    _run_log_dir.mkdir(parents=True, exist_ok=True)
    _run_stats = _RunStats()
    _run_call_counter = 0
    return _run_log_dir


def get_current_log_path() -> Path | None:
    """Directory holding the active extraction's call logs (None if idle)."""
    return _run_log_dir


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(label: str | None, fallback: str) -> str:
    if not label:
        return fallback
    s = _SLUG_RE.sub("-", label.lower()).strip("-")
    return s[:80] or fallback


def _next_call_id() -> int:
    """Monotonically increasing per-run id used to prefix log filenames so
    two calls with the same step_label slug never share a JSONL/HTML pair
    (llmfacade's HtmlLogger overwrites on each Conversation construction)."""
    global _run_call_counter
    _run_call_counter += 1
    return _run_call_counter


# =============================================================================
# Per-section definitions (used by the multi-chunk extraction path)
# =============================================================================

_SECTIONS = [
    (
        "World Overview",
        "Write 2-4 paragraphs covering: what is this world, tone, genre, "
        "central conflicts, time period, geography, what makes it distinctive.",
    ),
    (
        "Themes",
        "Bulleted list of narrative and mechanical themes suitable for an MTG set. "
        "Include both story themes and gameplay themes.",
    ),
    (
        "Creature Types",
        "List creature types with DETAILED physical descriptions - body type, "
        "coloring, size, distinguishing features, clothing/equipment. "
        "Enough for an artist to paint them. Include setting-specific AND "
        "standard MTG types as they appear in this setting.",
    ),
    (
        "Factions",
        "List organized groups, factions, military forces, cults, guilds. "
        "Include goals, visual identity (what members look like, wear, carry), "
        "where they operate. Format: faction_name: description.",
    ),
    (
        "Landmarks",
        "List significant locations, buildings, geographical features. "
        "Include visual descriptions - architecture, atmosphere, scale. "
        "Format: landmark_name: description.",
    ),
    (
        "Notable Characters",
        "List named characters who could become legendary creature or "
        "planeswalker cards. Include physical appearance in detail (build, "
        "face, hair, clothing, equipment), role, personality, faction. "
        "Format: character_name: description.",
    ),
    (
        "Races",
        "List sentient races or species, especially non-human ones. "
        "Include detailed physical description (skin, proportions, features, "
        "height), cultural notes, how they differ from similar fantasy races. "
        "Format: race_name: description.",
    ),
]


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class ExtractionPlan:
    """Pre-extraction analysis returned to the UI for confirmation."""

    text: str
    token_count: int
    context_window: int
    fits_in_context: bool
    chunk_count: int
    estimated_cost_usd: float
    model_key: str
    model_name: str


@dataclass
class ConstraintsResult:
    """Aggregated output from the constraints + card-suggestions pass."""

    constraints: list[str]
    card_suggestions: list[dict[str, str]]
    cost_usd: float
    constraints_error: str | None = None
    constraints_raw: str | None = None
    suggestions_error: str | None = None
    suggestions_raw: str | None = None
    # True if the run aborted because the AI lock was held by another action.
    # Endpoints translate this into a 409 + ai_lock.busy_payload().
    busy: bool = False


# =============================================================================
# File reading
# =============================================================================


def extract_file_content(file_bytes: bytes, filename: str) -> str:
    """Extract text from an uploaded file.

    PDF goes through PyMuPDF, everything else is decoded as UTF-8.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(file_bytes)
    return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(file_bytes: bytes) -> str:
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text: list[str] = []
    for page in doc:
        pages_text.append(page.get_text("text"))
    doc.close()
    text = "\n\n".join(pages_text)
    text = _clean_pdf_text(text)
    logger.info("PDF extracted: %d pages, %d chars", len(pages_text), len(text))
    return text


def _clean_pdf_text(text: str) -> str:
    """Strip PDF extraction artifacts (zero-width spaces, page numbers, etc.)."""
    text = text.replace("​", " ")  # zero-width space
    text = text.replace("‌", " ")  # zero-width non-joiner
    text = text.replace("‍", " ")  # zero-width joiner
    text = text.replace("﻿", "")  # BOM
    text = text.replace(" ", " ")  # non-breaking space
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =============================================================================
# Token counting / planning
# =============================================================================


def _get_system_prompt() -> str:
    return (_PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")


def count_tokens(text: str, model_key: str) -> int:
    """Count input tokens for an extraction request.

    Anthropic models use the count_tokens API (free, server-side).
    Local models use tiktoken cl100k_base as an approximation.
    """
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    system_prompt = _get_system_prompt()

    if model_info.provider == "anthropic":
        return _count_tokens_anthropic(text, system_prompt, model_info.model_id)
    return _count_tokens_tiktoken(system_prompt + "\n\n" + text)


def _count_tokens_anthropic(text: str, system_prompt: str, model_id: str) -> int:
    """Exact server-side count via llmfacade (uses the free Anthropic
    messages.count_tokens endpoint - exact_count_tokens=True is set on the
    cached provider in llm_client._get_provider).

    Use the actual single-pass user template so the count matches what we
    would really send. Falls back to a chars/4 heuristic on any error.
    """
    from mtgai.generation.llm_client import _get_provider

    try:
        single_template = (_PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
        user_content = single_template.format(text=text)
    except Exception:
        user_content = text
    try:
        provider = _get_provider("anthropic")
        full = system_prompt + "\n\n" + user_content
        return provider.count_tokens(full, model_id=model_id)
    except Exception as e:
        logger.warning("count_tokens API failed, using heuristic: %s", e)
        return (len(system_prompt) + len(user_content)) // 4


def _count_tokens_tiktoken(text: str) -> int:
    from mtgai.generation.token_utils import count_tokens as _count

    return _count(text)


def analyze_extraction(text: str, model_key: str) -> ExtractionPlan:
    """Plan an extraction: token count, chunk count, cost estimate."""
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    token_count = count_tokens(text, model_key)
    available = model_info.context_window - _OUTPUT_BUDGET
    fits = token_count <= available

    chunk_token_budget = model_info.context_window // 2
    if fits:
        chunk_count = 1
    else:
        chunk_count = max(1, math.ceil(token_count / max(chunk_token_budget, 1)))

    if fits:
        total_input_tokens = token_count
        total_output_tokens = _OUTPUT_BUDGET
    else:
        # Per-section x per-chunk. After the first chunk per section, the
        # prompt also includes the "accumulated theme so far". With the
        # compaction guard active, accumulated stays bounded by
        # _COMPACT_AT_FRACTION * chunk_budget on average.
        section_count = len(_SECTIONS)
        scaffold = 1000  # static prompt overhead per call
        accumulated_avg = int(_COMPACT_AT_FRACTION * chunk_token_budget)

        first_calls = section_count
        next_calls = section_count * (chunk_count - 1)
        # Roughly one compaction per section per "extra" chunk past the first
        # two (compaction kicks in once accumulated grows past the threshold).
        compaction_calls = section_count * max(0, chunk_count - 2)

        total_input_tokens = (
            first_calls * (chunk_token_budget + scaffold)
            + next_calls * (chunk_token_budget + accumulated_avg + scaffold)
            + compaction_calls * (accumulated_avg + scaffold)
        )
        total_output_tokens = (first_calls + next_calls) * _OUTPUT_BUDGET + compaction_calls * int(
            accumulated_avg * 0.7
        )

    estimated_cost = (
        total_input_tokens * model_info.input_price + total_output_tokens * model_info.output_price
    ) / 1_000_000

    return ExtractionPlan(
        text=text,
        token_count=token_count,
        context_window=model_info.context_window,
        fits_in_context=fits,
        chunk_count=chunk_count,
        estimated_cost_usd=estimated_cost,
        model_key=model_key,
        model_name=model_info.name,
    )


# =============================================================================
# Chunking
# =============================================================================


def _split_oversized_paragraph(para: str, max_tokens: int) -> list[str]:
    """Split a paragraph that exceeds max_tokens.

    Tries sentence boundaries first (.!? followed by whitespace). If a single
    sentence is still too big, falls back to a character-budget split (which
    can break mid-sentence - acceptable as a safety hatch for pathological
    PDFs with no sentence punctuation).
    """
    if _count_tokens_tiktoken(para) <= max_tokens:
        return [para]

    sentences = re.split(r"(?<=[.!?])\s+", para)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _count_tokens_tiktoken(sent)
        if sent_tokens > max_tokens:
            if current:
                chunks.append(" ".join(current))
                current, current_tokens = [], 0
            # Conservative chars/token. tiktoken underestimates Gemma/Qwen
            # by 10-30%, so 3x would overshoot; 2.5x leaves headroom.
            char_budget = int(max_tokens * 2.5)
            for i in range(0, len(sent), char_budget):
                chunks.append(sent[i : i + char_budget])
            continue
        if current_tokens + sent_tokens > max_tokens and current:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks


def _chunk_text_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Split text into chunks that each fit within *max_tokens*.

    Splits on paragraph boundaries (\\n\\n). An oversized paragraph is broken
    into sentence-level (then char-level) sub-chunks via
    :func:`_split_oversized_paragraph`.
    """
    total_tokens = _count_tokens_tiktoken(text)
    if total_tokens <= max_tokens:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _count_tokens_tiktoken(para)
        if para_tokens > max_tokens:
            if current:
                chunks.append("\n\n".join(current))
                current, current_tokens = [], 0
            chunks.extend(_split_oversized_paragraph(para, max_tokens))
            continue
        if current_tokens + para_tokens > max_tokens and current:
            chunks.append("\n\n".join(current))
            current, current_tokens = [], 0
        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    logger.info(
        "Token-aware chunking: %d chunks for %d tokens (budget %d/chunk)",
        len(chunks),
        total_tokens,
        max_tokens,
    )
    return chunks


# =============================================================================
# Theme extraction (top-level entry point)
# =============================================================================


def stream_theme_extraction(
    text: str,
    model_key: str,
) -> Generator[dict, None, None]:
    """Stream theme extraction from document text.

    Single extraction at a time - if a run is already in progress this yields
    an error event immediately. Use :func:`request_cancel` to abort.

    Yielded events:
        {"type": "status", "message": "..."}
        {"type": "theme_chunk", "text": "..."}
        {"type": "complete", "theme_text": "...", "cost_usd": float}
        {"type": "error", "message": "...", "log_path": "..."}
        {"type": "cancelled"}
    """
    from mtgai.settings.model_registry import get_registry

    with ai_lock.hold("Theme extraction") as acquired:
        if not acquired:
            yield {
                "type": "error",
                "busy": True,
                "message": (
                    "Another AI action is already running. "
                    "Cancel it first or wait for it to finish."
                ),
                **ai_lock.busy_payload(),
            }
            return

        registry = get_registry()
        model_info = registry.get_llm(model_key)
        if model_info is None:
            yield {"type": "error", "message": f"Unknown model key: {model_key}"}
            return

        system_prompt = _get_system_prompt()
        log_dir = _init_run_log_dir()
        ai_lock.update_log_path(log_dir)
        _structural.reset()
        _emit_phase(phase="loading", activity="Loading document")
        logger.info(
            "Starting theme extraction: model=%s provider=%s text_len=%d log_dir=%s",
            model_info.model_id,
            model_info.provider,
            len(text),
            log_dir,
        )

        try:
            available = model_info.context_window - _OUTPUT_BUDGET
            _emit_phase(phase="counting", activity="Counting tokens")
            token_count = count_tokens(text, model_key)
            logger.info(
                "Token count: %d, available budget: %d, context_window: %d",
                token_count,
                available,
                model_info.context_window,
            )

            fits = token_count <= available
            if fits:
                yield from _run_single_pass(text, system_prompt, model_info)
            else:
                yield from _run_multi_chunk(text, model_info)
        except _CancelledError:
            if _run_stats:
                _run_stats.cancelled = True
            _emit_phase(phase="done", activity="Cancelled")
            yield {"type": "cancelled"}
        except Exception as e:
            logger.error("Theme extraction failed: %s", e, exc_info=True)
            if _run_stats:
                _run_stats.aborted_reason = str(e)
            _emit_phase(phase="done", activity=f"Error: {e}")
            yield {
                "type": "error",
                "message": str(e),
                "log_path": str(_run_log_dir) if _run_log_dir else None,
            }
        finally:
            _structural.reset()


def _run_single_pass(text: str, system_prompt: str, model_info) -> Generator[dict, None, None]:
    yield {"type": "status", "message": "Generating theme..."}
    _emit_phase(phase="extracting", activity="Single-pass extraction")
    template = (_PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
    user_msg = template.format(text=text)

    # Intercept the stream so we can post-check structural completeness:
    # the single-pass path trusts the LLM to emit all 7 section headers,
    # unlike multi-chunk which builds them explicitly. Downstream consumers
    # (constraints, card-suggestion prompts, any parser that keys off
    # "# Creature Types" etc.) break silently if one is missing.
    theme_text = ""
    complete_event: dict | None = None
    for event in _stream_single_call(
        user_msg,
        system_prompt,
        model_info,
        stream_to_ui=True,
        step_label="Single-pass extraction",
        phase_kind="extracting",
        activity_prefix="Single-pass",
    ):
        etype = event.get("type")
        if etype == "theme_chunk":
            theme_text += event.get("text", "")
            yield event
        elif etype == "complete":
            complete_event = event
        else:
            yield event

    if complete_event is None:
        # No complete event arrived (upstream already yielded an error or
        # cancellation). Nothing to post-check.
        return

    final_text = complete_event.get("theme_text") or theme_text
    fixed, missing = _ensure_section_headers(final_text)
    if missing:
        warn = (
            "SINGLE-PASS STRUCTURE WARNING: model omitted section header(s): "
            + ", ".join(missing)
            + ". Injected empty stubs so downstream parsers don't break."
        )
        logger.warning(warn)
        yield {
            "type": "status",
            "message": (
                f"Model omitted {len(missing)} section header(s): "
                f"{', '.join(missing)}. Added empty stubs."
            ),
        }
        complete_event = dict(complete_event)
        complete_event["theme_text"] = fixed
    yield complete_event


def _ensure_section_headers(text: str) -> tuple[str, list[str]]:
    """Guarantee all 7 canonical section headers are present in *text*.

    Returns (possibly_repaired_text, list_of_missing_header_names).
    """
    missing: list[str] = []
    # Use a case-insensitive match to catch "# creature types" etc.
    lower = text.lower()
    to_append: list[str] = []
    for sec_name, _ in _SECTIONS:
        marker = f"# {sec_name.lower()}"
        if marker not in lower:
            missing.append(sec_name)
            to_append.append(f"# {sec_name}\n\nNo information found.")
    if not missing:
        return text, []
    repaired = text.rstrip() + "\n\n" + "\n\n".join(to_append) + "\n"
    return repaired, missing


def _run_multi_chunk(text: str, model_info) -> Generator[dict, None, None]:
    chunk_token_budget = model_info.context_window // 2
    chunks = _chunk_text_by_tokens(text, chunk_token_budget)
    for ci, ch in enumerate(chunks):
        ch_tokens = _count_tokens_tiktoken(ch)
        logger.info(
            "  Chunk %d: %d chars, %d tokens (budget: %d)",
            ci + 1,
            len(ch),
            ch_tokens,
            chunk_token_budget,
        )
    logger.info(
        "Per-section extraction: %d sections x %d chunks",
        len(_SECTIONS),
        len(chunks),
    )

    yield {
        "type": "status",
        "message": (
            f"Large document - extracting {len(_SECTIONS)} sections across {len(chunks)} chunks..."
        ),
    }

    sys_template = (_PROMPTS_DIR / "theme_section_system.txt").read_text(encoding="utf-8")
    first_template = (_PROMPTS_DIR / "theme_section_first.txt").read_text(encoding="utf-8")
    next_template = (_PROMPTS_DIR / "theme_section_next.txt").read_text(encoding="utf-8")
    compact_template = (_PROMPTS_DIR / "theme_section_compact.txt").read_text(encoding="utf-8")

    completed_sections: list[str] = []
    total_cost = 0.0

    accumulated_max_tokens = int(_COMPACT_AT_FRACTION * chunk_token_budget)
    compact_target_tokens = int(accumulated_max_tokens * 0.7)

    for sec_idx, (sec_name, sec_guidance) in enumerate(_SECTIONS):
        _check_cancelled()
        _structural.section_index = sec_idx + 1
        _structural.section_total = len(_SECTIONS)
        _structural.section_name = sec_name
        _structural.chunk_total = len(chunks)
        _structural.chunk_index = None
        logger.info("=== Section %d/%d: %s ===", sec_idx + 1, len(_SECTIONS), sec_name)
        yield {
            "type": "status",
            "message": (f"Extracting {sec_name} ({sec_idx + 1}/{len(_SECTIONS)})..."),
        }
        _emit_phase(
            phase="extracting",
            activity=f"Extracting {sec_name} ({sec_idx + 1}/{len(_SECTIONS)})",
        )
        logger.info("Section %d/%d: %s", sec_idx + 1, len(_SECTIONS), sec_name)

        section_prompt = sys_template.format(
            section_name=sec_name,
            section_guidance=sec_guidance,
        )
        accumulated = ""

        for ci, chunk_part in enumerate(chunks):
            _check_cancelled()
            _structural.chunk_index = ci + 1

            # --- Compaction guard --------------------------------------------
            # Before the next "next" call, if accumulated has grown past the
            # threshold, ask the model to compact it. Information loss is
            # accepted (it is the explicit trade-off of staying in budget).
            if accumulated and ci > 0:
                acc_tokens = _count_tokens_tiktoken(accumulated)
                if acc_tokens > accumulated_max_tokens:
                    yield {
                        "type": "status",
                        "message": (
                            f"{sec_name}: compacting (accumulated {acc_tokens} tok > "
                            f"{accumulated_max_tokens}) before chunk {ci + 1}/{len(chunks)}..."
                        ),
                    }
                    _emit_phase(
                        phase="compacting",
                        activity=(
                            f"Compacting {sec_name} "
                            f"({acc_tokens:,} tok > {accumulated_max_tokens:,} budget)"
                        ),
                    )
                    logger.info(
                        "  compaction trigger: %s accumulated=%d > %d",
                        sec_name,
                        acc_tokens,
                        accumulated_max_tokens,
                    )
                    compact_msg = compact_template.format(
                        section_name=sec_name,
                        accumulated=accumulated,
                        target_tokens=compact_target_tokens,
                    )
                    compact_label = (
                        f"COMPACTION section {sec_idx + 1}/{len(_SECTIONS)} "
                        f"{sec_name} ({acc_tokens} tok -> target {compact_target_tokens})"
                    )
                    compact_result = ""
                    compact_cost = 0.0
                    compact_failed = False
                    compact_err = ""
                    for event in _stream_single_call(
                        compact_msg,
                        section_prompt,
                        model_info,
                        stream_to_ui=False,
                        step_label=compact_label,
                        phase_kind="compacting",
                        activity_prefix=f"Compacting {sec_name}",
                    ):
                        if event["type"] == "theme_chunk":
                            compact_result += event["text"]
                        elif event["type"] == "complete":
                            compact_result = event.get("theme_text", compact_result)
                            compact_cost += event.get("cost_usd", 0)
                        elif event["type"] == "error":
                            compact_err = event.get("message", "unknown")
                            logger.warning(
                                "Compaction failed for %s: %s; truncating instead",
                                sec_name,
                                compact_err,
                            )
                            compact_failed = True
                            break
                    total_cost += compact_cost
                    if compact_failed or not compact_result.strip():
                        # Fallback: hard-truncate. Keep the first slice
                        # (founding entries, likely the ones that came up
                        # early) AND the last slice (most recently added
                        # from the chunk that just triggered compaction)
                        # with a gap marker in the middle. Losing the
                        # middle hurts less than losing either end, and
                        # the previous head-only approach silently
                        # dropped the just-added chunk's contribution.
                        head_frac = 0.35
                        tail_frac = 0.35
                        head_n = int(len(accumulated) * head_frac)
                        tail_n = int(len(accumulated) * tail_frac)
                        accumulated = (
                            accumulated[:head_n].rstrip()
                            + "\n\n[middle entries truncated to stay within budget]\n\n"
                            + accumulated[-tail_n:].lstrip()
                        )
                        logger.info(
                            "  compaction fallback (hard-truncate head+tail): "
                            "%s -> %d chars (reason: %s)",
                            sec_name,
                            len(accumulated),
                            compact_err or "empty result",
                        )
                    else:
                        new_acc = compact_result.strip()
                        new_tok = _count_tokens_tiktoken(new_acc)
                        accumulated = new_acc
                        logger.info(
                            "  compacted %s: %d -> %d tokens",
                            sec_name,
                            acc_tokens,
                            new_tok,
                        )

            yield {
                "type": "status",
                "message": (
                    f"{sec_name} ({sec_idx + 1}/{len(_SECTIONS)}): chunk {ci + 1}/{len(chunks)}..."
                ),
            }
            chunk_activity = (
                f"{sec_name} (sec {sec_idx + 1}/{len(_SECTIONS)}, chunk {ci + 1}/{len(chunks)})"
            )
            _emit_phase(phase="extracting", activity=chunk_activity)

            if ci == 0:
                user_msg = first_template.format(
                    section_name=sec_name,
                    chunk_num=ci + 1,
                    total_chunks=len(chunks),
                    chunk_text=chunk_part,
                )
            else:
                user_msg = next_template.format(
                    section_name=sec_name,
                    chunk_num=ci + 1,
                    total_chunks=len(chunks),
                    accumulated=accumulated,
                    chunk_text=chunk_part,
                )

            chunk_label = (
                f"Section {sec_idx + 1}/{len(_SECTIONS)} {sec_name} "
                f"chunk {ci + 1}/{len(chunks)}"
                f"{' (first)' if ci == 0 else ' (next)'}"
            )

            chunk_result = ""
            for event in _stream_single_call(
                user_msg,
                section_prompt,
                model_info,
                stream_to_ui=False,
                step_label=chunk_label,
                phase_kind="extracting",
                activity_prefix=chunk_activity,
            ):
                if event["type"] == "theme_chunk":
                    chunk_result += event["text"]
                elif event["type"] == "complete":
                    chunk_result = event.get("theme_text", chunk_result)
                    total_cost += event.get("cost_usd", 0)
                elif event["type"] == "error":
                    err_msg = f"{sec_name} chunk {ci + 1}/{len(chunks)} failed: {event['message']}"
                    if _run_stats and not _run_stats.aborted_reason:
                        _run_stats.aborted_reason = err_msg
                    logger.error("ABORT: %s", err_msg)
                    yield {
                        "type": "error",
                        "message": err_msg,
                        "log_path": str(_run_log_dir) if _run_log_dir else None,
                    }
                    return

            stripped = chunk_result.strip()
            if _looks_like_no_info(stripped):
                logger.info(
                    "  chunk %d/%d: no info for %s",
                    ci + 1,
                    len(chunks),
                    sec_name,
                )
                continue

            # --- Copy-through diff guard ----------------------------------
            # "next" calls ask the model to output existing entries + new
            # ones. Models sometimes drop existing entries in the rewrite.
            # Warn when the output is meaningfully shorter than what we fed
            # in, so the log surfaces silent information loss.
            if ci > 0 and accumulated:
                old_len = len(accumulated)
                new_len = len(stripped)
                # "Much shorter" = below 70% of prior length.
                if new_len < int(old_len * 0.7):
                    warn = (
                        f"COPY-THROUGH SHRINK: {sec_name} chunk "
                        f"{ci + 1}/{len(chunks)} shrank accumulated "
                        f"{old_len} -> {new_len} chars "
                        f"({new_len / max(old_len, 1):.0%}). Model likely "
                        f"dropped existing entries."
                    )
                    logger.warning(warn)
                    yield {
                        "type": "status",
                        "message": (
                            f"{sec_name} chunk {ci + 1}: model shrank "
                            f"accumulated {old_len} -> {new_len} chars; "
                            f"entries may have been dropped (see log)."
                        ),
                    }

            accumulated = stripped
            logger.info(
                "  chunk %d/%d: %d chars for %s",
                ci + 1,
                len(chunks),
                len(stripped),
                sec_name,
            )

        if accumulated:
            section_text = f"# {sec_name}\n\n{accumulated}"
            if _run_stats:
                _run_stats.sections_with_content += 1
        else:
            section_text = f"# {sec_name}\n\nNo information found."
            if _run_stats:
                _run_stats.sections_empty += 1
        completed_sections.append(section_text)

        separator = "\n\n" if sec_idx > 0 else ""
        yield {"type": "theme_chunk", "text": f"{separator}{section_text}"}
        logger.info("Section %s complete: %d chars", sec_name, len(accumulated))

    full_theme = "\n\n".join(completed_sections)
    yield {
        "type": "complete",
        "theme_text": full_theme,
        "cost_usd": total_cost,
    }


# =============================================================================
# LLM call dispatch
# =============================================================================


def _stream_single_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool = True,
    json_mode: bool = False,
    step_label: str | None = None,
    output_budget_override: int | None = None,
    repeat_penalty_override: float | None = None,
    temperature_override: float | None = None,
    phase_kind: str = "extracting",
    activity_prefix: str = "",
) -> Generator[dict, None, None]:
    """Dispatch one streaming call to the configured provider.

    Yields theme_chunk events (if *stream_to_ui*), then a final ``complete``
    event with the full text and cost - or an ``error`` event on failure.

    ``step_label`` tags the call in the conversation log filename (e.g.
    "section-3-7-creature-types-chunk-4-10"). If None, a generic name is used.

    ``output_budget_override`` forces a specific llamacpp ``max_tokens`` for
    this call (ignored on Anthropic, which uses its own fixed max_tokens).

    ``repeat_penalty_override`` overrides the provider-default llamacpp
    repeat_penalty for this call (ignored on Anthropic). Used by the JSON
    subcall retry loop to escalate the penalty on repetition-loop retries.

    ``phase_kind`` and ``activity_prefix`` thread the live-progress phase
    label through to the llamacpp prompt-eval poller. Anthropic ignores
    them (no analogous /slots introspection).
    """
    if model_info.provider == "anthropic":
        yield from _stream_anthropic_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            step_label=step_label,
        )
    elif model_info.provider == "llamacpp":
        yield from _stream_llamacpp_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            json_mode=json_mode,
            step_label=step_label,
            output_budget_override=output_budget_override,
            repeat_penalty_override=repeat_penalty_override,
            temperature_override=temperature_override,
            phase_kind=phase_kind,
            activity_prefix=activity_prefix,
        )
    else:
        yield {
            "type": "error",
            "message": f"Unsupported provider: {model_info.provider}",
        }


def _build_call_log_path(step_label: str | None, fallback: str) -> Path | None:
    """Return the per-call jsonl path under the active run dir, or None.

    Filename is ``<NNN>-<slug>.jsonl`` where NNN is a per-run call counter -
    guarantees uniqueness so retries / repeated compactions don't collide
    on the HTML twin (llmfacade's HtmlLogger overwrites the .html on each
    Conversation construction even when the .jsonl is append-only)."""
    if _run_log_dir is None:
        return None
    n = _next_call_id()
    return _run_log_dir / f"{n:03d}-{_slugify(step_label, fallback)}.jsonl"


def _write_call_meta(jsonl_path: Path | None, data: dict) -> None:
    """Write MTGAI-derived per-call diagnostics to ``<NNN>-<slug>.meta.json``.

    llmfacade owns the .jsonl (raw stream events, prompts, usage); this is
    our sibling file for derived counters and outcomes that don't fit its
    format - frame tallies for buffering diagnosis, finish_reason, outcome
    classification, etc. No-op if jsonl_path is None (no run dir active).
    Best-effort: a failed write logs a warning but never raises."""
    if jsonl_path is None:
        return
    meta_path = jsonl_path.with_suffix(".meta.json")
    try:
        meta_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write call meta to %s: %s", meta_path, e)


def _stream_anthropic_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    step_label: str | None = None,
) -> Generator[dict, None, None]:
    """Single Anthropic streaming call via llmfacade.

    System prompt is marked cacheable; the provider also has
    auto_cache_tools=True (no tools here, but harmless). The cached prefix
    survives across calls within the 5-minute TTL window, so per-section
    multi-chunk runs share the system-block discount.
    """
    from mtgai.generation.llm_client import _get_provider, calc_cost

    provider = _get_provider("anthropic")
    facade_model = provider.new_model(model_info.model_id)
    log_path = _build_call_log_path(step_label, "anthropic-call")
    convo = facade_model.new_conversation(
        system_blocks=[SystemBlock(text=system_prompt, cache=True)],
        max_tokens=_OUTPUT_BUDGET,
        temperature=0.7,
        log_path=log_path,
        log_max_message_lines=_LOG_MAX_MESSAGE_LINES,
    )

    theme_text = ""
    last_usage = None
    cost = 0.0
    frames_total = 0
    frames_with_content = 0
    meta: dict[str, Any] = {
        "provider": "anthropic",
        "model_id": model_info.model_id,
        "step_label": step_label,
        "outcome": "unknown",
    }
    try:
        try:
            for ev in convo.stream(user_msg):
                if ai_lock.is_cancelled():
                    meta["outcome"] = "cancelled"
                    raise _CancelledError("cancelled mid-stream")
                frames_total += 1
                if ev.text_delta:
                    frames_with_content += 1
                    theme_text += ev.text_delta
                    if stream_to_ui:
                        yield {"type": "theme_chunk", "text": ev.text_delta}
                if ev.usage is not None:
                    last_usage = ev.usage
        except _CancelledError:
            raise
        except Exception as e:
            logger.error("Anthropic streaming call failed: %s", e, exc_info=True)
            meta["outcome"] = "stream_exception"
            meta["error"] = str(e)
            yield {
                "type": "error",
                "message": str(e),
                "partial_text": theme_text,
            }
            return

        if last_usage is not None:
            cost = calc_cost(
                model_info.model_id,
                last_usage.prompt_tokens,
                last_usage.completion_tokens,
                cache_creation_input_tokens=last_usage.cache_creation_tokens,
                cache_read_input_tokens=last_usage.cache_read_tokens,
            )
            _record_call(
                last_usage.prompt_tokens
                + last_usage.cache_creation_tokens
                + last_usage.cache_read_tokens,
                last_usage.completion_tokens,
                cost,
            )

        logger.info("Anthropic call complete: %d chars, cost=$%.4f", len(theme_text), cost)
        meta["outcome"] = "complete"
        meta["cost_usd"] = cost
        yield {"type": "complete", "theme_text": theme_text, "cost_usd": cost}
    finally:
        meta["frames_total"] = frames_total
        meta["frames_with_content"] = frames_with_content
        meta["theme_text_chars"] = len(theme_text)
        if last_usage is not None:
            meta["prompt_tokens"] = last_usage.prompt_tokens
            meta["completion_tokens"] = last_usage.completion_tokens
            meta["cache_creation_tokens"] = last_usage.cache_creation_tokens
            meta["cache_read_tokens"] = last_usage.cache_read_tokens
        _write_call_meta(log_path, meta)


class _NullPoller:
    """No-op stand-in used when no phase emitter is registered.

    Lets the streaming loop wear a single ``with`` shape without paying
    for a polling thread it'd publish nothing through (the section-refresh
    non-streaming path is the canonical case).
    """

    def __enter__(self) -> _NullPoller:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


_NULL_POLLER = _NullPoller()


class _PromptEvalPoller:
    """Background poller that surfaces ``/slots`` introspection as phase events.

    Started for the lifetime of a llamacpp streaming call. Polls every
    ``poll_interval`` seconds; emits a ``phase`` event whenever the
    observed prompt-eval or generation counters move materially.

    Lifecycle:
        with _PromptEvalPoller(provider, model_id, phase_kind="extracting"):
            for ev in convo.stream(...): ...

    The poller runs on a daemon thread so a stuck HTTP probe can never
    block process shutdown. Errors during a poll are swallowed and
    logged at debug — telemetry must never crash the run.
    """

    # Don't spam events — only emit when prompt-eval token count moves by
    # at least this fraction of total or this many tokens, whichever is
    # smaller. Keeps the SSE stream readable on long prompt-eval spans.
    _MIN_DELTA_TOKENS = 200
    _MIN_DELTA_FRACTION = 0.01

    def __init__(
        self,
        provider: Any,
        model_id: str,
        phase_kind: str,
        activity_prefix: str,
        poll_interval: float = 0.5,
    ) -> None:
        self._provider = provider
        self._model_id = model_id
        self._phase_kind = phase_kind
        self._activity_prefix = activity_prefix
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_processed = -1
        self._last_total = -1
        self._last_decoded = -1
        self._gen_started_at: float | None = None
        self._switched_to_generation = False

    def __enter__(self) -> _PromptEvalPoller:
        self._thread = threading.Thread(
            target=self._loop,
            name="theme-prompt-eval-poller",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            try:
                slots = self._provider.slots(model=self._model_id)
            except Exception as e:
                logger.debug("slots poll failed (transient): %s", e)
                continue
            active = next(
                (s for s in slots if s.get("is_processing")),
                None,
            )
            if active is None:
                continue
            self._publish(active)

    def _publish(self, slot: dict[str, Any]) -> None:
        processed = int(slot.get("n_prompt_tokens_processed") or 0)
        total = int(slot.get("n_prompt_tokens") or 0)
        decoded = int(slot.get("n_decoded") or 0)

        # Once decoding starts we switch to generation phase. Each tick
        # past that point reports tokens + tok/s; the prompt-eval bar
        # gets replaced with an indeterminate animation client-side.
        if decoded > 0:
            if not self._switched_to_generation:
                self._switched_to_generation = True
                self._gen_started_at = time.monotonic()
            self._publish_generation(decoded)
            return

        if total <= 0:
            return
        if not self._should_emit_prompt_eval(processed, total):
            return
        self._last_processed = processed
        self._last_total = total
        _emit_phase(
            phase=self._phase_kind,
            activity=f"{self._activity_prefix} — processing prompt {processed:,}/{total:,}",
            prompt_eval={"processed": processed, "total": total},
        )

    def _publish_generation(self, decoded: int) -> None:
        # Every poll while decoding emits a generation tick so the UI's
        # tok/s display refreshes. No min-delta gate here — at 0.5s
        # interval the rate is naturally bounded.
        if decoded == self._last_decoded:
            return
        self._last_decoded = decoded
        elapsed = (
            time.monotonic() - self._gen_started_at if self._gen_started_at is not None else 0.0
        )
        tok_per_sec = decoded / elapsed if elapsed > 0 else 0.0
        activity = (
            f"{self._activity_prefix} — generating ({decoded:,} tok @ {tok_per_sec:.1f} tok/s)"
        )
        _emit_phase(
            phase="generation",
            activity=activity,
            generation={
                "tokens": decoded,
                "tok_per_sec": round(tok_per_sec, 2),
                "elapsed_s": round(elapsed, 2),
            },
        )

    def _should_emit_prompt_eval(self, processed: int, total: int) -> bool:
        if processed <= self._last_processed and total == self._last_total:
            return False
        if self._last_processed < 0:
            return True
        delta = processed - self._last_processed
        if delta >= self._MIN_DELTA_TOKENS:
            return True
        if total > 0 and delta / total >= self._MIN_DELTA_FRACTION:
            return True
        # Always emit the first sighting and the final tick (processed == total).
        return processed == total


def _stream_llamacpp_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    json_mode: bool = False,
    step_label: str | None = None,
    output_budget_override: int | None = None,
    repeat_penalty_override: float | None = None,
    temperature_override: float | None = None,
    phase_kind: str = "extracting",
    activity_prefix: str = "",
) -> Generator[dict, None, None]:
    """Single llamacpp streaming call via llmfacade.

    Pre-checks input fits in context, post-checks llmfacade Usage for
    truncation. Also runs MTGAI's mid-stream repetition detector every 64
    chars — local models (Gemma 4 in particular) sometimes loop forever
    inside ``max_tokens``, and breaking the iterator early salvages the
    pre-loop text.

    ``output_budget_override`` overrides the default ``max_tokens`` for
    this call (used by JSON subcalls that need a larger output budget).

    ``phase_kind`` and ``activity_prefix`` are forwarded into the
    prompt-eval poller so its tick events stay tagged with whatever the
    higher-level call site is doing (e.g. "extracting" + "Creature Types
    chunk 2/4").
    """
    from mtgai.generation.llm_client import _get_provider, _llamacpp_new_model
    from mtgai.generation.token_utils import (
        SAFETY_MARGIN,
        InputTruncatedError,
        OutputTruncatedError,
        check_post_call,
        count_messages_tokens,
    )

    num_ctx = model_info.context_window
    if output_budget_override is not None:
        output_reserve = output_budget_override
    elif json_mode:
        output_reserve = _JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS
    else:
        output_reserve = _OUTPUT_BUDGET

    legacy_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    estimated_input_tokens = count_messages_tokens(legacy_messages)
    safe_budget = int(num_ctx * (1 - SAFETY_MARGIN)) - output_reserve

    if estimated_input_tokens > safe_budget:
        msg = (
            f"Input too large for {model_info.model_id}: ~{estimated_input_tokens} "
            f"tokens estimated, only {safe_budget} available "
            f"(context_size={num_ctx}, output_reserve={output_reserve}). "
            f"Reduce input or increase context window."
        )
        logger.error(msg)
        yield {"type": "error", "message": msg}
        return

    logger.info(
        "llamacpp call: model=%s, est_input=%d tok, ctx=%d, output_reserve=%d",
        model_info.model_id,
        estimated_input_tokens,
        num_ctx,
        output_reserve,
    )

    provider = _get_provider("llamacpp")
    facade_model = _llamacpp_new_model(provider, model_info.model_id)
    log_path = _build_call_log_path(step_label, "llamacpp-call")
    effective_temperature = temperature_override if temperature_override is not None else 0.7
    convo_kwargs: dict[str, Any] = {
        "system_blocks": [SystemBlock(text=system_prompt)],
        "max_tokens": output_reserve,
        "temperature": effective_temperature,
        "log_path": log_path,
        "log_max_message_lines": _LOG_MAX_MESSAGE_LINES,
    }
    if json_mode:
        convo_kwargs["output_format"] = "json"
    if repeat_penalty_override is not None:
        # Per-call override of provider-default repeat_penalty. Forwarded by
        # llmfacade through OpenAI-compat extra_body to llama-server, where
        # the sampler actually honours it (unlike the retired Ollama path).
        convo_kwargs["repeat_penalty"] = repeat_penalty_override
    convo = facade_model.new_conversation(**convo_kwargs)

    theme_text = ""
    loop_err: str | None = None
    chars_since_check = 0
    last_usage = None
    last_finish_reason: str | None = None
    frames_total = 0
    frames_with_content = 0
    meta: dict[str, Any] = {
        "provider": "llamacpp",
        "model_id": model_info.model_id,
        "step_label": step_label,
        "json_mode": json_mode,
        "context_size": num_ctx,
        "output_reserve": output_reserve,
        "estimated_input_tokens": estimated_input_tokens,
        "outcome": "unknown",
    }
    if repeat_penalty_override is not None:
        meta["repeat_penalty"] = repeat_penalty_override
    if temperature_override is not None:
        meta["temperature"] = temperature_override

    try:
        stream_iter = convo.stream(user_msg, stop=_LLAMACPP_STOP_SEQUENCES)
        # Poller runs only while the stream is open. Skip it when no
        # phase emitter is registered (no SSE consumer to receive ticks)
        # so the section-refresh non-streaming path doesn't pay for HTTP
        # probes whose output goes nowhere.
        poller_ctx: Any = (
            _PromptEvalPoller(
                provider=provider,
                model_id=model_info.model_id,
                phase_kind=phase_kind,
                activity_prefix=activity_prefix,
            )
            if _phase_emit_fn is not None
            else _NULL_POLLER
        )
        try:
            with poller_ctx:
                for ev in stream_iter:
                    if ai_lock.is_cancelled():
                        meta["outcome"] = "cancelled"
                        raise _CancelledError("cancelled mid-stream")
                    frames_total += 1
                    if ev.text_delta:
                        frames_with_content += 1
                        theme_text += ev.text_delta
                        if stream_to_ui:
                            yield {"type": "theme_chunk", "text": ev.text_delta}
                        chars_since_check += len(ev.text_delta)
                        if chars_since_check >= 64:
                            chars_since_check = 0
                            loop_err = _detect_repetition_loop(theme_text)
                            if loop_err:
                                logger.warning(
                                    "Repetition loop detected mid-stream after %d chars: %s",
                                    len(theme_text),
                                    loop_err,
                                )
                                break
                    if ev.usage is not None:
                        last_usage = ev.usage
                    if ev.finish_reason is not None:
                        last_finish_reason = ev.finish_reason
        except _CancelledError:
            raise
        except Exception as e:
            logger.error("llamacpp streaming call failed: %s", e, exc_info=True)
            meta["outcome"] = "stream_exception"
            meta["error"] = str(e)
            yield {
                "type": "error",
                "message": str(e),
                "partial_text": theme_text,
            }
            return
        finally:
            # convo.stream() returns a Generator at runtime; closing it eagerly
            # releases the underlying HTTP connection on early break (cancel,
            # repetition-loop). getattr keeps the static Iterator type annotation
            # happy.
            close = getattr(stream_iter, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:
                    pass

        if loop_err:
            logger.info(
                "llamacpp call aborted (repetition): %d chars before abort",
                len(theme_text),
            )
            # No usage frame on early-break; record with our estimate so the
            # run footer doesn't undercount aborted calls.
            _record_call(
                last_usage.prompt_tokens if last_usage else estimated_input_tokens,
                last_usage.completion_tokens if last_usage else _count_tokens_tiktoken(theme_text),
                0.0,
            )
            meta["outcome"] = "repetition_abort"
            meta["error"] = loop_err
            yield {
                "type": "error",
                "message": loop_err,
                "partial_text": theme_text,
            }
            return

        if last_usage is None:
            msg = (
                f"llamacpp stream ended with no usage frame after {len(theme_text)} "
                "chars. Possible connection drop or server error."
            )
            logger.error(msg)
            _record_call(
                estimated_input_tokens,
                _count_tokens_tiktoken(theme_text),
                0.0,
            )
            meta["outcome"] = "no_usage_frame"
            meta["error"] = msg
            yield {
                "type": "error",
                "message": msg,
                "partial_text": theme_text,
            }
            return

        _record_call(
            last_usage.prompt_tokens or estimated_input_tokens,
            last_usage.completion_tokens,
            0.0,
        )
        logger.info(
            "llamacpp call complete: %d chars, prompt_tokens=%d, completion_tokens=%d, "
            "frames_total=%d, frames_with_content=%d",
            len(theme_text),
            last_usage.prompt_tokens,
            last_usage.completion_tokens,
            frames_total,
            frames_with_content,
        )

        try:
            check_post_call(
                {
                    "prompt_tokens": last_usage.prompt_tokens,
                    "completion_tokens": last_usage.completion_tokens,
                    "finish_reason": last_finish_reason or "",
                },
                estimated_input_tokens=estimated_input_tokens,
                model=model_info.model_id,
                num_predict=output_reserve,
            )
        except (InputTruncatedError, OutputTruncatedError) as trunc:
            logger.warning("Truncation detected: %s", trunc)
            meta["outcome"] = "truncated"
            meta["error"] = str(trunc)
            yield {
                "type": "error",
                "message": str(trunc),
                "partial_text": theme_text,
            }
            return

        meta["outcome"] = "complete"
        yield {"type": "complete", "theme_text": theme_text, "cost_usd": 0.0}
    finally:
        meta["frames_total"] = frames_total
        meta["frames_with_content"] = frames_with_content
        meta["theme_text_chars"] = len(theme_text)
        if last_usage is not None:
            meta["prompt_tokens"] = last_usage.prompt_tokens
            meta["completion_tokens"] = last_usage.completion_tokens
        if last_finish_reason is not None:
            meta["finish_reason"] = last_finish_reason
        _write_call_meta(log_path, meta)


# =============================================================================
# Repetition loop detection
# =============================================================================


# Tail size for the suffix-periodicity scan. Bounded so the detector cost
# stays trivial regardless of total stream length.
_REPETITION_TAIL_CHARS = 4096

# Largest period we scan for. Beyond this, the per-call cost grows and real
# LLM loops are vanishingly rare (degeneration cycles are short phrases).
_REPETITION_MAX_PERIOD = 120


# Period-length-aware confidence thresholds. Index = period in characters.
# A hit requires both: (1) at least MIN_REPS[p] consecutive copies of the
# period at the suffix, and (2) total repeated content >= MIN_TOTAL[p] chars.
# Probability of a random tandem repeat at the suffix falls geometrically
# with period length, so longer periods need fewer reps to be confident.
def _build_repetition_thresholds() -> tuple[list[int], list[int]]:
    reps = [0] * (_REPETITION_MAX_PERIOD + 1)
    total = [0] * (_REPETITION_MAX_PERIOD + 1)
    bands = [
        (1, 1, 20, 20),
        (2, 4, 8, 24),
        (5, 10, 5, 30),
        (11, 25, 4, 50),
        (26, 60, 3, 90),
        (61, _REPETITION_MAX_PERIOD, 2, 130),
    ]
    for lo, hi, r, t in bands:
        for p in range(lo, hi + 1):
            reps[p] = r
            total[p] = t
    return reps, total


_MIN_REPS_BY_PERIOD, _MIN_TOTAL_BY_PERIOD = _build_repetition_thresholds()


def _detect_tandem_repeat(text: str) -> str | None:
    """Detect a tandem repeat at the suffix of ``text``.

    Scans the last ``_REPETITION_TAIL_CHARS`` of the buffer for the smallest
    period ``p`` (1..``_REPETITION_MAX_PERIOD``) such that the suffix consists
    of at least ``_MIN_REPS_BY_PERIOD[p]`` consecutive copies of a ``p``-char
    window, totalling at least ``_MIN_TOTAL_BY_PERIOD[p]`` characters.

    Iterating ``p`` upward and returning on the first hit guarantees the
    canonical smallest period (Fine and Wilf): reporting ``p=8 "thethethe"``
    when the real period is ``3 "the"`` would distort the threshold check.

    The period window must contain at least one alphanumeric character. This
    suppresses realistic non-loop patterns that look superficially periodic
    (ASCII-art separators, markdown horizontal rules ``"-"*N``, table borders
    ``"|---|---|"``, blank-fill underscores, runs of whitespace). Real LLM
    repetition loops always cycle through tokens with letters/digits.

    Returns a human-readable hit description or ``None``.
    """
    if not text:
        return None
    tail = text[-_REPETITION_TAIL_CHARS:]
    n = len(tail)
    max_p = min(_REPETITION_MAX_PERIOD, n // 2)
    for p in range(1, max_p + 1):
        window = tail[n - p :]
        if not any(c.isalnum() for c in window):
            continue
        copies = 1
        while n - p * (copies + 1) >= 0 and (tail[n - p * (copies + 1) : n - p * copies] == window):
            copies += 1
        if copies >= _MIN_REPS_BY_PERIOD[p] and p * copies >= _MIN_TOTAL_BY_PERIOD[p]:
            display = window if len(window) <= 40 else window[:37] + "..."
            return f"Period {display!r} (len={p}) repeated {copies}+ times at tail"
    return None


def _detect_repetition_loop(text: str) -> str | None:
    """Public detector entry point. See :func:`_detect_tandem_repeat`."""
    return _detect_tandem_repeat(text)


# =============================================================================
# Constraints + card-suggestions extraction (second pass)
# =============================================================================


def _attempt_json_subcall(
    theme_text: str,
    model_info,
    prompt: str,
    json_key: str,
    step_label: str,
    output_budget: int,
    repeat_penalty_override: float | None = None,
    temperature_override: float | None = None,
    activity_prefix: str = "",
) -> tuple[list, str | None, str]:
    raw = ""
    stream_err: str | None = None
    try:
        for event in _stream_single_call(
            f"Setting:\n\n{theme_text}",
            prompt,
            model_info,
            stream_to_ui=False,
            json_mode=True,
            step_label=step_label,
            output_budget_override=output_budget,
            repeat_penalty_override=repeat_penalty_override,
            temperature_override=temperature_override,
            phase_kind="json_subcall",
            activity_prefix=activity_prefix,
        ):
            if event["type"] == "complete":
                raw = event.get("theme_text", "")
            elif event["type"] == "error":
                stream_err = event.get("message") or "stream error"
                # Preserve partial streamed content so the UI error panel
                # and the retry-aggregation loop can show what the model
                # produced before TRUNCATION / repetition abort. Without
                # this the raw field stays "" and failed attempts look
                # empty even though 4K tokens of JSON streamed out.
                partial = event.get("partial_text")
                if partial and not raw:
                    raw = partial
    except _CancelledError:
        raise
    except Exception as exc:
        stream_err = f"{type(exc).__name__}: {exc}"
        logger.exception("subcall stream raised")

    if stream_err:
        return [], f"Stream failed: {stream_err}", raw

    loop_err = _detect_repetition_loop(raw)
    if loop_err:
        return [], loop_err, raw

    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        return [], f"Malformed JSON output ({exc.msg} at pos {exc.pos})", raw

    items = parsed.get(json_key, [])
    if not isinstance(items, list):
        return (
            [],
            f"Expected list at '{json_key}', got {type(items).__name__}",
            raw,
        )
    return items, None, raw


def _run_json_subcall(
    theme_text: str,
    model_info,
    label: str,
    prompt_file: str,
    json_key: str,
    output_budget: int,
) -> Generator[dict, None, tuple[list, str | None, str]]:
    from mtgai.generation.llm_client import MAX_RETRIES

    prompt = (_PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
    # Collect every attempt so the UI error surface shows the full
    # retry history, not just the final attempt.
    attempts: list[tuple[int, str, str]] = []  # (attempt_no, err, raw)

    for attempt in range(1, MAX_RETRIES + 1):
        _check_cancelled()
        # Escalate repeat_penalty on retries so a model that fell into a
        # tandem-repeat on attempt 1 has a real chance of breaking out on
        # attempt 2/3. repeat_penalty actually moves the sampler now that
        # we're on llama.cpp (Ollama silently dropped it on Gemma-class
        # models). Temperature stays at the provider default — escalating
        # it produced malformed JSON on smaller models.
        rp_override = (
            _RETRY_REPEAT_PENALTIES[attempt - 1]
            if attempt - 1 < len(_RETRY_REPEAT_PENALTIES)
            else _RETRY_REPEAT_PENALTIES[-1]
        )

        knob_note = f", repeat_penalty={rp_override}" if rp_override is not None else ""

        last_err = attempts[-1][1] if attempts else None
        if attempt == 1:
            yield {"type": "status", "message": f"{label}..."}
            _emit_phase(
                phase="json_subcall",
                activity=label,
                structural_override={
                    "section_name": label,
                    "attempt": attempt,
                    "attempt_total": MAX_RETRIES,
                },
            )
        else:
            yield {
                "type": "status",
                "message": (
                    f"{label}: retry attempt {attempt}/{MAX_RETRIES} "
                    f"(previous failed: {last_err}{knob_note})..."
                ),
            }
            _emit_phase(
                phase="json_subcall",
                activity=(
                    f"{label}: retry {attempt}/{MAX_RETRIES} (prev failed: {last_err}{knob_note})"
                ),
                structural_override={
                    "section_name": label,
                    "attempt": attempt,
                    "attempt_total": MAX_RETRIES,
                },
            )
            _record_retry()

        step_label = (
            f"{label} attempt {attempt}/{MAX_RETRIES} "
            f"(json_mode, key='{json_key}', max_tokens={output_budget}{knob_note})"
        )
        items, err, raw = _attempt_json_subcall(
            theme_text,
            model_info,
            prompt,
            json_key,
            step_label,
            output_budget,
            repeat_penalty_override=rp_override,
            activity_prefix=f"{label} (attempt {attempt}/{MAX_RETRIES})",
        )

        if err is None:
            if attempt > 1:
                logger.info(
                    "%s: succeeded on attempt %d/%d",
                    label,
                    attempt,
                    MAX_RETRIES,
                )
            return items, None, raw

        attempts.append((attempt, err or "unknown", raw))
        logger.warning(
            "%s attempt %d/%d failed: %s; raw head: %s",
            label,
            attempt,
            MAX_RETRIES,
            err,
            raw[:200],
        )

    final_err = attempts[-1][1] if attempts else "no attempts"
    logger.error(
        "%s FINAL FAILURE after %d/%d attempts: %s",
        label,
        MAX_RETRIES,
        MAX_RETRIES,
        final_err,
    )
    # Build an aggregated raw view surfacing every attempt's output.
    # Kept modest in size (~400 chars per attempt) so the UI error
    # panel stays readable; the full output for each attempt lives in
    # the extraction log.
    per_attempt_cap = 400
    rendered = []
    for att_no, att_err, att_raw in attempts:
        head = (att_raw or "").strip()
        if len(head) > per_attempt_cap:
            head = head[:per_attempt_cap] + " [... truncated ...]"
        rendered.append(f"--- Attempt {att_no}/{MAX_RETRIES} ({att_err}) ---\n{head}")
    aggregated_raw = "\n\n".join(rendered)
    return [], final_err, aggregated_raw


# Per-section subcall specs. Each entry maps `kind` → the args needed to drive
# `_run_json_subcall` plus the success/error event types emitted to the UI.
_SECTION_SPECS: dict[str, dict[str, Any]] = {
    "constraints": {
        "label": "Constraints extraction",
        "prompt_file": "constraints_system.txt",
        "json_key": "constraints",
        "output_budget": _JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS,
        "success_event": "constraints",
        "error_event": "constraints_error",
        "items_field": "constraints",
    },
    "card_suggestions": {
        "label": "Card suggestions extraction",
        "prompt_file": "card_suggestions_system.txt",
        "json_key": "card_suggestions",
        "output_budget": _JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS,
        "success_event": "card_suggestions",
        "error_event": "suggestions_error",
        "items_field": "suggestions",
    },
}


def _stream_section_subcall(theme_text: str, model_info, kind: str) -> Iterator[dict[str, Any]]:
    """Yield status + result events for one section subcall.

    Used by both the full constraints pass and the per-section refresh path.
    """
    spec = _SECTION_SPECS[kind]
    gen = _run_json_subcall(
        theme_text,
        model_info,
        spec["label"],
        spec["prompt_file"],
        spec["json_key"],
        spec["output_budget"],
    )
    try:
        while True:
            yield next(gen)
    except StopIteration as stop:
        items, err, raw = stop.value

    logger.info(
        "%s: %d items (err=%s)",
        spec["label"],
        len(items),
        err,
    )
    if err:
        yield {
            "type": spec["error_event"],
            "message": err,
            "raw": (raw or "")[:2000],
        }
    else:
        yield {"type": spec["success_event"], spec["items_field"]: items}


def _resolve_model_info(model_key: str):
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")
    return model_info


def stream_constraints_extraction(theme_text: str, model_key: str) -> Iterator[dict[str, Any]]:
    """Yield constraints + card-suggestion events as each subcall completes.

    Two sequential JSON subcalls. Each retries up to MAX_RETRIES on parse /
    repetition failures. Yields ``status`` events between attempts so the UI
    progress bar moves during slow local-model retries.

    Yielded events:
        {"type": "status", "message": "..."}
        {"type": "constraints", "constraints": [...]}
        {"type": "constraints_error", "message": "...", "raw": "..."}
        {"type": "card_suggestions", "suggestions": [...]}
        {"type": "suggestions_error", "message": "...", "raw": "..."}
        {"type": "done", "cost_usd": 0.0}
    """
    model_info = _resolve_model_info(model_key)

    logger.info(
        "Extracting constraints + suggestions: model=%s, theme_len=%d",
        model_info.model_id,
        len(theme_text),
    )

    # Acquire the shared AI lock for the entire constraints pass.
    with ai_lock.hold("Refresh constraints + card suggestions") as acquired:
        if not acquired:
            yield {
                "type": "error",
                "busy": True,
                "message": "Another AI action is already running.",
                **ai_lock.busy_payload(),
            }
            return

        # Each acquisition starts a fresh per-run log directory so
        # /api/ai/status reports a live tail target on every refresh.
        log_dir = _init_run_log_dir()
        ai_lock.update_log_path(log_dir)
        # The structural state slot (section/chunk indices) is stale at
        # this point if we were just running multi-chunk extraction;
        # constraints + card-suggestions live outside that grid.
        _structural.reset()

        try:
            yield from _stream_section_subcall(theme_text, model_info, "constraints")
            yield from _stream_section_subcall(theme_text, model_info, "card_suggestions")

            _emit_phase(phase="done", activity="Extraction complete")
            yield {"type": "done", "cost_usd": 0.0}
        except _CancelledError:
            if _run_stats:
                _run_stats.cancelled = True
            _emit_phase(phase="done", activity="Cancelled")
            yield {"type": "cancelled"}


def stream_section_extraction(
    theme_text: str, model_key: str, kind: str
) -> Iterator[dict[str, Any]]:
    """Run only one of the constraints / card-suggestions subcalls.

    Used by the per-section refresh endpoints so a "Refresh AI" click on
    Set Constraints doesn't also pay for the (discarded) card-suggestions
    subcall, and vice versa.
    """
    if kind not in _SECTION_SPECS:
        raise ValueError(f"Unknown section kind: {kind}")

    model_info = _resolve_model_info(model_key)

    logger.info(
        "Extracting section=%s: model=%s, theme_len=%d",
        kind,
        model_info.model_id,
        len(theme_text),
    )

    action_name = "Refresh set constraints" if kind == "constraints" else "Refresh card requests"
    with ai_lock.hold(action_name) as acquired:
        if not acquired:
            yield {
                "type": "error",
                "busy": True,
                "message": "Another AI action is already running.",
                **ai_lock.busy_payload(),
            }
            return

        # Each acquisition gets a fresh per-run log directory.
        log_dir = _init_run_log_dir()
        ai_lock.update_log_path(log_dir)
        _structural.reset()

        try:
            yield from _stream_section_subcall(theme_text, model_info, kind)

            yield {"type": "done", "cost_usd": 0.0}
        except _CancelledError:
            if _run_stats:
                _run_stats.cancelled = True
            yield {"type": "cancelled"}


def extract_section(theme_text: str, model_key: str, kind: str) -> ConstraintsResult:
    """Non-streaming wrapper around :func:`stream_section_extraction`.

    Used by the per-section refresh endpoints (one LLM subcall per click).
    Returns a :class:`ConstraintsResult` with only the requested section
    populated; the unrelated section's fields stay at their defaults.
    """
    constraints: list = []
    card_suggestions: list = []
    constraints_error: str | None = None
    constraints_raw: str | None = None
    suggestions_error: str | None = None
    suggestions_raw: str | None = None
    cost = 0.0
    busy = False
    for event in stream_section_extraction(theme_text, model_key, kind):
        t = event.get("type")
        if t == "constraints":
            constraints = event["constraints"]
        elif t == "constraints_error":
            constraints_error = event["message"]
            constraints_raw = event.get("raw")
        elif t == "card_suggestions":
            card_suggestions = event["suggestions"]
        elif t == "suggestions_error":
            suggestions_error = event["message"]
            suggestions_raw = event.get("raw")
        elif t == "done":
            cost = event.get("cost_usd", 0.0)
        elif t == "error" and event.get("busy"):
            busy = True

    return ConstraintsResult(
        constraints=constraints,
        card_suggestions=card_suggestions,
        cost_usd=cost,
        constraints_error=constraints_error,
        constraints_raw=constraints_raw,
        suggestions_error=suggestions_error,
        suggestions_raw=suggestions_raw,
        busy=busy,
    )
