"""Centralized sampling temperatures for every LLM call in the pipeline — one
place to tune, modelled on :mod:`token_budgets`.

Temperature controls how much randomness is injected into decoding: low values
sharpen the distribution toward the most-likely token (good for objective,
structured, "one right answer" work), high values flatten it (good for open
creative generation). Anthropic's own guidance is to use temperature "closer to
``0.0`` for analytical / multiple choice, and closer to ``1.0`` for creative and
generative tasks" — the ladder below mirrors that, with the valid range
``0.0``-``1.0`` (the Claude ceiling; llama.cpp would allow >1 but we never need
it).

Two hard rules, both grounded in measured behaviour — see
``learnings/gemma-repetition-loops.md`` and the temperature research that
produced these values:

1. **Never ``0.0`` on a local-default stage.** Greedy decode is *not* actually
   deterministic (MoE routing + non-associative float reductions flip top-token
   ties anyway) and it is the single biggest repetition-loop trigger on small
   quantized models like our Gemma. llama.cpp also short-circuits its
   anti-repetition samplers when ``temperature == 0``, removing the only guard.
   :data:`GREEDY` therefore exists for **cloud models only** (e.g. Haiku art
   selection), where there is no local sampler to bypass and no loop pathology.

2. **Any low-temp local call must pair with a temperature-bump retry.** A plain
   re-roll at the same low temperature reproduces the identical loop; bumping the
   temperature by :data:`RETRY_TEMP_STEP` per attempt is the verified lever out
   (``repeat_penalty`` escalation is *not*, for Gemma). The review gates
   (:mod:`analysis.gate_common`), the slot grouper, and reprint selection all do
   this off their low base.

The ladder is the recommendation for *new* stages — pick the closest rung. The
named outliers below it deviate from the ladder for a documented, measured
reason; do not "round" them to a tier.
"""

from __future__ import annotations

# --- The ladder: canonical tiers, low (objective) -> high (creative) ----------

GREEDY = 0.0
"""Deterministic-as-possible greedy decode. **CLOUD MODELS ONLY** — on a local
model this triggers repetition loops and bypasses the anti-loop samplers (rule 1
above). Used by the Haiku-vision art selector, a closed multiple-choice pick."""

ANALYTICAL = 0.3
"""Objective / structured local work that still needs a loop escape (interaction
scan, cycle clustering, reprint select+place). Sits at the top of the practitioner
"code / RAG" band (0.0-0.3); **always** driven through a +``RETRY_TEMP_STEP``
retry on local."""

BALANCED = 0.7
"""Grounded-but-varied default: extraction and constrained creative work that
wants natural variation without drifting off-spec (theme extraction, land art
briefs, skeleton-knob tuning, the manual reprint re-roll)."""

CREATIVE = 1.0
"""Maximally inventive open generation — Anthropic's creative end of the scale
and the Claude default (card generation, design-council review, archetype
intents, skeleton relabel, visual references)."""

# --- Tuned outliers: deviate from the ladder for a measured reason -------------

PRECISE = 0.2
"""Just below :data:`ANALYTICAL` for the strictest objective checks: the
conformance adherence check and the mechanic synthesizer's constrained
in-place revision (it edits, it doesn't invent)."""

FOCUSED = 0.4
"""Mechanic-council review — a touch of variation across the independent
reviewers without letting any one wander off the rules being checked."""

GROUNDED = 0.6
"""Art-prompt construction: more anchored than :data:`BALANCED` so the Flux
prompt stays faithful to the card's described scene."""

INVENTIVE = 0.9
"""Mechanic *generation*. Lab-measured: 0.9 produces better candidates than 1.1
(do not raise) — the one rung that beat the obvious creative default in testing."""

# --- Loop-escape retry step ---------------------------------------------------

RETRY_TEMP_STEP = 0.2
"""Per-retry temperature increment for low-temp local calls. A plain re-roll at
the same low temp reproduces a Gemma repetition loop; bumping the temperature is
the verified way out (``learnings/gemma-repetition-loops.md``). Shared by the
review gates, the slot grouper, and reprint selection."""
