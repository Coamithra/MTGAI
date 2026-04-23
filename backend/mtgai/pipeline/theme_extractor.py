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
import os
import re
import threading
import time
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# Tokens reserved for LLM output. Used both for budget calculations and as the
# concrete max_tokens / num_predict on each call - keep these in sync.
_OUTPUT_BUDGET = 16384
_LOG_DIR = Path("C:/Programming/MTGAI/output/extraction_logs")

OLLAMA_URL = os.environ.get("MTGAI_OLLAMA_URL", "http://localhost:11434").strip()

# Stop sequences keep the model from echoing the source-text divider markers
# back into the extraction (a real failure mode on weaker local models).
_OLLAMA_STOP_SEQUENCES = [
    "--- START OF SOURCE TEXT ---",
    "--- END OF SOURCE TEXT ---",
]

# Keep model warm between theme + constraints calls (Ollama default = 5m).
_OLLAMA_KEEP_ALIVE = "15m"

# Hard cap on JSON subcall output (constraints / card_suggestions). With
# num_predict=-1 a model in a repetition loop fills the entire context window
# before the post-hoc detector even runs.
_JSON_SUBCALL_MAX_TOKENS = 4096

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

# Reentrant so the SSE handler can hold the lock across both theme extraction
# and constraint extraction without deadlocking on the inner call.
_run_lock = threading.RLock()
_cancel_event = threading.Event()


def request_cancel() -> bool:
    """Signal the active extraction to abort.

    Returns True if a run was active, False if there was nothing to cancel.
    """
    if _is_locked():
        _cancel_event.set()
        logger.info("Cancel requested for active extraction")
        return True
    return False


def is_running() -> bool:
    return _is_locked()


def _is_locked() -> bool:
    # RLock has no public 'locked()' - probe by trying a non-blocking acquire.
    acquired = _run_lock.acquire(blocking=False)
    if acquired:
        _run_lock.release()
        return False
    return True


class _CancelledError(Exception):
    """Internal: raised when _cancel_event is set, to unwind the call stack."""


def _check_cancelled() -> None:
    if _cancel_event.is_set():
        raise _CancelledError("user cancelled")


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


# Module-global: safe because `_run_lock` enforces a single active run. Tests
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
# Conversation log (one file per run)
# =============================================================================

_conversation_log: Path | None = None
_log_handle: Any = None  # open file when streaming a call; None otherwise


def _init_conversation_log() -> Path:
    global _conversation_log, _run_stats
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _conversation_log = _LOG_DIR / f"extraction_{ts}.md"
    _conversation_log.write_text(
        f"# Theme Extraction Log - {ts}\n\n",
        encoding="utf-8",
    )
    _run_stats = _RunStats()
    return _conversation_log


def get_current_log_path() -> Path | None:
    """Path of the active extraction log (None if no run in progress)."""
    return _conversation_log


def _truncate_user_prompt(user_prompt: str) -> str:
    if len(user_prompt) <= 2000:
        return user_prompt
    return (
        user_prompt[:1000]
        + f"\n\n[... {len(user_prompt) - 2000} chars truncated ...]\n\n"
        + user_prompt[-1000:]
    )


def _log_call_start(
    step: str,
    system_prompt: str,
    user_prompt: str,
    extras: dict[str, str] | None = None,
) -> None:
    """Open a new call section in the conversation log.

    ``extras`` lets the caller dump critical mid-prompt state verbatim
    (e.g. accumulated section text, chunk text) as separate fenced blocks,
    so debugging doesn't depend on what survives :func:`_truncate_user_prompt`.
    """
    global _log_handle
    if _conversation_log is None:
        return
    if _log_handle is not None:
        try:
            _log_handle.close()
        except Exception:
            pass
        _log_handle = None
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    _log_handle = open(_conversation_log, "a", encoding="utf-8")
    _log_handle.write(f"---\n\n## [{ts}] {step}\n\n")
    _log_handle.write(f"### System Prompt\n\n```\n{system_prompt}\n```\n\n")
    _log_handle.write(
        f"### User Prompt\n\n```\n{_truncate_user_prompt(user_prompt)}\n```\n\n"
    )
    if extras:
        for label, value in extras.items():
            if value is None:
                continue
            _log_handle.write(f"### {label}\n\n```\n{value}\n```\n\n")
    _log_handle.write("### Response\n\n")
    _log_handle.flush()


