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

from llmfacade import SystemBlock
from llmfacade.exceptions import LLMError

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# Tokens reserved for LLM output. Used both for budget calculations and as the
# concrete max_tokens / num_predict on each call - keep these in sync.
_OUTPUT_BUDGET = 16384
_LOG_DIR = Path("C:/Programming/MTGAI/output/extraction_logs")

# Stop sequences keep the model from echoing the source-text divider markers
# back into the extraction (a real failure mode on weaker local models).
_OLLAMA_STOP_SEQUENCES = [
    "--- START OF SOURCE TEXT ---",
    "--- END OF SOURCE TEXT ---",
]

# Hard cap on JSON subcall output (constraints / card_suggestions). With
# num_predict=-1 a model in a repetition loop fills the entire context window
# before the post-hoc detector even runs. Mid-stream repetition detection (every
# 200 chars) is the primary runaway guard; this cap is just a backstop.
# Constraints output is tiny (3-8 short strings). Card suggestions (3-5 cards
# with descriptions) needs more room - local models sometimes pad descriptions
# or emit extra cards before the JSON closes.
_JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS = 4096
_JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS = 8192

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
        single_template = (_PROMPTS_DIR / "theme_chunk_single.txt").read_text(
            encoding="utf-8"
        )
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


# TEMPORARY TEST HACK: hardcoded theme used when MTGAI_THEME_HACK_LOG is set.
# Lets us skip the slow theme-extraction step while iterating on downstream
# constraints / card-suggestions passes. Delete this constant and the
# _replay_hardcoded_theme helper (plus the caller block at the top of
# stream_theme_extraction) when no longer needed.
_HARDCODED_THEME = """\
# World Overview

Athas is a brutal, sun-scorched desert wasteland characterized by extreme temperatures, ranging from blistering heat during the day to freezing temperatures at night. The world is defined by a "crimson sun" and an "olive-tinged sky," where the scarcity of water and metal dictates every aspect of life. It is described as a "barbaric shadow of some better world," a place where once-lush landscapes have been warped into a savage, dying environment.

The central conflict revolves around survival in a land of "mortal desolation." Societies are divided by how they interact with the world's dwindling life force: the destructive "Defilers" who drain magic from the land, and the "Preservers" who attempt to balance it. Political strife is constant, with powerful Sorcerer-Kings ruling city-states as absolute dictators, while nomadic tribes, raiding groups, and escaped slaves struggle for autonomy in the vast, dangerous wilds.

# Themes

- **Scarcity and Survival:** The desperate struggle for water, food, and metal.
- **Ecological Decay:** The tension between Defilers (who wither the land) and Preservers (who sustain it).
- **The Power of the Mind:** The widespread use of psionics as a "great equalizer."
- **Tyranny vs. Freedom:** The absolute rule of Sorcerer-Kings and Templars against the desperate efforts of slave tribes and the Veiled Alliance.
- **The Shadow of a Golden Age:** The presence of massive, decaying ruins from a more prosperous past.
- **Brutality and Darwinism:** A "kill or be killed" social order where even herbivores have deadly defenses.

# Creature Types

- **Human:** Versatile and common; often found in any social role from farmer to sorcerer-king.
- **Wizard:** Magic users who either drain the life from the world (Defilers) or work to balance it (Preservers).
- **Cleric:** Priests who pay homage to the four elemental forces (air, earth, fire, water) or serve as Druids.
- **Druid:** Special clerics who serve nature and the planetary equilibrium, often living in isolation to protect their "guarded land."
- **Templar:** Clergy who tap into the magical energy of a Sorcerer-King rather than elemental forces; they act as the king's bureaucratic and religious agents.
- **Soldier:** Often composed of burly slaves or highly trained elite units; can include half-giants.
- **Gladiator:** Highly trained combatants, often muls, used for public entertainment in arenas.
- **Erdlu:** Large, flightless, featherless birds. They have massive, round bodies, lanky legs with four-toed feet and razor-sharp claws, and yellow, snake-like necks with small, round heads and wedge-shaped beaks. Their skin is covered in flaky gray-to-red scales.
- **Kank:** Giant, six-legged insects. They are gentle, docile beasts of burden that produce a thick green honey on their abdomens.
- **Mekillot:** Massive, six-ton lizards with incredibly thick hides. They are cantankerous and predatory.
- **Thri-Kreen:** Giant, intelligent insects that never sleep. They are highly aggressive and organize by dominance.
- **Mul:** A crossbreed of human and dwarf. They stand over six feet tall, weigh 200-300 pounds, and have hairless, coppery skin as tough as gith hide. They are sterile and possess a single-minded, vicious nature.
- **Half-Giant:** A magical crossbreed of human and giant. They are immensely strong but possess limited intellectual capacity.
- **Silt Horror:** A creature consisting of huge, white, fleshy tentacles attached to a bulbous, malleable body that resembles soft clay.
- **Kluzd:** Ten-foot-long, snake-like reptiles that live in mudflats.
- **Braxat:** Predatory creatures of the Tablelands.
- **Tembo:** Predatory creatures of the Tablelands.
- **Belgoi:** Predatory creatures of the Tablelands.
- **Silk Wyrm:** A dangerous monster of the Hinterlands.
- **Gaj:** Ferocious, mid-sized predators found on islands.
- **Klars:** Huge, nocturnal bears that hunt using psionics.

# Factions

- **Sorcerer-Kings:** Absolute dictators of the city-states. They are powerful wizards (mostly Defilers) who use magic to prolong their lives for centuries. They rule from fortified palaces.
- **Templars:** The religious and bureaucratic agents of the Sorcerer-Kings. They control the population, manage the bureaucracy, and are the sole guardians of reading and writing. Their rank is often denoted by necklaces (in Gulg).
- **Nobility:** Families that control the farms and water of the cities. They sit on advisory councils and maintain private armies of slave soldiers.
- **Merchant Houses:** Sophisticated, family-owned trading companies. They operate through headquarters, emporiums, outposts, and caravans. They follow a strict, secret Merchant Code.
- **Veiled Alliance:** A secret confederation of Preservers working together to protect their members from the persecution of Sorcerer-Kings.
- **Raiding Tribes:** Despicable bands of cutthroats that live in desolate places and survive by pillaging caravans, villages, and herds.
- **Slave Tribes:** Groups of escaped slaves who live in remote villages. They are diverse in race and often target city-states or caravans for revenge.
- **Nomadic Herdsmen (Douars):** Small groups of families that wander the wastes with flocks of animals. They are led by a magic-wielding patriarch/wizard.
- **Hunting and Gathering Clans:** Small, primitive groups (often thri-kreen or halflings) that live most freely, following game and foraging.
- **Dwarven Villages:** Communities centered around a specific purpose (like mining or building), governed by a strict code of honor and a leader chosen by arrival order.
- **Halfling Tribes:** Small, isolated clans that inhabit forest ridges. They are led by a Preserver chief and value racial harmony among themselves, but view other races as food.
- **Giant Clans:** Groups inhabiting islands in the Sea of Silt; they are polite but highly territorial.

# Landmarks

- **Sea of Silt:** A vast, sunken basin filled with pearly gray, fine dust. It can be a calm, flat plain or a churning, dark storm that obscures all vision. It is deep enough to swallow travelers.
- **Tablelands:** A wide band of terrain surrounding the Sea of Silt, consisting of stony barrens, sandy wastes, salt flats, rocky badlands, scrub plains, and silt basins.
- **Ringing Mountains:** A massive range of mountains and foothills encircling the Tablelands. They feature deep canyons, high peaks, and a lush "Forest Ridge" at the summit.
- **Hinterlands:** The vast, flat, and largely unexplored plains lying beyond the Ringing Mountains.
- **Tyr:** A major city-state in the Tyr region, known for its iron mines and a massive ziggurat currently under construction by Kalak.
- **Balic:** A city ruled by Andropinis, featuring a white marble palace on a fortified bluff and an agora filled with merchant emporiums.
- **Draj:** A city built on a large mudflat, featuring a massive stone pyramid and a large gladiatorial arena.
- **Gulg:** A city hidden behind a thick hedge of thorny trees, with houses made of mud and thatched vines.
- **Nibenay:** A city near the Crescent Forest, characterized by buildings decorated with elaborate stone reliefs and bubbling springs.
- **Raam:** A chaotic city ruled by Abalach-Re, featuring an ivory-walled palace on a grassy knoll.
- **Urik:** A powerful city-state with a massive fortress and economy based on obsidian quarrying.
- **Smoking Crown:** A volcanic mountain/region with yellowish steam and obsidian deposits.
- **Dragon's Bowl:** A great, awe-inspiring basin formed by the birth of a dragon, containing the cerulean Lake Pit.
- **Lake Pit:** A large, pristine, cerulean lake located at the northern end of the Dragon's Bowl.
- **Lake of Golden Dreams:** A boiling lake with yellowish steam and a network of underwater tunnels.
- **Lost Oasis:** A geyser in a salt flat surrounded by a forest of pinyon trees.
- **Mud Palace:** A magnificent white marble castle with no doors or windows, rising from a jungle-like mudflat.
- **Waverly:** An ancient, walled city on an island, featuring petrified wood crafts and a central fountain.
- **Lake Island:** A massive volcano rising from the Sea of Silt, featuring a crater with a clear blue lake and bluish steam.
- **Dragon Crown Mountain:** An ancient volcano in the Hinterlands with a hidden pine forest and an alabaster palace.

# Notable Characters

- **Andropinis:** The Dictator of Balic. A powerful sorcerer-king who has ruled for over 700 years.
- **Tectuktitlay:** The Sorcerer-king of Draj, known as "The Mighty and Omnipotent." He claims to be a god and rules from a stone pyramid.
- **Lalali-Puy:** The "Oba" (forest goddess) and Sorcerer-queen of Gulg. She rules from an agafari tree.
- **Nibenay:** The "Shadow King" of Nibenay. An enigmatic ruler who lives in a palace shaped like a giant bust of his own head.
- **Abalach-Re:** The "Great Vizier" of Raam. A sorcerer-queen who claims to be a servant of a higher, mysterious power.
- **Kalak:** The "Tyrant of Tyr." A pragmatic, ruthless ruler who is currently obsessed with building a massive ziggurat.
- **Hamanu:** The warrior king of Urik. A legendary general who leads his armies personally and has never been defeated.
- **Urga-Zoltapl:** The halfling chief of the Ogo village.
- **Xaynon:** An ex-gladiator mul who leads the slave-tribe village of Salt View.
- **Enola:** A mul who protects the Dragon's Bowl.
- **Durwadala:** A thri-kreen druid who protects the Lost Oasis.

# Races

- **Humans:** The most common and versatile race; they occupy all social strata and are noted for their talent for political intrigue and treachery.
- **Dwarves:** Strong and determined; they are often found as laborers, soldiers, or craftsmen, and follow a strict code of honor.
- **Elves:** Nomadic and restless; they are expert traders, fast, and stealthy, but are considered untrustworthy by outsiders. They maintain strict honor within their own tribes.
- **Half-Elves:** Often loners who grow up between cultures; they are frequently found as templars or farmers.
- **Half-Giants:** A magical crossbreed of human and giant; they are immensely strong but have limited intelligence.
- **Muls:** A sterile crossbreed of human and dwarf; they are characterized by their strength, coppery skin, and fierce, single-minded nature.
- **Thri-Kreen:** Giant, intelligent insects that live in packs and follow a strict dominance hierarchy. They are tireless hunters.
- **Halflings:** Feral and primitive; they live in small clans in the mountains and view most other races as potential food.
- **Giants:** A large, polite, but highly territorial race that inhabits islands in the Sea of Silt."""


