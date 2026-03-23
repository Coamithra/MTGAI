"""Theme extraction from uploaded documents.

Handles PDF/text file reading, token counting, chunking for large
documents, and LLM-based theme extraction with streaming output.
"""

from __future__ import annotations

import base64
import datetime
import logging
import math
import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_OUTPUT_BUDGET = 8192  # tokens reserved for LLM output
_OVERLAP_CHARS = 2000  # character overlap between chunks
_LOG_DIR = Path("C:/Programming/MTGAI/output/extraction_logs")

OLLAMA_URL = os.environ.get("MTGAI_OLLAMA_URL", "http://localhost:11434").strip()

# Conversation log file — set once per extraction run
_conversation_log: Path | None = None


def _init_conversation_log() -> Path:
    """Create a new timestamped conversation log file."""
    global _conversation_log
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _conversation_log = _LOG_DIR / f"extraction_{ts}.md"
    _conversation_log.write_text(
        f"# Theme Extraction Log — {ts}\n\n",
        encoding="utf-8",
    )
    return _conversation_log


def _log_conversation(
    step: str,
    system_prompt: str,
    user_prompt: str,
    response: str,
) -> None:
    """Append a full LLM conversation turn to the log file."""
    if _conversation_log is None:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    with open(_conversation_log, "a", encoding="utf-8") as f:
        f.write(f"---\n\n## [{ts}] {step}\n\n")
        f.write(f"### System Prompt\n\n```\n{system_prompt}\n```\n\n")
        # Truncate user prompt if huge (don't log full source text)
        user_display = user_prompt
        if len(user_prompt) > 2000:
            user_display = (
                user_prompt[:1000]
                + f"\n\n[... {len(user_prompt) - 2000} chars truncated ...]\n\n"
                + user_prompt[-1000:]
            )
        f.write(f"### User Prompt\n\n```\n{user_display}\n```\n\n")
        f.write(f"### Response\n\n{response}\n\n")


# Section definitions for per-section multi-pass extraction
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
        "List creature types with DETAILED physical descriptions — body type, "
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
        "Include visual descriptions — architecture, atmosphere, scale. "
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


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ExtractionPlan:
    """Pre-extraction analysis returned to the UI for confirmation."""

    text: str
    image_count: int
    token_count: int
    context_window: int
    fits_in_context: bool
    chunk_count: int
    estimated_cost_usd: float
    model_key: str
    model_name: str
    supports_vision: bool


@dataclass
class ConstraintsResult:
    """Structured output from the constraints extraction pass."""

    constraints: list[str]
    card_suggestions: list[dict[str, str]]  # [{name, description}]
    cost_usd: float


# ---------------------------------------------------------------------------
# File content extraction
# ---------------------------------------------------------------------------