def _log_call_chunk(text: str) -> None:
    if _log_handle is None or not text:
        return
    _log_handle.write(text)
    _log_handle.flush()


def _log_call_end(note: str | None = None, metadata: dict | None = None) -> None:
    global _log_handle
    if _log_handle is None:
        return
    if metadata:
        _log_handle.write("\n\n```\n")
        for k, v in metadata.items():
            _log_handle.write(f"{k}: {v}\n")
        _log_handle.write("```\n")
    if note:
        _log_handle.write(f"\n\n_{note}_\n\n")
    else:
        _log_handle.write("\n\n")
    _log_handle.flush()
    _log_handle.close()
    _log_handle = None


def _log_marker(text: str) -> None:
    """One-line italics marker between call sections."""
    if _conversation_log is None:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    with open(_conversation_log, "a", encoding="utf-8") as f:
        f.write(f"_[{ts}] {text}_\n\n")


def _write_plan_header(
    *,
    model_key: str,
    model_info: Any,
    text: str,
    token_count: int,
    available: int,
    fits: bool,
    est_chunks: int,
) -> None:
    """Dump the pre-extraction plan into the log so post-mortems don't need
    to reconstruct what we thought was going to happen."""
    if _conversation_log is None:
        return
    with open(_conversation_log, "a", encoding="utf-8") as f:
        f.write("## Extraction Plan\n\n")
        f.write(f"- Model key: `{model_key}`\n")
        f.write(f"- Model id: `{model_info.model_id}`\n")
        f.write(f"- Provider: `{model_info.provider}`\n")
        f.write(f"- Context window: {model_info.context_window:,}\n")
        f.write(f"- Output budget: {_OUTPUT_BUDGET:,}\n")
        f.write(f"- Available budget: {available:,}\n")
        f.write(f"- Input length: {len(text):,} chars\n")
        f.write(f"- Estimated input tokens: {token_count:,}\n")
        f.write(f"- Fits single pass: {'yes' if fits else 'no'}\n")
        if not fits:
            f.write(f"- Planned chunks: {est_chunks}\n")
            f.write(f"- Sections: {len(_SECTIONS)}\n")
            f.write(
                f"- Planned section x chunk calls: "
                f"{len(_SECTIONS) * est_chunks}\n"
            )
        f.write("\n")


