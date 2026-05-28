"""Post-card_gen review gates — the LLM checks the review→regen loop runs.

Two whole-set LLM gates flag cards for regeneration (the set-level
balance/coverage/algorithmic-conformance machinery was removed when the balance
stage became the loop — see ``plans/review-loop-stage-split.md``):

* :mod:`mtgai.analysis.conformance` — each card vs. its slot spec.
* :mod:`mtgai.analysis.interactions` — whole-pool degenerate-combo scan.

Per-card design-quality heuristics live in :mod:`mtgai.analysis.heuristic_checks`
(consumed by AI review + render QA), independent of these gates.
"""

from mtgai.analysis.conformance import check_conformance
from mtgai.analysis.interactions import analyze_interactions
from mtgai.analysis.models import ConformanceFinding, InteractionFlag

__all__ = [
    "ConformanceFinding",
    "InteractionFlag",
    "analyze_interactions",
    "check_conformance",
]
