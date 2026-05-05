"""Prompt-eval / generation poller for llamacpp streaming.

Lifted from ``mtgai.pipeline.theme_extractor`` so any pipeline stage that
runs a llamacpp call can show real-time progress in the activity banner
(prompt-eval percent during TTFT, then tok/s once decoding starts).

Designed for use as a context manager around a synchronous or streaming
LLM call. The poll loop runs on a daemon thread so a stuck HTTP probe
never blocks process shutdown. All errors during a poll are swallowed —
telemetry must never crash the run.
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

    # Newer llama-server builds dropped n_prompt_tokens / _processed from
    # /slots, so we can't compute a precise prompt-eval percent. Heartbeat
    # at this interval so the banner gets activity + elapsed_s ticks
    # during TTFT and the frontend's phase-default paints the bar.
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
        self._last_processed = -1
        self._last_total = -1
        self._last_decoded = -1
        self._last_gen_emit_at: float = 0.0
        self._last_prompt_eval_emit_at: float = 0.0
        self._gen_started_at: float | None = None
        self._switched_to_generation = False

    def __enter__(self) -> PromptEvalPoller:
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
                logger.debug("slots poll failed (transient): %s", e)
                continue
            if self._stop.is_set():
                return
            active = next(
                (s for s in slots if s.get("is_processing")),
                None,
            )
            if active is None:
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
            if not self._switched_to_generation:
                self._switched_to_generation = True
                self._gen_started_at = time.monotonic()
            self._publish_generation(decoded)
            return

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

        now = time.monotonic()
        if now - self._last_prompt_eval_emit_at < self._PROMPT_EVAL_HEARTBEAT_S:
            return
        self._last_prompt_eval_emit_at = now
        sep = " — " if self._activity_prefix else ""
        self._safe_emit(
            phase=self._phase_kind,
            activity=f"{self._activity_prefix}{sep}evaluating prompt",
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

    def _safe_emit(self, **kwargs: Any) -> None:
        try:
            self._emit(**kwargs)
        except Exception as e:
            logger.warning("phase emit from poller failed: %s", e)