def _write_summary_footer() -> None:
    if _conversation_log is None or _run_stats is None:
        return
    elapsed = time.monotonic() - _run_stats.started_at
    with open(_conversation_log, "a", encoding="utf-8") as f:
        f.write("---\n\n## Run Summary\n\n")
        f.write(f"- Wall time: {elapsed:.1f}s ({elapsed / 60:.1f} min)\n")
        f.write(f"- Total LLM calls: {_run_stats.total_calls}\n")
        f.write(f"- Input tokens (recorded): {_run_stats.total_input_tokens:,}\n")
        f.write(f"- Output tokens (recorded): {_run_stats.total_output_tokens:,}\n")
        f.write(f"- Total cost: ${_run_stats.total_cost_usd:.4f}\n")
        f.write(f"- Retries: {_run_stats.retries}\n")
        f.write(f"- Sections with content: {_run_stats.sections_with_content}\n")
        f.write(f"- Sections empty: {_run_stats.sections_empty}\n")
        if _run_stats.cancelled:
            f.write("- **CANCELLED by user**\n")
        if _run_stats.aborted_reason:
            f.write(f"- **ABORTED**: {_run_stats.aborted_reason}\n")
        f.write("\n")


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
    from anthropic import Anthropic

    client = Anthropic()
    # Use the actual single-pass user template so the count matches what we
    # would really send. For multi-chunk runs this is only a planning
    # estimate anyway, but keeping the string honest avoids a subtle drift
    # between "planned" tokens and "actually sent" tokens.
    try:
        single_template = (_PROMPTS_DIR / "theme_chunk_single.txt").read_text(
            encoding="utf-8"
        )
        user_content = single_template.format(text=text)
    except Exception:
        user_content = text
    try:
        result = client.messages.count_tokens(
            model=model_id,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return result.input_tokens
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
        total_output_tokens = (
            (first_calls + next_calls) * _OUTPUT_BUDGET
            + compaction_calls * int(accumulated_avg * 0.7)
        )

    estimated_cost = (
        total_input_tokens * model_info.input_price
        + total_output_tokens * model_info.output_price
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

    if not _run_lock.acquire(blocking=False):
        yield {
            "type": "error",
            "message": (
                "Another extraction is already running. Cancel it first or wait "
                "for it to finish."
            ),
        }
        return

    _cancel_event.clear()
    try:
        registry = get_registry()
        model_info = registry.get_llm(model_key)
        if model_info is None:
            yield {"type": "error", "message": f"Unknown model key: {model_key}"}
            return

        system_prompt = _get_system_prompt()
        log_path = _init_conversation_log()
        logger.info(
            "Starting theme extraction: model=%s provider=%s text_len=%d log=%s",
            model_info.model_id,
            model_info.provider,
            len(text),
            log_path,
        )

        try:
            available = model_info.context_window - _OUTPUT_BUDGET
            token_count = count_tokens(text, model_key)
            logger.info(
                "Token count: %d, available budget: %d, context_window: %d",
                token_count,
                available,
                model_info.context_window,
            )

            fits = token_count <= available
            chunk_budget = model_info.context_window // 2
            est_chunks = (
                1 if fits else max(1, math.ceil(token_count / max(chunk_budget, 1)))
            )
            _write_plan_header(
                model_key=model_key,
                model_info=model_info,
                text=text,
                token_count=token_count,
                available=available,
                fits=fits,
                est_chunks=est_chunks,
            )

            if fits:
                yield from _run_single_pass(text, system_prompt, model_info)
            else:
                yield from _run_multi_chunk(text, model_info)
        except _CancelledError:
            if _run_stats:
                _run_stats.cancelled = True
            yield {"type": "cancelled"}
        except Exception as e:
            logger.error("Theme extraction failed: %s", e, exc_info=True)
            if _run_stats:
                _run_stats.aborted_reason = str(e)
            yield {
                "type": "error",
                "message": str(e),
                "log_path": str(_conversation_log) if _conversation_log else None,
            }
        finally:
            _write_summary_footer()
    finally:
        _run_lock.release()


def _run_single_pass(
    text: str, system_prompt: str, model_info
) -> Generator[dict, None, None]:
    yield {"type": "status", "message": "Generating theme..."}
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
        _log_marker(warn)
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
            f"Large document - extracting {len(_SECTIONS)} sections "
            f"across {len(chunks)} chunks..."
        ),
    }

    sys_template = (_PROMPTS_DIR / "theme_section_system.txt").read_text(
        encoding="utf-8"
    )
    first_template = (_PROMPTS_DIR / "theme_section_first.txt").read_text(
        encoding="utf-8"
    )
    next_template = (_PROMPTS_DIR / "theme_section_next.txt").read_text(
        encoding="utf-8"
    )
    compact_template = (_PROMPTS_DIR / "theme_section_compact.txt").read_text(
        encoding="utf-8"
    )

    completed_sections: list[str] = []
    total_cost = 0.0

    accumulated_max_tokens = int(_COMPACT_AT_FRACTION * chunk_token_budget)
    compact_target_tokens = int(accumulated_max_tokens * 0.7)

    for sec_idx, (sec_name, sec_guidance) in enumerate(_SECTIONS):
        _check_cancelled()
        _log_marker(
            f"=== Section {sec_idx + 1}/{len(_SECTIONS)}: {sec_name} ==="
        )
        yield {
            "type": "status",
            "message": (
                f"Extracting {sec_name} ({sec_idx + 1}/{len(_SECTIONS)})..."
            ),
        }
        logger.info("Section %d/%d: %s", sec_idx + 1, len(_SECTIONS), sec_name)

        section_prompt = sys_template.format(
            section_name=sec_name,
            section_guidance=sec_guidance,
        )
        accumulated = ""

        for ci, chunk_part in enumerate(chunks):
            _check_cancelled()

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
                        log_extras={"accumulated (input to compaction)": accumulated},
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
                        _log_marker(
                            f"COMPACTION FALLBACK (hard-truncate): {sec_name} "
                            f"head+tail kept, middle dropped (reason: "
                            f"{compact_err or 'empty result'})"
                        )
                        logger.info(
                            "  compaction fallback (hard-truncate head+tail): "
                            "%s -> %d chars",
                            sec_name,
                            len(accumulated),
                        )
                    else:
                        new_acc = compact_result.strip()
                        new_tok = _count_tokens_tiktoken(new_acc)
                        accumulated = new_acc
                        _log_marker(
                            f"COMPACTION OK: {sec_name} "
                            f"{acc_tokens} tok -> {new_tok} tok"
                        )
                        logger.info(
                            "  compacted %s: %d -> %d tokens",
                            sec_name,
                            acc_tokens,
                            new_tok,
                        )

            yield {
                "type": "status",
                "message": (
                    f"{sec_name} ({sec_idx + 1}/{len(_SECTIONS)}): "
                    f"chunk {ci + 1}/{len(chunks)}..."
                ),
            }

            if ci == 0:
                user_msg = first_template.format(
                    section_name=sec_name,
                    chunk_num=ci + 1,
                    total_chunks=len(chunks),
                    chunk_text=chunk_part,
                )
                chunk_extras = {"chunk_text (input)": chunk_part}
            else:
                user_msg = next_template.format(
                    section_name=sec_name,
                    chunk_num=ci + 1,
                    total_chunks=len(chunks),
                    accumulated=accumulated,
                    chunk_text=chunk_part,
                )
                chunk_extras = {
                    "accumulated (input)": accumulated,
                    "chunk_text (input)": chunk_part,
                }

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
                log_extras=chunk_extras,
            ):
                if event["type"] == "theme_chunk":
                    chunk_result += event["text"]
                elif event["type"] == "complete":
                    chunk_result = event.get("theme_text", chunk_result)
                    total_cost += event.get("cost_usd", 0)
                elif event["type"] == "error":
                    err_msg = (
                        f"{sec_name} chunk {ci + 1}/{len(chunks)} failed: "
                        f"{event['message']}"
                    )
                    if _run_stats and not _run_stats.aborted_reason:
                        _run_stats.aborted_reason = err_msg
                    _log_marker(f"ABORT: {err_msg}")
                    yield {
                        "type": "error",
                        "message": err_msg,
                        "log_path": (
                            str(_conversation_log) if _conversation_log else None
                        ),
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
                    _log_marker(warn)
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
    log_extras: dict[str, str] | None = None,
) -> Generator[dict, None, None]:
    """Dispatch one streaming call to the configured provider.

    Yields theme_chunk events (if *stream_to_ui*), then a final ``complete``
    event with the full text and cost - or an ``error`` event on failure.

    ``step_label`` tags the call in the conversation log (e.g.
    "Section 3/7 Creature Types chunk 4/10" or "COMPACTION: ..."). If None,
    falls back to a generic provider label.

    ``log_extras`` gets written as separate fenced blocks in the log so large
    mid-prompt state (accumulated, chunk_text) survives user-prompt truncation.
    """
    if model_info.provider == "anthropic":
        yield from _stream_anthropic_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            step_label=step_label,
            log_extras=log_extras,
        )
    elif model_info.provider == "ollama":
        yield from _stream_ollama_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            json_mode=json_mode,
            step_label=step_label,
            log_extras=log_extras,
        )
    else:
        yield {
            "type": "error",
            "message": f"Unsupported provider: {model_info.provider}",
        }


