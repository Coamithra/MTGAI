"""Shared helpers for the post-card_gen review gates.

Both LLM steps (conformance, interactions) of the merged ``conformance`` gate
scan the same subset of the pool: every generated card *except* basic lands and
reprints. Basic lands carry no design to conform or combo; reprints are
pre-balanced staples (and aren't even materialized as cards yet). Keeping the
filter in one place means the two steps never drift on what they consider.

Both steps also run the **same batched, flag-only, streamed** shape: the pool is
grouped into batches, each batch is one streamed free-text call, and the model
emits a ``--CARD <slot_id>--`` block only for the cards it flags. The streaming +
truncation-retry + block-parsing machinery lives here (``stream_flag_batch`` and
the ``--CARD`` parse helpers) so the two gates stay byte-for-byte in lockstep on
the format we ask local models to produce — the same format the skeleton relabel
uses, chosen because a truncated reply still parses block-by-block (a giant JSON
tool call does not).

The structural ``generate_gate_tool`` (a retrying *tool-call* wrapper) is kept
for callers that still want a single structured response.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from mtgai.generation import temperatures as temps
from mtgai.generation.llm_client import (
    DrySampler,
    cost_from_result,
    generate_with_tool,
    stream_text,
)
from mtgai.generation.token_utils import OutputTruncatedError
from mtgai.models.card import Card
from mtgai.runtime import ai_lock

logger = logging.getLogger(__name__)

# A batch whose stream truncated (or errored) is re-rolled this many times total,
# bumping the temperature each retry to perturb a local repetition loop out of it
# (the verified lever where ``repeat_penalty`` is not — see
# ``learnings/gemma-repetition-loops.md``).
MAX_BATCH_ATTEMPTS = 3

# DRY (Don't Repeat Yourself) sampler enabled as the *escalation* step on a
# truncation retry, on top of the temperature bump. A plain temp bump usually
# breaks a Gemma repetition loop, but DRY structurally penalizes repeated token
# sequences and catches the loops that survive 0.6+. ``multiplier`` is the
# enabling knob (>0 required); the rest of llama.cpp's DRY defaults are fine.
RETRY_DRY_MULTIPLIER = 0.8


def _local_retry_dry(model: str | None) -> DrySampler | None:
    """A :class:`DrySampler` for the truncation-retry — only for a local model.

    DRY is a llama.cpp-only sampler; setting it on a hosted (Anthropic) model
    raises ``UnsupportedFeature`` in llmfacade, so we send it only when the
    resolved model is local. The local-vs-hosted gate mirrors
    :func:`temperatures.floor_for_local` exactly — a provider-aware, best-effort
    registry lookup keyed on ``provider == "llamacpp"`` that degrades to "not
    local" (``None``) on an unknown / no-registry model rather than raising (this
    runs inside the gate retry loop). Returns ``None`` for a hosted / unknown /
    missing model so DRY is never sent where it would 400.
    """
    if not model:
        return None
    try:
        from mtgai.settings.model_registry import get_registry

        info = get_registry().get_llm_by_model_id(model)
    except Exception:
        return None
    if info is not None and info.provider == "llamacpp":
        return DrySampler(multiplier=RETRY_DRY_MULTIPLIER)
    return None


# Re-scan the growing stream buffer for newly-closed ``--CARD`` blocks every
# this-many new chars (not every token), so the per-card UI push stays O(cards)
# rather than O(stream²). A block is short, so 80 lands roughly one scan per
# flagged card without thrashing.
LIVE_SCAN_STRIDE = 80

# A ``--CARD <id>--`` marker (2+ dashes either side, case-insensitive); the id is
# captured. The block's body is whatever follows up to the next marker. Identical
# to the skeleton relabel's marker so the gates + relabel stay in lockstep.
CARD_MARKER = re.compile(r"-{2,}\s*CARD\s+(\S+?)\s*-{2,}", re.IGNORECASE)


def generate_gate_tool(
    *,
    base_temperature: float,
    retries: int = 2,
    temperature_step: float = temps.RETRY_TEMP_STEP,
    **kwargs,
) -> dict:
    """Run a gate's ``generate_with_tool`` call, retrying on output truncation.

    Local models (Gemma) occasionally fall into a repetition loop and exhaust
    the output budget mid-tool-call, surfacing as :class:`OutputTruncatedError`.
    A plain re-roll at the same low temperature tends to reproduce the loop, so
    each retry **bumps the temperature** by ``temperature_step`` to perturb the
    decode out of it (a verified lever where ``repeat_penalty`` escalation is
    not — see ``learnings/gemma-repetition-loops.md``).

    Makes up to ``retries + 1`` attempts. Honours cancellation between attempts
    (so the Cancel button still halts the gate) and re-raises the last
    ``OutputTruncatedError`` after the final attempt. ``kwargs`` are forwarded to
    ``generate_with_tool`` verbatim (it must NOT include ``temperature`` — this
    helper owns it).
    """
    # Lift the base off the near-greedy floor for a local reasoning model so the
    # decode terminates instead of looping; the per-retry bump still stacks on
    # top of the floored base (see temperatures.floor_for_local).
    base_temperature = temps.floor_for_local(base_temperature, kwargs.get("model"))
    # DRY escalation for the retry — local-only (UnsupportedFeature on Anthropic),
    # applied from the 2nd attempt on, beyond the temperature bump.
    retry_dry = _local_retry_dry(kwargs.get("model"))
    last_exc: OutputTruncatedError | None = None
    for attempt in range(retries + 1):
        if attempt and ai_lock.is_cancelled():
            raise last_exc if last_exc else RuntimeError("gate cancelled")
        temperature = base_temperature + temperature_step * attempt
        dry = retry_dry if attempt else None
        try:
            return generate_with_tool(temperature=temperature, dry=dry, **kwargs)
        except OutputTruncatedError as exc:
            last_exc = exc
            logger.warning(
                "Gate LLM output truncated (attempt %d/%d at temp %.2f): %s",
                attempt + 1,
                retries + 1,
                temperature,
                exc,
            )
    assert last_exc is not None
    raise last_exc


def is_basic_land(card: Card) -> bool:
    """True for a basic land printing (``Basic`` supertype + ``Land`` type)."""
    return "Basic" in (card.supertypes or []) and "Land" in (card.card_types or [])


def filter_gate_cards(cards: list[Card]) -> list[Card]:
    """Drop basic lands and reprints — the cards a review gate never flags."""
    return [c for c in cards if not c.is_reprint and not is_basic_land(c)]


# ---------------------------------------------------------------------------
# ``--CARD <id>--`` block parsing (shared by both streamed gates)
# ---------------------------------------------------------------------------


def resolve_slot_id(tok: str, valid_ids: set[str], by_int: dict[int, str]) -> str | None:
    """Reconcile a returned id token to a real slot id — exact, then int-
    normalized so a dropped leading zero (``42`` → ``0042``) still lands."""
    tok = tok.strip()
    if tok in valid_ids:
        return tok
    if tok.isdigit() and int(tok) in by_int:
        return by_int[int(tok)]
    return None


def first_line(block: str) -> str:
    """The first non-empty line of a ``--CARD`` block."""
    return next((ln.strip() for ln in block.splitlines() if ln.strip()), "")


def closed_blocks(
    text: str, valid_ids: set[str], by_int: dict[int, str], *, include_trailing: bool
) -> list[tuple[str, str]]:
    """Parse ``--CARD <id>--`` blocks out of ``text`` as ``(slot_id, block_text)``.

    ``block_text`` is the raw text between this marker and the next (each gate
    parses it its own way — conformance wants the first line, interactions wants
    a reason + an ``AVOID:`` line). A block has "closed" (its body is final) once
    a later marker appears; the trailing block is included only when
    ``include_trailing`` (the authoritative end-of-stream parse on a clean
    finish). Unresolvable ids are dropped. Order follows the markers in the text.
    """
    out: list[tuple[str, str]] = []
    markers = list(CARD_MARKER.finditer(text))
    last = len(markers) if include_trailing else len(markers) - 1
    for i in range(max(last, 0)):
        m = markers[i]
        sid = resolve_slot_id(m.group(1), valid_ids, by_int)
        if not sid:
            continue
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        out.append((sid, text[m.end() : end]))
    return out


def stream_flag_batch(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_temperature: float,
    max_tokens: int,
    log_dir,
    name: str,
    valid_ids: set[str],
    on_block: Callable[[str, str], None],
    is_flag_block: Callable[[str], bool] | None = None,
    thinking: str | None = None,
) -> tuple[bool, float]:
    """Stream a flag-only free-text gate reply, retrying on truncation.

    The model emits ``--CARD <id>--`` blocks only for the items it flags.
    ``on_block(slot_id, block_text)`` fires once per flagged block — live as the
    block closes during streaming, plus the trailing block at a clean finish.
    Because a truncated/errored attempt is re-rolled (bumping temperature) and
    re-streams every block, **``on_block`` MUST be idempotent** (dedupe by
    slot_id). The trailing (possibly cut-off) block is never fired on a truncated
    attempt, so a partial reason is never committed — it is re-streamed whole on
    the retry. Honours cancellation between attempts.

    ``is_flag_block(block_text)`` is an optional guard against a drifting local
    model that ignores the flag-only contract and emits a ``--CARD`` block for a
    *non-flagged* card too (e.g. conformance bodies ending "Conforms."). When
    supplied, a parsed block is forwarded to ``on_block`` only if the predicate
    returns True; a block it rejects is dropped (the card is treated as never
    flagged). With no predicate every block is a flag (the original contract).
    The drop applies uniformly to the live-stride and trailing parses.

    Returns ``(completed, cost_usd)`` — ``completed`` is False only when every
    attempt truncated/errored, so the caller can treat the unreached items as
    "unknown" rather than silently passed.
    """
    by_int = {int(s): s for s in valid_ids if s.isdigit()}
    # Lift the base off the near-greedy floor for a local reasoning model so the
    # decode terminates instead of looping; the per-retry bump still stacks on
    # top of the floored base (see temperatures.floor_for_local).
    base_temperature = temps.floor_for_local(base_temperature, model)
    # DRY escalation for the truncation retry — only for a local model (it would
    # raise UnsupportedFeature on Anthropic). Resolved once; applied from the 2nd
    # attempt on, beyond the temperature bump.
    retry_dry = _local_retry_dry(model)
    cost = 0.0

    def _process(sid: str, block: str, emitted: set[str]) -> None:
        """Fire ``on_block`` once per block, dropping non-flag (OK) blocks."""
        if sid in emitted:
            return
        emitted.add(sid)
        if is_flag_block is not None and not is_flag_block(block):
            return  # drifting model emitted a block for a non-flagged card
        on_block(sid, block)

    for attempt in range(1, MAX_BATCH_ATTEMPTS + 1):
        if attempt > 1 and ai_lock.is_cancelled():
            break
        temperature = base_temperature + temps.RETRY_TEMP_STEP * (attempt - 1)
        dry = retry_dry if attempt > 1 else None
        buf = ""
        scanned = 0
        emitted: set[str] = set()  # block ids already processed (fired or dropped) this attempt
        response: dict | None = None
        errored = False
        try:
            for ev in stream_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                log_dir=log_dir,
                name=name,
                thinking=thinking,
                dry=dry,
            ):
                if ev.get("type") == "text_delta":
                    buf += ev.get("text", "")
                    if len(buf) - scanned >= LIVE_SCAN_STRIDE:
                        scanned = len(buf)
                        for sid, block in closed_blocks(
                            buf, valid_ids, by_int, include_trailing=False
                        ):
                            _process(sid, block, emitted)
                elif ev.get("type") == "complete":
                    response = ev
        except Exception as exc:  # transport / context overflow (possibly mid-stream)
            logger.warning(
                "Gate batch '%s' attempt %d/%d failed: %s",
                name,
                attempt,
                MAX_BATCH_ATTEMPTS,
                exc,
            )
            errored = True

        cost += cost_from_result(response) if response else 0.0
        truncated = errored or (response is not None and response.get("stop_reason") == "length")
        # Fire any blocks the live stride skipped. The trailing block is included
        # only on a clean finish, so a cut-off reason is never committed.
        for sid, block in closed_blocks(buf, valid_ids, by_int, include_trailing=not truncated):
            _process(sid, block, emitted)
        if not truncated:
            return True, cost
        logger.warning(
            "Gate batch '%s' truncated (attempt %d/%d) — retrying",
            name,
            attempt,
            MAX_BATCH_ATTEMPTS,
        )
    return False, cost