def extract_file_content(file_bytes: bytes, filename: str) -> tuple[str, list[bytes]]:
    """Extract text and embedded images from an uploaded file.

    Returns ``(text, images)`` where *images* is a list of PNG byte buffers
    extracted from PDF pages.  For plain-text files *images* is empty.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(file_bytes)
    else:
        # .txt, .md, or anything else — treat as UTF-8 text
        text = file_bytes.decode("utf-8", errors="replace")
        return text, []


def _extract_pdf(file_bytes: bytes) -> tuple[str, list[bytes]]:
    """Extract text and embedded images from a PDF using PyMuPDF."""
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text: list[str] = []
    images: list[bytes] = []

    for page in doc:
        pages_text.append(page.get_text("text"))

        # Extract embedded images
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                # Convert CMYK or other color spaces to RGB
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                # Skip tiny images (icons, bullets, etc.)
                if pix.width < 100 or pix.height < 100:
                    continue
                images.append(pix.tobytes("png"))
            except Exception:
                logger.debug("Skipping unreadable image xref=%d", xref)

    doc.close()
    text = "\n\n".join(pages_text)
    text = _clean_pdf_text(text)
    logger.info(
        "PDF extracted: %d pages, %d chars, %d images",
        len(pages_text),
        len(text),
        len(images),
    )
    return text, images


def _clean_pdf_text(text: str) -> str:
    """Clean up common PDF extraction artifacts.

    Google Docs exports (and many other PDF generators) insert zero-width
    spaces (U+200B), non-breaking spaces, and other Unicode junk between
    words. This collapses them into normal text.
    """
    import re

    # Replace zero-width spaces with real spaces (Google Docs PDFs use these
    # as word separators instead of actual space characters)
    text = text.replace("\u200b", " ")
    text = text.replace("\u200c", " ")
    text = text.replace("\u200d", " ")
    text = text.replace("\ufeff", "")  # BOM

    # Replace non-breaking spaces with regular spaces
    text = text.replace("\u00a0", " ")

    # Collapse multiple spaces into one
    text = re.sub(r" {2,}", " ", text)

    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # Strip standalone page numbers (lines that are just a number)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    # Collapse any resulting blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def _get_system_prompt() -> str:
    """Load the theme extraction system prompt from disk."""
    return (_PROMPTS_DIR / "theme_extraction.txt").read_text(encoding="utf-8")


def count_tokens(
    text: str,
    model_key: str,
    include_images: bool = False,
    image_count: int = 0,
) -> int:
    """Count input tokens for extraction.

    For Anthropic models uses the ``count_tokens`` API (free, server-side).
    For Ollama models falls back to a ~4 chars/token heuristic.
    """
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    system_prompt = _get_system_prompt()

    if model_info.provider == "anthropic":
        return _count_tokens_anthropic(
            text, system_prompt, model_info.model_id, include_images, image_count
        )
    else:
        # Use tiktoken for accurate local model counts
        total = _count_tokens_tiktoken(system_prompt + "\n\n" + text)
        if include_images and image_count > 0:
            total += image_count * 1600  # ~1600 tokens per image
        return total


def _count_tokens_anthropic(
    text: str,
    system_prompt: str,
    model_id: str,
    include_images: bool,
    image_count: int,
) -> int:
    """Count tokens using the Anthropic count_tokens API (free call)."""
    from anthropic import Anthropic

    client = Anthropic()

    user_content = f"Extract theme from:\n\n{text}"

    try:
        result = client.messages.count_tokens(
            model=model_id,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        token_count = result.input_tokens
    except Exception as e:
        logger.warning("count_tokens API failed, using heuristic: %s", e)
        token_count = (len(system_prompt) + len(text)) // 4

    # Add image token estimate (count_tokens doesn't count images we haven't sent)
    if include_images and image_count > 0:
        token_count += image_count * 1600

    return token_count


def _count_tokens_tiktoken(text: str) -> int:
    """Count tokens using tiktoken (works offline, used for local models).

    Falls back to chars//4 if tiktoken is not available.
    """
    try:
        import tiktoken

        # cl100k_base covers GPT-4/GPT-3.5 and is close enough for Qwen
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        logger.debug("tiktoken not installed, using chars//4 heuristic")
        return len(text) // 4


# ---------------------------------------------------------------------------
# Pre-extraction analysis
# ---------------------------------------------------------------------------


def analyze_extraction(
    text: str,
    image_count: int,
    model_key: str,
    include_images: bool = False,
) -> ExtractionPlan:
    """Analyze a document and return an ExtractionPlan for UI confirmation."""
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    token_count = count_tokens(text, model_key, include_images, image_count)

    # Budget available for input (context window minus output reservation)
    available = model_info.context_window - _OUTPUT_BUDGET
    fits = token_count <= available

    if fits:
        chunk_count = 1
    else:
        # Match the actual per-section chunking budget (half context window)
        chunk_token_budget = model_info.context_window // 2
        chunk_count = max(1, math.ceil(token_count / max(chunk_token_budget, 1)))

    # Cost estimate: for multi-chunk, it's 7 sections x N chunks calls
    if fits:
        total_input_tokens = token_count
        total_output_tokens = _OUTPUT_BUDGET
    else:
        # Each call sends ~chunk_token_budget input + prompt overhead
        calls = len(_SECTIONS) * chunk_count
        total_input_tokens = calls * (chunk_token_budget + 1000)
        total_output_tokens = calls * _OUTPUT_BUDGET

    estimated_cost = (
        total_input_tokens * model_info.input_price + total_output_tokens * model_info.output_price
    ) / 1_000_000

    return ExtractionPlan(
        text=text,
        image_count=image_count,
        token_count=token_count,
        context_window=model_info.context_window,
        fits_in_context=fits,
        chunk_count=chunk_count,
        estimated_cost_usd=estimated_cost,
        model_key=model_key,
        model_name=model_info.name,
        supports_vision=model_info.supports_vision,
    )


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def _chunk_text_by_tokens(text: str, max_tokens: int, model_info) -> list[str]:
    """Split text into chunks that each fit within *max_tokens*.

    Uses actual token counting (tiktoken for local, Anthropic API for cloud).
    Falls back to char-based chunking if token counting fails.
    """
    # First check if text already fits
    total_tokens = _count_tokens_tiktoken(text)
    if total_tokens <= max_tokens:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _count_tokens_tiktoken(para)
        if current_tokens + para_tokens > max_tokens and current:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0
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


def chunk_text(text: str, max_chars: int, overlap_chars: int = _OVERLAP_CHARS) -> list[str]:
    """Split text on paragraph boundaries with overlap.

    Each chunk is at most *max_chars* characters.  The last ~overlap_chars
    of each chunk are prepended to the next to maintain context continuity.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # account for \n\n separator
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            # Overlap: keep tail paragraphs up to overlap_chars
            overlap: list[str] = []
            overlap_len = 0
            for p in reversed(current):
                if overlap_len + len(p) > overlap_chars:
                    break
                overlap.insert(0, p)
                overlap_len += len(p) + 2
            current = overlap
            current_len = overlap_len
        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    logger.info(
        "Split text into %d chunks (max %d chars, overlap %d)",
        len(chunks),
        max_chars,
        overlap_chars,
    )
    return chunks