def _stream_anthropic_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    step_label: str | None = None,
    log_extras: dict[str, str] | None = None,
) -> Generator[dict, None, None]:
    from anthropic import Anthropic

    from mtgai.generation.llm_client import calc_cost

    client = Anthropic()
    model_id = model_info.model_id

    # Prompt caching: the system prompt is identical across all per-section
    # calls in a multi-chunk run. Marking it as ephemeral cache cuts input
    # cost on subsequent calls within the ~5 min window by 90%.
    from anthropic.types import TextBlockParam

    system_blocks: list[TextBlockParam] = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    theme_text = ""
    metadata: dict[str, Any] = {}
    cost = 0.0

    label = f"Anthropic call - {step_label}" if step_label else "Anthropic call"
    _log_call_start(label, system_prompt, user_msg, extras=log_extras)
    try:
        with client.messages.stream(
            model=model_id,
            max_tokens=_OUTPUT_BUDGET,
            system=system_blocks,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.7,
        ) as stream:
            for event in stream:
                if _cancel_event.is_set():
                    raise _CancelledError("cancelled mid-stream")
                delta_text: str | None = None
                if getattr(event, "type", None) == "content_block_delta":
                    delta = getattr(event, "delta", None)  # pyright: ignore[reportAttributeAccessIssue]
                    delta_text = getattr(delta, "text", None)
                if delta_text:
                    theme_text += delta_text
                    _log_call_chunk(delta_text)
                    if stream_to_ui:
                        yield {"type": "theme_chunk", "text": delta_text}

            final = stream.get_final_message()
            usage = final.usage
            cache_creation = (
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cost = calc_cost(
                model_id,
                usage.input_tokens,
                usage.output_tokens,
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
            )
            metadata = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation": cache_creation,
                "cache_read": cache_read,
                "cost_usd": f"{cost:.4f}",
            }
            _record_call(
                usage.input_tokens + cache_creation + cache_read,
                usage.output_tokens,
                cost,
            )
    except _CancelledError:
        _log_call_end(note="CANCELLED")
        raise
    except Exception as e:
        logger.error("Anthropic streaming call failed: %s", e, exc_info=True)
        _log_call_end(note=f"STREAM ERROR: {e}")
        yield {"type": "error", "message": str(e)}
        return

    logger.info(
        "Anthropic call complete: %d chars, cost=$%.4f", len(theme_text), cost
    )
    _log_call_end(metadata=metadata, note=f"cost: ${cost:.4f}")
    yield {"type": "complete", "theme_text": theme_text, "cost_usd": cost}