def _replay_hardcoded_theme() -> Generator[dict, None, None]:
    """TEMPORARY TEST HACK: emit _HARDCODED_THEME as if it came from the LLM.

    Keeps the SSE event shape identical to a real extraction run so downstream
    code (UI progress bar, constraints/card-suggestions pass) can't tell the
    difference.
    """
    yield {"type": "status", "message": "[HACK] Using hardcoded theme"}
    # Chunk so the UI progress bar animates a bit; any chunk size works.
    chunk_size = 2000
    for i in range(0, len(_HARDCODED_THEME), chunk_size):
        yield {
            "type": "theme_chunk",
            "text": _HARDCODED_THEME[i : i + chunk_size],
        }
    yield {
        "type": "complete",
        "theme_text": _HARDCODED_THEME,
        "cost_usd": 0.0,
    }


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
    # =========================================================================
    # TEMPORARY TEST HACK: skip LLM, emit a hardcoded theme so downstream
    # constraints / card-suggestions passes can be iterated on without
    # waiting for the slow real extraction. Controlled by MTGAI_THEME_HACK_LOG
    # (env-var name kept for continuity with existing .env entries - any
    # truthy value enables the hack). Remove the env lookup, the helper
    # _replay_hardcoded_theme, and the _HARDCODED_THEME constant at the
    # module bottom when no longer needed.
    # =========================================================================
    # Mirror the .env loader from llm_client.py so the hack flag works even
    # if llm_client hasn't been imported yet in this process.
    _env_path = Path("C:/Programming/MTGAI/.env")
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

    if os.environ.get("MTGAI_THEME_HACK_LOG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        yield from _replay_hardcoded_theme()
        return

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
        log_dir = _init_run_log_dir()
        logger.info(
            "Starting theme extraction: model=%s provider=%s text_len=%d log_dir=%s",
            model_info.model_id,
            model_info.provider,
            len(text),
            log_dir,
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
                "log_path": str(_run_log_dir) if _run_log_dir else None,
            }
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
        logger.info("=== Section %d/%d: %s ===", sec_idx + 1, len(_SECTIONS), sec_name)
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
) -> Generator[dict, None, None]:
    """Dispatch one streaming call to the configured provider.

    Yields theme_chunk events (if *stream_to_ui*), then a final ``complete``
    event with the full text and cost - or an ``error`` event on failure.

    ``step_label`` tags the call in the conversation log filename (e.g.
    "section-3-7-creature-types-chunk-4-10"). If None, a generic name is used.

    ``output_budget_override`` forces a specific Ollama ``num_predict`` for
    this call (ignored on Anthropic, which uses its own fixed max_tokens).
    """
    if model_info.provider == "anthropic":
        yield from _stream_anthropic_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            step_label=step_label,
        )
    elif model_info.provider == "ollama":
        yield from _stream_ollama_call(
            user_msg,
            system_prompt,
            model_info,
            stream_to_ui,
            json_mode=json_mode,
            step_label=step_label,
            output_budget_override=output_budget_override,
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
                if _cancel_event.is_set():
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

        logger.info(
            "Anthropic call complete: %d chars, cost=$%.4f", len(theme_text), cost
        )
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


def _stream_ollama_call(
    user_msg: str,
    system_prompt: str,
    model_info,
    stream_to_ui: bool,
    json_mode: bool = False,
    step_label: str | None = None,
    output_budget_override: int | None = None,
) -> Generator[dict, None, None]:
    """Single Ollama streaming call via llmfacade.

    Pre-checks input fits in context, post-checks llmfacade Usage for
    truncation. Also runs MTGAI's mid-stream repetition detector every 200
    chars - local models (Gemma 4 in particular) sometimes loop forever
    inside ``num_predict``, and breaking the iterator early salvages the
    pre-loop text.

    ``output_budget_override`` overrides the default ``num_predict`` for
    this call (used by JSON subcalls that need a larger output budget).
    """
    from mtgai.generation.llm_client import _get_provider
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
            f"(num_ctx={num_ctx}, output_reserve={output_reserve}). "
            f"Reduce input or increase context window."
        )
        logger.error(msg)
        yield {"type": "error", "message": msg}
        return

    logger.info(
        "Ollama call: model=%s, est_input=%d tok, num_ctx=%d, output_reserve=%d",
        model_info.model_id,
        estimated_input_tokens,
        num_ctx,
        output_reserve,
    )

    provider = _get_provider("ollama")
    facade_model = provider.new_model(model_info.model_id, context_size=num_ctx)
    log_path = _build_call_log_path(step_label, "ollama-call")
    convo_kwargs: dict[str, Any] = {
        "max_tokens": output_reserve,
        "temperature": 0.7,
        "log_path": log_path,
    }
    if json_mode:
        convo_kwargs["output_format"] = "json"
    convo = facade_model.new_conversation(**convo_kwargs)

    theme_text = ""
    loop_err: str | None = None
    chars_since_check = 0
    last_usage = None
    last_finish_reason: str | None = None
    frames_total = 0
    frames_with_content = 0
    meta: dict[str, Any] = {
        "provider": "ollama",
        "model_id": model_info.model_id,
        "step_label": step_label,
        "json_mode": json_mode,
        "num_ctx": num_ctx,
        "output_reserve": output_reserve,
        "estimated_input_tokens": estimated_input_tokens,
        "outcome": "unknown",
    }

    try:
        stream_iter = convo.stream(user_msg, stop=_OLLAMA_STOP_SEQUENCES)
        try:
            for ev in stream_iter:
                if _cancel_event.is_set():
                    meta["outcome"] = "cancelled"
                    raise _CancelledError("cancelled mid-stream")
                frames_total += 1
                if ev.text_delta:
                    frames_with_content += 1
                    theme_text += ev.text_delta
                    if stream_to_ui:
                        yield {"type": "theme_chunk", "text": ev.text_delta}
                    chars_since_check += len(ev.text_delta)
                    if chars_since_check >= 200:
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
            logger.error("Ollama streaming call failed: %s", e, exc_info=True)
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
                "Ollama call aborted (repetition): %d chars before abort",
                len(theme_text),
            )
            # No usage frame on early-break; record with our estimate so the
            # run footer doesn't undercount aborted calls.
            _record_call(
                last_usage.prompt_tokens if last_usage else estimated_input_tokens,
                last_usage.completion_tokens
                if last_usage
                else _count_tokens_tiktoken(theme_text),
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
                f"Ollama stream ended with no usage frame after {len(theme_text)} "
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
            "Ollama call complete: %d chars, prompt_tokens=%d, completion_tokens=%d, "
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
                    "prompt_eval_count": last_usage.prompt_tokens,
                    "eval_count": last_usage.completion_tokens,
                    "done_reason": last_finish_reason or "",
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

    logger.info(
        "Extracting constraints + suggestions: model=%s, theme_len=%d",
        model_info.model_id,
        len(theme_text),
    )

    def _attempt_json_subcall(
        prompt: str, json_key: str, step_label: str, output_budget: int
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
        label: str, prompt_file: str, json_key: str, output_budget: int
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
                f"(json_mode, key='{json_key}', num_predict={output_budget})"
            )
            items, err, raw = _attempt_json_subcall(
                prompt, json_key, step_label, output_budget
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
        # Init the per-run log dir under the lock so a concurrent theme
        # extraction can't clobber our directory / stats / call counter, and
        # vice versa. Reentrant lock: when the caller is theme extraction it
        # already initialised these and we no-op.
        if _run_log_dir is None:
            _init_run_log_dir()

        # --- Call 1: Constraints (JSON mode) ---
        gen = _run_json_subcall(
            "Constraints extraction",
            "constraints_system.txt",
            "constraints",
            _JSON_SUBCALL_CONSTRAINTS_MAX_TOKENS,
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
            _JSON_SUBCALL_SUGGESTIONS_MAX_TOKENS,
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