# ---------------------------------------------------------------------------
# Streaming theme extraction
# ---------------------------------------------------------------------------


def stream_theme_extraction(
    text: str,
    model_key: str,
    include_images: bool = False,
    images: list[bytes] | None = None,
) -> Generator[dict, None, None]:
    """Stream theme extraction from document text.

    Handles chunking at this level so all providers benefit.
    Yields dicts with one of these shapes:
        ``{"type": "status", "message": "..."}``
        ``{"type": "theme_chunk", "text": "..."}``
        ``{"type": "complete", "theme_text": "...", "cost_usd": float}``
        ``{"type": "error", "message": "..."}``
    """
    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        yield {"type": "error", "message": f"Unknown model key: {model_key}"}
        return

    system_prompt = _get_system_prompt()
    _init_conversation_log()
    logger.info(
        "Starting theme extraction: model=%s provider=%s text_len=%d",
        model_info.model_id,
        model_info.provider,
        len(text),
    )

    # Determine if chunking is needed
    available = model_info.context_window - _OUTPUT_BUDGET
    token_count = count_tokens(text, model_key, include_images, len(images or []))
    logger.info(
        "Token count: %d, available budget: %d, context_window: %d",
        token_count,
        available,
        model_info.context_window,
    )

    if token_count <= available:
        # --- Single-pass extraction ---
        logger.info("Single-pass extraction (fits in context)")
        yield {"type": "status", "message": "Generating theme..."}

        template = (_PROMPTS_DIR / "theme_chunk_single.txt").read_text(encoding="utf-8")
        user_msg = template.format(text=text)
        yield from _stream_single_call(
            user_msg,
            system_prompt,
            model_info,
            include_images,
            images,
            stream_to_ui=True,
        )
    else:
        # --- Multi-chunk: per-section extraction ---
        # Each section is extracted independently across all chunks,
        # then streamed to the UI as it completes.
        # Use at most half the context for input, leaving the rest for
        # system prompt, accumulated theme in merge prompts, and output.
        chunk_token_budget = model_info.context_window // 2
        chunks = _chunk_text_by_tokens(text, chunk_token_budget, model_info)
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
                f"Large document — extracting {len(_SECTIONS)} "
                f"sections across {len(chunks)} chunks..."
            ),
        }

        sys_template = (_PROMPTS_DIR / "theme_section_system.txt").read_text(
            encoding="utf-8",
        )
        first_template = (_PROMPTS_DIR / "theme_section_first.txt").read_text(
            encoding="utf-8",
        )
        next_template = (_PROMPTS_DIR / "theme_section_next.txt").read_text(
            encoding="utf-8",
        )

        completed_sections: list[str] = []
        total_cost = 0.0

        for sec_idx, (sec_name, sec_guidance) in enumerate(_SECTIONS):
            yield {
                "type": "status",
                "message": (f"Extracting {sec_name} ({sec_idx + 1}/{len(_SECTIONS)})..."),
            }
            logger.info("Section %d/%d: %s", sec_idx + 1, len(_SECTIONS), sec_name)

            section_prompt = sys_template.format(
                section_name=sec_name,
                section_guidance=sec_guidance,
            )
            accumulated = ""

            for ci, chunk_part in enumerate(chunks):
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

                chunk_result = ""
                for event in _stream_single_call(
                    user_msg,
                    section_prompt,
                    model_info,
                    stream_to_ui=False,
                ):
                    if event["type"] == "theme_chunk":
                        chunk_result += event["text"]
                    elif event["type"] == "complete":
                        chunk_result = event.get("theme_text", chunk_result)
                        total_cost += event.get("cost_usd", 0)
                    elif event["type"] == "error":
                        yield {
                            "type": "error",
                            "message": (f"{sec_name} chunk {ci + 1} failed: {event['message']}"),
                        }
                        return

                # Skip "no info" placeholder responses
                stripped = chunk_result.strip()
                if stripped.lower().startswith("no information found"):
                    logger.info(
                        "  chunk %d/%d: no info for %s",
                        ci + 1,
                        len(chunks),
                        sec_name,
                    )
                    continue

                # The merge prompt asks the model to output ALL entries
                # (existing + new), so the result replaces the accumulated text
                accumulated = stripped
                logger.info(
                    "  chunk %d/%d: %d chars for %s",
                    ci + 1,
                    len(chunks),
                    len(stripped),
                    sec_name,
                )

            # Section complete — stream it to UI
            if accumulated:
                section_text = f"# {sec_name}\n\n{accumulated}"
            else:
                section_text = f"# {sec_name}\n\nNo information found."
            completed_sections.append(section_text)

            # Send section to textarea
            separator = "\n\n" if sec_idx > 0 else ""
            yield {"type": "theme_chunk", "text": f"{separator}{section_text}"}
            logger.info(
                "Section %s complete: %d chars",
                sec_name,
                len(accumulated),
            )

        full_theme = "\n\n".join(completed_sections)
        yield {
            "type": "complete",
            "theme_text": full_theme,
            "cost_usd": total_cost,
        }


