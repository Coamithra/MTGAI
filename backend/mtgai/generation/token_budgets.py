"""Centralized output-token budgets (``max_tokens``) for every LLM call in the
pipeline — one place to tune.

These are **safety caps, not targets**: a healthy call stops at EOS far below
them. They exist to (a) leave headroom for a reasoning model's chain-of-thought
*plus* the answer, and (b) bound the worst case when a call over-reasons or
loops. Local Gemma emits its reasoning into ``reasoning_content`` (which the
transport drops); on heavy calls that CoT can run several thousand tokens before
the answer, so a too-tight cap truncates mid-reasoning and the answer is never
emitted (``finish_reason=length`` with empty output). See
``learnings/reasoning-budget-overrun.md``.

Do **not** set these to the model maximum:
- it removes the circuit breaker — a genuinely looping call would run to the
  full context (minutes on a CPU-offloaded local model; real cost on the API);
- locally it's impossible anyway — ``check_pre_call`` reserves ``max_tokens``
  against the context window, so ``max_tokens == ctx`` leaves no room for the
  prompt and raises ``ContextOverflowError``;
- on the API there are per-model output ceilings and a streaming-required
  threshold.

Every value stays at or below :data:`MAX_OUTPUT_CEILING`, which is comfortable
within the local models' 128k context and below the Anthropic streaming
threshold, so the same constant is safe on both providers.
"""

from __future__ import annotations

# Hard ceiling. No budget should exceed this. Already used in production
# (theme extraction, skeleton relabel) so it carries no new provider risk.
MAX_OUTPUT_CEILING = 16384

# Standard single-item generation — one card / mechanic / land / reprint set,
# a knob-tune, a slot grouping. Small (~300-token) answer; room for moderate CoT.
STANDARD = 8192

# Batch / multi-item generation — several cards in one call, a full archetype
# set, a skeleton relabel pass: bigger answer + proportionally more reasoning.
BATCH = 12288

# Heavy reasoning — whole-set review gates and the design council, where the
# model deliberates extensively before emitting a structured verdict.
HEAVY = MAX_OUTPUT_CEILING