def _stream_ollama_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    json_mode: bool = False,
    step_label: str | None = None,
    log_extras: dict[str, str] | None = None,
) -> Generator[dict, None, None]:
    """Single Ollama streaming call using the native ``/api/chat`` endpoint.

    Performs a pre-call overflow check (errors out if input exceeds budget)
    and a post-call truncation check (warns if Ollama silently dropped input
    or hit the output cap).
    """
    import requests

    from mtgai.generation.llm_client import OLLAMA_REPEAT_PENALTY
    from mtgai.generation.token_utils import (
        InputTruncatedError,
        OutputTruncatedError,
        check_post_call,
        count_messages_tokens,
    )

    num_ctx = model_info.context_window
    output_reserve = _JSON_SUBCALL_MAX_TOKENS if json_mode else _OUTPUT_BUDGET

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    estimated_input_tokens = count_messages_tokens(messages)
    safe_budget = int(num_ctx * 0.95) - output_reserve

    call_label = f"Ollama call - {step_label}" if step_label else "Ollama call"

    # --- Pre-call overflow check ---
    if estimated_input_tokens > safe_budget:
        msg = (
            f"Input too large for {model_info.model_id}: ~{estimated_input_tokens} "
            f"tokens estimated, only {safe_budget} available "
            f"(num_ctx={num_ctx}, output_reserve={output_reserve}). "
            f"Reduce input or increase context window."
        )
        logger.error(msg)
        _log_call_start(
            f"{call_label} (skipped)", system_prompt, user_msg, extras=log_extras
        )
        _log_call_end(note=f"OVERFLOW: {msg}")
        yield {"type": "error", "message": msg}
        return

    logger.info(
        "Ollama call: model=%s, est_input=%d tok, num_ctx=%d, output_reserve=%d",
        model_info.model_id,
        estimated_input_tokens,
        num_ctx,
        output_reserve,
    )

    body: dict = {
        "model": model_info.model_id,
        "messages": messages,
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.7,
            "num_predict": output_reserve,
            "repeat_penalty": OLLAMA_REPEAT_PENALTY,
            "stop": _OLLAMA_STOP_SEQUENCES,
        },
        "keep_alive": _OLLAMA_KEEP_ALIVE,
        "stream": True,
    }
    if json_mode:
        body["format"] = "json"

    theme_text = ""
    loop_err: str | None = None
    chars_since_check = 0
    final_data: dict = {}

    _log_call_start(call_label, system_prompt, user_msg, extras=log_extras)
    resp = None
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=body,
            stream=True,
            timeout=1800,
        )
        if resp.status_code != 200:
            body_txt = resp.text[:1000] if resp.text else ""
            err_msg = f"Ollama HTTP {resp.status_code}: {body_txt}"
            logger.error(err_msg)
            _log_call_end(note=f"HTTP ERROR: {err_msg}")
            yield {"type": "error", "message": err_msg}
            return

        for line in resp.iter_lines():
            if _cancel_event.is_set():
                resp.close()
                raise _CancelledError("cancelled mid-stream")
            if not line:
                continue
            try:
                data = _json.loads(line)
            except _json.JSONDecodeError:
                logger.warning(
                    "Ollama: skipping malformed line %s", str(line)[:120]
                )
                continue
            if data.get("done"):
                final_data = data
                break
            content = data.get("message", {}).get("content", "")
            if not content:
                continue
            theme_text += content
            _log_call_chunk(content)
            if stream_to_ui:
                yield {"type": "theme_chunk", "text": content}

            chars_since_check += len(content)
            if chars_since_check >= 200:
                chars_since_check = 0
                loop_err = _detect_repetition_loop(theme_text)
                if loop_err:
                    logger.warning(
                        "Repetition loop detected mid-stream after %d chars: %s",
                        len(theme_text),
                        loop_err,
                    )
                    resp.close()
                    break
    except _CancelledError:
        _log_call_end(note="CANCELLED")
        raise
    except Exception as e:
        logger.error("Ollama streaming call failed: %s", e, exc_info=True)
        _log_call_end(note=f"STREAM ERROR: {e}")
        yield {"type": "error", "message": str(e)}
        return
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    if loop_err:
        logger.info(
            "Ollama call aborted (repetition): %d chars before abort",
            len(theme_text),
        )
        # Cut the loop off mid-sentence so the caller still gets usable text.
        # The repetition detector inspects the last 4000 chars; the run-up to
        # the loop is intact and can sometimes be salvaged.
        # Record token estimates so the run footer doesn't undercount aborted
        # calls (no `done` frame arrives when we close the connection early).
        _record_call(
            estimated_input_tokens,
            _count_tokens_tiktoken(theme_text),
            0.0,
        )
        _log_call_end(note=f"ABORTED: {loop_err}")
        yield {"type": "error", "message": loop_err}
        return

    # --- Missing-done detection ---
    # If the Ollama stream ended (iter_lines exhausted) without ever
    # seeing a `{"done": true}` frame, treat it as an error rather than
    # silently returning whatever partial text accumulated. Dropped
    # connections, proxy resets, and Ollama internal errors can all land
    # here.
    if not final_data:
        msg = (
            f"Ollama stream ended without a 'done' frame after "
            f"{len(theme_text)} chars. Possible connection drop or server "
            f"error - check Ollama server.log."
        )
        logger.error(msg)
        _record_call(
            estimated_input_tokens,
            _count_tokens_tiktoken(theme_text),
            0.0,
        )
        _log_call_end(note=f"MISSING DONE FRAME: {msg}")
        yield {"type": "error", "message": msg}
        return

    metadata: dict[str, Any] = {}
    if final_data:
        metadata = {
            "prompt_eval_count": final_data.get("prompt_eval_count"),
            "eval_count": final_data.get("eval_count"),
            "total_duration_ms": (
                (final_data.get("total_duration") or 0) // 1_000_000
            ),
            "prompt_eval_duration_ms": (
                (final_data.get("prompt_eval_duration") or 0) // 1_000_000
            ),
            "eval_duration_ms": (
                (final_data.get("eval_duration") or 0) // 1_000_000
            ),
            "done_reason": final_data.get("done_reason"),
        }
        _record_call(
            final_data.get("prompt_eval_count", 0) or estimated_input_tokens,
            final_data.get("eval_count", 0),
            0.0,
        )
        # --- Post-call truncation check ---
        try:
            check_post_call(
                final_data,
                estimated_input_tokens=estimated_input_tokens,
                model=model_info.model_id,
                num_predict=output_reserve,
            )
        except (InputTruncatedError, OutputTruncatedError) as trunc:
            logger.warning("Truncation detected: %s", trunc)
            _log_call_end(metadata=metadata, note=f"TRUNCATION: {trunc}")
            yield {"type": "error", "message": str(trunc)}
            return

    logger.info("Ollama call complete: %d chars extracted", len(theme_text))
    _log_call_end(metadata=metadata)
    yield {"type": "complete", "theme_text": theme_text, "cost_usd": 0.0}