def _build_user_content(
    text: str,
    prefix: str,
    include_images: bool,
    images: list[bytes] | None,
) -> list[dict] | str:
    """Build user message content, optionally including images."""
    if include_images and images:
        content: list[dict] = []
        for img_bytes in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(img_bytes).decode(),
                    },
                }
            )
        content.append({"type": "text", "text": f"{prefix}\n\n{text}"})
        return content
    return f"{prefix}\n\n{text}"


def _stream_single_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    include_images: bool = False,
    images: list[bytes] | None = None,
    stream_to_ui: bool = True,
    json_mode: bool = False,
) -> Generator[dict, None, None]:
    """Stream a single LLM call (no chunking — caller handles that).

    Yields theme_chunk events (if *stream_to_ui*), then a final
    ``complete`` event with the full text and cost.
    """
    if model_info.provider == "anthropic":
        yield from _stream_anthropic_call(
            user_msg,
            system_prompt,
            model_info,
            include_images,
            images,
            stream_to_ui,
        )
    elif model_info.provider == "ollama":
        yield from _stream_ollama_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            json_mode=json_mode,
        )
    else:
        yield {"type": "error", "message": f"Unsupported provider: {model_info.provider}"}


def _stream_anthropic_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    include_images: bool,
    images: list[bytes] | None,
    stream_to_ui: bool,
) -> Generator[dict, None, None]:
    """Single Anthropic streaming call."""
    from anthropic import Anthropic

    from mtgai.generation.llm_client import calc_cost

    client = Anthropic()
    model_id = model_info.model_id

    user_content = _build_user_content(user_msg, "", include_images, images)

    theme_text = ""
    try:
        with client.messages.stream(
            model=model_id,
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            temperature=0.7,
        ) as stream:
            for event in stream:
                if (
                    hasattr(event, "type")
                    and event.type == "content_block_delta"
                    and hasattr(event.delta, "text")
                ):
                    theme_text += event.delta.text
                    if stream_to_ui:
                        yield {"type": "theme_chunk", "text": event.delta.text}

            final = stream.get_final_message()
            cost = calc_cost(
                model_id,
                final.usage.input_tokens,
                final.usage.output_tokens,
            )
    except Exception as e:
        logger.error("Anthropic streaming call failed: %s", e, exc_info=True)
        yield {"type": "error", "message": str(e)}
        return

    logger.info(
        "Anthropic call complete: %d chars, cost=$%.4f",
        len(theme_text),
        cost,
    )
    _log_conversation("Anthropic call", system_prompt, str(user_content), theme_text)
    yield {"type": "complete", "theme_text": theme_text, "cost_usd": cost}


