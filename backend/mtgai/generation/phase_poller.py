"""Prompt-eval / generation poller for llamacpp streaming.

Lifted from ``mtgai.pipeline.theme_extractor`` so any pipeline stage that
runs a llamacpp call can show real-time progress in the activity banner
(prompt-eval percent during TTFT, then tok/s once decoding starts).

Designed for use as a context manager around a synchronous or streaming
LLM call. The poll loop runs on a daemon thread so a stuck HTTP probe
never blocks process shutdown. All errors during a poll are swallowed —
telemetry must never crash the run.

:func:`make_poller` is the one-call factory: hand it a stage assignment
key and a phase-emit callable and it resolves the stage's model, returns
a real poller for a local (llamacpp) model, or a :class:`NullPoller` for a
cloud model / no open project / any setup failure — so callers always wear
a single ``with`` shape.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


# Signature of the phase emitter the poller calls. Matches StageEmitter.phase.
PhaseEmitFn = Callable[..., None]


class NullPoller:
    """No-op stand-in. Use when no emitter is registered or for non-local models.

    Lets callers wear a single ``with`` shape regardless of whether
    polling is enabled — saves the conditional from leaking into every
    callsite.
    """

    def __enter__(self) -> NullPoller:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class PromptEvalPoller:
    """Polls an llmfacade llamacpp provider's ``/slots`` and emits phase ticks.

    Lifecycle (single-use, not re-entrant)::

        with PromptEvalPoller(provider, model_id, emit, phase_kind="running",
                               activity_prefix="Selecting reprints"):
            result = blocking_or_streaming_llm_call(...)

    The emitter callable receives keyword args matching ``StageEmitter.phase``::

        emit(phase: str, activity: str, **extra)

    where ``extra`` may include ``prompt_eval={"processed": int, "total": int}``
    or ``generation={"tokens": int, "tok_per_sec": float, "elapsed_s": float}``.

    A single span may wrap *several* LLM calls (e.g. card_gen's per-batch
    loop, mechanics' council, ai_review's per-card pass). llama-server resets
    a slot's decode counter to ~0 on each new request, so the poller restarts
    its generation clock when the counter drops — otherwise tok/s after the
    first call would be a meaningless cross-call average.
    """

    # Don't spam events — only emit when prompt-eval token count moves by
    # at least this fraction of total or this many tokens, whichever is
    # smaller. Keeps the SSE stream readable on long prompt-eval spans.
    _MIN_DELTA_TOKENS = 200
    _MIN_DELTA_FRACTION = 0.01

    # Floor on time between consecutive generation-phase ticks. The poll
    # loop runs at 0.5s, but we don't need to publish that fast — users
    # can't read it, and every tick lands in the replay buffer.
    _GEN_MIN_INTERVAL_S = 1.0

    # Newer llama-server builds (9010+) dropped n_prompt_tokens / _processed
    # from /slots, so we can't compute a precise prompt-eval percent. And
    # during a cold model load /slots doesn't answer at all. In both "dark
    # window" cases we heartbeat at this interval with a ticking elapsed so
    # the banner never freezes on a static label.
    _PROMPT_EVAL_HEARTBEAT_S = 1.0

    def __init__(
        self,
        provider: Any,
        model_id: str,
        emit: PhaseEmitFn,
        phase_kind: str = "running",
        activity_prefix: str = "",
        poll_interval: float = 0.5,
    ) -> None:
        self._provider = provider
        self._model_id = model_id
        self._emit = emit
        self._phase_kind = phase_kind
        self._activity_prefix = activity_prefix
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float = 0.0
        self._last_processed = -1
        self._last_total = -1
        self._last_decoded = -1
        self._last_gen_emit_at: float = 0.0
        self._last_prompt_eval_emit_at: float = 0.0
        self._gen_started_at: float | None = None
        self._switched_to_generation = False
        self._warned_slots_failure = False

    def __enter__(self) -> PromptEvalPoller:
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._loop,
            name="phase-poller",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.0)
            if t.is_alive():
                logger.warning(
                    "Phase poller thread did not exit within 1s; leaking thread (model=%s)",
                    self._model_id,
                )

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            try:
                slots = self._provider.slots(model=self._model_id)
            except Exception as e:
                # The server isn't answering yet — almost always a cold model
                # load (llama-swap spawning + weights loading). Heartbeat so
                # the strip shows ticking activity instead of freezing.
                self._note_slots_failure(e)
                # A probe can take 100s of ms; if __exit__ landed during it,
                # don't publish a stale heartbeat after stop (mirrors the
                # post-success guard above).
                if self._stop.is_set():
                    return
                self._heartbeat()
                continue
            if self._stop.is_set():
                return
            active = next(
                (s for s in slots if s.get("is_processing")),
                None,
            )
            if active is None:
                # Server is up but this model has no in-flight request yet
                # (warmup / between calls in a multi-call span). Keep the
                # banner alive.
                self._heartbeat()
                continue
            self._publish(active)

    def _publish(self, slot: dict[str, Any]) -> None:
        # llama-server's /slots shape changed: per-slot decoder counters now
        # live under next_token[0] instead of the top level. Read both so
        # we work on old and new builds.
        next_tok = (slot.get("next_token") or [{}])[0]
        decoded = int(next_tok.get("n_decoded") or slot.get("n_decoded") or 0)
        processed = int(slot.get("n_prompt_tokens_processed") or 0)
        total = int(slot.get("n_prompt_tokens") or 0)

        if decoded > 0:
            # Start (or restart) the generation clock when decoding begins, or
            # when the counter drops below the last value — the latter means a
            # fresh call rolled in within this span, so tok/s should reflect it
            # rather than averaging across calls.
            if not self._switched_to_generation or decoded < self._last_decoded:
                self._switched_to_generation = True
                self._gen_started_at = time.monotonic()
                self._last_decoded = -1
            self._publish_generation(decoded)
            return

        # decoded == 0 → prompt-eval or dark window. If we'd previously rolled
        # into generation, this is the *next* call's prompt-eval beginning;
        # reset the per-call trackers so its clock + heartbeat gate apply.
        if self._switched_to_generation:
            self._switched_to_generation = False
            self._last_decoded = -1
            self._last_processed = -1
            self._last_total = -1

        if total > 0:
            if not self._should_emit_prompt_eval(processed, total):
                return
            self._last_processed = processed
            self._last_total = total
            sep = " — " if self._activity_prefix else ""
            self._safe_emit(
                phase=self._phase_kind,
                activity=f"{self._activity_prefix}{sep}processing prompt {processed:,}/{total:,}",
                prompt_eval={"processed": processed, "total": total},
            )
            return

        # No counters (build 9010+ prompt-eval) → time-based heartbeat.
        self._heartbeat()

    def _heartbeat(self) -> None:
        """Emit a ticking-elapsed banner tick during the dark window.

        The "dark window" is any stretch with no usable counters: a cold
        model load (``/slots`` unreachable), warmup before the slot reports
        ``is_processing``, or a build-9010 prompt-eval that drops the
        prompt-token counters. Rate-limited to one tick per
        ``_PROMPT_EVAL_HEARTBEAT_S``. Suppressed once decoding has started —
        generation ticks carry their own (richer) activity, and between calls
        in a multi-call span the last tok/s tick is better left on screen than
        flicked back to "evaluating prompt".
        """
        if self._switched_to_generation:
            return
        now = time.monotonic()
        if now - self._last_prompt_eval_emit_at < self._PROMPT_EVAL_HEARTBEAT_S:
            return
        self._last_prompt_eval_emit_at = now
        elapsed = now - self._started_at if self._started_at else 0.0
        sep = " — " if self._activity_prefix else ""
        self._safe_emit(
            phase=self._phase_kind,
            activity=f"{self._activity_prefix}{sep}evaluating prompt ({elapsed:.0f}s)",
        )

    def _publish_generation(self, decoded: int) -> None:
        if decoded == self._last_decoded:
            return
        now = time.monotonic()
        if now - self._last_gen_emit_at < self._GEN_MIN_INTERVAL_S:
            return
        self._last_decoded = decoded
        self._last_gen_emit_at = now
        elapsed = (now - self._gen_started_at) if self._gen_started_at is not None else 0.0
        tok_per_sec = decoded / elapsed if elapsed > 0 else 0.0
        sep = " — " if self._activity_prefix else ""
        activity = (
            f"{self._activity_prefix}{sep}generating ({decoded:,} tok @ {tok_per_sec:.1f} tok/s)"
        )
        self._safe_emit(
            phase="generation",
            activity=activity,
            generation={
                "tokens": decoded,
                "tok_per_sec": round(tok_per_sec, 2),
                "elapsed_s": round(elapsed, 2),
            },
        )

    def _should_emit_prompt_eval(self, processed: int, total: int) -> bool:
        if processed == self._last_processed and total == self._last_total:
            return False
        if self._last_processed < 0:
            return True
        delta = processed - self._last_processed
        if delta >= self._MIN_DELTA_TOKENS:
            return True
        if total > 0 and delta / total >= self._MIN_DELTA_FRACTION:
            return True
        # Final tick: cleanest "prompt eval done" signal for the UI.
        return processed == total

    def _note_slots_failure(self, exc: Exception) -> None:
        """Log a ``/slots`` probe failure — once at WARN, then DEBUG.

        A failure is expected (and harmless) during a cold model load, so we
        don't want a WARN per poll. But a *genuine* drop (wrong target, wedged
        probe) would otherwise be invisible at DEBUG, so surface the first one
        at WARN with the resolved URL to make it catchable.
        """
        if not self._warned_slots_failure:
            self._warned_slots_failure = True
            logger.warning(
                "Phase poller: /slots probe failed at %s (%s). tok/s telemetry is "
                "delayed until the server answers — expected briefly during a cold "
                "model load; persistent failures mean the probe can't reach the model.",
                self._slots_url(),
                exc,
            )
        else:
            logger.debug("slots poll failed (transient): %s", exc)

    def _slots_url(self) -> str:
        """Best-effort resolved ``/slots`` URL for the diagnostic WARN.

        Reads the llamacpp provider's private ``_http_base`` if present
        (managed-mode server root); falls back to just the upstream path. This
        is a log string only, so an approximate value is fine.
        """
        base = getattr(self._provider, "_http_base", "") or ""
        return f"{base}/upstream/{self._model_id}/slots"

    def _safe_emit(self, **kwargs: Any) -> None:
        try:
            self._emit(**kwargs)
        except Exception as e:
            logger.warning("phase emit from poller failed: %s", e)


def make_poller(
    stage: str,
    emit: PhaseEmitFn,
    *,
    activity_prefix: str = "",
    phase_kind: str = "running",
) -> PromptEvalPoller | NullPoller:
    """Build a poller for ``stage``'s assigned model, or a :class:`NullPoller`.

    Resolves the active project's model assignment for ``stage`` and returns a
    live :class:`PromptEvalPoller` only when that model runs on the local
    ``llamacpp`` provider (the one with a ``/slots`` endpoint). Returns a
    :class:`NullPoller` for a cloud (Anthropic) model, when no project is open,
    or on any setup failure — telemetry is strictly best-effort and must never
    block generation. Either way the caller wears one ``with`` shape::

        with make_poller("card_gen", emitter.phase, activity_prefix="Generating cards"):
            result = generate_set(...)

    ``stage`` is the model-assignment key (e.g. ``"card_gen"``, ``"mechanics"``,
    ``"balance"``) — the same key the stage passes to ``get_llm_model_id`` — so
    the poller polls exactly the model the call uses (llama-swap routes per
    model id).
    """
    try:
        from mtgai.generation.llm_client import _get_provider, _resolve_provider
        from mtgai.runtime.active_project import require_active_project

        model_id = require_active_project().settings.get_llm_model_id(stage)
        if _resolve_provider(model_id) != "llamacpp":
            return NullPoller()
        return PromptEvalPoller(
            provider=_get_provider("llamacpp"),
            model_id=model_id,
            emit=emit,
            phase_kind=phase_kind,
            activity_prefix=activity_prefix,
        )
    except Exception as e:
        logger.warning(
            "Poller setup for stage %r failed (%s); continuing without telemetry", stage, e
        )
        return NullPoller()