# =============================================================================
# Repetition loop detection
# =============================================================================


_PUNCT_STRIP = ".,;:!?\"'"


def _detect_token_repetition(text: str, min_repeats: int = 15) -> str | None:
    """Catch a single token (the last word) repeating N+ times at the tail."""
    if not text:
        return None
    tail = text[-4000:]
    words = tail.split()
    if len(words) < min_repeats:
        return None

    # Prefer the stripped form so "word." and "word" count as one, but if
    # stripping leaves nothing (pure punctuation like "---" or "..."), fall
    # back to the raw token so pure-punctuation loops still get caught.
    raw_last = words[-1]
    stripped_last = raw_last.strip(_PUNCT_STRIP)
    use_stripped = bool(stripped_last)
    compare_val = stripped_last if use_stripped else raw_last

    streak = 0
    for w in reversed(words):
        cmp = w.strip(_PUNCT_STRIP) if use_stripped else w
        if cmp == compare_val:
            streak += 1
        else:
            break
    if streak >= min_repeats:
        return f"Token {compare_val!r} repeated {streak}+ times at end of output"
    return None


def _detect_phrase_repetition(
    text: str, max_phrase_len: int = 60, min_repeats: int = 6
) -> str | None:
    """Catch a multi-token phrase repeating verbatim at the tail.

    The model's output sometimes degenerates into a loop where a fixed
    multi-word phrase repeats verbatim, e.g.::

        "...preserver of life. A preserver of life. A preserver of life..."

    The simple last-token detector misses these because the last token rotates
    through several distinct words. This scanner walks phrase lengths
    2..max_phrase_len chars and checks whether the last ``plen * min_repeats``
    chars of the tail consist of the same ``plen``-char block repeated
    ``min_repeats`` times.

    Trade-off: ``min_repeats=6`` avoids false positives on legitimate
    rhetorical repetition (lists, parallel structure). A 17-char phrase looped
    only 5 times slips through, which is acceptable - 5 repetitions are short
    enough that the post-hoc loop killer plus retry recover cleanly.
    """
    if not text:
        return None
    tail = text[-4000:]
    n = len(tail)
    for plen in range(2, max_phrase_len + 1):
        if plen * min_repeats > n:
            break
        phrase = tail[n - plen :]
        ok = True
        for i in range(1, min_repeats):
            if tail[n - plen * (i + 1) : n - plen * i] != phrase:
                ok = False
                break
        if ok:
            display = phrase if len(phrase) <= 40 else phrase[:37] + "..."
            return (
                f"Phrase {display!r} (len={plen}) repeated {min_repeats}+ times"
            )
    return None