def _stream_ollama_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    json_mode: bool = False,
) -> Generator[dict, None, None]:
    """Single Ollama streaming call using native API (not OpenAI compat).

    The OpenAI compatibility layer silently ignores ``num_ctx``, so we
    must use Ollama's native ``/api/chat`` endpoint to set context size.
    """
    import json as _json

    import requests

    num_ctx = model_info.context_window
    theme_text = ""

    logger.info(
        "Ollama call: model=%s, prompt_len=%d, num_ctx=%d",
        model_info.model_id,
        len(user_msg),
        num_ctx,
    )

    body: dict = {
        "model": model_info.model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.7,
            "num_predict": -1,
        },
    }
    if json_mode:
        body["format"] = "json"

    try:
        if stream_to_ui:
            body["stream"] = True
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=body,
                stream=True,
                timeout=600,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = _json.loads(line)
                if data.get("done"):
                    break
                content = data.get("message", {}).get("content", "")
                if content:
                    theme_text += content
                    yield {"type": "theme_chunk", "text": content}
        else:
            body["stream"] = False
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=body,
                timeout=600,
            )
            resp.raise_for_status()
            theme_text = resp.json().get("message", {}).get("content", "")
    except Exception as e:
        logger.error("Ollama streaming call failed: %s", e, exc_info=True)
        yield {"type": "error", "message": str(e)}
        return

    logger.info("Ollama call complete: %d chars extracted", len(theme_text))
    _log_conversation("Ollama call", system_prompt, user_msg, theme_text)
    yield {"type": "complete", "theme_text": theme_text, "cost_usd": 0.0}


# ---------------------------------------------------------------------------
# Constraints extraction (second pass)
# ---------------------------------------------------------------------------


def extract_constraints(theme_text: str, model_key: str) -> ConstraintsResult:
    """Extract set constraints and card suggestions in two separate calls.

    Uses plain text output (not tool use) for better local model compatibility.
    For Anthropic models, falls back to generate_with_tool for structured output.
    """

    from mtgai.settings.model_registry import get_registry

    registry = get_registry()
    model_info = registry.get_llm(model_key)
    if model_info is None:
        raise ValueError(f"Unknown model key: {model_key}")

    # Ensure we have a log file (may be called standalone via refresh)
    if _conversation_log is None:
        _init_conversation_log()

    logger.info(
        "Extracting constraints + suggestions: model=%s, theme_len=%d",
        model_info.model_id,
        len(theme_text),
    )

    import json as _json

    # --- Call 1: Constraints (JSON mode) ---
    constraints_prompt = (_PROMPTS_DIR / "constraints_system.txt").read_text(
        encoding="utf-8",
    )
    constraints_text = ""
    for event in _stream_single_call(
        f"Setting:\n\n{theme_text}",
        constraints_prompt,
        model_info,
        stream_to_ui=False,
        json_mode=True,
    ):
        if event["type"] == "complete":
            constraints_text = event.get("theme_text", "")

    _log_conversation(
        "Constraints extraction",
        constraints_prompt,
        f"Setting:\n\n{theme_text[:500]}...",
        constraints_text,
    )

    constraints: list[str] = []
    try:
        parsed = _json.loads(constraints_text)
        constraints = parsed.get("constraints", [])
    except _json.JSONDecodeError:
        logger.warning("Failed to parse constraints JSON: %s", constraints_text[:200])

    logger.info("Constraints extracted: %d items", len(constraints))

    # --- Call 2: Card suggestions (JSON mode) ---
    suggestions_prompt = (_PROMPTS_DIR / "card_suggestions_system.txt").read_text(
        encoding="utf-8",
    )
    suggestions_text = ""
    for event in _stream_single_call(
        f"Setting:\n\n{theme_text}",
        suggestions_prompt,
        model_info,
        stream_to_ui=False,
        json_mode=True,
    ):
        if event["type"] == "complete":
            suggestions_text = event.get("theme_text", "")

    _log_conversation(
        "Card suggestions extraction",
        suggestions_prompt,
        f"Setting:\n\n{theme_text[:500]}...",
        suggestions_text,
    )

    card_suggestions: list[dict[str, str]] = []
    try:
        parsed = _json.loads(suggestions_text)
        card_suggestions = parsed.get("card_suggestions", [])
    except _json.JSONDecodeError:
        logger.warning("Failed to parse suggestions JSON: %s", suggestions_text[:200])

    logger.info("Card suggestions extracted: %d items", len(card_suggestions))

    return ConstraintsResult(
        constraints=constraints,
        card_suggestions=card_suggestions,
        cost_usd=0.0,
    )