def _detect_repetition_loop(text: str) -> str | None:
    """Composite check: token-level OR phrase-level loop."""
    return _detect_token_repetition(text) or _detect_phrase_repetition(text)


# =============================================================================
# Constraints + card-suggestions extraction (second pass)
# =============================================================================


def stream_constraints_extraction(
    theme_text: str, model_key: str
) -> Iterator[dict[str, Any]]:
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
    from mtgai.generation.llm_client import MAX_RETRIES
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    if _conversation_log is None:
        _init_conversation_log()

    logger.info(
        "Extracting constraints + suggestions: model=%s, theme_len=%d",
        model_info.model_id,
        len(theme_text),
    )

    def _attempt_json_subcall(
        prompt: str, json_key: str, step_label: str
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
            ):
                if event["type"] == "complete":
                    raw = event.get("theme_text", "")
                elif event["type"] == "error":
                    stream_err = event.get("message") or "stream error"
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
        label: str, prompt_file: str, json_key: str
    ) -> Generator[dict, None, tuple[list, str | None, str]]:
        prompt = (_PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
        # Collect every attempt so the UI error surface shows the full
        # retry history, not just the final attempt.
        attempts: list[tuple[int, str, str]] = []  # (attempt_no, err, raw)

        for attempt in range(1, MAX_RETRIES + 1):
            _check_cancelled()
            last_err = attempts[-1][1] if attempts else None
            if attempt == 1:
                yield {"type": "status", "message": f"{label}..."}
            else:
                yield {
                    "type": "status",
                    "message": (
                        f"{label}: retry attempt {attempt}/{MAX_RETRIES} "
                        f"(previous failed: {last_err})..."
                    ),
                }
                _record_retry()

            step_label = (
                f"{label} attempt {attempt}/{MAX_RETRIES} "
                f"(json_mode, key='{json_key}')"
            )
            items, err, raw = _attempt_json_subcall(prompt, json_key, step_label)

            if err is None:
                if attempt > 1:
                    logger.info(
                        "%s: succeeded on attempt %d/%d",
                        label,
                        attempt,
                        MAX_RETRIES,
                    )
                    _log_marker(
                        f"{label} succeeded on attempt {attempt}/{MAX_RETRIES}"
                    )
                else:
                    _log_marker(f"{label} succeeded")
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
            if attempt < MAX_RETRIES:
                _log_marker(
                    f"{label} attempt {attempt}/{MAX_RETRIES} FAILED: "
                    f"{err} - retrying"
                )

        final_err = attempts[-1][1] if attempts else "no attempts"
        _log_marker(
            f"{label} FINAL FAILURE after {MAX_RETRIES}/{MAX_RETRIES} "
            f"attempts: {final_err}"
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
            rendered.append(
                f"--- Attempt {att_no}/{MAX_RETRIES} ({att_err}) ---\n{head}"
            )
        aggregated_raw = "\n\n".join(rendered)
        return [], final_err, aggregated_raw

    # Acquire the run lock for the entire constraints pass. Reentrant: if the
    # caller (theme extraction) already holds it, this is free.
    if not _run_lock.acquire(blocking=False):
        yield {
            "type": "error",
            "message": "Another extraction is already running.",
        }
        return

    try:
        # --- Call 1: Constraints (JSON mode) ---
        gen = _run_json_subcall(
            "Constraints extraction", "constraints_system.txt", "constraints"
        )
        try:
            while True:
                yield next(gen)
        except StopIteration as stop:
            constraints, constraints_err, constraints_raw = stop.value

        logger.info(
            "Constraints extracted: %d items (err=%s)",
            len(constraints),
            constraints_err,
        )
        if constraints_err:
            yield {
                "type": "constraints_error",
                "message": constraints_err,
                "raw": (constraints_raw or "")[:2000],
            }
        else:
            yield {"type": "constraints", "constraints": constraints}

        # --- Call 2: Card suggestions (JSON mode) ---
        gen = _run_json_subcall(
            "Card suggestions extraction",
            "card_suggestions_system.txt",
            "card_suggestions",
        )
        try:
            while True:
                yield next(gen)
        except StopIteration as stop:
            card_suggestions, suggestions_err, suggestions_raw = stop.value

        logger.info(
            "Card suggestions extracted: %d items (err=%s)",
            len(card_suggestions),
            suggestions_err,
        )
        if suggestions_err:
            yield {
                "type": "suggestions_error",
                "message": suggestions_err,
                "raw": (suggestions_raw or "")[:2000],
            }
        else:
            yield {"type": "card_suggestions", "suggestions": card_suggestions}

        yield {"type": "done", "cost_usd": 0.0}
    except _CancelledError:
        if _run_stats:
            _run_stats.cancelled = True
        yield {"type": "cancelled"}
    finally:
        _run_lock.release()


def extract_constraints(theme_text: str, model_key: str) -> ConstraintsResult:
    """Aggregating wrapper around :func:`stream_constraints_extraction`.

    Used by the non-streaming refresh endpoint. Streaming SSE handlers should
    call ``stream_constraints_extraction`` directly so per-subcall results
    flush to the browser as soon as they're ready.
    """
    constraints: list = []
    card_suggestions: list = []
    constraints_error: str | None = None
    constraints_raw: str | None = None
    suggestions_error: str | None = None
    suggestions_raw: str | None = None
    cost = 0.0
    for event in stream_constraints_extraction(theme_text, model_key):
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

    return ConstraintsResult(
        constraints=constraints,
        card_suggestions=card_suggestions,
        cost_usd=cost,
        constraints_error=constraints_error,
        constraints_raw=constraints_raw,
        suggestions_error=suggestions_error,
        suggestions_raw=suggestions_raw,
    )
